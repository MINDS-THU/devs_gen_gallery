import math
from collections import deque
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

class StorageQueue(Atomic):
    """
    Function: 
        - Acts as a FIFO buffer for packets received from ServerReceiver.
        - On 'packet_in', stores the packet in an internal deque.
        - On 'pop_request', if the queue is not empty, it prepares the oldest packet for output.
        - Maintains the 'is_empty' status for the ServerSender.

    Logging in this model:
        - No specific logging required by parent for this component.

    Input Ports:
        - packet_in (dict): Receives packets from ServerReceiver:storage_out.
            structure:
                seq (int): Sequence number.
                bit (int): Alternating bit.
            protocol: initialize: empty ; process: add to internal queue.
        - pop_request (bool): Receives requests from ServerSender:queue_pop_req.
            structure: bool
            protocol: initialize: waiting ; process: if queue not empty, trigger packet output.

    Output Ports:
        - packet_out (dict): Sends popped packet to ServerSender:queue_packet_in.
            structure:
                seq (int): Sequence number.
                bit (int): Alternating bit.
            protocol: initialize: idle ; process: output the popped packet.
        - is_empty (bool): Status signal to ServerSender:queue_empty_status.
            structure: bool
            protocol: initialize: True ; process: output True if queue is empty, False otherwise.
    """

    def __init__(self, name: str, parent: Coupled | None):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Register Ports
        self.add_in_port(Port(dict, "packet_in"))
        self.add_in_port(Port(bool, "pop_request"))
        self.add_out_port(Port(dict, "packet_out"))
        self.add_out_port(Port(bool, "is_empty"))

        # Internal State
        self.queue = deque()
        self.packet_to_emit = None
        self.status_to_emit = None
        
        # Parameters
        self.params = {}

        self.hold_in("IDLE", float('inf'))

    def initialize(self):
        """Initialize the model state."""
        self.queue = deque()
        self.packet_to_emit = None
        self.status_to_emit = None
        # Note: Specification says initial_signal is "no", so we don't send is_empty=True at t=0.
        self.hold_in("IDLE", float('inf'))

    def deltext(self, e: float):
        """Handle external packet arrivals or pop requests."""
        # Update sigma
        new_sigma = self.ta() - e
        
        # 1. Process packet arrivals
        packets = list(self.input["packet_in"].values)
        was_empty = len(self.queue) == 0
        for pkt in packets:
            self.queue.append(pkt)
        
        # 2. Process pop requests
        pop_requested = False
        for req in self.input["pop_request"].values:
            if req is True:
                pop_requested = True

        # Transition Logic
        if pop_requested and len(self.queue) > 0:
            # Prepare to pop and emit
            self.packet_to_emit = self.queue.popleft()
            self.status_to_emit = (len(self.queue) == 0)
            self.hold_in("EMITTING", 0)
        elif was_empty and len(self.queue) > 0:
            # Queue became non-empty, notify sender
            self.packet_to_emit = None
            self.status_to_emit = False
            self.hold_in("STATUS_UPDATE", 0)
        else:
            # Continue current state
            self.hold_in(self.phase, new_sigma)

    def deltint(self):
        """Internal transition after outputting."""
        # After emitting a packet or status, return to IDLE and wait for next event
        self.packet_to_emit = None
        self.status_to_emit = None
        self.hold_in("IDLE", float('inf'))

    def lambdaf(self):
        """Output the prepared packet and/or status."""
        if self.phase == "EMITTING":
            if self.packet_to_emit is not None:
                self.output["packet_out"].add(self.packet_to_emit)
            if self.status_to_emit is not None:
                self.output["is_empty"].add(self.status_to_emit)
        elif self.phase == "STATUS_UPDATE":
            if self.status_to_emit is not None:
                self.output["is_empty"].add(self.status_to_emit)

    def exit(self):
        """Cleanup on simulation end."""
        pass