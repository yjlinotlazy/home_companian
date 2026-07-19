#!/bin/sh

set -u

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
CONFIG_PATH=${2:-"$SCRIPT_DIR/client.conf"}

if [ ! -r "$CONFIG_PATH" ]; then
    echo "Cannot read config: $CONFIG_PATH" >&2
    exit 2
fi

# shellcheck source=/dev/null
. "$CONFIG_PATH"
WORK_DIR=${WORK_DIR:-/tmp/home_companian}
PID_FILE=$WORK_DIR/daemon.pid
STOP_FILE=$WORK_DIR/daemon.stop
LOG_FILE=$SCRIPT_DIR/client.log

case "${1:-}" in
    start)
        mkdir -p "$WORK_DIR" || exit 1
        if [ -r "$PID_FILE" ]; then
            pid=$(cat "$PID_FILE")
            if kill -0 "$pid" 2>/dev/null; then
                echo "Daemon is already running as PID $pid"
                exit 0
            fi
        fi
        rm -f "$STOP_FILE"
        nohup "$SCRIPT_DIR/daemon.sh" "$CONFIG_PATH" >> "$LOG_FILE" 2>&1 &
        echo "Daemon start requested"
        ;;
    stop)
        mkdir -p "$WORK_DIR" || exit 1
        : > "$STOP_FILE"
        if [ -r "$PID_FILE" ]; then
            pid=$(cat "$PID_FILE")
            kill "$pid" 2>/dev/null || true
        fi
        echo "Daemon stop requested"
        ;;
    status)
        if [ -r "$PID_FILE" ]; then
            pid=$(cat "$PID_FILE")
            if kill -0 "$pid" 2>/dev/null; then
                echo "Daemon is running as PID $pid"
                exit 0
            fi
        fi
        echo "Daemon is not running"
        exit 1
        ;;
    refresh)
        exec "$SCRIPT_DIR/client.sh" "$CONFIG_PATH"
        ;;
    *)
        echo "Usage: $0 {start|stop|status|refresh} [config]" >&2
        exit 2
        ;;
esac
