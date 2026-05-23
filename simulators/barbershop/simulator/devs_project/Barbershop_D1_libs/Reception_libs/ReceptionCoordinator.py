from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class ReceptionCoordinator(Atomic):
    """
    Function:
        - Orchestrates reception check-in timing (exact delay), blocked/unblocked handoff logic, and checkhair availability tracking.
        - States and Output at the end of the state:
            - IDLE: No active check-in and not blocked; waits for queue updates or done notifications.
            - CHECKIN: A head-of-line customer is in the 5.0s check-in hold; emits no output at CHECKIN timeout.
              After CHECKIN completes, transitions immediately (sigma=0) to HANDOFF if possible, else to BLOCKED/IDLE.
            - HANDOFF: Emits the handoff to checkhair (`cust="newcust"`) and immediately commands waiting_area dequeue
              (`dequeue_cmd={"count": 1}`), then waits for a queue update (WAIT_QUEUE_UPDATE).
            - BLOCKED: Check-in has completed but cannot handoff because checkhair is unavailable; waits for `in_done="done"`.
              Upon receiving done, performs immediate HANDOFF at the same simulation time (sigma=0).
            - WAIT_QUEUE_UPDATE: After sending a dequeue command, waits for the next queue update; only then may start next CHECKIN.

    Logging in this model:
        - When sending `cust="newcust"` to checkhair:
            log_type: PROCESS
            msg (dict):
                time (float): Current simulation time at send.
                type (str): Literal "message".
                model (str): Literal "reception".
                port (str): Literal "cust".
                content (str): Literal "newcust".

    Input Ports:
      - in_done (str): Availability notification. Must be the literal string "done" only.
        structure: str
        protocol: initialize: no pending notifications; internal `checkhair_available` starts true at T=0 ; process: when "done" arrives, set available true and if blocked with queue_length>0, handoff immediately.
      - in_queue_update (dict): Queue status update.
        structure:
            queue_length (int): Current queue length after enqueue/dequeue; range 0..8.
        protocol: initialize: no updates at T=0 (queue assumed empty until first update) ; process: update local queue_length and decide whether to start CHECKIN when idle and not blocked, or after dequeue update.

    Output Ports:
      - cust (str): Customer token sent onward. Must be the literal string "newcust" only.
        structure: str
        protocol: initialize: no pending sends ; process: sent only after check-in completes and checkhair is available, or immediately upon receiving done if previously blocked.
      - dequeue_cmd (dict): Dequeue command to waiting_area.
        structure:
            count (int): Number of customers to remove; must always be 1.
        protocol: initialize: no pending commands ; process: sent immediately after each successful `cust` handoff.
    """

    def __init__(self, name: str, parent: Coupled | None, checkin_time: float):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            checkin_time (float): Exact check-in processing time in seconds. Must be 5.0.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match specification)
        self.add_in_port(Port(str, "in_done"))
        self.add_in_port(Port(dict, "in_queue_update"))
        self.add_out_port(Port(str, "cust"))
        self.add_out_port(Port(dict, "dequeue_cmd"))

        # Internal hardcoded parameters (not passed via __init__)
        self.param: dict = {
            "dequeue_count": 1
        }

        # Config
        self.checkin_time: float = float(checkin_time)

        # Internal state
        self.queue_length: int = 0
        self.checkhair_available: bool = True  # per spec: starts true at T=0

        self.processing: bool = False
        self.blocked: bool = False
        self.awaiting_dequeue_update: bool = False

        # Prepared outputs for lambdaf
        self._out_cust: str | None = None
        self._out_dequeue_cmd: dict | None = None

        # Start passive; initialize() will set the correct initial hold
        self.hold_in("IDLE", float("inf"))

    def initialize(self):
        # Per spec: checkhair_available = True at T=0, no initial signal required.
        self.queue_length = 0
        self.checkhair_available = True

        self.processing = False
        self.blocked = False
        self.awaiting_dequeue_update = False

        self._out_cust = None
        self._out_dequeue_cmd = None

        self.hold_in("IDLE", float("inf"))

    def _prepare_handoff_outputs(self):
        # Prepare payloads to be emitted in lambdaf during HANDOFF phase
        self._out_cust = "newcust"
        self._out_dequeue_cmd = {"count": int(self.param["dequeue_count"])}

    def _clear_prepared_outputs(self):
        self._out_cust = None
        self._out_dequeue_cmd = None

    def _maybe_start_checkin(self, remaining_sigma: float):
        # Start CHECKIN only if allowed by spec.
        if (not self.processing) and (not self.blocked) and (not self.awaiting_dequeue_update) and (self.queue_length > 0):
            self.processing = True
            self._clear_prepared_outputs()
            self.hold_in("CHECKIN", self.checkin_time)
        else:
            # Maintain current phase with updated remaining sigma
            self.hold_in(self.phase, remaining_sigma)

    def lambdaf(self):
        # Output only; no state changes here.
        if self.phase == "HANDOFF":
            if self._out_cust == "newcust":
                self.output["cust"].add(self._out_cust)
                # Required message log (only when sending to checkhair)
                self.logger.info(
                    {
                        "time": float(get_current_time()),
                        "type": "message",
                        "model": "reception",
                        "port": "cust",
                        "content": "newcust",
                    },
                    log_type="PROCESS",
                )
            if isinstance(self._out_dequeue_cmd, dict):
                self.output["dequeue_cmd"].add(self._out_dequeue_cmd)

    def deltint(self):
        # Internal transitions only (lambdaf already executed for the old phase).
        old_phase = self.phase

        if old_phase == "CHECKIN":
            # Check-in completed exactly now; decide whether to handoff or block.
            self.processing = False

            if self.queue_length > 0 and self.checkhair_available:
                # Perform immediate handoff at the same simulation time via HANDOFF (sigma=0).
                self.checkhair_available = False
                self.blocked = False
                self.awaiting_dequeue_update = True
                self._prepare_handoff_outputs()
                self.hold_in("HANDOFF", 0.0)
            else:
                # No handoff: either queue empty -> idle, or checkhair unavailable -> blocked if queue still has customers.
                self._clear_prepared_outputs()
                if self.queue_length > 0 and (not self.checkhair_available):
                    self.blocked = True
                    self.hold_in("BLOCKED", float("inf"))
                else:
                    self.blocked = False
                    self.hold_in("IDLE", float("inf"))

        elif old_phase == "HANDOFF":
            # Handoff/dequeue command already emitted; now wait for queue_update after dequeue.
            self._clear_prepared_outputs()
            self.hold_in("WAIT_QUEUE_UPDATE", float("inf"))

        else:
            # IDLE / BLOCKED / WAIT_QUEUE_UPDATE should have sigma=inf normally.
            self._clear_prepared_outputs()
            self.hold_in(old_phase, float("inf"))

    def deltext(self, e: float):
        # External transitions: handle queue updates and done notifications.
        remaining_sigma = max(0.0, float(self.ta()) - float(e))

        # 1) Process done notifications
        for msg in self.input["in_done"].values:
            if isinstance(msg, str) and msg == "done":
                self.checkhair_available = True

        # 2) Process queue length updates (keep the latest)
        got_queue_update = False
        for q_update in self.input["in_queue_update"].values:
            if isinstance(q_update, dict) and ("queue_length" in q_update) and isinstance(q_update["queue_length"], int):
                self.queue_length = int(q_update["queue_length"])
                got_queue_update = True

        # Clear awaiting_dequeue_update when we receive a queue update after a handoff+dequeue.
        if self.awaiting_dequeue_update and got_queue_update:
            self.awaiting_dequeue_update = False

        # If blocked and now checkhair is available and there is a customer waiting, handoff immediately.
        # (Spec: retry handoff ONLY when done received; done sets checkhair_available True and triggers this.)
        if self.blocked and self.checkhair_available and (self.queue_length > 0):
            self.checkhair_available = False
            self.blocked = False
            self.awaiting_dequeue_update = True
            self.processing = False
            self._prepare_handoff_outputs()
            self.hold_in("HANDOFF", 0.0)
            return

        # If currently CHECKIN, just continue CHECKIN with updated remaining time (no restart).
        if self.phase == "CHECKIN":
            self.hold_in("CHECKIN", remaining_sigma)
            return

        # Otherwise, maybe start a new check-in if allowed.
        self._maybe_start_checkin(remaining_sigma)

    def exit(self):
        # No additional logs required by specification for this model.
        return