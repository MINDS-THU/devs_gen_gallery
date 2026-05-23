import math
from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class WaitingArea(Atomic):
    """
    Function:
        - Manages the reception waiting-area FIFO queue and enforces a strict capacity limit.
        - States and Output at the end of the state:
            - IDLE: Waits for external events (arrivals and dequeue commands). No output.
            - SEND_UPDATE: Outputs one or more queued `queue_update` dict(s) (prepared earlier by deltext),
              then transitions back to IDLE.

    Logging in this model:
        - event: Accepted arrival enqueue (queue length increases)
            log_type: PROCESS
            msg (dict):
                time (float): Current simulation time.
                type (str): Literal "state".
                model (str): Must be exactly "reception".
                field (str): Must be exactly "total customers num".
                value (int): Current queue length after enqueue (0..8).
        - event: Successful dequeue (queue length decreases)
            log_type: PROCESS
            msg (dict): Same structure as above, with value after dequeue.
        - Important: No logs are emitted when arrivals are ignored due to full capacity, or when dequeue
          command is received while queue is empty.

    Input Ports:
      - in_newcust (str): Arrival token from [Parent/Reception: in_newcust].
        structure:
            (str): Must be the literal string "newcust" only.
        protocol: initialize: empty queue at T=0 ; process: if queue length < capacity, enqueue and notify
      - in_dequeue (dict): Dequeue command from [Sibling-reception_coordinator: dequeue_cmd].
        structure:
            count (int): Number of customers to remove from the front; must always be 1 in this model.
        protocol: initialize: no pending dequeue ; process: if count==1 and queue non-empty, dequeue and notify

    Output Ports:
      - queue_update (dict): Queue length update to [Sibling-reception_coordinator: in_queue_update].
        structure:
            queue_length (int): Current queue length after an enqueue/dequeue operation; range 0..8.
        protocol: initialize: no pending updates ; process: emitted immediately after each accepted enqueue
                  and each successful dequeue
    """

    def __init__(self, name: str, parent: Coupled | None, capacity: int):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent model. If None, the model is a root model.
            capacity (int): Maximum number of customers allowed in the waiting area including any being checked in.
                Must be 8.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        if capacity != 8:
            raise ValueError("WaitingArea.capacity must be 8 as required by the specification.")
        self.capacity = capacity

        # Ports (must match specification)
        self.add_in_port(Port(str, "in_newcust"))
        self.add_in_port(Port(dict, "in_dequeue"))
        self.add_out_port(Port(dict, "queue_update"))

        # Internal hardcoded parameters
        self.param = {
            "infinity": float("inf")
        }

        # Internal state
        self.queue: list[str] = []
        self._pending_updates: list[dict] = []

        self.hold_in("IDLE", self.param["infinity"])

    def initialize(self):
        self.queue = []
        self._pending_updates = []
        self.hold_in("IDLE", self.param["infinity"])

    def _log_queue_length_state(self):
        self.logger.info(
            {
                "time": float(get_current_time()),
                "type": "state",
                "model": "reception",
                "field": "total customers num",
                "value": int(len(self.queue)),
            },
            log_type="PROCESS",
        )

    def deltext(self, e: float):
        # Process external events; if any queue change occurs, schedule immediate output.
        changed = False

        # 1) Process dequeue commands first (free space before accepting new arrivals at same sim time)
        for cmd in self.input["in_dequeue"].values:
            if not isinstance(cmd, dict):
                continue
            count = cmd.get("count", None)
            if isinstance(count, int) and count == 1 and len(self.queue) > 0:
                # Dequeue exactly one
                self.queue.pop(0)
                self._log_queue_length_state()
                self._pending_updates.append({"queue_length": int(len(self.queue))})
                changed = True

        # 2) Process arrivals
        for token in self.input["in_newcust"].values:
            if not isinstance(token, str):
                continue
            if token != "newcust":
                continue

            if len(self.queue) < self.capacity:
                self.queue.append("newcust")
                self._log_queue_length_state()
                self._pending_updates.append({"queue_length": int(len(self.queue))})
                changed = True
            else:
                # Ignore when full: no state/log/output changes
                pass

        # Schedule next internal event
        if changed:
            self.hold_in("SEND_UPDATE", 0.0)
        else:
            # Maintain phase with reduced remaining time
            remaining = self.ta()
            if remaining == float("inf"):
                self.hold_in(self.phase, float("inf"))
            else:
                self.hold_in(self.phase, max(0.0, remaining - float(e)))

    def lambdaf(self):
        # Output only; no state changes here.
        if self.phase == "SEND_UPDATE":
            for upd in self._pending_updates:
                self.output["queue_update"].add(upd)

    def deltint(self):
        # Internal transition after output has been emitted.
        if self.phase == "SEND_UPDATE":
            self._pending_updates = []
            self.hold_in("IDLE", self.param["infinity"])
        else:
            self.hold_in("IDLE", self.param["infinity"])

    def exit(self):
        # No final logs in this child (spec restricts output to state logs only).
        return