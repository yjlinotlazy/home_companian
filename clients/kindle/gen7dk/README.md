# Kindle Gen 7 客户端

这是基于 Kindle 系统自带 `curl`、`eips` 和 LIPC 的薄客户端，不依赖 KOReader UI。KOReader 当前只用于提供 SSH server。

当前实机 framebuffer 为 600×800、约 167 PPI。设备按“正常竖屏姿势逆时针旋转 90°”横放；Forge 按 800×600 排版，再将设备 Frame 顺时针旋转成 `eips` 接收的 600×800 PNG。服务端 Device Instance ID 是 `kindleGen7dk`，Profile 是 `kindle_6_167ppi_landscape`。

当前横屏画面使用三个每日清单区和一个随机图片区。checkbox 只能在服务器网页操作；Kindle 客户端仍只下载、显示和 ACK Frame。

## 工作方式

- 首次运行：下载 `/next` → `eips` 全刷 → 提交 `displayed` ACK。
- 正常休眠：厂商屏保短暂绘制后，客户端用缓存 dashboard 覆盖；设备仍正常 suspend。
- 手动唤醒：等待 Wi-Fi 进入 `CONNECTED`，再下载、显示并 ACK 新 Frame。
- 家中服务器不可达且配置了 `REMOTE_IMAGE_URL` 时：改为下载公网静态 PNG；此路径没有 ACK。
- 不设置 RTC，不会定时自动唤醒。
- 下载或显示失败时不清屏，保留缓存画面。

## 已验证的手机热点与 Dropbox 回退链路

该链路已在 Kindle Gen 7 实机验证：服务器把最终 600×800 PNG 原地覆盖到 `library/rendered/kindleGen7dk.png`，Dropbox 自动同步；Kindle 无法连接家庭服务器时，等待本地请求超时后从 `REMOTE_IMAGE_URL` 下载并显示图片。

户外更新时，手机先通过 WireGuard VPN 打开家中的 Home Companian 网页并修改状态；家中服务器生成新图，Dropbox 完成同步后，连接 iPhone 热点的 Kindle 再从公网共享链接下载。Kindle 本身不需要连接 WireGuard。

- Dropbox 共享链接在 Kindle 的私有 `client.conf` 中配置，结尾使用 `dl=1`，不得提交到仓库。
- iPhone 个人热点必须打开“最大兼容性”（Maximize Compatibility）。
- 服务器必须原地覆盖已有 PNG，不能删除后重建或使用原子替换；否则 Dropbox 会保留文件但使原共享链接失效。
- 公网静态图片没有 Frame ACK，网页中的“当前画面”不会因此变成已确认状态。

关闭家庭服务器后运行 `./client.sh`，以下日志表示整个回退流程成功：

```text
Home server unavailable; downloading remote image
Displayed frame remote-static
```

## 前提

- Kindle 已越狱，并能通过 SSH 登录。
- Kindle 上存在 `curl`、`eips`、`lipc-wait-event` 和 `lipc-get-prop`。
- 使用 iPhone 个人热点时，必须打开“最大兼容性”（Maximize Compatibility），旧 Kindle 才能连接。
- Home Companian 服务端已配置 `kindleGen7dk` 并可从局域网访问。
- Linux 电脑已使用 mkcert 配置服务端 HTTPS。

## 1. 创建 Kindle 目录

在 Kindle SSH 终端运行：

```sh
mkdir -p /mnt/us/home_companian
```

`/mnt/us` 是 Kindle 的用户存储区；`-p` 让目录已存在时也不报错。

## 2. 复制客户端

在 Linux 电脑的 repo 根目录运行：

```sh
scp -P <SSH端口> \
  clients/kindle/gen7dk/client.sh \
  clients/kindle/gen7dk/daemon.sh \
  clients/kindle/gen7dk/control.sh \
  clients/kindle/gen7dk/client.conf.example \
  root@<Kindle-IP>:/mnt/us/home_companian/
```

`scp` 使用大写 `-P` 指定 SSH 端口。这条命令不会覆盖 Kindle 上已有的 `client.conf`。

## 3. 复制公开根证书

仍在 Linux 电脑运行：

```sh
scp -P <SSH端口> \
  "$(mkcert -CAROOT)/rootCA.pem" \
  root@<Kindle-IP>:/mnt/us/home_companian/
```

`mkcert -CAROOT` 只输出当前 CA 目录，不生成或覆盖证书。这里只复制公开的 `rootCA.pem`；绝对不要复制 `rootCA-key.pem`。

