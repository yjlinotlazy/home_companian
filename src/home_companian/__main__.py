from __future__ import annotations

import argparse
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from .http_server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Home companion e-paper server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()

    try:
        load_config(args.config)
    except ConfigError as exc:
        parser.error(str(exc))

    server = create_server(args.host, args.port, args.config)
    print(f"Serving on http://{args.host}:{args.port} using {args.config}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
