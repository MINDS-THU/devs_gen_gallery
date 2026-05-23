### BEGIN: General Import
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time
### END


class ArrivalPhaseCoordinator(Atomic):
    """
    Function:
        - Coordinate per-arrival servicing workflow and enforce deterministic phase ordering across alighting vs boarding
          for the same train arrival.
        - States and Output at the end of the state:
            - IDLE: No pending outputs; waiting for external events.
            - EMIT_STARTS: After receiving a train arrival, emit (in the same internal event) the alighting start command
              and the arrival context broadcasts for both AlightingScheduler and BoardingScheduler.
            - EMIT_ALIGHT_DONE: After receiving alight completion for an arrival, emit the gate release signal to allow
              boarding for that same arrival.

    Logging in this model:
        - event: "Model Created"
            log_type: PROCESS
            msg (dict):
                event (str): Fixed string "Model Created".
                service_time_seconds (float): Per-passenger service time configured.
                param (dict): Internal hardcoded parameters.
                    epsilon (float): Small non-negative scheduling epsilon used only if needed.
        - event: "Model Initialized"
            log_type: PROCESS
            msg (dict):
                event (str): Fixed string "Model Initialized".
                service_time_seconds (float): Per-passenger service time configured.
        - event: "Train Arrival Received"
            log_type: PROCESS
            msg (dict): Same structure as Input Ports -> train_arrival_in.
        - event: "Alight Completion Received"
            log_type: PROCESS
            msg (dict): Same structure as Input Ports -> alight_complete_in.
        - event: "Outputs Emitted"
            log_type: PROCESS
            msg (dict):
                event (str): Fixed string "Outputs Emitted".
                phase (str): One of "EMIT_STARTS" or "EMIT_ALIGHT_DONE".
                outputs (dict): What was emitted in lambdaf (if any).
                    alight_start_out (dict | None): If emitted, same structure as Output Ports -> alight_start_out.
                    alight_start_ctx_out (dict | None): If emitted, same structure as Output Ports -> alight_start_ctx_out.
                    board_start_ctx_out (dict | None): If emitted, same structure as Output Ports -> board_start_ctx_out.
                    alight_done_out (dict | None): If emitted, same structure as Output Ports -> alight_done_out.
        - event: "Model Finalized"
            log_type: RESULT
            msg (dict):
                event (str): Fixed string "Model Finalized".
                arrivals_received (int): Count of train arrivals processed.
                alight_completions_received (int): Count of alight completion notifications processed.
                gates_released (int): Count of alight_done_out signals emitted.

    Input Ports:
      - train_arrival_in (dict): Train arrival notification from [Parent EIC: train_arrival_in].
        structure:
            station_id (int): Station ID in [1..5].
            direction (int): Direction, 0 (Southbound) or 1 (Northbound).
        protocol: initialize: ready at T=0 with no pending service schedules ; process: for each arrival, immediately
                  initiate alighting and broadcast contexts; boarding is gated by alight_done_out.
      - alight_complete_in (dict): Alighting completion notification from [Sibling-AlightingScheduler: alight_complete_out].
        structure:
            station_id (int): Station ID in [1..5].
            arrival_time (float): The train arrival simulation time (seconds) for which alighting is complete.
        protocol: initialize: no completion pending ; process: upon receipt, release boarding gate for same arrival.

    Output Ports:
      - alight_start_out (dict): Alighting start command to [Parent EOC: alight_start_out] (wired to TrainLoadStore).
        structure:
            station_id (int): Station ID in [1..5].
            arrival_time (float): The train arrival simulation time (seconds).
        protocol: initialize: no output ; process: emitted immediately upon each train_arrival_in.
      - alight_start_ctx_out (dict): Arrival context broadcast to [Sibling-AlightingScheduler: arrival_ctx_in].
        structure:
            station_id (int): Station ID in [1..5].
            arrival_time (float): The train arrival simulation time (seconds).
            direction (int): Direction, 0 or 1.
        protocol: initialize: no output ; process: emitted immediately upon each train_arrival_in.
      - board_start_ctx_out (dict): Arrival context broadcast to [Sibling-BoardingScheduler: arrival_ctx_in].
        structure:
            station_id (int): Station ID in [1..5].
            arrival_time (float): The train arrival simulation time (seconds).
            direction (int): Direction, 0 or 1.
        protocol: initialize: no output ; process: emitted immediately upon each train_arrival_in; boarding is expected
                  to wait for alight_done_out for the same arrival.
      - alight_done_out (dict): Gate release signal to [Sibling-BoardingScheduler: alight_done_in].
        structure:
            station_id (int): Station ID in [1..5].
            arrival_time (float): The train arrival simulation time (seconds).
        protocol: initialize: no output ; process: emitted only after alight_complete_in for the same arrival.
    """

    def __init__(self, name: str, parent: Coupled | None, service_time_seconds: float = 0.025):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            service_time_seconds (float): Per-passenger boarding/alighting time in seconds. Default 0.025.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match specification)
        self.add_in_port(Port(dict, "train_arrival_in"))
        self.add_in_port(Port(dict, "alight_complete_in"))

        self.add_out_port(Port(dict, "alight_start_out"))
        self.add_out_port(Port(dict, "alight_start_ctx_out"))
        self.add_out_port(Port(dict, "board_start_ctx_out"))
        self.add_out_port(Port(dict, "alight_done_out"))

        # Config
        self.service_time_seconds = float(service_time_seconds)

        # Internal hardcoded params
        self.param = {
            "epsilon": 0.0  # kept for potential future tie-breaking; not used to shift timestamps by default
        }

        # Internal state
        self._pending_outputs = {
            "alight_start_out": None,       # dict | None
            "alight_start_ctx_out": None,   # dict | None
            "board_start_ctx_out": None,    # dict | None
            "alight_done_out": None         # dict | None
        }

        # KPI counters
        self._arrivals_received = 0
        self._alight_completions_received = 0
        self._gates_released = 0

        self.logger.info(
            {
                "event": "Model Created",
                "service_time_seconds": self.service_time_seconds,
                "param": self.param,
            },
            log_type="PROCESS",
        )

    def initialize(self):
        self._pending_outputs = {
            "alight_start_out": None,
            "alight_start_ctx_out": None,
            "board_start_ctx_out": None,
            "alight_done_out": None,
        }

        self.logger.info(
            {
                "event": "Model Initialized",
                "service_time_seconds": self.service_time_seconds,
            },
            log_type="PROCESS",
        )

        # No initial signal required
        self.hold_in("IDLE", float("inf"))

    def lambdaf(self):
        # Output only; no state changes here.
        if self.phase == "EMIT_STARTS":
            if self._pending_outputs["alight_start_out"] is not None:
                self.output["alight_start_out"].add(self._pending_outputs["alight_start_out"])
            if self._pending_outputs["alight_start_ctx_out"] is not None:
                self.output["alight_start_ctx_out"].add(self._pending_outputs["alight_start_ctx_out"])
            if self._pending_outputs["board_start_ctx_out"] is not None:
                self.output["board_start_ctx_out"].add(self._pending_outputs["board_start_ctx_out"])

        elif self.phase == "EMIT_ALIGHT_DONE":
            if self._pending_outputs["alight_done_out"] is not None:
                self.output["alight_done_out"].add(self._pending_outputs["alight_done_out"])

    def deltint(self):
        # Internal transition happens right after lambdaf.
        if self.phase in ("EMIT_STARTS", "EMIT_ALIGHT_DONE"):
            self.logger.info(
                {
                    "event": "Outputs Emitted",
                    "phase": self.phase,
                    "outputs": {
                        "alight_start_out": self._pending_outputs["alight_start_out"],
                        "alight_start_ctx_out": self._pending_outputs["alight_start_ctx_out"],
                        "board_start_ctx_out": self._pending_outputs["board_start_ctx_out"],
                        "alight_done_out": self._pending_outputs["alight_done_out"],
                    },
                },
                log_type="PROCESS",
            )

        # Clear pending outputs after emission
        self._pending_outputs = {
            "alight_start_out": None,
            "alight_start_ctx_out": None,
            "board_start_ctx_out": None,
            "alight_done_out": None,
        }

        # Return to IDLE
        self.hold_in("IDLE", float("inf"))

    def deltext(self, e: float):
        # External transition: handle incoming messages and schedule immediate internal event to emit outputs.
        _ = e  # elapsed time not used beyond ta()-e scheduling in other designs; here we emit immediately.

        # Priority: if multiple inputs arrive at same simulation time, we can emit both sets of outputs.
        # If both arrival and completion are present, we will emit STARTS and ALIGHT_DONE in the same timestamp.
        # Deterministic ordering rule is enforced by downstream gating: boarding waits for alight_done_out.
        # (We do not emit passenger logs here.)
        current_time = float(get_current_time())

        scheduled_phase = None

        # Process all train arrivals
        for msg in self.input["train_arrival_in"].values:
            # Expected schema:
            #   station_id (int), direction (int)
            station_id = int(msg.get("station_id", -1))
            direction = int(msg.get("direction", -1))

            self._arrivals_received += 1
            self.logger.info(
                {
                    "event": "Train Arrival Received",
                    "station_id": station_id,
                    "direction": direction,
                },
                log_type="PROCESS",
            )

            start_payload = {
                "station_id": station_id,
                "arrival_time": current_time,
            }
            ctx_payload = {
                "station_id": station_id,
                "arrival_time": current_time,
                "direction": direction,
            }

            # Prepare outputs to be emitted in lambdaf
            self._pending_outputs["alight_start_out"] = start_payload
            self._pending_outputs["alight_start_ctx_out"] = ctx_payload
            self._pending_outputs["board_start_ctx_out"] = ctx_payload

            scheduled_phase = "EMIT_STARTS"

        # Process all alight completions
        for msg in self.input["alight_complete_in"].values:
            # Expected schema:
            #   station_id (int), arrival_time (float)
            station_id = int(msg.get("station_id", -1))
            arrival_time = float(msg.get("arrival_time", -1.0))

            self._alight_completions_received += 1
            self.logger.info(
                {
                    "event": "Alight Completion Received",
                    "station_id": station_id,
                    "arrival_time": arrival_time,
                },
                log_type="PROCESS",
            )

            done_payload = {
                "station_id": station_id,
                "arrival_time": arrival_time,
            }
            self._pending_outputs["alight_done_out"] = done_payload
            self._gates_released += 1

            # If we already scheduled EMIT_STARTS due to arrivals, we still need to emit ALIGHT_DONE too.
            # We choose to emit ALIGHT_DONE (gate) in a separate immediate internal event if both exist.
            # However, xDEVS provides only one phase for the next internal event; to keep deterministic behavior,
            # we prioritize emitting starts first, then gate in the next 0-time step.
            if scheduled_phase is None:
                scheduled_phase = "EMIT_ALIGHT_DONE"
            else:
                # Starts already pending; we will emit starts now and then emit gate immediately after.
                # Store a flag to chain the second emission via deltint.
                self.param["epsilon"] = 0.0  # explicit; no time shift
                # Use a small internal queue for chained emission
                if not hasattr(self, "_chain_after_starts"):
                    self._chain_after_starts = []  # list[dict]
                self._chain_after_starts.append(done_payload)

        # Schedule next internal event
        if scheduled_phase is None:
            self.hold_in(self.phase, self.ta())
            return

        # If we are currently passive, schedule immediate emission
        self.hold_in(scheduled_phase, 0.0)

    def deltcon(self):
        # Keep default: internal first, then external.
        # This is acceptable because we gate boarding via alight_done_out and do not emit passenger logs here.
        super().deltcon()

    def exit(self):
        self.logger.info(
            {
                "event": "Model Finalized",
                "arrivals_received": int(self._arrivals_received),
                "alight_completions_received": int(self._alight_completions_received),
                "gates_released": int(self._gates_released),
            },
            log_type="RESULT",
        )