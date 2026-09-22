"""
Sparkplug B edge node simulator.

Publishes a generic production line as one edge node with one device:

    spBv1.0/<GROUP>/NBIRTH/<NODE>
    spBv1.0/<GROUP>/DBIRTH/<NODE>/<DEVICE>
    spBv1.0/<GROUP>/DDATA/<NODE>/<DEVICE>
    spBv1.0/<GROUP>/NDEATH/<NODE>      (registered as the MQTT will)

Ignition MQTT Engine turns this into a tag folder under
MQTT Engine / Edge Nodes / <GROUP> / <NODE> / <DEVICE>.
"""

import math
import os
import random
import signal
import sys
import time

import paho.mqtt.client as mqtt

import sparkplug_b_pb2 as sp


# ---------------------------------------------------------------- config

BROKER_HOST = os.getenv("MQTT_HOST", "ignition-emqx")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME", "")
MQTT_PASS = os.getenv("MQTT_PASSWORD", "")

GROUP_ID = os.getenv("SP_GROUP_ID", "Lab")
NODE_ID = os.getenv("SP_NODE_ID", "Line1")
DEVICE_ID = os.getenv("SP_DEVICE_ID", "Packer")

INTERVAL = float(os.getenv("SIM_INTERVAL", "2"))
DEADBAND = float(os.getenv("SIM_DEADBAND", "0.5"))  # percent of span

NS = "spBv1.0"


# ------------------------------------------------------- datatype codes

INT32 = 3
INT64 = 4
UINT64 = 8
FLOAT = 9
BOOLEAN = 11
STRING = 12


def now_ms():
    return int(time.time() * 1000)


def set_value(metric, datatype, value):
    """Place a Python value into the right protobuf field for its datatype."""
    metric.datatype = datatype
    if value is None:
        metric.is_null = True
    elif datatype == INT32:
        metric.int_value = int(value) & 0xFFFFFFFF
    elif datatype in (INT64, UINT64):
        metric.long_value = int(value)
    elif datatype == FLOAT:
        metric.float_value = float(value)
    elif datatype == BOOLEAN:
        metric.boolean_value = bool(value)
    elif datatype == STRING:
        metric.string_value = str(value)
    else:
        raise ValueError(f"unhandled datatype {datatype}")


# ------------------------------------------------------------ the model

class Tag:
    """One simulated metric, with an alias and a report-by-exception check."""

    def __init__(self, name, datatype, alias, span=100.0):
        self.name = name
        self.datatype = datatype
        self.alias = alias
        self.span = span
        self.value = None
        self.reported = None

    def changed(self):
        if self.reported is None:
            return True
        if self.datatype in (BOOLEAN, STRING, INT32, INT64, UINT64):
            return self.value != self.reported
        return abs(self.value - self.reported) >= self.span * DEADBAND / 100.0


class Line:
    """A generic production line. Swap the tag list to model your own gear."""

    def __init__(self):
        self.t0 = time.time()
        self.count = 0
        self.running = True
        self.tags = [
            Tag("Line/Running", BOOLEAN, 1),
            Tag("Line/Mode", STRING, 2),
            Tag("Line/Speed", FLOAT, 3, span=120.0),
            Tag("Line/Motor Current", FLOAT, 4, span=40.0),
            Tag("Line/Motor Temp", FLOAT, 5, span=100.0),
            Tag("Line/Part Count", INT64, 6),
            Tag("Line/Fault Code", INT32, 7),
        ]
        self.by_name = {t.name: t for t in self.tags}
        self.step()

    def step(self):
        """Advance one scan. Roughly 5 percent of scans go into a fault."""
        t = time.time() - self.t0

        if self.running and random.random() < 0.01:
            self.running = False
            self.fault = random.choice([101, 204, 310])
        elif not self.running and random.random() < 0.25:
            self.running = True
            self.fault = 0
        if not hasattr(self, "fault"):
            self.fault = 0

        if self.running:
            speed = 85.0 + 8.0 * math.sin(t / 30.0) + random.uniform(-1.5, 1.5)
            current = 18.0 + speed * 0.06 + random.uniform(-0.4, 0.4)
            self.count += max(0, int(speed / 60.0 * INTERVAL))
        else:
            speed = 0.0
            current = 0.8 + random.uniform(-0.1, 0.1)

        temp = 42.0 + current * 0.9 + 4.0 * math.sin(t / 240.0)

        self.by_name["Line/Running"].value = self.running
        self.by_name["Line/Mode"].value = "Auto" if self.running else "Faulted"
        self.by_name["Line/Speed"].value = round(speed, 2)
        self.by_name["Line/Motor Current"].value = round(current, 2)
        self.by_name["Line/Motor Temp"].value = round(temp, 2)
        self.by_name["Line/Part Count"].value = self.count
        self.by_name["Line/Fault Code"].value = self.fault


# ------------------------------------------------------------ the node

