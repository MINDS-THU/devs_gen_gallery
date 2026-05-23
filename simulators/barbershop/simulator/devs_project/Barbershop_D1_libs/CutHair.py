from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class CutHair(Atomic):
    """
    Function:
        - Implements the `cuthair` module of Barbershop_D1. Receives a customer token "newcust" from `checkhair`,
          performs hair cutting for an exact duration, then signals completion back to `checkhair` with "done".
        - States and Output at the end of the state:
            - IDLE:
                - Waits indefinitely for an input "newcust" on port `in_newcust`.
                - No output is produced in this state.
            - CUTTING:
                - Entered upon receiving "newcust". Holds for exactly `cut_time` seconds.
                - When CUTTING ends (internal event time):
                    - Output in lambdaf: sends "done" on port `out` and emits the corresponding message log.
                    - Internal transition in deltint (same simulation time): increments `total_customer_done` and emits
                      the corresponding state log, then returns to IDLE.

    Logging in this model:
        - event: Initial counter state emitted
            log_type: PROCESS
            msg (dict):
                time (float): current simulation time (at initialization, typically 0.0)
                type (str): "state"
                model (str): "cuthair"
                field (str): "total customer done"
                value (int): 0
        - event: Cutting completion message emitted
            log_type: PROCESS
            msg (dict):
                time (float): current simulation time (when output is sent)
                type (str): "message"
                model (str): "cuthair"
                port (str): "out"
                content (str): "done"
        - event: Counter incremented at completion
            log_type: PROCESS
            msg (dict):
                time (float): current simulation time (when increment occurs; same time as output send)
                type (str): "state"
                model (str): "cuthair"
                field (str): "total customer done"
                value (int): cumulative number of completed haircuts

    Input Ports:
      - in_newcust (str): Customer token from [Sibling-checkhair: to_cut].
        structure:
            in_newcust (str): Must be the literal string "newcust".
        protocol: initialize: IDLE; no job in service at T=0. ; process: upon receiving "newcust" while IDLE,
                  start an exact `cut_time` seconds CUTTING hold.

    Output Ports:
      - out (str): Completion token sent to [Sibling-checkhair: in_done].
        structure:
            out (str): Must be the literal string "done".
        protocol: initialize: no pending sends. ; process: after exactly `cut_time` seconds cutting completes,
                  send "done" and emit message log (port="out", content="done"); increment counter and emit
                  state log (field="total customer done") at the same simulation time.
    """

    def __init__(self, name: str, parent: Coupled | None, cut_time: float):
        """
        Args:
            name (str): The unique name of the model (should be "cuthair" in this project).
            parent (Coupled | None): The parent model. If None, the model is a root model.
            cut_time (float): Exact cutting time in seconds. Must be 20.0.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match specification)
        self.add_in_port(Port(str, "in_newcust"))
        self.add_out_port(Port(str, "out"))

        # Internal hardcoded parameters (not passed via __init__)
        self.param = {
            "required_cut_time": 20.0
        }

        # Enforce spec: cutting time must be exactly 20.0 seconds.
        self.cut_time: float = self.param["required_cut_time"] if float(cut_time) != self.param["required_cut_time"] else float(cut_time)

        # State variables
        self.total_customer_done: int = 0
        self._pending_out: str | None = None  # prepared payload for lambdaf

        # Initial state is set in initialize()
        self.hold_in("IDLE", float("inf"))

    def initialize(self):
        # Reset state variables
        self.total_customer_done = 0
        self._pending_out = None

        # Emit initial tracked state (kept within required schema)
        self.logger.info(
            {
                "time": float(get_current_time()),
                "type": "state",
                "model": "cuthair",
                "field": "total customer done",
                "value": int(self.total_customer_done),
            },
            log_type="PROCESS",
        )

        self.hold_in("IDLE", float("inf"))

    def deltext(self, e: float):
        # Keep remaining time semantics consistent
        remaining = max(0.0, float(self.ta()) - float(e))

        # Consume inputs
        for token in self.input["in_newcust"].values:
            # Only literal "newcust" is meaningful per specification.
            if not isinstance(token, str) or token != "newcust":
                # Ignore invalid tokens without logging to avoid violating required output schema.
                continue

            # Start cutting only if idle (no queueing in this module by spec)
            if self.phase == "IDLE":
                self._pending_out = "done"  # prepare payload for lambdaf at completion time
                self.hold_in("CUTTING", float(self.cut_time))
                return

        # No state change due to external input; continue current phase with updated remaining time.
        self.hold_in(self.phase, remaining)

    def lambdaf(self):
        # Output only; payload must be prepared earlier (deltext/deltint/initialize)
        if self.phase == "CUTTING" and self._pending_out == "done":
            self.output["out"].add("done")
            self.logger.info(
                {
                    "time": float(get_current_time()),
                    "type": "message",
                    "model": "cuthair",
                    "port": "out",
                    "content": "done",
                },
                log_type="PROCESS",
            )

    def deltint(self):
        # Internal transition happens right after lambdaf at the same simulation time.
        if self.phase == "CUTTING":
            # Completion: increment KPI counter and log tracked state change
            self.total_customer_done += 1
            self.logger.info(
                {
                    "time": float(get_current_time()),
                    "type": "state",
                    "model": "cuthair",
                    "field": "total customer done",
                    "value": int(self.total_customer_done),
                },
                log_type="PROCESS",
            )

            # Clear job
            self._pending_out = None

            # Return to idle
            self.hold_in("IDLE", float("inf"))
        else:
            # Safety fallback
            self.hold_in("IDLE", float("inf"))

    def exit(self):
        # No extra logs here to keep output strictly within the required schema.
        return