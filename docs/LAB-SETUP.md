# Ignition IT/OT lab

A single command brings up an Ignition gateway with a database, an MQTT
broker, and two device simulators feeding it live data. Everything runs
in Docker on one machine and tears down cleanly.

## What is in it

| Service | Image | Reach it at | Why it is here |
| --- | --- | --- | --- |
| `ignition` | `inductiveautomation/ignition:8.3.9` | http://localhost:8088 | The gateway |
| `postgres` | `postgres:17` | `localhost:5432` | Tag history and SQL queries |
| `emqx` | `emqx/emqx:6.2` | http://localhost:18083 | MQTT broker with a dashboard |
| `opc-plc` | `mcr.microsoft.com/iotedge/opc-plc:2.15.5` | `opc.tcp://opc-plc:50000` | An OPC UA server to browse |
| `line-sim` | `eclipse-mosquitto:2` | publishes to `lab/line1/*` | Fake line data on MQTT |

## Start it

You need Docker Desktop running. From this folder:

```
docker compose up -d
```

First run pulls about 2 GB and the gateway takes a minute or two to
finish commissioning. Watch it come up with:

```
docker compose logs -f ignition
```

When the log settles, open http://localhost:8088 and sign in with the
credentials from `.env`, which start as `admin` and `labpassword1`.

To stop everything but keep your work:

```
docker compose stop
```

To throw it all away, gateway config included, and start clean:

```
docker compose down -v
```

## Licensing

The gateway runs in trial mode. It works fully for two hours, then the
gateway stops passing data until you reset the trial from the banner in
the web UI. Resetting is one click and there is no limit on resets. Your
projects and configuration are untouched by the timer.

If you would rather avoid the timer, get a free Maker Edition license
from Inductive Automation, then add these two lines to `.env` and to the
`ignition` environment block:

```
IGNITION_EDITION=MAKER
IGNITION_LICENSE_KEY=your-key
IGNITION_ACTIVATION_TOKEN=your-token
```

Maker is free for personal, non commercial use, which is what this lab
is. It includes Perspective and the historian, which is most of what you
would want to practice on.

## Connect Ignition to the database

The containers talk to each other by service name on a private network,
so the host is `postgres`, not `localhost`.

In the gateway, go to Config, then Databases, then Connections, and
create a new PostgreSQL connection:

| Field | Value |
| --- | --- |
| Name | `postgres` |
| Connect URL | `jdbc:postgresql://postgres:5432/ignition` |
| Username | `ignition` |
| Password | `ignition` |

The PostgreSQL JDBC driver ships with Ignition, so there is nothing to
install. Save it and the status should go to Valid within a few seconds.

The database already has a `lab` schema with a `machine_state` table and
a `downtime_reason` lookup, seeded with a handful of rows. Try a named
query against it before you wire up anything real:

```sql
SELECT machine, state, temp_c, speed_rpm, recorded_at
FROM lab.machine_state
ORDER BY recorded_at DESC
LIMIT 20;
```

If you want to poke at the database directly:

```
docker compose exec postgres psql -U ignition -d ignition
```

## Connect Ignition to the OPC UA simulator

Go to Config, then OPC Client, then OPC Connections, and add an OPC UA
connection with this endpoint:

```
opc.tcp://opc-plc:50000
```

Choose the `None` security policy and anonymous authentication. The
simulator is started with `--autoaccept` and `--unsecuretransport` so it
will take the connection without a certificate exchange.

Once it is connected, browse it in the OPC Browser. You get fast nodes
that change every second, slow nodes that change every ten seconds, and
a few others. Drag some into a tag provider and you have live tags.

If the connection fails with a complaint about the endpoint URL, the
simulator is advertising a hostname Ignition cannot resolve. Uncomment
the `--ph=opc-plc` line in `docker-compose.yml` and run
`docker compose up -d opc-plc`.

## Look at the MQTT traffic

The EMQX dashboard is at http://localhost:18083. Sign in with `admin`
and the password from `.env`, which starts as `labpassword1`. EMQX may
ask you to change it on first login.

Under Diagnose, then WebSocket, subscribe to `lab/line1/#` and you will
see the simulator publishing every two seconds. Payloads look like:

