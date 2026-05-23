import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

class ServerReceiver(Atomic):
    """
    Function: 
        - Monitors 'packet_in' for incoming packets from the Sender.
        - Implements a fixed processing delay (default 3s) upon packet arrival.
        - Maintains an 'expected_bit' to implement the Alternating Bit Protocol (ABP).
        - If the received packet's bit matches 'expected_bit':
            - After processing, sends the packet to 'storage_out'.
            - Sends an ACK with the 'expected_bit' to 'ack_out'.
            - Flips the 'expected_bit' (0 -> 1 or 1 -> 0).
        - If the received packet's bit does not match 'expected_bit' (duplicate):
            - After processing, sends an ACK with the previous bit (1 - expected_bit) to 'ack_out'.
            - Does not forward the packet to storage.

    Logging in this model:
        - packet_received: Logged in deltext when a packet arrives.
            - seq (int): Sequence number of the packet.
            - bit (int): Protocol bit (0 or 1).
        - ack_sent_to_sender: Logged in deltint after the processing delay, when the ACK is sent.
            - bit (int): The bit value of the ACK sent.

    Input Ports:
        - packet_in (dict): Packet containing data from the Sender.
            structure:
                seq (int): Sequence number.
                bit (int): ABP bit (0 or 1).
            protocol: initialize: waiting ; process: 3s processing delay before ACK.

    Output Ports:
        - storage_out (dict): Valid packet forwarded to the StorageQueue.
            structure:
                seq (int): Sequence number.
                bit (int): ABP bit (0 or 1).
            protocol: initialize: idle ; process: sent only if bit matches expected_bit.
        - ack_out (dict): ACK packet sent back to the Sender.
            structure:
                bit (int): ACK bit (0 or 1).
            protocol: initialize: idle ; process: sent after 3s processing delay.
    """

    def __init__(self, name: str, parent: Coupled | None, processing_delay: float = 3000.0):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent model.
            processing_delay (float): Fixed delay in milliseconds for processing a packet.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Registration of Ports
        self.add_in_port(Port(dict, "packet_in"))
        self.add_out_port(Port(dict, "storage_out"))
        self.add_out_port(Port(dict, "ack_out"))

        # Configuration and State Initialization
        self.param = {
            "processing_delay": processing_delay
        }
        
        self.expected_bit = 0
        self.current_packet = None
        self.out_ack_payload = None
        self.out_storage_payload = None

        # Initial State
        self.hold_in("WAITING", float('inf'))
        
        self.logger.info({
            "event": "Model Created", 
            "name": self.name, 
            "expected_bit": self.expected_bit,
            "processing_delay": self.param["processing_delay"]
        }, log_type="PROCESS")

    def initialize(self):
        """Initialize the model state."""
        self.expected_bit = 0
        self.current_packet = None
        self.out_ack_payload = None
        self.out_storage_payload = None
        self.hold_in("WAITING", float('inf'))
        
        self.logger.info({
            "event": "Model Initialized", 
            "time": get_current_time()
        }, log_type="PROCESS")

    def deltext(self, e: float):
        """Handle incoming packets."""
        # Only process if we are currently waiting (simple 1-packet-at-a-time buffer for ABP)
        if self.phase == "WAITING":
            for packet in self.input["packet_in"].values:
                self.current_packet = packet
                
                # Log packet arrival
                self.logger.info({
                    "model": self.name,
                    "type": "packet_received",
                    "val": {
                        "seq": packet.get("seq"),
                        "bit": packet.get("bit")
                    },
                    "timestamp_ms": get_current_time()
                }, log_type="PROCESS")

                # Prepare outputs for the end of the processing delay
                received_bit = packet.get("bit")
                if received_bit == self.expected_bit:
                    # Valid Packet
                    self.out_ack_payload = {"bit": self.expected_bit}
                    self.out_storage_payload = {"seq": packet.get("seq"), "bit": packet.get("bit")}
                else:
                    # Duplicate Packet: Send ACK for the previous bit (which is 1 - expected_bit)
                    self.out_ack_payload = {"bit": 1 - self.expected_bit}
                    self.out_storage_payload = None
                
                self.hold_in("PROCESSING", self.param["processing_delay"])
                break # Process only one packet at a time as per ABP logic
        else:
            # If already processing, we maintain state (ABP Sender waits for ACK before sending next)
            self.hold_in(self.phase, self.ta() - e)

    def lambdaf(self):
        """Output ACK and Storage packet after processing delay."""
        if self.phase == "PROCESSING":
            if self.out_ack_payload is not None:
                self.output["ack_out"].add(self.out_ack_payload)
            
            if self.out_storage_payload is not None:
                self.output["storage_out"].add(self.out_storage_payload)

    def deltint(self):
        """Update state after sending outputs."""
        if self.phase == "PROCESSING":
            # Log the ACK event
            if self.out_ack_payload:
                self.logger.info({
                    "model": self.name,
                    "type": "ack_sent_to_sender",
                    "val": {"bit": self.out_ack_payload["bit"]},
                    "timestamp_ms": get_current_time()
                }, log_type="PROCESS")

            # If it was a valid packet, flip the expected bit
            if self.out_storage_payload is not None:
                self.expected_bit = 1 - self.expected_bit
            
            # Reset buffers and return to waiting
            self.current_packet = None
            self.out_ack_payload = None
            self.out_storage_payload = None
            self.hold_in("WAITING", float('inf'))

    def exit(self):
        """Cleanup."""
        self.logger.info({
            "event": "Model Finalized", 
            "name": self.name, 
            "final_expected_bit": self.expected_bit,
            "time": get_current_time()
        }, log_type="RESULT")