# Home Companian 里程碑

M1–M9 记录 CrowPanel baseline。当前代码已迁移到 Application → Scene → Forge → Frame → Protocol → Device 分层；仅保留 `/display.bin` 作为旧固件兼容口。

## M1：服务端静态画面

- [x] 建立 Python 项目和依赖管理。
- [x] 定义并加载 `config.yaml`。
- [x] 使用 Pillow 生成 792x272 黑白画面。
- [x] 实现 792x272 可见画面到 800x272 framebuffer 的接缝映射和旋转。
- [x] 添加 framebuffer 大小及关键像素映射测试。
- [x] 实现 `GET /display.bin`，固定返回 27,200 字节。
- [x] 实现 `GET /preview.png` 和网页预览。

验收：浏览器能预览静态打卡项目，下载的 framebuffer 能由现有 ESP32 测试项目正确显示。

## M2：内容配置与选择

- [x] 定义打卡项目、定时计划和随机池的 YAML 格式。
- [x] 校验重复或不存在的项目 `id`、非法时间及空项目池。
- [x] 实现定时模式选择逻辑及测试。
- [x] 实现随机模式选择逻辑及测试。
- [x] 避免随机模式连续显示相同项目。
- [x] 将单一文字内容和时间排版到画面。
- [x] 隔离网页随机预览和设备随机状态。
- [x] 支持用预览项目替换内存中的下一屏。
- [x] 手动更改保留到下一次设备请求，消费或服务重启后失效。
- [x] 显示下一次刷新时间，并在内存中预生成下一条随机内容及缩略预览。
- [x] 默认网页预览持久保存并显示最后一次发给设备的完整画面；“更改”只影响下一屏。

验收：修改 YAML 后无需改代码，即可按两种模式生成正确内容。

## M3：内容库

- [x] 在 `config.yaml` 中增加 `library_dir`，并移除内联项目。
- [x] 从 `<library_dir>/items.csv` 加载文字项目。
- [x] 校验 CSV 列、正整数 ID、重复 ID、空文字和项目类型。
- [x] 支持 `personal` 和 `family_task` 两种类型。
- [x] 将定时计划和随机池迁移到数字 ID。
- [x] 支持绝对和相对 `library_dir`，并提供可运行的示例内容库。
- [x] 确保服务端不保存原图，不引入缓存目录。

验收：用户可以移动整个内容库，只修改 `library_dir` 即可继续使用；修改 `items.csv` 后无需修改代码或重启服务。

## M4：ESP32 联网刷新

- [x] 在现有 CrowPanel 测试项目中加入 Wi-Fi 连接。
- [x] 通过 HTTPS 请求 `display.bin`。
- [x] 验证 HTTP 状态、Content-Length 和实际下载长度。
- [x] 将下载结果交给现有 e-ink 刷新流程。
- [x] 失败时保留旧画面。
- [x] 由服务端计算 07:00–22:00 活跃窗口内的 30 分钟检查周期。
- [x] 通过响应头把下次检查时间交给设备，并完成定时唤醒和深睡流程。

验收：ESP32 能从服务端取得画面，成功刷新后休眠，并在网络故障时保留旧内容。

## M5：部署与可维护性

- [ ] 提供示例配置和启动说明。
- [ ] 明确字体查找及缺少字体时的错误信息。
- [ ] 添加健康检查和基础日志。
- [ ] 验证服务重启、配置错误和设备重复请求场景。
- [ ] 补充端到端测试步骤。

验收：新环境可按文档启动服务，并能快速定位配置或设备请求问题。

## M6：模板与模块架构

- [x] 定义固定模板及数字区域模型。
- [x] 从应用资源加载模板，并校验区域编号、边界和重叠。
- [x] 定义模块的内容准备及区域渲染接口。
- [x] 将现有 `items.csv` 功能迁移为第一个模块。
- [x] 通过 `config.yaml` 选择内置模板并配置 `slot → module`。
- [x] 允许未分配区域保持白色。
- [x] 将下一条内存状态升级为整屏 `PreparedPanel`。
- [x] 模板或编排变化时使预生成画面失效。
- [x] 添加 `chinese` 模块，校验六个年级的完整字表及 `select.md` 子集。
- [x] 添加首个双区域模板，并验证 `items + chinese` 组合渲染。
- [x] 将顶部 44px 状态栏移出内容模板。
- [x] 建立独立于内容模块的状态栏模块接口和注册表。
- [x] 支持 `left`、`center`、`right` 三组布局及溢出校验。
- [x] 实现右侧星期和中央二十四节气；保留但默认隐藏时间、日期模块。

验收：不修改模板代码即可通过 YAML 选择内置模板、填充多个模块，并保证网页下一屏预览与设备实际取得的画面一致。

## M7：屏幕编辑器

- [ ] 在网页中浏览内置模板及其缩略图。
- [ ] 浏览可用模块及模块配置项。
- [ ] 通过点击或拖拽将模块放入模板的数字区域。
- [ ] 校验分配并写回与 YAML 手工配置相同的数据结构。
- [ ] 修改后使下一屏预生成状态失效并立即更新预览。

验收：用户无需手写 YAML，即可选择模板、完成模块编排并保存；编辑器不允许修改模板 topology。

## M8：图像内容

