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

: "${SERVER_URL:?SERVER_URL must be configured}"
REMOTE_IMAGE_URL=${REMOTE_IMAGE_URL:-}
DEVICE_ID=${DEVICE_ID:-kindleGen7dk}
CA_CERT=${CA_CERT:-}
INSECURE=${INSECURE:-0}
WORK_DIR=${WORK_DIR:-/tmp/home_companian}
WAVEFORM=${WAVEFORM:-gc16}

NEXT_URL=${SERVER_URL%/}/v1/devices/${DEVICE_ID}/next
ACK_URL=${SERVER_URL%/}/v1/devices/${DEVICE_ID}/ack
FRAME_PATH=$WORK_DIR/frame.png
FRAME_TEMP=$WORK_DIR/frame.png.download
HEADERS_TEMP=$WORK_DIR/headers.download

mkdir -p "$WORK_DIR" || exit 1

cleanup() {
    rm -f "$FRAME_TEMP" "$HEADERS_TEMP"
}
trap cleanup 0 1 2 15

curl_with_tls() {
    if [ -n "$CA_CERT" ]; then
        curl --cacert "$CA_CERT" "$@"
    elif [ "$INSECURE" = "1" ]; then
        curl -k "$@"
    else
        curl "$@"
    fi
}

header_value() {
    name=$1
    sed -n "s/^$name:[[:space:]]*//p" "$HEADERS_TEMP" \
        | tr -d '\r' \
        | tail -n 1
}

send_ack() {
    status=$1
    body=$(printf '{"frame_id":"%s","status":"%s"}' "$frame_id" "$status")
    curl_with_tls -fSs \
        -H 'Content-Type: application/json' \
        -d "$body" \
        -o /dev/null \
        "$ACK_URL"
}

echo "Downloading $NEXT_URL"
download_source=server
if ! curl_with_tls -fSs \
    --connect-timeout 15 \
    --max-time 60 \
    -D "$HEADERS_TEMP" \
    -o "$FRAME_TEMP" \
    "$NEXT_URL"; then
    if [ -z "$REMOTE_IMAGE_URL" ]; then
        echo "Frame download failed; keeping the current display" >&2
        exit 1
    fi
    echo "Home server unavailable; downloading remote image"
    download_source=remote
    : > "$HEADERS_TEMP"
    if ! curl -fLSs \
        --connect-timeout 15 \
        --max-time 60 \
        -o "$FRAME_TEMP" \
        "$REMOTE_IMAGE_URL"; then
        echo "Remote image download failed; keeping the current display" >&2
        exit 1
    fi
fi

if [ "$download_source" = "server" ]; then
    frame_id=$(header_value 'X-Frame-Id')
    content_type=$(header_value 'Content-Type')
    next_check_seconds=$(header_value 'X-Next-Check-Seconds')

    case "$frame_id" in
        ''|*[!A-Za-z0-9._:]*)
            echo "Missing or invalid X-Frame-Id" >&2
            exit 1
            ;;
    esac

    case "$content_type" in
        image/png*) ;;
        *)
            echo "Expected image/png, received: ${content_type:-missing}" >&2
            exit 1
            ;;
    esac

    case "$next_check_seconds" in
        ''|*[!0-9]*) next_check_seconds=1800 ;;
    esac
else
    frame_id=remote-static
    next_check_seconds=1800
fi

mv "$FRAME_TEMP" "$FRAME_PATH" || exit 1

if ! eips -g "$FRAME_PATH" -w "$WAVEFORM" -f; then
    echo "eips failed" >&2
    if [ "$download_source" = "server" ]; then
        send_ack failed || true
    fi
    exit 1
fi

if [ "$download_source" = "server" ] && ! send_ack displayed; then
    echo "Display succeeded, but ACK failed" >&2
    exit 1
fi

printf '%s\n' "$frame_id" > "$WORK_DIR/current-frame-id"
printf '%s\n' "$next_check_seconds" > "$WORK_DIR/next-check-seconds"
echo "Displayed frame $frame_id; next check in $next_check_seconds seconds"
