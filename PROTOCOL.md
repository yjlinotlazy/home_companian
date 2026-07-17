# Home Companian HTTP Protocol

## 范围

Protocol 只负责在服务端和薄客户端之间传输不可变 Frame、ACK 和通用 Event。它不定义内容模块、Scene 选择、模板、字体或渲染算法。

本文描述多设备协议。Frame 获取和 ACK 已实现；Event 接口仍是计划。当前 CrowPanel 使用的 `GET /display.bin` 继续保留。

## 基本原则

- 每台设备使用稳定的 `device_id`；型号能力由服务端绑定的 Device Profile 决定。
- 客户端不提交布局、分辨率或业务类型，也不解析 Scene。
- 服务端根据 Device Instance 的 channel 和 profile 选择 Scene 并生成 Frame。
- Frame 生成后不可变；相同 `frame_id` 的 payload 和元数据必须保持一致。
- ACK 表示设备报告的显示结果，不等于服务端发送成功。
- 重复 GET、ACK 和 Event 必须能够安全重试。

## 获取下一帧

```http
GET /v1/devices/{device_id}/next
```

客户端可使用 `X-Current-Frame-Id` 告知自己目前实际显示的 Frame。服务端也会结合最近一次 ACK 判断是否需要返回新 Frame。

有新目标画面时返回二进制响应：

```http
HTTP/1.1 200 OK
Content-Type: image/png
Content-Length: ...
ETag: "frame-id"
X-Frame-Id: ...
X-Scene-Id: ...
X-Profile-Id: kindle_paperwhite_11
X-Next-Check-Seconds: 1800

<frame payload>
```

`Content-Type` 和 payload 由 Device Profile/encoder 决定。例如 Kindle 可以收到 `image/png`，CrowPanel 可以收到 `application/octet-stream`。

如果设备已经显示最新目标 Frame，可返回：

```http
HTTP/1.1 204 No Content
X-Next-Check-Seconds: 1800
```

`X-Next-Check-Seconds` 是服务端刷新策略给出的建议。客户端负责执行休眠，并可在网络错误或低电保护时采用本地安全值。

## 确认显示结果

```http
POST /v1/devices/{device_id}/ack
Content-Type: application/json

{
  "frame_id": "...",
  "status": "displayed"
}
```

`status` 初始支持：

- `displayed`：设备报告 Frame 已完成刷新。
- `failed`：下载完成后解码或显示失败。

失败时可以附加短错误码：

```json
{
  "frame_id": "...",
  "status": "failed",
  "error": "display_timeout"
}
```

对同一设备、Frame 和状态重复提交 ACK 不应产生额外业务效果。

## 上报通用事件

```http
POST /v1/devices/{device_id}/events
Content-Type: application/json

{
  "event_id": "...",
  "type": "tap",
  "frame_id": "...",
  "timestamp": "2026-07-17T12:00:00Z",
  "payload": {
    "x": 120,
    "y": 300
  }
}
```

初始事件名称保留：

- `wake`
- `sleep`
- `tap`
- `swipe`
- `button`

`payload` 随事件类型变化。Protocol 层记录来源设备并完成去重，然后把规范化事件交给 Application；Application 不应根据 Kindle/CrowPanel 型号分支业务逻辑。

## 错误与重试

- 未知设备返回 `404`。
- 未授权设备返回 `401` 或 `403`；具体注册和认证方式待定。
- Scene、profile 或渲染配置错误返回 `500`，并在服务端日志中记录具体原因。
- 获取失败时客户端保留现有画面，不主动清屏。
- 客户端按响应建议或本地退避策略重试，不进行紧密循环。
- Frame 下载成功但未收到 ACK 时，服务端可以再次返回同一不可变 Frame。

## 当前兼容接口

`GET /display.bin` 固定映射到 `wall_panel`，继续返回固定 27,200 字节的 1-bit framebuffer，并使用 `X-Next-Check-Seconds` 控制下次检查。它不跟随 `default_device`，避免默认设备切换到 Kindle 后破坏现有 CrowPanel 固件。

兼容接口没有显式 `device_id` 和 ACK，因此网页中的“当前画面”只代表最后一次发出的画面。CrowPanel 迁移到通用接口并提交 `displayed` ACK 后，网页才能区分“已发送”和“设备确认显示”。

## 未来传输

WebSocket、MQTT、push 或本地 IPC 可以复用相同 Frame/Event 语义。增加传输方式不应修改 Application、Scene 或 Forge。
