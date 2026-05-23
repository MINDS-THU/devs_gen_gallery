import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

class Receiver(Atomic):
    """
    Function: 
        - Receives data packets from the Server via SubnetB1.
        - Simulates a 10s (10000ms) processing delay for each received packet.
        - After processing, sends an ACK with the corresponding bit back to the Server via SubnetB2.
        - States:
            - IDLE: Waiting for a packet to arrive.
            - PROCESSING: Busy processing a packet for a fixed duration. After completion, outputs ACK.

    Logging in this model:
        - processing_started: Logged when a packet is received and the 10s delay begins.
            - seq (int): Sequence number of the packet.
            - duration (int): Processing time (10000).
        - ack_sent: Logged when the processing is complete and the ACK is sent.
            - bit (int): The bit value of the ACK.

    Input Ports:
        - packet_in (dict): Receives packets from Subnet_B1.
            structure:
                seq (int): Sequence number.
                bit (int): Alternating bit (0 or 1).
            protocol: initialize: enter IDLE state; process: handle packets one by one with 10s delay.

    Output Ports:
        - ack_out (dict): Sends ACKs to Subnet_B2.
            structure:
                bit (int): The bit being acknowledged.
            protocol: initialize: idle; process: emit ACK after 10s processing.
    """

    param = {
        "processing_duration": 10000.0  # 10 seconds in ms
    }

    def __init__(self, name: str, parent: Coupled | None):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent coupled model.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Register Ports
        self.add_in_port(Port(dict, "packet_in"))
        self.add_out_port(Port(dict, "ack_out"))

        # Internal State Variables
        self.processing_queue = []
        self.current_ack_payload = None

        # Log creation
        self.logger.info({"event": "Model Created", "name": self.name}, log_type="PROCESS")

    def initialize(self):
        """Initialize the model to IDLE state."""
        self.processing_queue = []
        self.current_ack_payload = None
        self.hold_in("IDLE", float('inf'))
        self.logger.info({"event": "Model Initialized", "state": self.phase}, log_type="PROCESS")

    def deltext(self, e: float):
        """Handle incoming packets."""
        # Get packets from input port
        packets = list(self.input["packet_in"].values)
        
        for pkt in packets:
            self.processing_queue.append(pkt)

        if self.phase == "IDLE" and self.processing_queue:
            # Start processing the first packet in queue
            target_pkt = self.processing_queue.pop(0)
            
            # Log processing start as per specification
            self.logger.info({
                "timestamp_ms": get_current_time(),
                "model": self.name,
                "type": "processing_started",
                "val": {"seq": target_pkt["seq"], "duration": int(self.param["processing_duration"])}
            }, log_type="PROCESS")

            # Prepare the ACK payload for the next lambdaf
            self.current_ack_payload = {"bit": target_pkt["bit"]}
            
            self.hold_in("PROCESSING", self.param["processing_duration"])
        else:
            # If already processing, just update sigma and wait
            self.hold_in(self.phase, self.ta() - e)

    def lambdaf(self):
        """Output the ACK after processing delay."""
        if self.phase == "PROCESSING" and self.current_ack_payload is not None:
            self.output["ack_out"].add(self.current_ack_payload)

    def deltint(self):
        """Transition after sending ACK."""
        if self.phase == "PROCESSING":
            # Log ACK sent as per specification
            self.logger.info({
                "timestamp_ms": get_current_time(),
                "model": self.name,
                "type": "ack_sent",
                "val": {"bit": self.current_ack_payload["bit"]}
            }, log_type="PROCESS")
            
            self.current_ack_payload = None

        # Check if there are more packets waiting in the queue
        if self.processing_queue:
            target_pkt = self.processing_queue.pop(0)
            
            self.logger.info({
                "timestamp_ms": get_current_time(),
                "model": self.name,
                "type": "processing_started",
                "val": {"seq": target_pkt["seq"], "duration": int(self.param["processing_duration"])}
            }, log_type="PROCESS")

            self.current_ack_payload = {"bit": target_pkt["bit"]}
            self.hold_in("PROCESSING", self.param["processing_duration"])
        else:
            self.hold_in("IDLE", float('inf'))

    def deltcon(self):
        """Handle confluent events: process internal transition then external."""
        self.deltint()
        self.deltext(0)

    def exit(self):
        """Cleanup on simulation end."""
        self.logger.info({"event": "Simulation Finished", "model": self.name}, log_type="RESULT")