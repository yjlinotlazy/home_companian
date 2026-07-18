# Home Companian 设计文档

## 产品目标

家宠是运行在家庭服务器上的多设备显示项目。服务端持有内容、调度、排版和渲染逻辑；CrowPanel、Kindle 及未来设备是稳定、可复用的薄客户端。

当前已打通 CrowPanel 的定时拉取与电子墨水屏刷新，支持文字、图片、识字、健身和数学模块；服务端也已具备 Kindle profile、PNG Frame 和通用 Frame/ACK 接口。下一阶段是接入 Kindle 客户端，并继续收紧 Application、Forge、Protocol 和 Device 的代码边界。

## 架构原则

1. 服务端优先：内容选择、调度、布局、字体、图像处理和输出编码均在服务端。
2. 薄客户端：设备只负责联网、请求 Frame、显示、上报结果/事件和电源管理。
3. 设备无关 Scene：业务内容不包含 Kindle 或 CrowPanel 的像素坐标和编码细节。
4. Forge 专注于组合与渲染：不吸收 HTTP、业务调度、设备状态或事件业务逻辑。
5. Frame 不可变：已生成的 Frame 不会被覆盖；ACK 只更新设备投递状态。
6. 渲染与传输分离：PNG、raw bitmap、HTTP 或未来 MQTT 都不改变应用和 Scene。
7. 扩展设备不改应用：新型号优先只增加 Device Profile；新硬件系列才增加 backend/encoder。

## 目标分层

```text
Application / Modules
        │
        ▼
Scene fragments
        │
        ▼
Channel Scene
        │
        ▼
Forge + Device Profile
        │
        ▼
Immutable Frame
        │
        ▼
Protocol
        │
        ▼
Device
```

### Application 与模块

Home Companian 是整个产品，也是当前的应用。items、images、chinese、health 和 math 等模块拥有各自的内容加载、验证和选择逻辑。模块产生语义内容，不产生最终设备像素。

随机/定时调度、推荐、AI 及未来互动属于 Application 层，不属于 Forge。

### Scene 与 Scene fragment

Scene fragment 是单个模块的已选定内容，例如文字、图像素材引用、健身动作或一组 24 点数字。Scene 是一次应显示的完整语义快照，包含 fragment、语义角色和必要元数据，但不包含绝对像素坐标、硬件旋转或输出格式。

Scene 生成后不可变。同一 Scene 可以由 Forge 为不同 Device Profile 生成不同 Frame。

### Channel

Channel 表示一组设备共享的逻辑内容流。例如 Kindle 和 CrowPanel 都订阅 home，它们共享当前/下一 Scene，但拥有独立的 Frame、刷新时间、投递状态和 ACK。

设备离线后重新连接时默认取得频道的最新目标 Scene，不补发已错过的每一帧。手动“更改”作用于 Channel 的下一 Scene，不直接覆盖任何设备已显示的 Frame。

### Forge

Forge 是 Home Companian 内部的组合与渲染引擎，不是 repo 或整个产品的名字。它负责：

- 根据 Device Profile 选择 presentation/模板。
- 把 Scene fragments 映射到布局区域。
- 状态栏等统一画面组合。
- 字体、排版、缩放、二值化和抖动。
- 调用目标 encoder 生成设备所需的 Frame payload。

Forge 不负责内容推荐、随机/定时选择、HTTP 路由、ACK 存储、事件业务处理或设备休眠。

### Device Instance、Profile 与 Backend

- Device Instance：具体设备的稳定 ID，绑定 profile、channel、授权信息和刷新策略。
- Device Profile：可复用的型号能力描述，包括 viewport、方向、色深、safe area、输出 MIME type、刷新限制和输入 capabilities。
- Display Backend / Encoder：将 Forge 的标准渲染结果编码为 PNG、CrowPanel raw 1-bit framebuffer 或未来格式。

多个 Kindle 型号应尽量共享 kindle_png backend，只使用不同 profile。CrowPanel 的接缝和旋转映射属于 crowpanel_1bit encoder。

### Frame

Frame 是针对某个 Scene 和 Device Profile 生成的不可变输出，至少包含 frame_id、scene_id、profile_id、MIME type、payload/hash 和生成时间。PNG 与 raw 1-bit 是并行格式，不是全局演进阶段。

### Protocol 与 Event

