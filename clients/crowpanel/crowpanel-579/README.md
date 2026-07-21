# CrowPanel 5.79 英寸客户端

这是用于 792×272 CrowPanel 电子墨水屏的 ESP-IDF 客户端。它连接 Wi-Fi，从设备专属 `/v1/devices/<id>/next` 下载 framebuffer，刷新屏幕，确认该帧已显示，然后按照服务端返回的时间休眠。

它是薄客户端。内容选择、排版、渲染和刷新策略都由 Home Companian 服务端负责。

## 前置条件

- CrowPanel 5.79 英寸 ESP32-S3 电子墨水屏。
- 用于配置和刷写的 USB 数据线。
- 支持 ESP32-S3 的 ESP-IDF。
- 设备能够访问正在运行的 Home Companian 服务端。

按照 Espressif 的 [ESP32-S3 官方安装文档](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/get-started/index.html)安装 ESP-IDF，然后安装 ESP32-S3 所需工具：

```bash
cd /path/to/esp-idf
./install.sh esp32s3
```

每次打开新 shell 后，先启用 ESP-IDF 环境：

```bash
source /path/to/esp-idf/export.sh
```

## 配置

进入本客户端目录，运行：

```bash
idf.py menuconfig
```

在 `CrowPanel network configuration` 中设置：

- `Wi-Fi SSID`
- `Wi-Fi password`
- `Maximum connection retries`
- `Device-specific framebuffer URL`，例如 `https://<server-ip>:8003/v1/devices/wall_panel/next`

使用 HTTPS 时，用签发服务端证书的公开根 CA 替换 `main/rootCA.pem`。使用 mkcert 时可通过下面的命令找到 CA 目录：

```bash
mkcert -CAROOT
```

只复制 `rootCA.pem`。绝对不要把 `rootCA-key.pem` 或任何私钥放进本仓库或设备。

## 构建

```bash
idf.py build
```

客户端目录中的 `.gitignore` 会忽略 `build/`、`sdkconfig` 和 `sdkconfig.old`。

## 刷写

使用 USB 数据线连接设备，确认串口，然后运行：

```bash
idf.py -p /dev/ttyACM0 flash
```

实际串口也可能是 `/dev/ttyUSB0` 或其他设备名，请替换示例中的路径。

刷写后立即查看日志：

```bash
idf.py -p /dev/ttyACM0 flash monitor
```

按 `Ctrl+]` 退出 ESP-IDF monitor。

## 正常运行

设备启动后会：

1. 连接 Wi-Fi；
2. 下载恰好 27,200 字节的 framebuffer；
3. 刷新屏幕；
4. 向 `/v1/devices/wall_panel/ack` 确认该帧已显示；
5. 读取 `X-Next-Check-Seconds`；
6. 深睡到下一次检查时间。

如果 Wi-Fi 连接或下载失败，设备会保留电子墨水屏上的原画面，并在 30 分钟后重试。刷写固件时必须连接 USB；正常运行时不需要 USB，可以使用兼容电池供电。
