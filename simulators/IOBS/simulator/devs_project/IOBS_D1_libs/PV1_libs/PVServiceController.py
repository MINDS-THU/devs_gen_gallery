import math
from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class PVServiceController(Atomic):
    """
    Function:
        - Owns PV1’s single-server + FIFO-queue service discipline and fixed service-time behavior.
        - Receives login requests from the parent, enqueues them, and processes them one-by-one with a fixed delay.
        - States and Output at the end of the state:
            - IDLE: Server is idle; no internal event is scheduled (sigma=inf). On external arrivals, enqueue; if queue becomes non-empty, immediately start service (enter BUSY with sigma=processing_delay).
            - BUSY: Server is processing exactly one request. When BUSY phase is over, outputs the completion message via port `service_done` (same payload as the request). After output, internally transitions to either:
                - BUSY again immediately (sigma=processing_delay) if queue has more requests, starting next request,
                - or IDLE (sigma=inf) if queue is empty.

    Logging in this model:
        - Optional debug logs only, using JSONL-like schema through the project logger:
            - {"time": (float), "model": (str), "event": (str), "data": (dict)}
        - Events emitted by this model (optional):
            - "created": Model instance created.
            - "initialized": Model initialized (queue empty; idle).
            - "enqueued": One or more requests enqueued (reports queue_size).
            - "service_start": A request started service (reports request and queue_size_after_pop).
            - "service_end_scheduled": Service completion scheduled (reports request and completion_time).
            - "service_completed": Service completed (right after output has been produced; reports request).

    Input Ports:
      - request_in (dict): Login request received from [Parent-PV1: request_in].
        structure:
            valid (int): Always 1 (compatibility input field).
            invalid (int): 0 for valid login, 1 for invalid login.
        protocol: initialize: FIFO queue empty; server idle at T=0 ; process: enqueue; if idle start service immediately; completion after exactly `processing_delay`.

    Output Ports:
      - service_done (dict): Completion message sent to [Sibling-PVVerificationEmitter: service_done_in].
        structure:
            valid (int): Echoed from the completed request.
            invalid (int): Echoed from the completed request.
        protocol: initialize: no message in transit at T=0 ; process: on service completion at time t, emits the same request payload.
    """

    def __init__(self, name: str, parent: Coupled | None, processing_delay: float = 10.0):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            processing_delay (float): Fixed service time per request in seconds. Default 10.0.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match the specification)
        self.add_in_port(Port(dict, "request_in"))
        self.add_out_port(Port(dict, "service_done"))

        # Configuration
        self.processing_delay = float(processing_delay)

        # Internal hardcoded parameters
        self.param = {
            "phase_idle": "IDLE",
            "phase_busy": "BUSY",
            "infinity": float("inf"),
        }

        # Internal state
        self._queue: list[dict] = []
        self._current_request: dict | None = None

        # Payload prepared for lambdaf (must be prepared before lambdaf is called)
        self._out_service_done: dict | None = None

        # Start passive; real init in initialize()
        self.hold_in(self.param["phase_idle"], self.param["infinity"])

        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "created",
                "data": {
                    "processing_delay": float(self.processing_delay),
                },
            },
            log_type="PROCESS",
        )

    def initialize(self):
        self._queue = []
        self._current_request = None
        self._out_service_done = None

        self.hold_in(self.param["phase_idle"], self.param["infinity"])

        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "initialized",
                "data": {"queue_size": int(len(self._queue)), "phase": str(self.phase)},
            },
            log_type="PROCESS",
        )

    def _start_next_service_if_possible(self):
        """
        Internal helper (no port I/O): if idle and queue non-empty, start service immediately.
        Prepares the payload for the eventual completion output.
        """
        if self._current_request is not None:
            return
        if not self._queue:
            return

        # Pop FIFO
        self._current_request = self._queue.pop(0)

        # Prepare payload for completion output (same as request payload)
        # Ensure only atomic primitives inside (valid/invalid are ints)
        self._out_service_done = {
            "valid": int(self._current_request.get("valid", 0)),
            "invalid": int(self._current_request.get("invalid", 0)),
        }

        # Schedule completion
        completion_time = float(get_current_time()) + float(self.processing_delay)

        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "service_start",
                "data": {
                    "request": {"valid": int(self._out_service_done["valid"]), "invalid": int(self._out_service_done["invalid"])},
                    "queue_size_after_pop": int(len(self._queue)),
                },
            },
            log_type="PROCESS",
        )
        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "service_end_scheduled",
                "data": {
                    "request": {"valid": int(self._out_service_done["valid"]), "invalid": int(self._out_service_done["invalid"])},
                    "completion_time": float(completion_time),
                },
            },
            log_type="PROCESS",
        )

        self.hold_in(self.param["phase_busy"], float(self.processing_delay))

    def deltext(self, e: float):
        # Enqueue all arrivals
        received_any = False
        for req in self.input["request_in"].values:
            # Enforce expected schema (only keep required keys as ints)
            cleaned = {"valid": int(req.get("valid", 0)), "invalid": int(req.get("invalid", 0))}
            self._queue.append(cleaned)
            received_any = True

        if received_any:
            self.logger.info(
                {
                    "time": float(get_current_time()),
                    "model": str(self.name),
                    "event": "enqueued",
                    "data": {"queue_size": int(len(self._queue)), "phase": str(self.phase)},
                },
                log_type="PROCESS",
            )

        # State evolution
        if self.phase == self.param["phase_idle"]:
            # If idle, start immediately if possible (no time elapses for starting)
            self._start_next_service_if_possible()
            if self.phase == self.param["phase_idle"]:
                self.hold_in(self.param["phase_idle"], self.param["infinity"])
        else:
            # BUSY: keep working, adjusting remaining time
            remaining = float(self.ta()) - float(e)
            if remaining < 0.0:
                remaining = 0.0
            self.hold_in(self.param["phase_busy"], remaining)

    def lambdaf(self):
        # Output only; no state changes
        if self.phase == self.param["phase_busy"] and self._out_service_done is not None:
            self.output["service_done"].add(
                {
                    "valid": int(self._out_service_done["valid"]),
                    "invalid": int(self._out_service_done["invalid"]),
                }
            )

    def deltint(self):
        # Internal transition after scheduled timeout
        if self.phase == self.param["phase_busy"]:
            # Completion has just been output by lambdaf; now clear current and move on
            if self._out_service_done is not None:
                self.logger.info(
                    {
                        "time": float(get_current_time()),
                        "model": str(self.name),
                        "event": "service_completed",
                        "data": {
                            "request": {"valid": int(self._out_service_done["valid"]), "invalid": int(self._out_service_done["invalid"])},
                            "queue_size": int(len(self._queue)),
                        },
                    },
                    log_type="PROCESS",
                )

            self._current_request = None
            self._out_service_done = None

            # Immediately start next if queued; otherwise go idle
            if self._queue:
                self._start_next_service_if_possible()
                # _start_next_service_if_possible sets phase BUSY with proper sigma
            else:
                self.hold_in(self.param["phase_idle"], self.param["infinity"])
        else:
            # IDLE internal transition should not normally happen; keep it safe
            self.hold_in(self.param["phase_idle"], self.param["infinity"])

    def exit(self):
        # Optional final debug summary
        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "finalized",
                "data": {
                    "queue_size": int(len(self._queue)),
                    "phase": str(self.phase),
                    "busy": bool(self._current_request is not None),
                },
            },
            log_type="RESULT",
        )