Protocol 只负责传输 Frame、ACK 和 Event，不调用排版细节。第一个通用协议使用 HTTP pull，具体契约见 [PROTOCOL.md](PROTOCOL.md)。

Event 使用通用类型，如 wake、sleep、tap、swipe 和 button。Protocol 层必须知道来源 device_id 和关联 frame_id，但 Application 不应依赖 Kindle 或 CrowPanel 的硬件名称。

## 目标代码边界

```text
src/home_companian/
├── modules/        # 内容加载、验证、选择和 Scene fragments
├── application/    # Channel、调度和业务事件
├── forge/          # composition、presentation、rendering、encoders
├── protocol/       # HTTP Frame/ACK/Event 契约
└── devices/        # instances、profiles、capabilities、投递状态
```

这是目标边界，不要求目录与分层一一对应。当前 `forge/` 和 `devices/` 已独立；Application 与 HTTP Protocol 仍有部分逻辑集中在 `service.py` 和 `http_server.py`，后续按实际复杂度再拆。设备端客户端可以因工具链不同继续放在独立项目中；本 repo 只要求服务端 Device Profile 和协议契约稳定。

## 当前 CrowPanel Profile

- 屏幕：5.79 inch 黑白 e-ink，横屏显示。
- 可见分辨率：792x272。
- 控制器显存尺寸：800x272，每像素 1 bit，共 27,200 字节。
- 屏幕由两个级联 SSD1683 控制器驱动，中间包含 8 像素不可见接缝。
- 当前驱动要求 framebuffer 包含接缝映射及 180 度旋转。
- 刷新后电子墨水屏会保持画面，不需要服务端持续推送。

参考硬件测试项目：`/home/yli/Embedded/esp32/crowpanel-579-epaper`。

## 当前 CrowPanel Baseline

### 服务端

使用 Python，HTTP 层使用标准库 `ThreadingHTTPServer`，减少第一版的外部依赖：

- Pillow 负责中文排版、画面合成及 framebuffer 转换。
- `config.yaml` 只存储程序设置、内容库路径和内容选择规则。
- 文字条目和成品图片存储在用户指定的内容库中。
- HTTP 服务同时提供设备画面和网页预览。

当前 HTTP 接口中，只有 `/display.bin` 是兼容接口；其余是当前网页 UI 接口：

- `GET /display.bin`：返回 `application/octet-stream`，响应体必须恰好为 27,200 字节；`X-Next-Check-Seconds` 响应头告诉设备下次唤醒时间。
- `GET /preview.png`：默认返回服务端最后一次为设备生成的完整 PNG 画面；带手动预览参数时返回临时预览。
- `GET /`：提供简单网页预览和手动刷新入口。

设备接口直接返回排版完成的 framebuffer。ESP32 不负责解析 JSON、字体排版或 PNG 解码。

### ESP32

设备主动请求 `display.bin`。服务端统一计算刷新周期和白天窗口，设备不需要校时。一次刷新流程为：

1. 连接网络。
2. 下载 framebuffer，并读取 `X-Next-Check-Seconds`。
3. 验证 HTTP 状态和响应长度。
4. 将内容交给现有 `EPD_Display()` 刷新。
5. 屏幕和设备进入深睡，按服务端给出的秒数唤醒。

下载失败或响应长度错误时不清屏，保留上一次画面，并使用 30 分钟的默认值再次检查。

## Kindle 6 inch Profile

- Profile ID：`kindle_6_212ppi`。
- 方向与分辨率：竖屏 758×1024。
- 屏幕：6 inch，约 4:3，212 PPI。
- 灰度：16-level grayscale。
- Frame：`image/png`，758×1024、8-bit grayscale 容器，像素量化到最多 16 级。
- 当前 presentation：48px 状态栏和 758×976 的 `portrait_1` 全屏内容区。

当前实例 ID 为 `kindleGen7dk`，服务端已支持 `GET /v1/devices/kindleGen7dk/next` 和显示 ACK。Kindle 设备端客户端仍需验证实际运行入口并实现下载、显示和定时检查。

## 内容模型

所有文字项目统一存放在 `<library_dir>/items.csv`，使用扁平结构：

```csv
id,type,text
1,personal,出门走一走
2,personal,安静读几页书
3,family_task,收拾家里两分钟
```

