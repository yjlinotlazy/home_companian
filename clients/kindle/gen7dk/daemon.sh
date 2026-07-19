#!/bin/sh

set -u
umask 077

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
CONFIG_PATH=${1:-"$SCRIPT_DIR/client.conf"}

if [ ! -r "$CONFIG_PATH" ]; then
    echo "Cannot read config: $CONFIG_PATH" >&2
    exit 2
fi

# shellcheck source=/dev/null
. "$CONFIG_PATH"

WORK_DIR=${WORK_DIR:-/tmp/home_companian}
WAVEFORM=${WAVEFORM:-gc16}
SCREEN_RESTORE_DELAY=${SCREEN_RESTORE_DELAY:-3}
WIFI_WAIT_SECONDS=${WIFI_WAIT_SECONDS:-60}
FRAME_PATH=$WORK_DIR/frame.png
PID_FILE=$WORK_DIR/daemon.pid
STOP_FILE=$WORK_DIR/daemon.stop

mkdir -p "$WORK_DIR" || exit 1

if [ -r "$PID_FILE" ]; then
    old_pid=$(cat "$PID_FILE")
    if kill -0 "$old_pid" 2>/dev/null; then
        echo "Daemon is already running as PID $old_pid" >&2
        exit 1
    fi
fi

rm -f "$STOP_FILE"
printf '%s\n' "$$" > "$PID_FILE"

cleanup() {
    rm -f "$PID_FILE"
}
trap 'exit 0' 1 2 15
trap cleanup 0

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

restore_dashboard() {
    if [ ! -r "$FRAME_PATH" ]; then
        log "No cached frame to restore"
        return
    fi
    sleep "$SCREEN_RESTORE_DELAY"
    if eips -g "$FRAME_PATH" -w "$WAVEFORM" -f; then
        log "Restored dashboard over screensaver"
    else
        log "Failed to restore cached dashboard"
    fi
}

wait_for_wifi() {
    elapsed=0
    while [ "$elapsed" -lt "$WIFI_WAIT_SECONDS" ]; do
        state=$(lipc-get-prop com.lab126.wifid cmState 2>/dev/null || true)
        if [ "$state" = "CONNECTED" ]; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

refresh_dashboard() {
    if ! wait_for_wifi; then
        log "Wi-Fi did not connect within $WIFI_WAIT_SECONDS seconds"
        return
    fi
    if "$SCRIPT_DIR/client.sh" "$CONFIG_PATH"; then
        log "Refreshed dashboard after manual wake"
    else
        log "Refresh failed; keeping cached dashboard"
    fi
}

log "Daemon started"
while [ ! -e "$STOP_FILE" ]; do
    event=$(lipc-wait-event -s 60 com.lab126.powerd \
        goingToScreenSaver,wakeupFromSuspend 2>/dev/null || true)
    case "$event" in
        goingToScreenSaver*) restore_dashboard ;;
        wakeupFromSuspend*) refresh_dashboard ;;
    esac
done
log "Daemon stopped"