## 4. 创建设备配置

在 Kindle SSH 终端运行：

```sh
cd /mnt/us/home_companian
cp client.conf.example client.conf
```

编辑 `client.conf`，结果应类似：

```sh
SERVER_URL=https://<服务器IP>:<端口>
REMOTE_IMAGE_URL='https://<private-shared-link>'
DEVICE_ID=kindleGen7dk
CA_CERT=/mnt/us/home_companian/rootCA.pem
INSECURE=0
WORK_DIR=/tmp/home_companian
WAVEFORM=gc16
SCREEN_RESTORE_DELAY=3
WIFI_WAIT_SECONDS=60
```

`INSECURE=1` 只用于临时排查证书问题，正常使用必须恢复为 `0`。

`REMOTE_IMAGE_URL` 可留空。外出使用手机热点时，可在 Kindle 本地的 `client.conf` 中填入 `library/rendered/kindleGen7dk.png` 对应的 Dropbox 直接下载共享链接。脚本先尝试家中服务器，失败后使用唯一查询参数和禁缓存请求头，跟随重定向下载该 PNG，避免 Dropbox 边缘缓存返回旧画面。完整共享链接等同访问凭据，不得写入仓库、示例配置或日志。公网静态图没有 ACK，因此网页“当前画面”只会在通过家中服务器刷新成功后确认更新。

## 5. 设置执行权限

在 Kindle 运行：

```sh
chmod +x client.sh daemon.sh control.sh
```

成功时通常没有输出。

## 6. 验证单次刷新

在 Kindle 运行：

```sh
./client.sh
```

成功输出类似：

```text
Downloading https://<server>/v1/devices/kindleGen7dk/next
update_to_display: update_mode=FULL, wave_mode=2 inverted=0
Displayed frame <frame-id>; next check in <seconds> seconds
```

`gc16` 全刷时屏幕闪一下是正常现象。脚本只有在 `eips` 成功后才提交 `displayed` ACK；服务器收到 ACK 后，网页中的当前画面才代表 Kindle 实际显示的 Frame。

## 7. 启动手动唤醒刷新

运行：

```sh
./control.sh start
./control.sh status
```

预期状态：

```text
Daemon is running as PID <pid>
```

后台监听器处理两个 Kindle 电源事件：

- `goingToScreenSaver`：等待 3 秒，再用缓存 Frame 覆盖厂商屏保。
- `wakeupFromSuspend`：等待 Wi-Fi 连接，然后执行一次 `client.sh`。

## 8. 实机验证

1. 按电源键进入休眠。
2. 厂商屏保可能短暂出现；约 3 秒后应恢复 dashboard。
3. 等待至少 90 秒，确保设备进入 suspend。
4. 按电源键手动唤醒。
5. Wi-Fi 连接后，屏幕应自动全刷并提交 ACK。

查看日志：

```sh
tail -n 20 /mnt/us/home_companian/client.log
```

成功时日志包含：

```text
Refreshed dashboard after manual wake
```

## 管理命令

```sh
./control.sh status
./control.sh refresh
./control.sh stop
```

- `status`：查看后台监听器状态。
- `refresh`：立即执行一次下载、显示和 ACK。
- `stop`：停止后台监听器；之后休眠会恢复正常厂商屏保行为。

## 重启与休眠

普通按电源键只是休眠/唤醒，不是重启，后台监听器会继续存在。

菜单 Restart、长按电源键、系统崩溃、电池耗尽或某些更新会真正重启 Kindle。当前没有修改系统启动配置；真正重启后需重新 SSH 登录并运行：

```sh
cd /mnt/us/home_companian
./control.sh start
```

这是低频操作，暂不为它增加自动启动和系统级改动。

## 常见问题

- `eips: unknown image type`：下载文件不是有效 PNG，通常是 HTTP 错误文本。确认下载使用了 `curl -f`，并检查服务端。
- `eips: 8bit only`：PNG 不是 8-bit grayscale；设备 `/next` 接口应返回服务端 encoder 生成的 PNG。
- 唤醒后没有刷新：检查 `./control.sh status` 和 `client.log`，并确认 `lipc-get-prop com.lab126.wifid cmState` 最终为 `CONNECTED`。
- 网页仍显示旧画面：等待 Kindle 显示并成功 ACK；待投递但未 ACK 的 Frame 不会冒充当前画面。