class EdgeNode:
    def __init__(self):
        self.line = Line()
        self.seq = 0
        self.bd_seq = 0
        self.born = False
        self.stop = False

        client_id = f"{NODE_ID}-{DEVICE_ID}-{os.getpid()}"
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            client_id=client_id,
            clean_session=True,
        )
        if MQTT_USER:
            self.client.username_pw_set(MQTT_USER, MQTT_PASS)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

    # -- sequence numbers ------------------------------------------------

    def next_seq(self):
        s = self.seq
        self.seq = (self.seq + 1) % 256
        return s

    # -- payload builders ------------------------------------------------

    def payload(self, seq=None):
        p = sp.Payload()
        p.timestamp = now_ms()
        if seq is not None:
            p.seq = seq
        return p

    def nbirth(self):
        p = self.payload(seq=self.next_seq())

        m = p.metrics.add()
        m.name = "bdSeq"
        m.timestamp = now_ms()
        set_value(m, UINT64, self.bd_seq)

        m = p.metrics.add()
        m.name = "Node Control/Rebirth"
        m.timestamp = now_ms()
        set_value(m, BOOLEAN, False)

        return p.SerializeToString()

    def ndeath(self):
        p = sp.Payload()
        m = p.metrics.add()
        m.name = "bdSeq"
        m.timestamp = now_ms()
        set_value(m, UINT64, self.bd_seq)
        return p.SerializeToString()

    def dbirth(self):
        """Every metric the device will ever publish must appear here."""
        self.line.step()
        p = self.payload(seq=self.next_seq())
        for tag in self.line.tags:
            m = p.metrics.add()
            m.name = tag.name
            m.alias = tag.alias
            m.timestamp = now_ms()
            set_value(m, tag.datatype, tag.value)
            tag.reported = tag.value
        return p.SerializeToString()

    def ddata(self):
        """Report by exception. Returns None when nothing moved enough."""
        self.line.step()
        changed = [t for t in self.line.tags if t.changed()]
        if not changed:
            return None
        p = self.payload(seq=self.next_seq())
        for tag in changed:
            m = p.metrics.add()
            m.alias = tag.alias  # name omitted after birth, alias is enough
            m.timestamp = now_ms()
            set_value(m, tag.datatype, tag.value)
            tag.reported = tag.value
        return p.SerializeToString()

    # -- topics ----------------------------------------------------------

    def topic(self, verb, device=False):
        base = f"{NS}/{GROUP_ID}/{verb}/{NODE_ID}"
        return f"{base}/{DEVICE_ID}" if device else base

    # -- callbacks -------------------------------------------------------

    def on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            print(f"connect failed, rc={rc}", flush=True)
            return
        print(f"connected to {BROKER_HOST}:{BROKER_PORT}", flush=True)
        self.seq = 0
        client.publish(self.topic("NBIRTH"), self.nbirth(), qos=0, retain=False)
        client.publish(
            self.topic("DBIRTH", device=True), self.dbirth(), qos=0, retain=False
        )
        client.subscribe(f"{NS}/{GROUP_ID}/NCMD/{NODE_ID}", qos=1)
        client.subscribe(f"{NS}/{GROUP_ID}/DCMD/{NODE_ID}/{DEVICE_ID}", qos=1)
        self.born = True
        print(
            f"born as {GROUP_ID}/{NODE_ID}/{DEVICE_ID}, "
            f"{len(self.line.tags)} metrics",
            flush=True,
        )

    def on_message(self, client, userdata, msg):
        """Engine sends Node Control/Rebirth when it sees an unknown metric."""
        p = sp.Payload()
        p.ParseFromString(msg.payload)
        for m in p.metrics:
            if m.name == "Node Control/Rebirth" and m.boolean_value:
                print("rebirth requested", flush=True)
                self.rebirth()

    def on_disconnect(self, client, userdata, rc):
        self.born = False
        if rc != 0:
            print(f"unexpected disconnect, rc={rc}", flush=True)

    # -- lifecycle -------------------------------------------------------

    def rebirth(self):
        self.seq = 0
        for tag in self.line.tags:
            tag.reported = None
        self.client.publish(self.topic("NBIRTH"), self.nbirth(), qos=0)
        self.client.publish(self.topic("DBIRTH", device=True), self.dbirth(), qos=0)

    def shutdown(self, *_):
        print("shutting down", flush=True)
        self.stop = True

    def run(self):
        signal.signal(signal.SIGTERM, self.shutdown)
        signal.signal(signal.SIGINT, self.shutdown)

        self.client.will_set(
            self.topic("NDEATH"), self.ndeath(), qos=1, retain=False
        )
        self.client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
        self.client.loop_start()

        while not self.stop:
            time.sleep(INTERVAL)
            if not self.born:
                continue
            data = self.ddata()
            if data is not None:
                self.client.publish(
                    self.topic("DDATA", device=True), data, qos=0, retain=False
                )

        if self.born:
            self.client.publish(
                self.topic("DDEATH", device=True),
                self.payload(seq=self.next_seq()).SerializeToString(),
                qos=1,
            )
            self.client.publish(self.topic("NDEATH"), self.ndeath(), qos=1)
            time.sleep(0.3)
        self.client.loop_stop()
        self.client.disconnect()


def main():
    node = EdgeNode()
    while True:
        try:
            node.run()
            return 0
        except (ConnectionRefusedError, OSError) as exc:
            if node.stop:
                return 0
            print(f"broker unreachable ({exc}), retry in 5 s", flush=True)
            node.bd_seq = (node.bd_seq + 1) % 256
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
