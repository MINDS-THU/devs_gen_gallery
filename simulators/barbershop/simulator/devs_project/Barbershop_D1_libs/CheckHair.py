from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class CheckHair(Atomic):
    """
    Function:
        - Implements the `checkhair` module of `Barbershop_D1` as a coordinator between `reception` and `cuthair`.
        - State machine with `status` in {available, busy_consult, waiting_cut_done}.
        - State transitions and outputs:
            - available:
                - On receiving "newcust" via input port `in_cust`, updates tracked variable `customer` to "newcust",
                  transitions to busy_consult, and holds for exactly consult_time seconds.
            - busy_consult:
                - After exactly consult_time seconds, outputs "newcust" via output port `to_cut`,
                  then transitions to waiting_cut_done.
            - waiting_cut_done:
                - On receiving "done" via input port `in_done`, updates tracked variable `customer` to "done",
                  then outputs "done" via output port `to_reception`, and only after that output transitions back to available.

    Logging in this model:
        - State-change log when consultation starts:
            {"time": float, "type": "state", "model": "checkhair", "field": "customer", "value": "newcust"}
        - Message log when sending to cuthair:
            {"time": float, "type": "message", "model": "checkhair", "port": "to_cut", "content": "newcust"}
        - State-change log when cut is reported done:
            {"time": float, "type": "state", "model": "checkhair", "field": "customer", "value": "done"}
        - Message log when sending done notification to reception:
            {"time": float, "type": "message", "model": "checkhair", "port": "to_reception", "content": "done"}

    Input Ports:
      - in_cust (str): Customer token from reception. Must be the literal string "newcust" only.
        structure: str
        protocol: initialize: Ready to accept at T=0 because status starts available ; process: accept only when available.
      - in_done (str): Completion token from cutting. Must be the literal string "done" only.
        structure: str
        protocol: initialize: empty ; process: handled only when waiting_cut_done.

    Output Ports:
      - to_cut (str): Customer token forwarded to cutting. Must be the literal string "newcust" only.
        structure: str
        protocol: initialize: no pending sends ; process: emitted after exactly consult_time seconds of consultation.
      - to_reception (str): Availability notification to reception. Must be the literal string "done" only.
        structure: str
        protocol: initialize: no pending sends ; process: emitted immediately (sigma=0) after receiving "done" from cutting.
    """

    def __init__(self, name: str, parent: Coupled | None, consult_time: float):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            consult_time (float): Exact consultation time in seconds. Must be 7.0.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match specification)
        self.add_in_port(Port(str, "in_cust"))
        self.add_in_port(Port(str, "in_done"))
        self.add_out_port(Port(str, "to_cut"))
        self.add_out_port(Port(str, "to_reception"))

        # Internal hardcoded parameters and configuration
        self.param: dict = {
            "time_unit": "seconds"
        }
        if abs(consult_time - 7.0) > 1e-9:
            raise ValueError("consult_time must be exactly 7.0 seconds per specification.")
        self.consult_time: float = consult_time

        # Internal state variables
        self.status: str = "available"  # "available" | "busy_consult" | "waiting_cut_done"
        self.customer: str | None = None  # tracked variable for logging ("newcust" | "done")
        self._pending_out_to_cut: str | None = None
        self._pending_out_to_reception: str | None = None

        # For correct message logging after output has been emitted (in lambdaf)
        self._last_sent_port: str | None = None
        self._last_sent_content: str | None = None

        # Initial state scheduling
        self.hold_in("AVAILABLE", float("inf"))

    def initialize(self):
        self.status = "available"
        self.customer = None
        self._pending_out_to_cut = None
        self._pending_out_to_reception = None
        self._last_sent_port = None
        self._last_sent_content = None
        self.hold_in("AVAILABLE", float("inf"))

    def lambdaf(self):
        # Output only; no state updates here.
        if self.phase == "BUSY_CONSULT":
            # Consultation finished: forward to cutter.
            if self._pending_out_to_cut is not None:
                self.output["to_cut"].add(self._pending_out_to_cut)
                self._last_sent_port = "to_cut"
                self._last_sent_content = self._pending_out_to_cut

        elif self.phase == "SEND_DONE":
            # Notify reception that the full service is complete and checkhair becomes available.
            if self._pending_out_to_reception is not None:
                self.output["to_reception"].add(self._pending_out_to_reception)
                self._last_sent_port = "to_reception"
                self._last_sent_content = self._pending_out_to_reception

    def deltint(self):
        old_phase = self.phase

        # Log message-sends here (same simulation time as send), after lambdaf has executed.
        if self._last_sent_port is not None and self._last_sent_content is not None:
            self.logger.info(
                {
                    "time": float(get_current_time()),
                    "type": "message",
                    "model": "checkhair",
                    "port": str(self._last_sent_port),
                    "content": str(self._last_sent_content),
                },
                log_type="PROCESS",
            )
            self._last_sent_port = None
            self._last_sent_content = None

        if old_phase == "BUSY_CONSULT":
            # Consultation finished and customer was forwarded to cutter.
            self._pending_out_to_cut = None
            self.status = "waiting_cut_done"
            self.hold_in("WAITING_CUT_DONE", float("inf"))
            return

        if old_phase == "SEND_DONE":
            # Done notification sent; now become available again.
            self._pending_out_to_reception = None
            self.status = "available"
            self.hold_in("AVAILABLE", float("inf"))
            return

        # Default: stay as-is
        self.hold_in(self.phase, float("inf"))

    def deltext(self, e: float):
        # Maintain DEVS timing semantics by reducing remaining time when applicable.
        remaining = self.ta()
        if remaining != float("inf"):
            remaining = max(0.0, remaining - float(e))

        # 1) Handle incoming new customer tokens
        for token in self.input["in_cust"].values:
            if token == "newcust" and self.status == "available":
                # Accept exactly one customer
                self.status = "busy_consult"
                self.customer = "newcust"
                self._pending_out_to_cut = "newcust"

                # Log tracked variable change
                self.logger.info(
                    {
                        "time": float(get_current_time()),
                        "type": "state",
                        "model": "checkhair",
                        "field": "customer",
                        "value": "newcust",
                    },
                    log_type="PROCESS",
                )

                # Start consultation timer
                self.hold_in("BUSY_CONSULT", float(self.consult_time))
                return
            # else: ignore per spec (cannot accept)

        # 2) Handle done tokens from cutter
        for token in self.input["in_done"].values:
            if token == "done" and self.status == "waiting_cut_done":
                # Update tracked variable
                self.customer = "done"
                self.logger.info(
                    {
                        "time": float(get_current_time()),
                        "type": "state",
                        "model": "checkhair",
                        "field": "customer",
                        "value": "done",
                    },
                    log_type="PROCESS",
                )

                # Prepare immediate notification to reception
                self._pending_out_to_reception = "done"
                self.status = "available"  # becomes available only after the send; phase SEND_DONE enforces ordering
                self.hold_in("SEND_DONE", 0.0)
                return
            # else: ignore per spec

        # No accepted external event: keep current phase with adjusted remaining time (if not passive)
        self.hold_in(self.phase, remaining)

    def exit(self):
        # No additional logs required by specification.
        return