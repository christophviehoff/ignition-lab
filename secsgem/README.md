# SECS/GEM add-on for the Ignition lab

Built on the open source `secsgem` 0.3.0 library (LGPL).

## Layout
Put this folder next to your main `docker-compose.yml` as `./secsgem`, and put
`docker-compose.secsgem.yml` beside `docker-compose.yml`.

## Run
    docker compose -f docker-compose.yml -f docker-compose.secsgem.yml up -d --build
    docker logs -f secsgem-bridge

## What you get
* `secsgem-equipment` simulated etch tool, HSMS passive on port 5000
* `secsgem-bridge` GEM host that polls the tool and publishes to EMQX
* `secsgem-equipment-ign` a second tool on port 5001 for Ignition's SECS/GEM module

## IDs
| Type | ID | Name |
|---|---|---|
| SV | 2101 | ChamberPressure (F4, mTorr) |
| SV | 2102 | ChamberTemp (F4, degC) |
| SV | 2103 | RFPower (F4, W) |
| SV | 2104 | ProcessState (A) |
| SV | 2105 | WaferCount (U4) |
| SV | 2106 | Recipe (A) |
| DV | 2001, 2002 | LotID, WaferID |
| CE | 3001, 3002, 3003 | WaferStart, WaferEnd, RecipeSelected |
| CE | 3101, 3102 | OverTemp set, clear |
| ALID | 5001 | OverTemp (above 80 degC) |
| RCMD | START, STOP, PP_SELECT(PPID) | |

## MQTT topics (prefix `fab/etch01`)
* `sv/<Name>` retained values, `{"ts": ..., "value": ...}`
* `event/WaferStart`, `event/WaferEnd` with LotID and WaferID
* `alarm` retained, `status` online flag with last will
* publish to `cmd` to send a remote command, reply on `cmd/ack`

      {"rcmd": "STOP"}
      {"rcmd": "PP_SELECT", "params": {"PPID": "ETCH_NIT_90S"}}

HCACK 4 means accepted and finishing later, which is the normal reply.

## Ignition
In the gateway, under SECS/GEM equipment connections, add an active
connection to host `secsgem-equipment-ign`, port 5001, device ID 0.
The MQTT topics also land in Ignition through the MQTT Engine module if you use it.