- `id`：正整数。新项目使用当前最大 ID 加一；删除后不重新编号，不复用旧 ID。
- `type`：`personal` 表示个人习惯或提醒，`family_task` 表示家庭任务。
- `text`：直接显示在小屏幕上的单个文字字段，不区分标题和说明。

定时模式和随机项目池都通过数字 `id` 引用项目。

## 内容库

`library_dir` 是用户指定的可移动、可同步内容根目录：

```text
home_companian_library/
├── items.csv
├── photos/
│   └── family_trip.png
└── images/
    └── stretching.png
```

- `items.csv`：个人提醒和家庭任务的统一文字数据源。
- `health/exercises.csv`：徒手动作名称、次数/时长和关键提示；两帧主图位于 `health/images/<id>/`。
- `math/problems.csv`：算术和数学思维题，答案只保存在内容库中，第一版不显示。
- `photos/`：已处理、可直接上屏的家庭图片。
- `images/`：已处理、可直接上屏的通用插图、背景和图标。

`photos/` 和 `images/` 只保存成品素材，不保存原图。图片规范为：

- PNG。
- 使用 PNG；推荐保存足够大的已清理灰度主图，以供不同模板复用。
- 模块按目标区域保持比例缩放、白底居中，再生成黑白 1-bit 画面。
- 横屏且视觉方向正确。
- 不包含硬件的 8 像素接缝或 180 度显存映射。

独立的 `image_utility.py` 负责把用户指定的原图转换为处理后的 PNG，支持铺满裁切、白边适配、照片抖动、固定阈值、灰度主图、自动对比度和反色。`raw/` 子目录可保留原图但不参与轮换。运行中的服务端只对处理后主图做槽位缩放和最终二值化，不设置缓存目录。

## 内容选择模式

`scheduled` 和 `random` 是 Channel 的两种选择模式。Device Instance 只决定订阅哪个 Channel、何时检查和使用哪个 presentation；选择模式不属于设备型号。

### 定时模式

定时配置通过项目 `id` 引用内容：

```yaml
channels:
  home:
    mode: scheduled
    schedule:
      - {time: "12:00", item: 1}
      - {time: "13:00", item: 2}
```

每次设备请求时，服务端根据当前本地时间选择最近一个已经开始的项目。例如 12:40 请求时仍选择 12:00 的项目。画面保持到设备下一次成功刷新，不需要单独的持续时间或过期时间字段。

### 随机模式

```yaml
channels:
  home:
    mode: random
    random_items: [1, 2]
devices:
  wall_panel:
    refresh:
      minutes: 30
      active_start: "07:00"
      active_end: "22:00"
```

CrowPanel 当前在 07:00–22:00 之间每 30 分钟请求一次，服务端从项目池选择一个项目。尽量避免连续两次显示相同项目。22:00 后设备直接休眠到次日 07:00。

`refresh.minutes`、`active_start` 和 `active_end` 共同决定该设备的下次检查时间；服务端不主动推送。

## 模板、模块与编排

当前 CrowPanel 多区域画面分为三个独立概念：

- 模板由程序提供，定义 `crowpanel_579` presentation 的固定 topology。区域使用模板内部的数字编号，例如 `1`、`2`、`3`；编号不在不同模板之间表达相同语义。
- CrowPanel 屏幕顶部固定预留 44px 状态栏。状态栏不属于内容模板；792x272 屏幕的模板内容区统一为 792x228。
- 模块的 `prepare` 阶段选择内容并生成 Scene fragment；当前模块仍负责在 Forge 给定的矩形内绘制自己的 tile，Forge 负责整体 composition、presentation 和最终编码。长期可以继续把通用文字排版和图像处理能力下沉到 Forge，但模块不得拥有设备绝对坐标或编码细节。
- 编排保存在用户的 `config.yaml` 中，记录当前选择的内置模板以及 `slot → module` 分配。用户可以选择模板和模块分配，但不能在配置中修改模板坐标。

模板/presentation 属于 Forge 和 Device Profile，不属于 `<library_dir>`。内容库只保存用户素材和各模块的数据源。

状态栏使用另一套独立模块系统，不与内容模块共享接口、注册表或配置。状态栏模块只生成紧凑的横向内容，由状态栏布局器按 `left`、`center`、`right` 三组排列；内容模块对应 Scene fragments。状态栏不参与下一屏内容预生成，而是由 Forge 按画面的目标时间即时渲染。

