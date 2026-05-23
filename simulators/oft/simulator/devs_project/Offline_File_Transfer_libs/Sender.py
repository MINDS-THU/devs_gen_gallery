import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

class Sender(Atomic):
    """
    Function:
        - Maintains 'total_packets_to_send' and 'current_bit' (starts at 0).
        - Upon receiving 'control N' from 'control_in', increments 'total_packets_to_send'.
        - Preparation: 10s delay (10000ms) before sending a new packet.
        - ABP Logic: Send Packet(seq, bit) to 'packet_out'. Start 20s (20000ms) timeout timer.
        - On ACK(bit) from 'ack_in' == current_bit: Stop timer, flip 'current_bit', decrement 'total_packets_to_send'.
        - If packets remain, repeat preparation; otherwise, go to IDLE.
        - On Timeout: Retransmit current Packet and restart 20s timer.

    Logging in this model:
        - control_cmd: Logged when control_in receives a command.
            added (int): Packets added in this command.
            total_remaining (int): Total packets now in queue.
        - preparation_started: Logged when the 10s preparation phase begins.
            duration (int): Fixed at 10000.
        - packet_sent: Logged when a packet is emitted.
            seq (int): Current sequence number.
            bit (int): Current ABP bit (0 or 1).
            is_retry (bool): True if this is a retransmission.
        - ack_received: Logged when any ACK is received.
            bit (int): The bit contained in the ACK.
        - timeout: Logged when the 20s retransmission timer expires.
            seq (int): Sequence number of the timed-out packet.

    Input Ports:
        - control_in (int): Integer N representing packets to add.
            protocol: initialize: idle ; process: increment total_packets_to_send and trigger preparation if idle.
        - ack_in (dict): ACK packet.
            structure:
                bit (int): The sequence bit being acknowledged.
            protocol: initialize: waiting ; process: if bit matches current_bit, move to next packet.

    Output Ports:
        - packet_out (dict): Data packet sent to Subnet.
            structure:
                seq (int): Sequence number.
                bit (int): ABP bit.
            protocol: initialize: idle ; process: sends packet after preparation or timeout.
    """

    param = {
        "prep_duration": 10000.0,
        "timeout_duration": 20000.0
    }

    def __init__(self, name: str, parent: Coupled | None = None):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent model.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports
        self.add_in_port(Port(int, "control_in"))
        self.add_in_port(Port(dict, "ack_in"))
        self.add_out_port(Port(dict, "packet_out"))

        # Internal State Variables
        self.total_packets_to_send = 0
        self.current_seq = 1
        self.current_bit = 0
        self.is_retry = False
        self.next_output = None

        self.logger.info({"event": "Model Created", "name": name}, log_type="PROCESS")

    def initialize(self):
        self.total_packets_to_send = 0
        self.current_seq = 1
        self.current_bit = 0
        self.is_retry = False
        self.next_output = None
        self.hold_in("IDLE", float('inf'))

    def deltext(self, e: float):
        # Handle control commands
        control_vals = list(self.input["control_in"].values)
        if control_vals:
            added = sum(control_vals)
            self.total_packets_to_send += added
            self.logger.info({
                "model": "sender",
                "type": "control_cmd",
                "val": {"added": added, "total_remaining": self.total_packets_to_send},
                "timestamp_ms": get_current_time()
            }, log_type="PROCESS")

        # Handle ACKs
        ack_received_valid = False
        for ack in self.input["ack_in"].values:
            self.logger.info({
                "model": "sender",
                "type": "ack_received",
                "val": {"bit": ack["bit"]},
                "timestamp_ms": get_current_time()
            }, log_type="PROCESS")
            
            if self.phase == "WAITING_ACK" and ack["bit"] == self.current_bit:
                ack_received_valid = True

        # State Transition Logic
        if ack_received_valid:
            self.total_packets_to_send -= 1
            self.current_bit = 1 - self.current_bit
            self.current_seq += 1
            self.is_retry = False
            if self.total_packets_to_send > 0:
                self.logger.info({
                    "model": "sender",
                    "type": "preparation_started",
                    "val": {"duration": int(self.param["prep_duration"])},
                    "timestamp_ms": get_current_time()
                }, log_type="PROCESS")
                self.hold_in("PREPARING", self.param["prep_duration"])
            else:
                self.hold_in("IDLE", float('inf'))
        elif self.phase == "IDLE" and self.total_packets_to_send > 0:
            self.logger.info({
                "model": "sender",
                "type": "preparation_started",
                "val": {"duration": int(self.param["prep_duration"])},
                "timestamp_ms": get_current_time()
            }, log_type="PROCESS")
            self.hold_in("PREPARING", self.param["prep_duration"])
        else:
            # Continue current phase
            self.hold_in(self.phase, self.ta() - e)

    def deltint(self):
        if self.phase == "PREPARING":
            # Preparation finished, move to sending
            self.next_output = {"seq": self.current_seq, "bit": self.current_bit}
            # hold_in(phase, 0) to trigger lambdaf immediately
            self.hold_in("SENDING", 0)
        
        elif self.phase == "SENDING":
            # Packet was sent in lambdaf, now wait for ACK or timeout
            self.hold_in("WAITING_ACK", self.param["timeout_duration"])
            
        elif self.phase == "WAITING_ACK":
            # Timeout occurred
            self.logger.info({
                "model": "sender",
                "type": "timeout",
                "val": {"seq": self.current_seq},
                "timestamp_ms": get_current_time()
            }, log_type="PROCESS")
            self.is_retry = True
            self.next_output = {"seq": self.current_seq, "bit": self.current_bit}
            self.hold_in("SENDING", 0)

    def lambdaf(self):
        if self.phase == "SENDING":
            self.output["packet_out"].add(self.next_output)
            self.logger.info({
                "model": "sender",
                "type": "packet_sent",
                "val": {
                    "seq": self.next_output["seq"], 
                    "bit": self.next_output["bit"], 
                    "is_retry": self.is_retry
                },
                "timestamp_ms": get_current_time()
            }, log_type="PROCESS")

    def exit(self):
        self.logger.info({
            "event": "Sender finalized",
            "remaining": self.total_packets_to_send,
            "timestamp_ms": get_current_time()
        }, log_type="RESULT")