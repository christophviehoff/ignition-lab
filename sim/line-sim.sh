#!/bin/sh
# Simulates three machines on a line, each as its own MQTT client that
# holds one connection open, the way a real edge device behaves.
#
# Each machine gets:
#   a stable client ID          lab-line1-mixer, and so on
#   one persistent connection   visible on the EMQX Clients page
#   a birth certificate         retained "online" on its status topic
#   a last will and testament   retained "offline", published by the
#                               broker if the connection drops badly
#
# Topics (with MQTT_BASE_TOPIC=lab/line1):
#   lab/line1/mixer          JSON  temp, pressure, speed, running
#   lab/line1/filler         JSON  fill volume, rejects, running
#   lab/line1/capper         JSON  torque, speed, running
#   lab/line1/<machine>/status  online | offline, retained
#   lab/line1/status            line level heartbeat, retained
#
# This file must keep Unix (LF) line endings. If your editor saves CRLF
# the container exits immediately with a "not found" error.

set -u

HOST="${MQTT_HOST:-emqx}"
PORT="${MQTT_PORT:-1883}"
BASE="${MQTT_BASE_TOPIC:-lab/line1}"
INTERVAL="${SIM_INTERVAL:-2}"
KEEPALIVE="${MQTT_KEEPALIVE:-15}"

# Client IDs must be unique on a broker. Derive them from the topic so
# two copies of this lab do not fight over the same ID.
PREFIX="$(echo "$BASE" | tr '/' '-')"

MACHINES="mixer filler capper"
RUNDIR="/tmp/line-sim"
rm -rf "$RUNDIR"
mkdir -p "$RUNDIR"

log() { echo "line-sim: $*"; }

log "broker ${HOST}:${PORT}, base ${BASE}, interval ${INTERVAL}s, keepalive ${KEEPALIVE}s"

# ---------------------------------------------------------------------
# Wait for the broker
# ---------------------------------------------------------------------
until mosquitto_pub -h "$HOST" -p "$PORT" -t "${BASE}/status" -m "starting" >/dev/null 2>&1; do
    log "broker not ready, retrying in 3s"
    sleep 3
done
log "broker reachable"

# ---------------------------------------------------------------------
# Shut down tidily. A clean stop publishes "offline" itself, so you only
# see the broker's will fire when the container is killed rather than
# stopped, which is the interesting case.
# ---------------------------------------------------------------------
cleanup() {
    log "stopping, publishing offline for each machine"
    for m in $MACHINES; do
        mosquitto_pub -h "$HOST" -p "$PORT" \
            -t "${BASE}/${m}/status" -m "offline" -q 1 -r >/dev/null 2>&1
    done
    mosquitto_pub -h "$HOST" -p "$PORT" \
        -t "${BASE}/status" -m "offline" -q 1 -r >/dev/null 2>&1
    exec 3>&- 2>/dev/null || true
    exec 4>&- 2>/dev/null || true
    exec 5>&- 2>/dev/null || true
    [ -f "$RUNDIR/pids" ] && kill $(cat "$RUNDIR/pids") 2>/dev/null
    exit 0
}
trap cleanup INT TERM

# ---------------------------------------------------------------------
# One long lived publisher per machine, fed through a named pipe.
# mosquitto_pub -l reads stdin and publishes each line as a message,
# keeping the connection open between them.
# ---------------------------------------------------------------------
: > "$RUNDIR/pids"
for m in $MACHINES; do
    mkfifo "$RUNDIR/$m.fifo"
    mosquitto_pub \
        -h "$HOST" -p "$PORT" \
        -i "${PREFIX}-${m}" \
        -t "${BASE}/${m}" \
        -q 1 \
        -k "$KEEPALIVE" \
        --will-topic "${BASE}/${m}/status" \
        --will-payload "offline" \
        --will-qos 1 \
        --will-retain \
        -l < "$RUNDIR/$m.fifo" &
    echo "$!" >> "$RUNDIR/pids"
done

# Opening the write end blocks until the reader is there, which is the
# handshake that tells us each publisher actually started.
exec 3> "$RUNDIR/mixer.fifo"
exec 4> "$RUNDIR/filler.fifo"
exec 5> "$RUNDIR/capper.fifo"
log "three publishers connected"

# ---------------------------------------------------------------------
# Birth certificates
# ---------------------------------------------------------------------
for m in $MACHINES; do
    mosquitto_pub -h "$HOST" -p "$PORT" \
        -t "${BASE}/${m}/status" -m "online" -q 1 -r
done
mosquitto_pub -h "$HOST" -p "$PORT" -t "${BASE}/status" -m "online" -q 1 -r
log "birth certificates published"

# ---------------------------------------------------------------------
# Publish loop
# ---------------------------------------------------------------------
SEQ=0
REJECTS=0

while true; do
    SEQ=$((SEQ + 1))

    # busybox awk has no $RANDOM, so seed from the pid and the counter.
    awk -v c="$SEQ" -v s="$$" 'BEGIN {
        srand(s + c * 7919);
        temp  = 60 + rand() * 9;
        press = 1.7 + rand() * 0.7;
        speed = 115 + rand() * 12;
        run   = (rand() > 0.05) ? "true" : "false";
        if (run == "false") speed = 0;
        printf "{\"seq\":%d,\"temp_c\":%.2f,\"pressure_bar\":%.3f,\"speed_rpm\":%.1f,\"running\":%s}\n", c, temp, press, speed, run;
    }' >&3

    awk -v c="$SEQ" -v s="$$" -v r="$REJECTS" 'BEGIN {
        srand(s + c * 104729);
        vol = 498 + rand() * 5;
        run = (rand() > 0.04) ? "true" : "false";
        printf "{\"seq\":%d,\"fill_ml\":%.2f,\"rejects\":%d,\"running\":%s}\n", c, vol, r, run;
    }' >&4

    awk -v c="$SEQ" -v s="$$" 'BEGIN {
        srand(s + c * 15485863);
        torque = 1.05 + rand() * 0.25;
        speed  = 290 + rand() * 20;
        run    = (rand() > 0.04) ? "true" : "false";
        if (run == "false") speed = 0;
        printf "{\"seq\":%d,\"torque_nm\":%.3f,\"speed_rpm\":%.1f,\"running\":%s}\n", c, torque, speed, run;
    }' >&5

    if [ $((SEQ % 17)) -eq 0 ]; then
        REJECTS=$((REJECTS + 1))
    fi

    # If a publisher died, exit so Docker restarts the whole thing
    # rather than leaving us publishing into a dead pipe.
    for p in $(cat "$RUNDIR/pids"); do
        if ! kill -0 "$p" 2>/dev/null; then
            log "publisher $p died, exiting so the container restarts"
            exit 1
        fi
    done

    sleep "$INTERVAL"
done
