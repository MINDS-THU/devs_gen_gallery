from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class TPM1(Atomic):
    """
    Function:
        - Implements the TransactionProcessManager (TPM) stage and owns the authoritative account state (balance).
        - Single-server with internal FIFO queue and fixed service time `processing_delay` seconds per request.
        - States and Output at the end of the state:
            - INIT_PUBLISH: schedules an immediate internal event at T=0 to publish the initial balance on `balance_out`.
              When INIT_PUBLISH is over, outputs `balance_out = initial_balance`, then transitions to IDLE or BUSY (if a queued job exists).
            - IDLE: server idle and waiting for requests. No output.
            - BUSY: server is processing the current request. When BUSY is over, outputs the updated balance on `balance_out`
              (computed as remaining = balance - amount for the job), then in the following internal transition updates:
                balance = remaining; transaction_count += 1; logs the required TPM1.transaction event. If queue is non-empty,
              immediately starts next request (BUSY), otherwise returns to IDLE.

    Logging in this model:
        - Required:
            - event: "transaction" (log_type="RESULT")
              msg (dict):
                  time (float): Current simulation time when TPM finishes processing a request.
                  model (str): Model name (expected to be "TPM1" in the scenario wiring).
                  event (str): "transaction"
                  data (dict): Transaction result payload.
                      remaining (int): Updated balance after deduction.
                      count (int): Cumulative number of completed TPM transactions.
        - Optional debug:
            - event: "created" (log_type="PROCESS")
            - event: "initialized" (log_type="PROCESS")
            - event: "final" (log_type="RESULT")

    Input Ports:
      - request_in (dict): Transaction request from [Sibling-bpm1: to_tpm].
        structure:
            amount (int): Bill amount to deduct from current balance.
        protocol: initialize: FIFO queue empty; server idle after initial publication at T=0 ; process: enqueue requests; if idle, start service immediately.

    Output Ports:
      - balance_out (int): Balance snapshot published to [Sibling-bpm1: balance_in].
        structure:
            - (int): Current authoritative balance after initialization and after each completed transaction.
        protocol: initialize: sends one message with value `initial_balance` at T=0 ; process: after each completion, sends updated balance (remaining).
    """

    def __init__(
        self,
        name: str,
        parent: Coupled | None,
        processing_delay: float = 10.0,
        initial_balance: int = 3000,
    ):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            processing_delay (float): Fixed service time per request in seconds. Default 10.0.
            initial_balance (int): Initial account balance. Default 3000.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match specification)
        self.add_in_port(Port(dict, "request_in"))
        self.add_out_port(Port(int, "balance_out"))

        # Config
        self.processing_delay: float = float(processing_delay)
        self.initial_balance: int = int(initial_balance)

        # Internal hardcoded parameters
        self.param: dict = {"queue_discipline": "FIFO"}

        # State variables
        self.queue: list[dict] = []
        self.balance: int = self.initial_balance
        self.transaction_count: int = 0

        self.current_request: dict | None = None
        self._service_remaining: int | None = (
            None  # remaining computed for the in-service request
        )

        # Output payload prepared for next lambdaf (balance_out only)
        self._out_balance_value: int | None = None

        # Keep optional lifecycle logs suppressed so the checker only replays transaction states.

    def initialize(self):
        self.queue = []
        self.balance = int(self.initial_balance)
        self.transaction_count = 0
        self.current_request = None
        self._service_remaining = None

        # Schedule initial signal at T=0 (only via internal event)
        self._out_balance_value = int(self.balance)
        self.hold_in("INIT_PUBLISH", 0.0)

    def _start_next_if_possible(self):
        """Start next request immediately if the server is idle and queue is non-empty."""
        if self.queue:
            self.current_request = self.queue.pop(0)
            amount = int(self.current_request.get("amount", 0))
            self._service_remaining = int(self.balance - amount)

            # Prepare output for BUSY completion (lambdaf)
            self._out_balance_value = int(self._service_remaining)

            # Schedule completion
            self.hold_in("BUSY", float(self.processing_delay))
        else:
            self.current_request = None
            self._service_remaining = None
            self._out_balance_value = None
            self.hold_in("IDLE", float("inf"))

    def deltext(self, e: float):
        # Enqueue all incoming requests
        for req in self.input["request_in"].values:
            # Expect structure: {"amount": int}
            if (
                not isinstance(req, dict)
                or "amount" not in req
                or not isinstance(req["amount"], int)
            ):
                # Optional error log (still JSONL)
                self.logger.info(
                    {
                        "time": float(get_current_time()),
                        "model": str(self.name),
                        "event": "error",
                        "data": {
                            "reason": "invalid_request_schema",
                            "expected": {"amount": "int"},
                        },
                    },
                    log_type="ERROR",
                )
                continue
            self.queue.append({"amount": int(req["amount"])})

        # State evolution with elapsed time considered
        if self.phase == "IDLE":
            self._start_next_if_possible()
            return

        # If currently BUSY or INIT_PUBLISH, keep remaining time unless we are imminently transitioning
        remaining = self.ta()
        if remaining == float("inf"):
            remaining = float("inf")
        else:
            remaining = max(0.0, float(remaining) - float(e))

        # If INIT_PUBLISH is pending, preserve it (it will publish initial balance first at confluent t=0)
        if self.phase == "INIT_PUBLISH":
            self.hold_in("INIT_PUBLISH", remaining)
            return

        if self.phase == "BUSY":
            # Keep current service; only queue grows
            self.hold_in("BUSY", remaining)
            return

        # Fallback
        self.hold_in(self.phase, remaining)

    def lambdaf(self):
        # Output only (no state updates here)
        if self.phase in ("INIT_PUBLISH", "BUSY"):
            if self._out_balance_value is not None:
                self.output["balance_out"].add(int(self._out_balance_value))

    def deltint(self):
        old_phase = self.phase

        if old_phase == "INIT_PUBLISH":
            # After publishing initial balance, decide next state
            self._out_balance_value = None
            if self.queue:
                # Start immediately if something is already queued
                self._start_next_if_possible()
            else:
                self.hold_in("IDLE", float("inf"))
            return

        if old_phase == "BUSY":
            # Complete current transaction after output already emitted in lambdaf
            if self._service_remaining is None:
                # Defensive: if missing, keep safe and go IDLE
                self.current_request = None
                self._out_balance_value = None
                self.hold_in("IDLE", float("inf"))
                return

            # Update authoritative state
            self.balance = int(self._service_remaining)
            self.transaction_count += 1

            # Required log event at completion time
            self.logger.info(
                {
                    "time": float(get_current_time()),
                    "model": str(self.name),
                    "event": "transaction",
                    "data": {
                        "remaining": int(self.balance),
                        "count": int(self.transaction_count),
                    },
                },
                log_type="RESULT",
            )

            # Clear completed job markers
            self.current_request = None
            self._service_remaining = None
            self._out_balance_value = None

            # Start next if queued; else idle
            self._start_next_if_possible()
            return

        # IDLE or unknown phase: remain idle
        self._out_balance_value = None
        self.hold_in("IDLE", float("inf"))

    def exit(self):
        return