```yaml
status_bar:
  left: []
  center:
    - module: solar_term
  right:
    - module: weekday
```

三组内部按配置顺序从左到右显示，左右边距为 16px，模块间距为 12px；模块越界或不同组发生重叠时直接报错。内置状态栏模块包括 `weekday`、`time`、`solar_term` 和 `date`。当前画面中央显示最近已经开始的二十四节气，右上角显示星期；`time` 和 `date` 保留实现但默认配置不显示。节气根据太阳视黄经计算，并按 UTC+8 的传统历法日期切换。

当前已用单区域 `landscape_1`、双区域 `landscape_2` 和三区域 `landscape_3` 打通链路。内存中的下一屏已改为不可变 Scene；模块选择结果保存为 Scene fragments，模板和 slot 映射由 Forge 的 Presentation 独立持有。

当前配置：

```yaml
panel:
  template: landscape_1
  slots:
    1: {module: items}
```

当前双区域配置：

```yaml
panel:
  template: landscape_2
  slots:
    1: {module: items}
    2: {module: chinese, source: select}
```

当前三区域配置使用两个 200x200 正方形侧栏和一个 368x228 中栏，区域间距为 12px：

```yaml
panel:
  template: landscape_3
  slots:
    1: {module: images, collections: "plants,animals"}
    2: {module: items}
    3: {module: chinese, source: select}
```

`images` 模块可用 `collection` 指定一个图片集合，或用逗号分隔的 `collections` 指定多个集合并统一随机轮换；图片来自 `<library_dir>/images/<collection>/`，并避免连续重复。素材是已处理的 PNG 主图，允许不同尺寸和灰度模式；模块运行时按区域 `contain` 缩放并最终二值化，因此同一素材可用于不同模板。

`chinese/full.md` 必须包含一年级至六年级标题，标题下汉字无需逐字换行；分类目前只供用户参考。`chinese/select.md` 只保存启用汉字。加载时忽略空白、去重并保序，同时拒绝非汉字、缺失年级标题及不属于完整字表的选择。

`health` 模块从 `health/exercises.csv` 随机选择动作并避免连续重复。每个动作使用两张原创极简线稿，画面只显示大号名称、次数/时长和两帧姿势；`instruction` 保存在内容库中但第一版不显示。第一版包含深蹲、俯卧撑、臀桥、鸟狗式、平板支撑、提踵、开合跳和原地高抬腿，不记录完成状态。

`math` 模块从 `math/problems.csv` 随机选择题目并避免连续重复。`type` 可为 `arithmetic`、`thinking`、`game24` 或 `all`。24 点的 `question` 是四个空格分隔的数字，画面显示“24点”标题和这四个数字；`answer` 仅保存解法，不显示。

未来的“屏幕编辑器”是 presentation 配置的图形界面：浏览程序内置模板、查看 Scene 中的语义模块，并为某个 Device Profile 配置模块到区域的映射。编辑器仍写回同一份配置，不维护第二套状态。

## 网页预览

当前网页行为：

- 网页同时提供随机预览和定时预览，不受 YAML 的当前模式限制。
- 随机预览提供“换一个”按钮，每次选择新的随机项目。
- 定时预览提供时间输入和“预览”按钮，可按指定时间模拟定时选择。
- 手动预览只影响当前网页，不修改 YAML，也不改变 ESP32 的设备结果。刷新网页后恢复真实全局画面。
- CrowPanel 把最后一次 `/display.bin` 生成的完整画面作为当前画面，因此项目、图片、字体和状态栏都与发给设备的 framebuffer 一致。兼容接口没有 ACK，所以它表示“最后一次发出”，不代表设备已经确认刷新成功。
- 预览后可以点击“更改”，用当前候选项目替换内存中的下一屏。网页的下一屏缩略预览立即更新，设备下一次请求 `/display.bin` 时消费该画面。
- 手动更改不按时钟提前过期；即使设备延迟唤醒，也保留到下一次设备请求。消费后恢复正常选择，服务重启或模板/编排变化也会清除该更改。
- 网页随机预览和设备随机选择使用独立状态，预览不会提前消耗或改变设备的下一个随机结果。
- `fonts` / `font` 保存中文字体候选和当前选择；`latin_fonts` / `latin_font` 保存非中文字体候选和当前选择。网页的两个下拉菜单写回各自选择，永久影响网页和设备画面。
- 网页显示下一次刷新时间和缩略预览。随机模式的下一条内容预先保存在服务内存中：网页只查看，设备请求时消费并生成再下一条；服务重启后清空。
- `wall_panel` 最后一次画面继续写入 `~/.local/state/home_companian/current.png`，其他设备按设备写入 `current-<device_id>.png`。服务重启后仍可恢复；下一屏状态仍只保存在内存中。设备从未请求过画面时，默认预览返回“尚无设备画面”，绝不拿下一屏冒充当前画面。

