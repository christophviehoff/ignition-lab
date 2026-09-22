"""SECS/GEM host that polls the tool and publishes to MQTT (EMQX)."""
import json
import logging
import os
import time

import paho.mqtt.client as mqtt
import secsgem.common
import secsgem.gem
import secsgem.hsms

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(name)s: %(message)s")
logging.getLogger("communication").setLevel(os.getenv("SECS_LOG_LEVEL", "WARNING"))
log = logging.getLogger("bridge")

TOOL = os.getenv("TOOL_ID", "etch01")
BASE = f"fab/{TOOL}"
SVIDS = {2101: "ChamberPressure", 2102: "ChamberTemp", 2103: "RFPower",
         2104: "ProcessState", 2105: "WaferCount", 2106: "Recipe"}
CE_NAMES = {3001: "WaferStart", 3002: "WaferEnd"}
POLL = float(os.getenv("POLL_SECONDS", "2"))


def to_py(value):
    return value.get() if hasattr(value, "get") else value


class Bridge(secsgem.gem.GemHostHandler):
    def __init__(self, settings, mq):
        super().__init__(settings)
        self.mq = mq
        self.events.collection_event_received += self.on_ce
        self.events.alarm_received += self.on_alarm

    def publish(self, topic, payload, retain=False):
        self.mq.publish(f"{BASE}/{topic}", json.dumps(payload), qos=1, retain=retain)

    def on_ce(self, data):
        ceid = to_py(data["ceid"])
        values = {str(x["dvid"]): to_py(x["value"]) for x in data["values"]}
        log.info("CE %s %s", ceid, values)
        self.publish(f"event/{CE_NAMES.get(ceid, ceid)}", {"ts": time.time(), "ceid": ceid, "data": values})

    def on_alarm(self, data):
        code = to_py(data["code"])
        payload = {"ts": time.time(), "alid": to_py(data["alid"]),
                   "set": bool(code & 128), "text": to_py(data["text"])}
        log.warning("Alarm %s", payload)
        self.publish("alarm", payload, retain=True)

    def setup(self):
        self.clear_collection_events()
        for ceid in CE_NAMES:
            self.subscribe_collection_event(ceid, [2001, 2002])
        for alid in (5001,):
            self.enable_alarm(alid)

    def poll_svs(self):
        rsp = self.send_and_waitfor_response(self.stream_function(1, 3)(list(SVIDS)))
        if rsp is None:
            return
        values = self.settings.streams_functions.decode(rsp).get()
        for svid, val in zip(SVIDS, values):
            if isinstance(val, float):
                val = round(val, 3)
            self.publish(f"sv/{SVIDS[svid]}", {"ts": time.time(), "value": val}, retain=True)

    def on_command(self, _client, _userdata, msg):
        try:
            cmd = json.loads(msg.payload or b"{}")
            rcmd = cmd.get("rcmd", "").upper()
            params = [[k, str(v)] for k, v in cmd.get("params", {}).items()]
            log.info("RCMD %s %s", rcmd, params)
            rsp = self.send_and_waitfor_response(
                self.stream_function(2, 41)({"RCMD": rcmd, "PARAMS": [
                    {"CPNAME": k, "CPVAL": v} for k, v in params]}))
            ack = self.settings.streams_functions.decode(rsp).HCACK.get() if rsp else None
            self.publish("cmd/ack", {"rcmd": rcmd, "hcack": ack})
        except Exception as exc:
            log.error("command failed: %s", exc)


def main():
    mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"secsgem-{TOOL}")
    if os.getenv("MQTT_USER"):
        mq.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASS", ""))
    mq.will_set(f"{BASE}/status", json.dumps({"online": False}), qos=1, retain=True)
    mq.connect_async(os.getenv("MQTT_HOST", "emqx"), int(os.getenv("MQTT_PORT", "1883")))
    mq.loop_start()

    settings = secsgem.hsms.HsmsSettings(
        address=os.getenv("EQUIPMENT_HOST", "secsgem-equipment"),
        port=int(os.getenv("HSMS_PORT", "5000")),
        connect_mode=secsgem.hsms.HsmsConnectMode.ACTIVE,
        device_type=secsgem.common.DeviceType.HOST,
        session_id=int(os.getenv("SESSION_ID", "0")),
    )
    host = Bridge(settings, mq)
    mq.on_connect = lambda c, *_: c.subscribe(f"{BASE}/cmd", qos=1)
    mq.message_callback_add(f"{BASE}/cmd", host.on_command)
    host.enable()

    while True:
        if not host.waitfor_communicating(10):
            log.info("Waiting for equipment...")
            host.publish("status", {"online": False}, retain=True)
            continue
        try:
            host.setup()
            host.publish("status", {"online": True}, retain=True)
            log.info("Communicating, polling every %ss", POLL)
            while host.communication_state.current.name == "COMMUNICATING":
                host.poll_svs()
                time.sleep(POLL)
        except Exception as exc:
            log.error("link error: %s", exc)
            time.sleep(3)


if __name__ == "__main__":
    main()