```json
{"seq":412,"temp_c":64.18,"pressure_bar":2.031,"speed_rpm":121.4,"running":true}
```

### Birth and death certificates

Each machine is its own MQTT client holding one connection open, with a
stable client ID like `lab-line1-mixer`. You will see all three on the
Clients page.

On startup each one publishes a retained `online` to its own status
topic, which is its birth certificate. Each also registers a last will
with the broker, so if the connection dies without a clean disconnect
the broker publishes a retained `offline` on that same topic on the
client's behalf.

```
lab/line1/mixer/status     online | offline, retained
lab/line1/filler/status    online | offline, retained
lab/line1/capper/status    online | offline, retained
lab/line1/status           line level heartbeat, retained
```

Subscribe to `lab/line1/+/status` and then kill the simulator the hard
way to watch it happen:

```
docker kill ignition-line-sim
```

Three `offline` messages appear within a second or two, published by the
broker, not by the dead container. That is the mechanism behind every
"device offline" indicator in a real MQTT architecture, and it is why
a subscriber can know a machine died rather than just going quiet.
Because the messages are retained, a subscriber connecting an hour later
still learns the machine is down.

A clean `docker compose stop line-sim` publishes `offline` itself before
disconnecting, so the will never fires. The difference between the two
is worth seeing.

You can also subscribe from the command line:

```
docker compose exec emqx emqx ctl listeners
docker run --rm --network ignition-lab eclipse-mosquitto:2 \
  mosquitto_sub -h emqx -t 'lab/line1/#' -v
```

Anonymous connections are allowed because no authenticator is
configured. That is fine for a lab and wrong for anything else, so if
you want to practice locking it down, add a password based authenticator
in the dashboard under Access Control.

## Getting MQTT into Ignition

This is the one piece that needs a manual download. Ignition has no
built in MQTT client. The Cirrus Link modules fill that gap and they are
a free download, but they are not part of the Ignition image.

Download MQTT Engine, currently v5.0.4 for Ignition 8.3:

```
https://releases.inductiveautomation.com/third-party/cirrus-link/5.0.4/MQTT-Engine-signed.modl
```

Save it into the `modules/` folder without renaming it, then start the
stack with the overlay:

```
docker compose -f docker-compose.yml -f compose.mqtt-modules.yml up -d
```

MQTT Engine appears under Config, then MQTT Engine, then Settings. Point
it at server `tcp://emqx:1883` and it will start turning payloads into
tags under a new tag provider.

Worth knowing: MQTT Engine expects Sparkplug B by default. The simulator
publishes plain JSON, so set the namespace to a custom one and configure
the JSON parsing, or switch the simulator to Sparkplug if you want to
learn that specifically. Plain JSON is the more common thing to meet in
the field.

## Changing ports and passwords

Everything adjustable lives in `.env`. If port 8088 or 5432 is already
taken on your machine, change the host side there and run
`docker compose up -d` again. The container side ports never change, so
the service names and internal ports in the connection strings above
stay the same no matter what you do to the host ports.

## Where your work lives

Gateway configuration, projects, and tags live in the `ignition-data`
Docker volume, not in this folder. That means your projects survive
`docker compose down` but not `docker compose down -v`.

Back up properly from the gateway itself, under Config, then Backup and
Restore. That gives you a `.gwbk` you can restore anywhere, which is the
file you would hand to someone else or commit alongside this repo.

## Troubleshooting

**Ignition container restarts in a loop.** Check the logs with
`docker compose logs ignition`. The usual cause is a memory setting
higher than Docker Desktop is allowed to use. Lower `IGNITION_MAX_MEMORY`
in `.env` or raise the Docker Desktop memory limit.

**line-sim exits immediately with a "not found" error.** The script got
saved with Windows line endings. Convert `sim/line-sim.sh` back to LF.
The included `.gitattributes` prevents this once the folder is in git.

**Database connection shows Faulted.** Check that you used `postgres` as
the host and not `localhost`. Inside the Ignition container, `localhost`
is the gateway itself.

**Nothing on the EMQX dashboard.** Give it thirty seconds after startup.
EMQX has a health check and `line-sim` waits for it, so the first
publish lands a little after the broker is up.
