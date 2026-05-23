import math
from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class AAM1(Atomic):
    """
    Function:
        - Implements the AAM (AccountAccessManager) stage as a single-server FIFO queue.
        - States and Output at the end of the state:
            - IDLE: server idle; waits indefinitely until at least one request arrives. No output.
            - BUSY: server processing exactly one head-of-line request for `processing_delay` seconds.
                When BUSY ends (service completion), outputs (if applicable) are emitted in `lambdaf`:
                    - If request has valid==1 and invalid==0: outputs the same request on `to_anv`.
                    - Otherwise: no output on `to_anv`.
                After output, `deltint` logs the required event and immediately starts the next queued request if any;
                otherwise transitions back to IDLE.

    Logging in this model:
        - Required completion events (emitted when AAM finishes processing a request at simulation time t):
            - {"time": t, "model": "AAM1", "event": "account_generated", "data": {}}
            - {"time": t, "model": "AAM1", "event": "logout", "data": {}}
        - Lifecycle / debug (optional):
            - {"time": t, "model": "AAM1", "event": "model_created", "data": {"processing_delay": <float>}}
            - {"time": t, "model": "AAM1", "event": "model_initialized", "data": {"processing_delay": <float>}}
            - {"time": t, "model": "AAM1", "event": "model_exit", "data": {"processed_total": <int>, "forwarded_total": <int>, "logout_total": <int>}}

    Input Ports:
      - request_in (dict): Login request received from [Sibling-input_reader1: to_aam].
        structure:
            valid (int): Expected 1 (kept for compatibility).
            invalid (int): 0 for valid login, 1 for invalid login.
        protocol: initialize: FIFO queue empty; server idle at T=0 ; process: enqueue on arrival; if server idle, start service immediately.

    Output Ports:
      - to_anv (dict): Forwarded login request to [Sibling-ANV1: request_in], only for valid login (invalid==0).
        structure:
            valid (int): Echoed from input request.
            invalid (int): Echoed from input request (will be 0 for forwarded messages).
        protocol: initialize: no message in transit at T=0 ; process: emitted only on service completion of a valid login.
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
        self.add_out_port(Port(dict, "to_anv"))

        # Config
        self.processing_delay: float = float(processing_delay)

        # Internal hardcoded parameters
        self.param: dict = {}

        # State
        self._queue: list[dict] = []
        self._current_request: dict | None = None

        # Payload prepared for next lambdaf (must be prepared before lambdaf runs)
        self._prepared_to_anv: dict | None = None
        self._prepared_log_event: str | None = None  # "account_generated" | "logout"

        # KPIs
        self._processed_total: int = 0
        self._forwarded_total: int = 0
        self._logout_total: int = 0

        # Creation log
        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "model_created",
                "data": {"processing_delay": float(self.processing_delay)},
            },
            log_type="PROCESS",
        )

    def initialize(self):
        self._queue = []
        self._current_request = None
        self._prepared_to_anv = None
        self._prepared_log_event = None

        self._processed_total = 0
        self._forwarded_total = 0
        self._logout_total = 0

        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "model_initialized",
                "data": {"processing_delay": float(self.processing_delay)},
            },
            log_type="PROCESS",
        )

        self.hold_in("IDLE", float("inf"))

    def _start_next_service_if_possible(self):
        """
        Starts service for the head-of-line request if the server is not currently busy and the queue is non-empty.
        Prepares the next output payload for `lambdaf` and schedules the internal completion event.
        """
        if self._current_request is not None:
            return
        if not self._queue:
            return

        self._current_request = self._queue.pop(0)

        valid = int(self._current_request.get("valid", 0))
        invalid = int(self._current_request.get("invalid", 1))

        if valid == 1 and invalid == 0:
            # Forward on completion
            self._prepared_to_anv = {"valid": valid, "invalid": invalid}
            self._prepared_log_event = "account_generated"
        else:
            # Logout on completion (do not forward)
            self._prepared_to_anv = None
            self._prepared_log_event = "logout"

        self.hold_in("BUSY", float(self.processing_delay))

    def deltext(self, e: float):
        # Enqueue all arrivals
        for req in self.input["request_in"].values:
            # Normalize to the specified schema (dict with int primitives)
            valid = int(req.get("valid", 0)) if isinstance(req, dict) else 0
            invalid = int(req.get("invalid", 1)) if isinstance(req, dict) else 1
            self._queue.append({"valid": valid, "invalid": invalid})

        if self.phase == "IDLE":
            # Start immediately if possible
            self._start_next_service_if_possible()
            if self._current_request is None:
                self.hold_in("IDLE", float("inf"))
        else:
            # Remain BUSY; reduce remaining time by elapsed e
            remaining = float(self.ta()) - float(e)
            self.hold_in("BUSY", max(0.0, remaining))

    def lambdaf(self):
        # Output only; state updates and logging happen in deltint
        if self.phase == "BUSY" and self._prepared_to_anv is not None:
            self.output["to_anv"].add(self._prepared_to_anv)

    def deltint(self):
        # Completion of current service (BUSY -> ...)
        if self.phase == "BUSY" and self._current_request is not None:
            # Update KPIs based on prepared action
            self._processed_total += 1
            if self._prepared_log_event == "account_generated":
                self._forwarded_total += 1
            else:
                self._logout_total += 1

            # Required event log at completion time
            t = float(get_current_time())
            event_name = str(self._prepared_log_event) if self._prepared_log_event is not None else "logout"
            self.logger.info(
                {"time": t, "model": str(self.name), "event": event_name, "data": {}},
                log_type="RESULT",
            )

            # Clear current job (output already emitted by lambdaf)
            self._current_request = None
            self._prepared_to_anv = None
            self._prepared_log_event = None

        # Start next request immediately if available
        if self._queue:
            self._start_next_service_if_possible()
        else:
            self.hold_in("IDLE", float("inf"))

    def exit(self):
        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "model_exit",
                "data": {
                    "processed_total": int(self._processed_total),
                    "forwarded_total": int(self._forwarded_total),
                    "logout_total": int(self._logout_total),
                },
            },
            log_type="RESULT",
        )