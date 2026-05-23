import random
from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class BPM1(Atomic):
    """
    Function:
        - Implements the BPM1 (BillPaymentManager) stage as a single-server with an internal FIFO queue.
        - States and Output at the end of the state:
            - IDLE: Server is idle and queue may be empty; waits for requests. No output.
            - BUSY: Server is processing one request for exactly `processing_delay` seconds. When BUSY ends, it generates
              the bill amount using the latest known balance snapshot (updated via `balance_in`) and immediately moves to EMIT.
            - EMIT: Outputs the prepared message to TPM via `to_tpm` (same simulation time as BUSY completion due to sigma=0).
              After EMIT, it logs the required `bill` event, then starts next queued request if any; otherwise returns to IDLE.

    Logging in this model:
        - bill (REQUIRED)
            Logged when BPM finishes its processing for a request (at service completion time t).
            Schema:
                time (float): Simulation time when the bill is produced.
                model (str): Model name (expected "BPM1").
                event (str): "bill".
                data (dict):
                    amount (int): Generated bill amount (0..40 by default) clipped by latest known balance.
        - created (optional debug)
            time (float), model (str), event (str), data (dict): model parameters.
        - initialized (optional debug)
            time (float), model (str), event (str), data (dict): initial state summary.
        - finished (optional debug)
            time (float), model (str), event (str), data (dict): processed count.

    Input Ports:
      - request_in (dict): Incoming request from [Sibling-PV1: to_bpm].
        structure:
            valid (int): Always 1 (compatibility).
            invalid (int): 0 for valid login, 1 for invalid login (BPM assumes it only receives successful PV outputs).
        protocol: initialize: FIFO queue empty; server idle at T=0. ; process: enqueue requests; if idle, start service immediately.

      - balance_in (int): Latest known account balance snapshot from [Sibling-TPM1: balance_out].
        structure:
            (int): Non-negative account balance used to clip bill at bill generation time.
        protocol: initialize: internal `latest_balance` set to `initial_balance_snapshot` at T=0. ; process: update latest balance.

    Output Ports:
      - to_tpm (dict): Forward bill payment request to [Sibling-TPM1: request_in].
        structure:
            amount (int): Bill amount after clipping by latest known balance.
        protocol: initialize: empty. ; process: on completion, output one message per processed request.
    """

    def __init__(
        self,
        name: str,
        parent: Coupled | None,
        processing_delay: float = 10.0,
        bill_min: int = 0,
        bill_max: int = 40,
        initial_balance_snapshot: int = 3000,
    ):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            processing_delay (float): Fixed service time per request in seconds. Default 10.0.
            bill_min (int): Minimum bill amount inclusive. Default 0.
            bill_max (int): Maximum bill amount inclusive before clipping by balance. Default 40.
            initial_balance_snapshot (int): Initial balance used for clipping until `balance_in` updates are received. Default 3000.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match specification)
        self.add_in_port(Port(dict, "request_in"))
        self.add_in_port(Port(int, "balance_in"))
        self.add_out_port(Port(dict, "to_tpm"))

        # Configuration
        self.processing_delay = float(processing_delay)
        self.bill_min = int(bill_min)
        self.bill_max = int(bill_max)
        self.initial_balance_snapshot = int(initial_balance_snapshot)

        # Internal hardcoded parameters
        self.param = {
            "queue_policy": "FIFO",
            "emit_phase_sigma": 0.0,  # EMIT is scheduled at the same simulation time as BUSY completion
        }

        # State variables
        self.queue: list[dict] = []
        self.current_request: dict | None = None
        self.latest_balance: int = int(initial_balance_snapshot)

        # Prepared output payload for lambdaf (must be set before EMIT)
        self._pending_to_tpm: dict | None = None
        self._pending_amount: int | None = None

        # KPIs
        self.processed_count: int = 0

        # Creation log (optional debug; kept JSONL schema)
        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "created",
                "data": {
                    "processing_delay": float(self.processing_delay),
                    "bill_min": int(self.bill_min),
                    "bill_max": int(self.bill_max),
                    "initial_balance_snapshot": int(self.initial_balance_snapshot),
                },
            },
            log_type="PROCESS",
        )

    def initialize(self):
        self.queue = []
        self.current_request = None
        self.latest_balance = int(self.initial_balance_snapshot)
        self._pending_to_tpm = None
        self._pending_amount = None
        self.processed_count = 0

        # Initialization log (optional debug; kept JSONL schema)
        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "initialized",
                "data": {
                    "latest_balance": int(self.latest_balance),
                    "queue_size": int(len(self.queue)),
                    "phase": str("IDLE"),
                },
            },
            log_type="PROCESS",
        )

        self.hold_in("IDLE", float("inf"))

    def lambdaf(self):
        # Output only; no state changes or logging here
        if self.phase == "EMIT" and self._pending_to_tpm is not None:
            self.output["to_tpm"].add(self._pending_to_tpm)

    def deltint(self):
        # Internal transitions only; outputs already sent by lambdaf for the old phase.
        if self.phase == "BUSY":
            # Service completion: generate bill using the latest known balance at this time.
            balance_snapshot = int(self.latest_balance)
            if balance_snapshot < 0:
                balance_snapshot = 0

            raw_amount = int(random.randint(int(self.bill_min), int(self.bill_max)))
            amount = int(min(raw_amount, balance_snapshot)) if balance_snapshot > 0 else 0

            # Prepare payload for immediate EMIT (sigma=0)
            self._pending_amount = amount
            self._pending_to_tpm = {"amount": int(amount)}
            self.hold_in("EMIT", float(self.param["emit_phase_sigma"]))
            return

        if self.phase == "EMIT":
            # Log required bill event at the completion time (same t as BUSY completion)
            if self._pending_amount is None:
                # Defensive: should not happen, but keep the model safe
                self._pending_amount = 0
                self._pending_to_tpm = {"amount": 0}

            self.logger.info(
                {
                    "time": float(get_current_time()),
                    "model": str(self.name),
                    "event": "bill",
                    "data": {"amount": int(self._pending_amount)},
                },
                log_type="RESULT",
            )

            self.processed_count += 1
            self.current_request = None
            self._pending_amount = None
            self._pending_to_tpm = None

            # Start next job if available; otherwise become idle
            if len(self.queue) > 0:
                self.current_request = self.queue.pop(0)
                self.hold_in("BUSY", float(self.processing_delay))
            else:
                self.hold_in("IDLE", float("inf"))
            return

        # IDLE should not have internal events; keep passive.
        self.hold_in("IDLE", float("inf"))

    def deltext(self, e: float):
        # External transitions only: update balance snapshot, enqueue requests, maybe start service.
        # Update latest balance first
        for bal in self.input["balance_in"].values:
            try:
                self.latest_balance = int(bal)
            except Exception:
                # Keep previous balance if malformed; do not raise.
                pass

        # Enqueue any incoming requests
        for req in self.input["request_in"].values:
            # Expect structure: {'valid': int, 'invalid': int}
            if isinstance(req, dict):
                self.queue.append(req)

        # State handling
        if self.phase == "IDLE":
            if self.current_request is None and len(self.queue) > 0:
                self.current_request = self.queue.pop(0)
                self.hold_in("BUSY", float(self.processing_delay))
            else:
                self.hold_in("IDLE", float("inf"))
            return

        # BUSY or EMIT: keep current phase, adjust remaining time
        remaining = float(self.ta()) - float(e)
        if remaining < 0.0:
            remaining = 0.0
        self.hold_in(str(self.phase), remaining)

    def deltcon(self):
        """
        Confluent transition: process external events first so that a balance update arriving at the same
        simulation time as service completion is applied before bill generation/clipping.
        """
        self.deltext(0.0)
        self.deltint()

    def exit(self):
        # Finalization log (optional debug; kept JSONL schema)
        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "finished",
                "data": {"processed_count": int(self.processed_count)},
            },
            log_type="RESULT",
        )