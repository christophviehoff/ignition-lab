# Vacuum pump UDT example

One `VacuumPump` UDT drives three simulated dry pumps on etch01. Each pump gets
its values, limits, health status and alarms from the same definition. A card
view and an overview page pick up every instance automatically.

## Files

| File | What it is |
|---|---|
| `pump-sim/` | Python simulator for pumps PP1, LL1 and TM1 |
| `docker-compose.pump.yml` | Adds the simulator to the lab stack |
| `VacuumPump-tags.json` | UDT definition plus three instances, for tag import |
| `views/Pumps/PumpCard` | One pump, takes `pumpPath` as a parameter |
| `views/Pumps/PumpOverview` | Every pump plus an alarm table |
| `import-views.ps1` | Copies the views into the gateway |

## Setup, from the ignition-lab folder

1. Start the simulator

       docker compose -f docker-compose.yml -f docker-compose.secsgem.yml -f pump-demo/docker-compose.pump.yml up -d --build
       docker logs -f pump-sim

2. Import the tags. In the Designer Tag Browser select the **default** provider
   (the top level, not a folder), click the three dots menu, then **Import Tags**,
   and choose `VacuumPump-tags.json`. You get:
   * `Data Types/VacuumPump`
   * `Fab/etch01/Pumps/PP1`, `LL1`, `TM1`

3. Import the views

       .\pump-demo\import-views.ps1 -Project lab

4. Open `Pumps/PumpOverview` and press F5.

## What is in the UDT

* **Parameters:** `Tool`, `PumpID`, `Role`, `Provider`
* **Reference tags** to `[{Provider}]fab/{Tool}/pump/{PumpID}/<Metric>/value`:
  State, Running, Speed, MotorCurrent, MotorPower, InletPressure,
  ExhaustPressure, BodyTemp, N2Purge, CoolingFlow, RunHours.
  History to PostgresHistory on current, power, temperature and cooling flow
* **Limits folder:** memory tags with defaults. LL1 and TM1 override the current
  limits, which shows per instance overrides
* **Info folder:** Tool, PumpID, Role and the command topic, all built from parameters
* **Expression tags with alarms:** Tripped (Critical), CurrentHighHigh,
  TempHighHigh, CoolingLow (High), CurrentHigh, TempHigh, ServiceDue (Low)
* **Health:** OK, WARN, ALARM, TRIPPED or STOPPED, plus CurrentLoadPct

## Demo script

* **Bearing wear:** press Wear on PP1. Current climbs about 1.2 A per minute,
  goes WARN at 10.5 A, ALARM at 12 A, and the pump trips near 13.5 A. Reset clears it.
* **Loss of cooling:** press Cooling on LL1. Flow drops below 2 L/min (ALARM at
  once) and body temperature climbs toward the warning limit.
* **Service due:** TM1 starts just under 20,000 run hours and passes the service
  limit after about 10 minutes (run hours are sped up 60 times).
* **Process load:** PP1 draws more current and runs warmer while the etch tool is PROCESSING.
* **Scale:** add a pump by creating one more UDT instance and one line in
  `pump_sim.py`. The overview page shows it with no view changes.

Commands go to `fab/etch01/pump/<id>/cmd` through MQTT Engine server `Chariot SCADA`.
