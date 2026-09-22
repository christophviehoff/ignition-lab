"""Simulated etch tool that speaks SECS/GEM over HSMS (passive, port 5000)."""
import logging
import os
import random
import threading
import time

import secsgem.common
import secsgem.gem
import secsgem.hsms
import secsgem.secs.variables as v

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(name)s: %(message)s")
logging.getLogger("communication").setLevel(os.getenv("SECS_LOG_LEVEL", "WARNING"))
log = logging.getLogger("equipment")

# IDs used by both the sim and the bridge
SV_PRESSURE, SV_TEMP, SV_RF, SV_STATE, SV_WAFERS, SV_RECIPE = 2101, 2102, 2103, 2104, 2105, 2106
DV_LOT, DV_WAFER = 2001, 2002
CE_WAFER_START, CE_WAFER_END, CE_RECIPE, CE_ALARM_ON, CE_ALARM_OFF = 3001, 3002, 3003, 3101, 3102
AL_OVERTEMP = 5001


class EtchTool(secsgem.gem.GemEquipmentHandler):
    def __init__(self, settings):
        super().__init__(settings)
        self.MDLN = "SIM-ETCH"
        self.SOFTREV = "1.0.0"
        self.running = False
        self.overtemp = False

        svs = [
            (SV_PRESSURE, "ChamberPressure", "mTorr", v.F4),
            (SV_TEMP, "ChamberTemp", "degC", v.F4),
            (SV_RF, "RFPower", "W", v.F4),
            (SV_STATE, "ProcessState", "", v.String),
            (SV_WAFERS, "WaferCount", "", v.U4),
            (SV_RECIPE, "Recipe", "", v.String),
        ]
        for svid, name, unit, typ in svs:
            self.status_variables[svid] = secsgem.gem.StatusVariable(
                svid, name, unit, typ, use_callback=False)
        self.status_variables[SV_STATE].value = "IDLE"
        self.status_variables[SV_RECIPE].value = "ETCH_OX_60S"

        self.data_values[DV_LOT] = secsgem.gem.DataValue(DV_LOT, "LotID", v.String, use_callback=False, value="")
        self.data_values[DV_WAFER] = secsgem.gem.DataValue(DV_WAFER, "WaferID", v.String, use_callback=False, value="")

        for ceid, name, dvs in [
            (CE_WAFER_START, "WaferStart", [DV_LOT, DV_WAFER]),
            (CE_WAFER_END, "WaferEnd", [DV_LOT, DV_WAFER]),
            (CE_RECIPE, "RecipeSelected", []),
            (CE_ALARM_ON, "OverTempSet", []),
            (CE_ALARM_OFF, "OverTempClear", []),
        ]:
            self.collection_events[ceid] = secsgem.gem.CollectionEvent(ceid, name, dvs)

        self.alarms[AL_OVERTEMP] = secsgem.gem.Alarm(
            AL_OVERTEMP, "OverTemp", "Chamber temperature above 80 degC",
            self.settings.data_items.ALCD.PARAMETER_CONTROL_WARNING,
            CE_ALARM_ON, CE_ALARM_OFF)

        # PP_SELECT with a PPID parameter, on top of the built in START and STOP
        self.remote_commands["PP_SELECT"] = secsgem.gem.RemoteCommand(
            "PP_SELECT", "Select recipe", ["PPID"], CE_RECIPE)

    # Remote command callbacks
    def _on_rcmd_START(self):
        log.info("START received")
        self.running = True

    def _on_rcmd_STOP(self):
        log.info("STOP received")
        self.running = False

    def _on_rcmd_PP_SELECT(self, PPID):
        log.info("PP_SELECT %s", PPID)
        self.status_variables[SV_RECIPE].value = str(PPID)

    # Process loop
    def simulate(self):
        wafer, lot = 0, f"LOT{random.randint(1000, 9999)}"
        cycle_start = None
        while True:
            sv = self.status_variables
            if self.running:
                sv[SV_STATE].value = "PROCESSING"
                sv[SV_PRESSURE].value = round(random.gauss(35.0, 1.5), 2)
                sv[SV_TEMP].value = round(random.gauss(65.0, 6.0), 2)
                sv[SV_RF].value = round(random.gauss(500.0, 10.0), 1)
                if cycle_start is None:
                    wafer += 1
                    self.data_values[DV_LOT].value = lot
                    self.data_values[DV_WAFER].value = f"{lot}-{wafer:02d}"
                    self._safe_ce(CE_WAFER_START)
                    cycle_start = time.time()
                elif time.time() - cycle_start > 20:
                    sv[SV_WAFERS].value += 1
                    self._safe_ce(CE_WAFER_END)
                    cycle_start = None
                    if wafer >= 25:
                        wafer, lot = 0, f"LOT{random.randint(1000, 9999)}"
            else:
                sv[SV_STATE].value = "IDLE"
                sv[SV_PRESSURE].value = round(random.gauss(0.5, 0.05), 3)
                sv[SV_TEMP].value = round(random.gauss(25.0, 0.5), 2)
                sv[SV_RF].value = 0.0
                cycle_start = None

            hot = sv[SV_TEMP].value > 80.0
            if hot != self.overtemp:
                self.overtemp = hot
                try:
                    (self.set_alarm if hot else self.clear_alarm)(AL_OVERTEMP)
                except Exception as exc:  # host may not be connected
                    log.debug("alarm send skipped: %s", exc)
            time.sleep(1)

    def _safe_ce(self, ceid):
        try:
            self.trigger_collection_events([ceid])
        except Exception as exc:
            log.debug("event %s skipped: %s", ceid, exc)


def main():
    settings = secsgem.hsms.HsmsSettings(
        address="0.0.0.0",
        port=int(os.getenv("HSMS_PORT", "5000")),
        connect_mode=secsgem.hsms.HsmsConnectMode.PASSIVE,
        device_type=secsgem.common.DeviceType.EQUIPMENT,
        session_id=int(os.getenv("SESSION_ID", "0")),
    )
    tool = EtchTool(settings)
    tool.running = os.getenv("AUTO_START", "true").lower() == "true"
    tool.enable()
    log.info("Equipment listening on port %s", settings.port)
    tool.simulate()


if __name__ == "__main__":
    main()