- [x] 提供独立命令行工具，可生成指定区域的 1-bit PNG 或供多模板复用的灰度主图。
- [x] 支持铺满裁切、白边适配、照片抖动和固定阈值。
- [x] 正确处理 EXIF 方向、透明背景、自动对比度和反色。
- [x] 采用 collection 文件夹作为图片池，实现跨集合随机轮换，并在运行时按模板区域缩放、二值化。
- [x] 添加左右 200x200、中间 368x228 的三区域模板。

验收：用户可以保存一份高分辨率处理后主图，在不同模板区域中正确缩放上屏，无需运行时缓存。

## M9：健身与数学模块

- [x] 定义 `health/exercises.csv` 和两帧动作图目录格式。
- [x] 实现 8 个徒手动作的原创极简线稿及全屏/小区域排版。
- [x] 定义 `math/problems.csv`，支持算术、数学思维和无说明文字的 24 点。
- [x] 数学画面只显示题目，保留但不暴露答案。
- [x] 两个模块均支持随机选择并避免连续重复。

验收：不修改代码即可编辑动作和题库，并能把 `health` 或 `math` 放入任一模板区域。

## M10：多设备领域模型

- [x] 定义不可变 `SceneFragment`、`Scene` 和 `Frame`。
- [ ] 定义 Channel，并把逻辑当前/下一 Scene 与具体设备 Frame 分开。
- [x] 定义 Device Instance、Device Profile、capabilities 和刷新策略。
- [x] 建立 profile/backend 注册表；内置 `crowpanel_579`。
- [x] 将配置直接迁移为 Channel/Device/Presentation；不兼容旧格式。
- [ ] 验证两台设备订阅同一 Channel 时共享 Scene、但不共享投递状态。

验收：代码可以表达“同一个 home Scene，分别面向 CrowPanel 和 Kindle 生成 Frame”，且不把设备尺寸写入 Scene。

## M11：Forge 组合与渲染引擎

- [x] 建立 `home_companian/forge/`，只包含 composition、layout、rendering、presentation 和 encoder。
- [ ] 将内容模块的选择结果改为语义 Scene fragment，不直接生成最终设备画面。
- [x] 将模板和状态栏迁入按 Device Profile 选择的 presentation。
- [x] 将 CrowPanel 的 8px 接缝、旋转和 1-bit 映射迁入 `crowpanel_1bit` encoder。
- [ ] 同一 Scene 支持生成预览 PNG 和 CrowPanel raw Frame。
- [ ] 保持现有模块、模板和网页画面视觉结果不回退。

验收：Forge 不依赖 HTTP、随机/定时选择或设备状态；现有 CrowPanel 仍可显示相同内容。

## M12：通用多设备协议

- [x] 实现 `GET /v1/devices/{device_id}/next`。
- [x] 实现不可变 Frame ID、Scene ID、profile ID 和 MIME type 响应元数据。
- [x] 实现 `POST /v1/devices/{device_id}/ack`，区分已发送与设备确认显示。
- [ ] 为每台设备保存独立的 current Frame、目标 Frame、下次检查时间和错误状态。
- [ ] 网页按 Device Instance 显示当前画面、下一帧和 ACK 状态。
- [x] 保留 `GET /display.bin` 作为 CrowPanel 固件接口。
- [ ] 添加重复 GET、重复 ACK、离线恢复和失败重试测试。

验收：不同 profile 的设备不会消费或覆盖彼此的 Frame，兼容 CrowPanel 固件无需立即重刷。

## M13：Kindle PNG 客户端

- [ ] 验证 Kindle 的实际运行入口：浏览器、越狱扩展或其他本地客户端。
- [x] 定义 `kindle_6_212ppi` Device Profile 和 `portrait_1` presentation。
- [x] 实现 16 级灰度 PNG backend。
- [ ] Kindle 能请求 PNG、显示、提交 ACK，并按建议时间再次检查。
- [ ] 新 Kindle 型号只需新增 profile；共享 backend 的型号不复制客户端业务逻辑。

验收：Kindle 与 CrowPanel 订阅同一 Channel，显示同一逻辑 Scene 的不同尺寸/格式 Frame。

## M14：通用事件

- [ ] 实现 `POST /v1/devices/{device_id}/events`。
- [ ] 定义 `wake`、`sleep`、`tap`、`swipe` 和 `button` 事件 envelope。
- [ ] 使用 `event_id` 去重，并关联产生事件时显示的 `frame_id`。
- [ ] 将设备坐标转换为规范化 Scene/presentation 事件后再交给 Application。
- [ ] Application 不按 Kindle/CrowPanel 型号分支业务逻辑。

验收：两个具有不同输入能力的设备可通过同一协议触发相同应用动作。

## M15：后续传输与刷新优化

- [ ] 根据设备能力支持灰度、raw bitmap 和未来 delta/dirty rectangle 编码。
- [ ] 支持按 Device Instance 调整活跃窗口、低电策略和刷新频率。
- [ ] 评估 Frame 内存缓存，保持内容库不产生运行时素材缓存目录。
- [ ] 评估 WebSocket、MQTT 或 push transport。

验收：优化仅影响 profile、encoder、refresh policy 或 protocol adapter，不修改 Application 和 Scene。

## 后续迭代候选

- [ ] 打卡确认及完成记录。
- [ ] 家务领取和奖币。
- [ ] 家庭相册。
- [ ] 可互动宠物和植物。
- [ ] 数学题答案揭晓及互动。
- [ ] 设备自动注册和认证。
