# Third party modules

Ignition has no built in MQTT client. The Cirrus Link modules add one.
They are a free download and run in the same two hour trial as the
gateway.

## Direct downloads (v5.0.4, for Ignition 8.3)

| Module | Link | Size |
| --- | --- | --- |
| MQTT Engine | https://releases.inductiveautomation.com/third-party/cirrus-link/5.0.4/MQTT-Engine-signed.modl | 52.1 MB |
| MQTT Transmission | https://releases.inductiveautomation.com/third-party/cirrus-link/5.0.4/MQTT-Transmission-signed.modl | 42.6 MB |
| MQTT Distributor | https://releases.inductiveautomation.com/third-party/cirrus-link/5.0.4/MQTT-Distributor-signed.modl | 43.0 MB |
| MQTT Recorder | https://releases.inductiveautomation.com/third-party/cirrus-link/5.0.4/MQTT-Recorder-signed.modl | 33.3 MB |

For this lab you only need MQTT Engine. It subscribes the gateway to a
broker and turns payloads into tags. Add Transmission only if you also
want to publish gateway tags outward. Distributor is a broker, which you
do not need because EMQX is already in the stack.

All Cirrus Link module versions must match each other. If you install
two, install both at 5.0.4.

The landing page, if you would rather pick versions yourself, is
https://inductiveautomation.com/downloads/third-party-modules with the
Ignition version selector set to 8.3.

## Install

Save the `.modl` files into this folder, keeping the names above, then
start the stack with the overlay:

```
docker compose -f docker-compose.yml -f compose.mqtt-modules.yml up -d
```

Verified against the downloads page on 20 September 2026, showing
Ignition 8.3.9 and Cirrus Link 5.0.4.
