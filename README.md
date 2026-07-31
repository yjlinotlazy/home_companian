# 家宠 Home Companian

家庭服务器上的多设备电子墨水显示项目。服务端负责内容、调度、排版和编码；Kindle、CrowPanel 等设备只负责取得画面、显示、上报结果和休眠。

CrowPanel ESP32 链路已经可用。Kindle 已实机打通 PNG 下载、`eips` 全刷、ACK、休眠保图和手动唤醒刷新。浏览器目前是预览和管理界面，不是独立显示设备。

高层架构和 monorepo 边界见 [ARCHITECTURE.md](ARCHITECTURE.md)，服务端与应用细节见 [DESIGN.md](DESIGN.md)，设备 HTTP 契约见 [PROTOCOL.md](PROTOCOL.md)，迭代计划见 [MILESTONE.md](MILESTONE.md)。

## 效果示例

设备端：

<img src="device_examples.png" alt="电子墨水屏上的图片、健身和 24 点模块" width="800">

网页端：

<img src="server_example.jpg" alt="Home Companian 网页预览和控制界面" width="420">

## 工作流程

![Home Companian 从服务端到客户端的工作流程](overview.png)

## 可以显示什么

- 家庭任务和个人提醒。
- 家庭照片、绿植、动物等图片。
- 识字内容。
- 徒手健身动作。
- 24 点等数学小游戏。
- 中文四字、英文四词的创意故事提示。
- 用三种图形替换 2–3 个字母的英文句子破解游戏。
- 节气、星期等状态栏信息。

目前支持定时和随机两种内容选择方式。每日清单在网页勾选，Kindle 下次唤醒时显示完成状态；设备本身不处理互动。当前已支持一项积分奖励，更复杂的任务领取仍是后续方向。

## 支持的设备

| 设备 | 状态 | 输出 |
| --- | --- | --- |
| CrowPanel 5.79 inch, 792×272 | 已支持 | 27,200-byte 1-bit framebuffer |
| Kindle Gen 7, 物理 600×800，横放后逻辑 800×600 | 已支持 | 16-level grayscale PNG |
| Browser | 预览和管理端 | PNG |

设备 ID 和设备型号是分开的：

- `wall_panel`、`kindleGen7dk` 是用户在配置中定义的 Device Instance ID。
- `crowpanel_579`、`kindle_6_167ppi_landscape` 是当前实例使用的 Device Profile。
- 多台相同型号设备使用不同 ID、相同 profile 即可。

通用设备接口使用配置中的 ID，例如 `/v1/devices/kindleGen7dk/next`。`/display.bin` 是唯一保留的旧固件兼容口，固定服务 `wall_panel`。

Kindle 待投递画面同时会写入内容库的 `rendered/<device-id>.png`，可由 Dropbox 等同步后供手机热点环境下下载。已有文件会保留其身份并原地覆盖内容，不能用删除后重建或原子替换，否则 Dropbox 共享链接会失效。公网链接按设备保存在本机私有配置的 `devices.<device-id>.remote_image_url`，并复制到对应 Kindle 的本地 `client.conf`；不要写入仓库或示例配置。

设备端源码与服务端放在同一仓库：

- `clients/crowpanel/crowpanel-579/`：当前 CrowPanel ESP-IDF 客户端；部署方法见其 [README.md](clients/crowpanel/crowpanel-579/README.md)。
- `clients/kindle/gen7dk/`：Kindle Gen 7 客户端；部署方法见其 [README.md](clients/kindle/gen7dk/README.md)。

各客户端保留自己的工具链和局部 `.gitignore`，但共同遵守 [PROTOCOL.md](PROTOCOL.md)。CrowPanel 目前仍通过兼容接口工作；Kindle 使用 PNG → 显示 → ACK → 休眠的通用协议链路。

## Kindle 更新与重启速查

如果只修改了服务端、模板、模块、配置或内容库，不需要重新复制 Kindle 客户端。重启服务器后，手动唤醒 Kindle，它会自动下载、显示并 ACK 新 Frame。

只有 `clients/kindle/gen7dk/*.sh` 发生变化时，才需要更新 Kindle 脚本。先在 Kindle SSH 终端停止旧 daemon：

```sh
cd /mnt/us/home_companian
./control.sh stop
```

然后在 Linux 的 repo 根目录复制脚本；这不会覆盖 Kindle 上的 `client.conf`：

```bash
scp -P <SSH端口> \
  clients/kindle/gen7dk/client.sh \
  clients/kindle/gen7dk/daemon.sh \
  clients/kindle/gen7dk/control.sh \
  root@<Kindle-IP>:/mnt/us/home_companian/
```

回到 Kindle SSH 终端，恢复权限并启动：

```sh
cd /mnt/us/home_companian
chmod +x client.sh daemon.sh control.sh
./control.sh start
./control.sh status
```

立即测试一次完整的下载 → 显示 → ACK：

```sh
./control.sh refresh
```

查看最近日志：

