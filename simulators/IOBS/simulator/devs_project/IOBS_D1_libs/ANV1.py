import random
from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class ANV1(Atomic):
    """
    Function:
        - Implements the AccountNumberVerifier (ANV) stage as a single-server FIFO queue.
        - States and Output at the end of the state:
            - IDLE: Server idle, waiting for new requests. No output.
            - BUSY: Server processes exactly one request for `processing_delay` seconds.
              When BUSY ends, it may output the request to PV (only if pass==1). The verification result is logged.

    Logging in this model:
        - verification (required):
            Logged when ANV finishes its processing at time t.
            Schema (dict):
                time (float): Current simulation time.
                model (str): Must be "ANV1" (the instance name).
                event (str): Must be "verification".
                data (dict): Verification result.
                    pass (int): 1 if verification passed, else 0.
                    fail (int): 1 if verification failed, else 0.

    Input Ports:
      - request_in (dict): Login request from AAM.
        structure:
            valid (int): Valid flag (always 1).
            invalid (int): Invalid flag (0=valid login, 1=invalid login).
        protocol: initialize: FIFO queue empty; server idle at T=0 ; process: enqueue; if idle, start service immediately.

    Output Ports:
      - to_pv (dict): Forwarded login request to PV (only if verification passes).
        structure:
            valid (int): Valid flag (always 1).
            invalid (int): Invalid flag (0=valid login, 1=invalid login).
        protocol: initialize: empty ; process: emitted at completion time only if pass==1.
    """

    def __init__(self, name: str, parent: Coupled | None, processing_delay: float = 10.0):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            processing_delay (float): Fixed service time per request in seconds.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match specification)
        self.add_in_port(Port(dict, "request_in"))
        self.add_out_port(Port(dict, "to_pv"))

        # Configuration
        self.processing_delay = float(processing_delay)

        # Internal hardcoded parameters
        self.param = {
            "verification_pass_probability": 0.5
        }

        # State variables
        self._queue: list[dict] = []
        self._current_request: dict | None = None

        # Prepared data for the next output/log at completion (must be ready before lambdaf)
        self._service_pass_flag: int = 0
        self._service_fail_flag: int = 0
        self._prepared_to_pv: dict | None = None

        # Initial hold (will be set properly in initialize)
        self.hold_in("IDLE", float("inf"))

    def initialize(self):
        # Protocol initial state: FIFO queue empty; server idle at T=0
        self._queue = []
        self._current_request = None
        self._service_pass_flag = 0
        self._service_fail_flag = 0
        self._prepared_to_pv = None
        self.hold_in("IDLE", float("inf"))

    def _start_next_service_if_possible(self) -> None:
        """
        Starts processing the next queued request if server is idle and queue is non-empty.
        Prepares completion-time outputs by sampling verification outcome at service start.
        """
        if self._current_request is not None:
            return
        if not self._queue:
            return

        self._current_request = self._queue.pop(0)

        # Sample verification outcome (used at completion time for both output decision and logging)
        pass_flag = 1 if random.random() < self.param["verification_pass_probability"] else 0
        fail_flag = 1 - pass_flag

        self._service_pass_flag = int(pass_flag)
        self._service_fail_flag = int(fail_flag)

        # Prepare output for lambdaf (only if pass==1)
        if self._service_pass_flag == 1:
            # Forward the same request dict
            self._prepared_to_pv = {
                "valid": int(self._current_request.get("valid", 1)),
                "invalid": int(self._current_request.get("invalid", 0)),
            }
        else:
            self._prepared_to_pv = None

        self.hold_in("BUSY", self.processing_delay)

    def deltext(self, e: float):
        # Enqueue all incoming requests
        for req in self.input["request_in"].values:
            # Enforce expected schema keys (keep only specified keys)
            cleaned_req = {
                "valid": int(req.get("valid", 1)),
                "invalid": int(req.get("invalid", 0)),
            }
            self._queue.append(cleaned_req)

        # Continue/adjust timing
        if self.phase == "BUSY":
            remaining = self.ta() - float(e)
            if remaining < 0.0:
                remaining = 0.0
            self.hold_in("BUSY", remaining)
        else:
            # IDLE: start immediately if work is available
            self._start_next_service_if_possible()
            if self._current_request is None:
                self.hold_in("IDLE", float("inf"))

    def lambdaf(self):
        # Output only (no state updates, no logging)
        if self.phase == "BUSY" and self._prepared_to_pv is not None:
            self.output["to_pv"].add(self._prepared_to_pv)

    def deltint(self):
        # Completion of BUSY service
        if self.phase == "BUSY":
            # Required log at completion time
            self.logger.info(
                {
                    "time": float(get_current_time()),
                    "model": str(self.name),
                    "event": "verification",
                    "data": {
                        "pass": int(self._service_pass_flag),
                        "fail": int(self._service_fail_flag),
                    },
                },
                log_type="RESULT",
            )

            # Clear current service
            self._current_request = None
            self._prepared_to_pv = None
            self._service_pass_flag = 0
            self._service_fail_flag = 0

        # Start next request if any
        self._start_next_service_if_possible()
        if self._current_request is None:
            self.hold_in("IDLE", float("inf"))

    def exit(self):
        # No additional stdout logs to avoid producing non-required events.
        pass