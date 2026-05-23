import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

class PalletQueue(Atomic):
    """
    Function: 
        - Maintains a FIFO queue of pallets received from PalletFacility.
        - Active Expiration: Monitors the head of the queue. If current_time reaches a pallet's expiration_time, 
          the pallet is removed immediately and a 'pallet_expired' event is logged.
        - Responds to 'request_pallet' from the Coordinator: if the queue is not empty, it pops the head and sends it.
        - Notifies 'queue_status' (size) after any change (arrival, expiration, or removal).

    Logging in this model:
        - pallet_queued: Triggered when a pallet enters the queue.
            time (float): Simulation time.
            entity (str): 'queue'
            payload (dict):
                pallet_id (int): ID of the pallet.
                queue_size (int): Size after arrival.
        - pallet_expired: Triggered when a pallet's deadline is reached.
            time (float): Simulation time.
            entity (str): 'queue'
            payload (dict):
                pallet_id (int): ID of the expired pallet.
                total_expired (int): Cumulative count of expired pallets.

    Input Ports:
        - pallet_in (dict): Receives pallets from PalletFacility.
            structure:
                pallet_id (int): Unique ID.
                expiration_time (float): Absolute deadline time.
                generation_time (float): Time of creation.
            protocol: initialize: empty ; process: add to FIFO.
        - request_pallet (bool): Trigger from Coordinator to release a pallet.
            structure: bool
            protocol: initialize: waiting ; process: if queue not empty, pop and output.

    Output Ports:
        - pallet_out (dict): Sends the popped pallet to Coordinator.
            structure: same as pallet_in.
            protocol: initialize: idle ; process: sends pallet data.
        - queue_status (int): Current size of the queue.
            structure: int
            protocol: initialize: 0 ; process: sends size after any change.
    """

    def __init__(self, name: str, parent: Coupled | None):
        """
        Args:
            name (str): Unique name of the model instance.
            parent (Coupled | None): The parent model.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports
        self.add_in_port(Port(dict, "pallet_in"))
        self.add_in_port(Port(bool, "request_pallet"))
        self.add_out_port(Port(dict, "pallet_out"))
        self.add_out_port(Port(int, "queue_status"))

        # Internal State
        self.queue = []  # List of dicts
        self.total_expired = 0
        self.out_payload_pallet = None
        self.out_payload_status = None
        
        # Parameters
        self.params = {}

        self.logger.info({"event": "Model Created", "name": self.name}, log_type="PROCESS")

    def initialize(self):
        self.queue = []
        self.total_expired = 0
        self.out_payload_pallet = None
        self.out_payload_status = None
        self.hold_in("IDLE", float('inf'))
        self.logger.info({"event": "Model Initialized", "time": get_current_time()}, log_type="PROCESS")

    def _get_next_expiration_sigma(self):
        """Helper to calculate time until the next pallet expires."""
        if not self.queue:
            return float('inf')
        # Pallets are FIFO, and expiration is typically generation + constant, 
        # so the head is usually the first to expire.
        now = get_current_time()
        # Find the minimum expiration time in the queue to be safe
        next_expiry = min(p['expiration_time'] for p in self.queue)
        return max(0.0, next_expiry - now)

    def lambdaf(self):
        if self.phase == "SENDING_PALLET":
            if self.out_payload_pallet:
                self.output["pallet_out"].add(self.out_payload_pallet)
            if self.out_payload_status is not None:
                self.output["queue_status"].add(self.out_payload_status)
        elif self.phase in ["SENDING_STATUS", "EXPIRING"]:
            if self.out_payload_status is not None:
                self.output["queue_status"].add(self.out_payload_status)

    def deltint(self):
        now = get_current_time()
        
        if self.phase == "EXPIRING":
            # Remove all pallets that have expired at this time
            expired_pallets = [p for p in self.queue if p['expiration_time'] <= now + 1e-9]
            for p in expired_pallets:
                self.queue.remove(p)
                self.total_expired += 1
                self.logger.info({
                    "time": now,
                    "entity": "queue",
                    "event": "pallet_expired",
                    "payload": {"pallet_id": p['pallet_id'], "total_expired": self.total_expired}
                }, log_type="PROCESS")
            
            # After expiration, we must notify the new status
            self.out_payload_status = len(self.queue)
            self.hold_in("SENDING_STATUS", 0)
            return

        # If we just finished sending a pallet or status, go back to monitoring
        sigma = self._get_next_expiration_sigma()
        if sigma == float('inf'):
            self.hold_in("IDLE", float('inf'))
        else:
            self.hold_in("MONITORING", sigma)

    def deltext(self, e):
        now = get_current_time()
        
        # Handle Arrivals
        new_pallets = list(self.input["pallet_in"].values)
        if new_pallets:
            for p in new_pallets:
                self.queue.append(p)
                self.logger.info({
                    "time": now,
                    "entity": "queue",
                    "event": "pallet_queued",
                    "payload": {"pallet_id": p['pallet_id'], "queue_size": len(self.queue)}
                }, log_type="PROCESS")
            
            # Status changed due to arrival
            self.out_payload_status = len(self.queue)
            self.hold_in("SENDING_STATUS", 0)
            return

        # Handle Requests
        requests = list(self.input["request_pallet"].values)
        if requests and any(requests):
            if self.queue:
                self.out_payload_pallet = self.queue.pop(0)
                self.out_payload_status = len(self.queue)
                self.hold_in("SENDING_PALLET", 0)
            else:
                # Request ignored if empty, but stay in current state minus elapsed
                sigma = self.ta() - e
                self.hold_in(self.phase, sigma)
            return

        # If no specific logic triggered, just update sigma
        sigma = self.ta() - e
        # Check if an expiration is due now (can happen if e was large)
        if self._get_next_expiration_sigma() <= 0:
            self.hold_in("EXPIRING", 0)
        else:
            self.hold_in(self.phase, sigma)

    def deltcon(self):
        """Internal (expiration) happens before External (request)."""
        self.deltint()
        self.deltext(0)

    def exit(self):
        self.logger.info({
            "event": "Simulation Finished",
            "total_expired": self.total_expired,
            "remaining_in_queue": len(self.queue),
            "time": get_current_time()
        }, log_type="RESULT")