```sh
tail -n 30 /mnt/us/home_companian/client.log
```

普通按电源键只是休眠/唤醒，daemon 会继续运行。Kindle 菜单 Restart、长按电源键重启、电池耗尽或系统更新后，需重新 SSH 登录并执行 `./control.sh start`。首次安装、HTTPS 根证书和 `client.conf` 配置见 [Kindle Gen 7 完整部署文档](clients/kindle/gen7dk/README.md)。

## 运行(服务器端)

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

使用示例配置，并通过 `--port` 指定端口：

```bash
python3 server.py --config config.example.yaml --port 8000
```

使用默认配置位置：

```bash
mkdir -p ~/.config/home_companian
cp config.example.yaml ~/.config/home_companian/config.yaml
python3 server.py --host 127.0.0.1 --port 8080
```

启动后访问 `http://localhost:<port>/`。

局域网 HTTPS、Caddy、mkcert 和客户端根证书信任的配置统一参考 [home_command_center 的“局域网 HTTPS”说明](https://github.com/yjlinotlazy/home_command_center#局域网-https)。Home Companian 自身只监听 localhost，由 Caddy 使用服务器 IP 的 HTTPS 端口反向代理；不要把 mkcert 根 CA 私钥复制到客户端。

## 配置

默认配置文件是 `~/.config/home_companian/config.yaml`。它保存字体、内容库路径、Channel 和 Device；素材不放在 `~/.config` 中。

最小结构：

```yaml
font: /path/to/chinese-font.ttf
latin_font: /path/to/latin-font.ttf
library_dir: /path/to/home_companian_library
default_device: wall_panel
reward: {id: toy, name: 玩具, cost: 50, initial_points: 25}
checklists:
  person_1: [1, 2, 3]
  person_2: [4, 5, 6]
  family: [7, 8]

channels:
  home:
    mode: random
    schedule:
      - {time: "12:00", item: 1}
    random_items: [1, 2, 3]

devices:
  wall_panel:
    profile: crowpanel_579
    channel: home
    refresh:
      schedule:
        - {start: "08:00", end: "12:00", profile: mixed}
        - {start: "12:00", end: "20:00", profile: dashboard_only}
    presentation:
      status_bar:
        center: [{module: solar_term}]
        right: [{module: weekday}]
      panels:
        dashboard:
          template: landscape_3
          slots:
            1: {module: images, collections: "plants,animals"}
            2: {module: items}
            3: {module: chinese, source: select}
        math:
          template: landscape_1
          slots:
            1: {module: math, type: games}
        creative:
          template: landscape_1
          slots:
            1: {module: creative, language: random}
        language:
          template: landscape_1
          slots:
            1: {module: language, type: cipher}
      display_profiles:
        mixed: {minutes: 20, panels: [dashboard, math, creative, language]}
        dashboard_only: {minutes: 40, panels: [dashboard]}
```

Channel 决定选择什么内容。Device 的硬件 `profile` 决定屏幕能力；`presentation.display_profiles` 则把刷新分钟数和允许轮换的命名 panels 绑定，`refresh.schedule` 按时段引用它。未配置 display profiles 时，旧的固定刷新窗口和 panel 列表仍兼容。完整示例见 [config.example.yaml](config.example.yaml)。

数学模块的 `type: games` 会轮换独立小游戏，目前包括 `game24` 和 `pattern`；也可以指定其中一种。找规律题包含数字、符号、词语、方向和图形化骰子点数序列。新题型实现放在 `modules/math_games/` 并注册到 `MathModule`。

主页为每台配置设备分别显示当前画面、下一次刷新时间和下一帧预览；右侧预览统一按设备原始宽高的 50% 显示。Kindle 的任务板区域始终预览任务板，不随当前显示模式切换；寻宝和 Fun Fact 使用各自的独立预览。包含 `items` 模块的设备还提供随机/定时预览及“更改”。临时预览不会改变设备当前画面，“更改”只影响下一屏。网页另有“今日清单”，勾选结果会更新下一帧，但不会冒充设备当前画面。字体菜单暂时全局共享。

设备专用 `preview.png` 优先显示设备已 ACK 的当前画面；尚无 ACK 时仍返回服务端生成的候选图，并在主页标注“设备尚未确认显示画面”，方便接入和调试。

## 内容库

`library_dir` 指向用户维护的素材库。常用结构：

```text
home_companian_library/
├── items.csv
├── checklists.csv
├── checklist_completions.csv
├── reward_redemptions.csv
├── chinese/
│   ├── full.md
│   └── select.md
├── health/
│   ├── exercises.csv
│   └── images/
├── math/
│   └── problems.csv
├── images/
│   ├── plants/
│   ├── animals/
│   └── etc/
├── fun_fact/
│   ├── police_station.md
│   └── police_station.png
├── treasure_hunt/
│   ├── current.yaml
│   ├── check_grey.png
│   └── background/
│       ├── background1.png
│       └── background1.yaml
└── photos/
```

- `items.csv`：`id,type,text`。
- `checklists.csv`：`id,type,text`；`personal` 每次完成积 1 分，`family_task` 每次完成积 2 分。清单 ID、成员归属、任务顺序和任务 ID 列表只写在 `config.yaml` 的 `checklists` 中。
- `checklist_completions.csv`：`date,item_id,points,completed_at`；由网页维护，保存每日完成和当次分值。
- `reward_redemptions.csv`：`date,reward_id,cost,redeemed_at`；由网页兑换按钮维护。
- `health/exercises.csv`：`id,name,dose,instruction`。
- `math/problems.csv`：`id,type,question,answer`，保存算术和数学思维题；答案暂不显示。24 点不写入 CSV，而由服务端随机生成，只使用加、减和低阶乘法，并保证有解。
- `chinese/full.md`：按一年级至六年级列出完整字表。
- `chinese/select.md`：只写当前启用的汉字。
- `creative/chinese.txt`：每行一个小学常用汉字，至少四个且不能重复。
- `creative/english.txt`：每行一个小学难度英文单词，至少四个且不能重复。
- `language/english_sentences.txt`：每行一句小学难度英文句子，供字母密码游戏随机选择。
- `language/fill_words.txt`：每行一题填字游戏，例如 `（八）月，（人）们`；中英文括号均可，括号数量决定填空数量，显示时答案位置为下划线。
- `language/chinese_poems.txt`：每行一首四句中文诗，显示为两行、每行两句。
- `images/` 和 `photos/`：供显示使用的已处理图片；集合中的 `raw/` 不参与轮换。
- `fun_fact/*.md`：每个 Markdown 文件是一条 Fun Fact；一级标题作为标题，其余文本和列表作为正文。同目录可放同名的 PNG、JPEG 或 WebP，作为右下角配图；配图可省略。
- `treasure_hunt/current.yaml`：网页维护的当前背景、六条线索和六个完成状态。
- `treasure_hunt/check_grey.png`：带透明通道的灰色完成勾，覆盖在线索纸张内并保持文字位于上层。
- `treasure_hunt/background/`：背景 PNG 及其同名 YAML；YAML 中必须用六组归一化 `[x, y, width, height]` 定义 `text_boxes`。

Kindle 当前使用 `landscape_5`：三个清单依次占三个区域，第四个区域从 `images/` 的所有直接子目录随机选取 PNG。清单名称、成员归属和顺序由 `config.yaml` 决定。图片配置写作 `{module: images, collections: "*"}`；名为 `raw` 的目录、各集合内部的 `raw/` 和空目录都不参与轮换。网页取消当天勾选时，只删除当天对应记录；以前日期的结算保留。

寻宝游戏和 Fun Fact 都不参与任务板 rotation。寻宝编辑器会扫描背景目录，按所选背景的六个区域摆放输入框；每条最多 200 个字符，并有独立“完成”复选框。完成后用透明 `check_grey.png` 在对应纸张上打勾，文字继续显示在勾上方。编辑器右侧显示 300×400 的最终 Kindle 竖屏预览。Fun Fact 使用与任务板相同的 800×600 横屏预览；网页下拉菜单以“标题（文件名）”列出素材，选择会保存在设备本地状态，并在 Fun Fact 为当前模式时立即更新待投递图片。Kindle 区块下方的模式下拉菜单可选择任务板、寻宝游戏或 Fun Fact，点击“确定”后立即生效；当前模式会标记在对应 section 标题中。手动选择的模式当天持续有效；进入第二天自动恢复任务板。

清单 slot 可用 `portrait: portraits/person_1.png` 以内容库中的 PNG 头像替代文字标题；头像靠区域右侧显示，任务仍排在左侧。可选的 `portrait_width` 用于单独调整头像宽度，范围为 40–190 像素。

当前奖励为“玩具”：所有成员的个人任务和家庭任务合并累计，初始赠送 25 分，50 分封顶。满分后网页启用“兑换”按钮；手动确认后写入兑换历史并直接清零，封顶期间的额外完成不会带入下一轮。Kindle 在配置了奖励的清单区域底部显示“玩具”和无数字进度条。

模块、模板和各文件的详细约束见 [DESIGN.md](DESIGN.md)。

## 图像处理

将图片处理成适合电子墨水屏的 PNG：

```bash
python3 image_utility.py input.jpg output.png
```

常用选项：

```bash
# 指定目标区域
python3 image_utility.py input.jpg output.png --size 528x228

# 线稿使用固定阈值
python3 image_utility.py input.png output.png --binarize threshold --threshold 180

# 保留完整图片并增强对比度
python3 image_utility.py input.jpg output.png --fit contain --autocontrast

# 保存可供不同模板运行时缩放的灰度主图
python3 image_utility.py input.jpg output.png --binarize grayscale
```

其他选项包括 `--trim`、`--content-scale` 和 `--invert`。输出图片不应包含顶部状态栏、CrowPanel 的 8px 硬件接缝或 framebuffer 旋转。
