# Kindle 客户端

Kindle 版本很多，不同年代和型号的资料不能混用。硬件参数和可用命令以实机输出为准。

注意：越狱本身合法，但是会让厂家保修作废，还有变砖风险。务必慎重。

## 当前实机

- Device Instance ID：`kindleGen7dk`
- Device Profile：`kindle_6_167ppi_landscape`
- `eips -i` 实测：600×800、8-bit framebuffer、约 167 PPI、rotate 3
- 摆放方式：拿着正常竖屏 Kindle，逆时针旋转 90° 横放
- 服务端按 800×600 横屏排版，再顺时针旋转为 600×800 的 8-bit grayscale PNG；像素量化到 16 级
- 已验证：`curl` 可用，`eips` 可用，PNG 能以 `gc16` waveform 全刷显示

显示不依赖 KOReader。KOReader 目前只用于提供 SSH server。

手动 smoke test 使用完整客户端，以保证取到设备 Frame 并正确 ACK：

```sh
cd /mnt/us/home_companian
./client.sh
```

私有 CA 应通过客户端配置的 `rootCA.pem` 验证。只有临时排查证书问题时才使用不验证证书的模式。浏览器用的 `preview.png` 是 800×600 逻辑预览，不应直接交给 `eips`。

`clients/kindle/gen7dk/` 已实现单次请求 `/next`、`eips` 显示、ACK、休眠保持 dashboard，以及手动唤醒后的联网刷新。完整配置流程见 [Gen 7 README](gen7dk/README.md)。当前不做 RTC 定时唤醒；真正重启后需手动重新启动监听器。

## SSH 与安装记录

参考：https://samkhawase.com/blog/hacking-kindle

越狱：https://kindlemodding.org/

mount: udisksctl mount -b /dev/sda1
unmount: udisksctl unmount -b /dev/sda1

会挂载到/run/media/<username>/kindle，传输文件靠它

### SSH

KOReader 自带 SSH，这是目前找到的最简单入口。ssh一定要搞，开发测试会方便很多。

koreader直接下载：https://github.com/koreader/koreader/releases。要查一下适配版本。

解压后有两层文件，一层是reader,放根目录，另一层在extensions里，放kindle的extensions文件夹。

在kindle里，KUAL->koreader，找settings->network->ssh server，enable后，记下ip,端口，就可以连了，密码是空的

我选择了不要password(dangerous)，绕开public key。

ssh -p <port> root@<kindle ip>

## 附录

以下是弃置方案，但是留个底万一以后有用。

### 装kterm

https://www.fabiszewski.net/kindle-terminal/

到https://github.com/bfabiszewski/kterm/releases里找适配版本

解压后整个文件夹放进extensions里

拔掉线，kindle里打开KUAL，kterm就会出现了，打开运行

kterm里操作

https://github.com/gingrspacecadet/kpm，其中curl和unzip是kterm自带的，所以只要有kterm就行。那一长串在kindle里输入，一定别输错了。

回车后，会显示下载和安装进度，成功后会说all done you can now run kpm
