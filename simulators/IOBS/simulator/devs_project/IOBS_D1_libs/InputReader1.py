from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class InputReader1(Atomic):
    """
    Function:
        - Implements the `input_reader1` stage (no processing delay).
        - States and Output at the end of the state:
            - IDLE: Waits for injected requests on `request_in`.
            - FORWARD: After receiving one or more requests, schedules an immediate internal event (sigma=0.0).
              When the FORWARD state is over, outputs all buffered requests via `to_aam` (same simulation time).

    Logging in this model:
        - Emits required JSONL records via `self.logger.info(...)` using the exact event schemas:
            - start: at t=0.0
            - input: on each request arrival (at its arrival time)

    Input Ports:
      - request_in (dict): Injected request.
        structure:
            valid (int): Expected 1 (compatibility field; echoed).
            invalid (int): 0 for valid login, 1 for invalid login (echoed).
        protocol: initialize: Idle; no buffered requests at T=0. ; process: on receipt at time t, immediately logs
                  `input_reader1.input` and forwards the same request dict to `to_aam` at time t.

    Output Ports:
      - to_aam (dict): Forwarded login request to AAM.
        structure:
            valid (int): Echoed from input.
            invalid (int): Echoed from input.
        protocol: initialize: Empty; no message in transit at T=0. ; process: outputs immediately (same simulation time)
                  for each received request.
    """

    def __init__(self, name: str, parent: Coupled | None):
        """
        Args:
            name (str): The unique name of the model (expected: "input_reader1").
            parent (Coupled | None): the parent model. If None, the model is a root model.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match specification)
        self.add_in_port(Port(dict, "request_in"))
        self.add_out_port(Port(dict, "to_aam"))

        # Internal hardcoded parameters
        self.param: dict = {
            "forward_delay": 0.0  # seconds, this stage forwards immediately
        }

        # Internal state
        self._buffer: list[dict] = []
        self._pending_out: list[dict] = []

        # Start in a passive state; initialize() will set the proper phase/sigma.
        self.hold_in("IDLE", float("inf"))

    def initialize(self):
        self._buffer = []
        self._pending_out = []

        # Required event at t=0.0
        self.logger.info(
            {"time": float(get_current_time()), "model": "input_reader1", "event": "start", "data": {}},
            log_type="PROCESS",
        )

        self.hold_in("IDLE", float("inf"))

    def deltext(self, e: float):
        # Consume all arriving requests (can be multiple at same simulation time)
        for req in self.input["request_in"].values:
            # Extract and normalize payload (keep only specified keys/types)
            valid_val = int(req.get("valid", 1))
            invalid_val = int(req.get("invalid", 0))
            payload = {"valid": valid_val, "invalid": invalid_val}

            # Required log event upon reading a request
            self.logger.info(
                {
                    "time": float(get_current_time()),
                    "model": "input_reader1",
                    "event": "input",
                    "data": {"valid": valid_val, "invalid": invalid_val},
                },
                log_type="PROCESS",
            )

            self._buffer.append(payload)

        # If anything arrived, schedule immediate forwarding
        if self._buffer:
            # Prepare payload for lambdaf (no state mutation inside lambdaf)
            self._pending_out = list(self._buffer)
            self.hold_in("FORWARD", self.param["forward_delay"])
        else:
            # No new work; continue waiting (deduct elapsed time)
            remaining = self.ta() - float(e)
            if remaining < 0.0:
                remaining = 0.0
            self.hold_in(self.phase, remaining)

    def lambdaf(self):
        # Output only (no state updates here)
        if self.phase == "FORWARD":
            for payload in self._pending_out:
                self.output["to_aam"].add(payload)

    def deltint(self):
        # After output has been produced, clear forwarded items and go idle
        if self.phase == "FORWARD":
            self._buffer = []
            self._pending_out = []
            self.hold_in("IDLE", float("inf"))
        else:
            self.hold_in("IDLE", float("inf"))

    def exit(self):
        # No additional required logs for this model
        self._buffer = []
        self._pending_out = []