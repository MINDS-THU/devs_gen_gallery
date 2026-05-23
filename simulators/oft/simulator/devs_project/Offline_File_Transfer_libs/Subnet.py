import math
from collections import deque
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

class Subnet(Atomic):
    """
    Function: 
        - FIFO queue logic that imposes a fixed delay on any data passing from 'in' to 'out'.
        - Acts as a reliable transmission medium with a constant latency.
        - States:
            - IDLE: No packets are currently in transit.
            - BUSY: One or more packets are currently being delayed. When the delay for the head packet expires, it is output.

    Logging in this model:
        - event: Subnet Created
            log_type: PROCESS
            msg (dict): Initialization parameters.
                delay (float): The fixed delay value.
        - event: Subnet Initialized
            log_type: PROCESS
            msg (dict): Status at start.

    Input Ports:
      - in (dict): Receives data to be delayed.
        structure:
            seq (int): Sequence number of the packet.
            bit (int): Alternating bit (0 or 1).
            is_retry (bool): Whether the packet is a retransmission (optional).
        protocol: initialize: empty ; process: Receives data to be delayed.

    Output Ports:
      - out (dict): Sends data after fixed delay.
        structure:
            seq (int): Sequence number of the packet.
            bit (int): Alternating bit (0 or 1).
            is_retry (bool): Whether the packet is a retransmission (optional).
        protocol: initialize: idle ; process: Sends data after 3s delay.
    """

    def __init__(self, name: str, parent: Coupled | None, delay: float):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            delay (float): Delay in milliseconds (fixed at 3000).
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Register Ports
        self.add_in_port(Port(dict, "in"))
        self.add_out_port(Port(dict, "out"))

        # Configuration
        self.params = {
            "delay": delay
        }

        # Internal State: Queue of (delivery_time, packet)
        self.transit_queue = deque()
        self.next_output_packet = None

        self.logger.info({"event": "Subnet Created", "params": self.params}, log_type="PROCESS")
        self.hold_in("IDLE", float('inf'))

    def initialize(self):
        """Initialize the subnet state."""
        self.transit_queue = deque()
        self.next_output_packet = None
        self.logger.info({"event": "Subnet Initialized", "time": get_current_time()}, log_type="PROCESS")
        self.hold_in("IDLE", float('inf'))

    def deltext(self, e: float):
        """Handle incoming packets and schedule their departure."""
        current_time = get_current_time()
        
        # Process all incoming packets
        for packet in self.input["in"].values:
            delivery_time = current_time + self.params["delay"]
            self.transit_queue.append((delivery_time, packet))

        # Update sigma based on the head of the queue
        if self.transit_queue:
            next_delivery_time, next_packet = self.transit_queue[0]
            # Preparation for lambdaf
            self.next_output_packet = next_packet
            new_sigma = max(0.0, next_delivery_time - current_time)
            self.hold_in("BUSY", new_sigma)
        else:
            self.hold_in("IDLE", float('inf'))

    def lambdaf(self):
        """Output the packet that has finished its delay."""
        if self.phase == "BUSY" and self.next_output_packet is not None:
            self.output["out"].add(self.next_output_packet)

    def deltint(self):
        """Remove the sent packet and schedule the next one if available."""
        if self.transit_queue:
            # Remove the packet that was just sent via lambdaf
            self.transit_queue.popleft()

        if self.transit_queue:
            current_time = get_current_time()
            next_delivery_time, next_packet = self.transit_queue[0]
            self.next_output_packet = next_packet
            new_sigma = max(0.0, next_delivery_time - current_time)
            self.hold_in("BUSY", new_sigma)
        else:
            self.next_output_packet = None
            self.hold_in("IDLE", float('inf'))

    def deltcon(self):
        """Confluent transition: process internal departure then external arrival."""
        self.deltint()
        self.deltext(0)

    def exit(self):
        """Cleanup subnet."""
        self.logger.info({"event": "Subnet Finalized", "name": self.name}, log_type="PROCESS")