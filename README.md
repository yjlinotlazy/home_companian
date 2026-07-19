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
- 节气、星期等状态栏信息。

目前支持定时和随机两种内容选择方式。互动、任务领取、完成记录和奖励系统仍是后续方向。

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

设备端源码与服务端放在同一仓库：

- `clients/crowpanel/crowpanel-579/`：当前 CrowPanel ESP-IDF 客户端；部署方法见其 [README.md](clients/crowpanel/crowpanel-579/README.md)。
- `clients/kindle/gen7dk/`：Kindle Gen 7 客户端；部署方法见其 [README.md](clients/kindle/gen7dk/README.md)。

各客户端保留自己的工具链和局部 `.gitignore`，但共同遵守 [PROTOCOL.md](PROTOCOL.md)。CrowPanel 目前仍通过兼容接口工作；Kindle 使用 PNG → 显示 → ACK → 休眠的通用协议链路。

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
      minutes: 30
      active_start: "07:00"
      active_end: "22:00"
    presentation:
      status_bar:
        center: [{module: solar_term}]
        right: [{module: weekday}]
      panel:
        template: landscape_3
        slots:
          1: {module: images, collections: "plants,animals"}
          2: {module: items}
          3: {module: chinese, source: select}
```

Channel 决定选择什么内容。Device 决定使用哪个 profile、订阅哪个 Channel、何时刷新以及如何排版。完整示例见 [config.example.yaml](config.example.yaml)。

主页为每台配置设备分别显示当前画面、随机/定时预览、“更改”、下一次刷新时间和下一帧缩略图。临时预览不会改变设备当前画面；某个设备区块中的“更改”只影响该设备的下一屏。字体菜单暂时全局共享，候选来自配置中的 `fonts` 和 `latin_fonts`。

设备专用 `preview.png` 优先显示设备已 ACK 的当前画面；尚无 ACK 时仍返回服务端生成的候选图，并在主页标注“设备尚未确认显示画面”，方便接入和调试。

## 内容库

`library_dir` 指向用户维护的素材库。常用结构：

```text
home_companian_library/
├── items.csv
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
│   └── animals/
└── photos/
```

- `items.csv`：`id,type,text`。
- `health/exercises.csv`：`id,name,dose,instruction`。
- `math/problems.csv`：`id,type,question,answer`；答案暂不显示。
- `chinese/full.md`：按一年级至六年级列出完整字表。
- `chinese/select.md`：只写当前启用的汉字。
- `images/` 和 `photos/`：供显示使用的已处理图片；集合中的 `raw/` 不参与轮换。

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