主页按配置列出设备。当前控制区仍服务 `default_device`，其他设备先显示各自已确认的当前画面；未来再加入设备选择器和逐设备控制。服务端不能用某台设备最后生成的 PNG 冒充另一台设备的当前画面。

## 页面内容

第一版画面显示内容模块，并在状态栏中央显示当前节气、右侧显示星期；不加标题、说明、边框或分隔线。

第一版暂不加入项目图片、动画和交互控件。

## 配置位置

用户配置默认存放在：

```text
~/.config/home_companian/config.yaml
```

配置通过绝对路径指向内容库：

```yaml
library_dir: /home/yli/Dropbox/home_companian_library
```

`~/.config` 不存放文字条目、照片或通用图片。

多设备配置使用以下结构：

```yaml
default_device: wall_panel
channels:
  home:
    mode: random

devices:
  wall_panel:
    profile: crowpanel_579
    channel: home
    refresh:
      minutes: 30
      active_start: "07:00"
      active_end: "22:00"
    presentation:
      status_bar: {}
      panel:
        template: landscape_3
        slots:
          1: {module: images, collections: "plants,animals"}
          2: {module: items}
          3: {module: chinese, source: select}
```

内置 Device Profile 与用户的 Device Instance 分开保存。不同设备可以选择不同刷新窗口、状态栏、模板和模块；用户只选择 profile，不复制硬件参数。旧的顶层显示配置不再兼容。

设备 ID 只存在于用户配置和由它派生的运行状态中，不等同于型号。多台同型号设备可以使用不同 ID 和同一个 profile。唯一例外是旧固件兼容口 `/display.bin` 固定查找 `wall_panel`；通用接口不要求这个名字。

字体候选和当前选择也保存在配置中。网页分别从 `fonts` 和 `latin_fonts` 生成中文、非中文下拉菜单，选中后写回 `font` 或 `latin_font`：

```yaml
font: /usr/share/fonts/TTF/LXGWWenKai-Medium.ttf
fonts:
  霞鹜文楷: /usr/share/fonts/TTF/LXGWWenKai-Medium.ttf
  思源黑体: /usr/share/fonts/adobe-source-han-sans/SourceHanSansCN-Regular.otf

latin_font: /usr/share/fonts/TTF/CaskaydiaCoveNerdFont-Regular.ttf
latin_fonts:
  Caskaydia Cove Nerd Font: /usr/share/fonts/TTF/CaskaydiaCoveNerdFont-Regular.ttf
  JetBrains Mono Nerd Font: /usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf
  Noto Sans Mono: /usr/share/fonts/noto/NotoSansMono-Regular.ttf
  霞鹜文楷: /usr/share/fonts/TTF/LXGWWenKai-Medium.ttf
```

## 当前阶段非目标

以下内容不属于当前多设备重构阶段：

- 打卡完成记录。
- 家务领取及奖币。
- 完整触摸手势业务和设备端菜单。
- WebSocket、MQTT 或服务端 push。
- Dirty rectangle 和局部刷新优化。
- 自动发现未知设备型号。
- 原始照片或原始图片管理。
- 持久化素材缓存；处理后的素材仍由内容库管理。
- 自定义模板 topology。
- 屏幕编辑器；当前先提供 YAML presentation 配置。

## 待确认

- Wi-Fi 凭据和服务器地址目前通过 ESP-IDF 配置写入固件，后续再决定是否支持设备端配置。
- Kindle 客户端采用浏览器页面、越狱扩展还是其他显示入口，需要在实现设备端下载和显示客户端前验证。
- 多设备认证和首次注册方式尚未确定；协议先保留稳定的 `device_id` 边界。
