"""Dry vacuum pump simulator. Publishes each pump to MQTT as fab/<tool>/pump/<id>/<Metric>.

Payloads match the SECS/GEM bridge: {"ts": ..., "value": ...}, retained.
Commands arrive on fab/<tool>/pump/<id>/cmd as JSON:
  {"cmd": "start" | "stop" | "reset"}
  {"fault": "wear" | "cooling" | "trip" | "clear"}
The process pump follows the etch tool: more gas load while it is PROCESSING.
"""
import json
import logging
import os
import random
import time

import paho.mqtt.client as mqtt

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s: %(message)s")
log = logging.getLogger("pumps")

TOOL = os.getenv("TOOL_ID", "etch01")
INTERVAL = float(os.getenv("SIM_INTERVAL", "2"))
HOURS_PER_MIN = float(os.getenv("RUN_HOURS_PER_MINUTE", "1"))  # accelerated run hours

# id, role, rated speed Hz, base current A, trip current A, base power kW, base inlet mTorr, start run hours
PUMPS = [
    ("PP1", "process", 100.0, 7.0, 13.5, 3.2, 35.0, 18500.0),
    ("LL1", "loadlock", 80.0, 4.0, 7.5, 1.6, 50.0, 9000.0),
    ("TM1", "transfer", 80.0, 4.2, 7.5, 1.7, 20.0, 19990.0),
]


class Pump:
    def __init__(self, pid, role, speed, amps, trip_amps, kw, inlet, hours):
        self.id, self.role, self.trip_amps = pid, role, trip_amps
        self.rated_speed, self.base_amps, self.base_kw, self.base_inlet = speed, amps, kw, inlet
        self.hours = hours
        self.running, self.tripped = True, False
        self.speed = speed
        self.temp = 60.0
        self.wear = 0.0          # extra amps from bearing wear
        self.wearing = False
        self.cooling_fault = False

    def command(self, msg):
        cmd, fault = msg.get("cmd"), msg.get("fault")
        if cmd == "start" and not self.tripped:
            self.running = True
        elif cmd == "stop":
            self.running = False
        elif cmd == "reset":
            self.tripped, self.wear, self.wearing, self.cooling_fault = False, 0.0, False, False
            self.temp = min(self.temp, 70.0)
        if fault == "wear":
            self.wearing = True
        elif fault == "cooling":
            self.cooling_fault = True
        elif fault == "trip":
            self.trip("manual trip")
        elif fault == "clear":
            self.wearing, self.cooling_fault = False, False
        log.info("%s command %s", self.id, msg)

    def trip(self, why):
        if not self.tripped:
            log.warning("%s TRIPPED: %s", self.id, why)
        self.tripped, self.running = True, False

    def step(self, tool_processing, dt):
        on = self.running and not self.tripped
        # speed ramps toward target
        target = self.rated_speed if on else 0.0
        self.speed += (target - self.speed) * min(1.0, dt / 6.0)
        frac = self.speed / self.rated_speed

        load = 1.0
        if self.role == "process" and tool_processing:
            load = 1.35
        if self.wearing:
            self.wear += 0.04 * dt / 2.0   # about 1.2 A per minute
        amps = (self.base_amps * load + self.wear) * frac + random.gauss(0, 0.08) * frac
        kw = (self.base_kw * load + self.wear * 0.4) * frac + random.gauss(0, 0.03) * frac

        flow = 0.0 if not on else (0.9 if self.cooling_fault else 3.6) + random.gauss(0, 0.05)
        # body temperature: heat from power, removed by cooling water
        heat_target = 35.0 + 25.0 * kw / max(self.base_kw, 0.1) + (25.0 if self.cooling_fault else 0.0) + self.wear * 3.0
        if not on:
            heat_target = 25.0
        self.temp += (heat_target - self.temp) * min(1.0, dt / 40.0)

        if on:
            self.hours += HOURS_PER_MIN * dt / 60.0
            if self.temp > 95.0:
                self.trip("body temperature %.1f" % self.temp)
            if amps > self.trip_amps:
                self.trip("motor current %.1f" % amps)

        inlet = self.base_inlet * (1.4 if (self.role == "process" and tool_processing) else 1.0) if on else 760000.0
        state = "TRIPPED" if self.tripped else ("RUNNING" if on else "STOPPED")
        return {
            "State": state,
            "Running": on,
            "Speed": round(max(self.speed, 0.0), 1),
            "MotorCurrent": round(max(amps, 0.0), 2),
            "MotorPower": round(max(kw, 0.0), 2),
            "InletPressure": round(inlet * (1 + random.gauss(0, 0.02)), 1),
            "ExhaustPressure": round(1013.0 + (15.0 if on else 0.0) + random.gauss(0, 1.0), 1),
            "BodyTemp": round(self.temp + random.gauss(0, 0.2), 1),
            "N2Purge": round((40.0 if on else 0.0) + random.gauss(0, 0.3) * (1 if on else 0), 1),
            "CoolingFlow": round(max(flow, 0.0), 2),
            "RunHours": round(self.hours, 1),
        }


def main():
    pumps = {p[0]: Pump(*p) for p in PUMPS}
    state = {"processing": False}
    base = f"fab/{TOOL}"

    mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pump-sim-{TOOL}")
    if os.getenv("MQTT_USER"):
        mq.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASS", ""))

    def on_connect(client, *_):
        client.subscribe(f"{base}/pump/+/cmd", qos=1)
        client.subscribe(f"{base}/sv/ProcessState", qos=0)
        log.info("connected, simulating %s", ", ".join(pumps))

    def on_message(_c, _u, msg):
        try:
            data = json.loads(msg.payload or b"{}")
        except ValueError:
            log.error("bad JSON on %s", msg.topic)
            return
        if msg.topic.endswith("/sv/ProcessState"):
            state["processing"] = data.get("value") == "PROCESSING"
            return
        pid = msg.topic.split("/")[-2]
        if pid in pumps:
            pumps[pid].command(data)

    mq.on_connect = on_connect
    mq.on_message = on_message
    mq.connect_async(os.getenv("MQTT_HOST", "emqx"), int(os.getenv("MQTT_PORT", "1883")))
    mq.loop_start()

    last = time.time()
    while True:
        time.sleep(INTERVAL)
        now = time.time()
        dt, last = now - last, now
        for pid, pump in pumps.items():
            for name, value in pump.step(state["processing"], dt).items():
                mq.publish(f"{base}/pump/{pid}/{name}", json.dumps({"ts": now, "value": value}), qos=0, retain=True)


if __name__ == "__main__":
    main()
