# Home Companian Architecture

Status: Accepted  
Date: 2026-07-18

## Decision

Home Companian is a server-first remote display platform for home devices. It is the product and the top-level repository.

The repository is a monorepo containing the existing server and its device clients. The server architecture remains based on the current implementation; adding clients does not rename the project or turn Forge into the whole platform.

Forge is one server-side component. It composes semantic content, applies presentation and rendering rules, and encodes device-specific Frames.

## Core principle

The server owns intelligence. Device clients are thin display appliances.

Clients do not know:

- application or recommendation logic;
- widgets or content modules;
- layouts and typography;
- AI or image generation;
- scheduling and refresh policy.

Clients only:

- connect to the network;
- request work and download Frames;
- display Frames;
- report acknowledgements and input events;
- execute server-provided sleep/wake instructions;
- provide watchdog, retry and local recovery behavior.

Local recovery is a safety mechanism, not an independent scheduler. On failure a client keeps the previous e-ink image and retries with bounded backoff or a safe fallback interval.

## Data flow

```text
Application / Content Modules
            │
            ▼
Server orchestration and scheduling
            │
            ▼
Forge: composition, rendering and encoding
            │
            ▼
Immutable device-specific Frame
            │
            ▼
Home Companian Protocol
            │
            ▼
Device Client
```

Input events and display acknowledgements travel back through the protocol. The server interprets them; clients do not attach application meaning to buttons, taps or gestures.

## Server responsibilities

- business and application logic;
- content selection and recommendation;
- scheduling and refresh policy;
- Scene construction;
- layouts and typography;
- image generation, scaling, dithering and output encoding;
- Frame identity and delivery state;
- acknowledgement and event handling;
- AI integrations.

The current Python server under `src/home_companian/` remains the source of truth. This decision does not require moving it into a new `server/` directory.

## Forge responsibilities

Forge is the rendering boundary inside the server. It receives selected semantic content plus a presentation and Device Profile, then produces an immutable Frame.

Forge does not own application selection, HTTP routing, device sleep state or event business logic.

## Client responsibilities

Each client owns only hardware-facing concerns:

- network setup and transport;
- display driver integration;
- supported input hardware;
- sleep, wake and watchdog behavior;
- payload integrity checks;
- safe recovery when the server or network is unavailable.

Device-family and model differences stay inside their client directories. They must not leak into application logic.

Every concrete client directory must contain a short `README.md` describing its required toolchain, configuration, build, deployment, logging and recovery workflow.

## Protocol authority

[PROTOCOL.md](PROTOCOL.md) is the shared contract between the server and every client. It is the single source of truth for:

- device identity and capabilities;
- Frame metadata and encodings;
- acknowledgements;
- generic input events;
- error and retry semantics;
- protocol versioning.

Server and client implementations consume this contract; they do not redefine it independently. Protocol changes that affect both sides must be updated and tested together in this monorepo.

`GET /display.bin` remains the only compatibility endpoint. It serves the existing `wall_panel` CrowPanel firmware. New clients use the versioned device protocol.

## Rendering and transport

The first generic vertical slice uses PNG over HTTP. PNG is an implementation starting point, not an architectural requirement.

Device profiles may later select raw bitmap, delta encoding or dirty rectangles. Transport may later add MQTT, WebSocket or push. These optimizations must not move layouts, scheduling or application logic into clients.

## Monorepo layout

The repository evolves toward this layout without moving the working server merely to match a diagram:

```text
home_companian/
├── src/home_companian/             # existing server
│   └── forge/                       # server-side renderer/encoder
├── clients/
│   ├── crowpanel/
│   │   └── crowpanel-579/           # ESP-IDF client
│   └── kindle/
│       └── gen7dk/                  # Kindle curl/eips client in progress
├── tests/                           # server and protocol tests
├── PROTOCOL.md                      # shared wire contract
├── ARCHITECTURE.md                  # this decision
└── DESIGN.md                        # detailed server/application design
```

The current browser page is a server-side preview and management UI, not a device client. A future browser display client may be added only when it follows the same thin-client contract.

Do not split clients into separate repositories unless a future constraint is strong enough to justify a new architecture decision. Different build systems inside the monorepo are expected.

## Initial generic vertical slice

```text
Server generates PNG
        ↓
Kindle downloads PNG
        ↓
Kindle displays PNG
        ↓
Kindle sends ACK
        ↓
Kindle sleeps for the server-provided interval
```

No Home Companian application logic may be implemented on the Kindle.

## Consequences

- Protocol, server and client changes can be reviewed and tested together.
- Client toolchains remain isolated inside their own directories.
- Adding a new instance of an existing model requires configuration, not copied application logic.
- Adding a new model should normally require a Device Profile and hardware adapter, not server application changes.
- The repository may contain Python, ESP-IDF/C++ and Kindle-specific tooling at the same time.
- Cross-component changes must preserve the thin-client boundary even when duplicating logic on a client appears faster.
