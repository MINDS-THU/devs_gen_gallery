import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class ServerSender(Atomic):
    """
    Function:
        - Manages the download valve state based on 'request_in' (1=allowed, 0=forbidden).
        - Logic to initiate forwarding: If download_allowed is True AND StorageQueue is not empty AND not waiting for an ACK, send 'pop_request' to StorageQueue.
        - ABP Forwarding: Upon receiving packet from queue, send to 'packet_forward_out' and wait for ACK on 'ack_forward_in'.
        - Valve Integrity: If download_allowed becomes False, it must finish the current packet-ACK exchange before stopping further transmissions.

    Logging in this model:
        - download_valve_change: Logged when the download_allowed state is toggled.
            allowed (bool): True if download is enabled, False otherwise.
        - packet_forwarded: Logged when a packet is sent to the receiver.
            seq (int): Sequence number of the packet.
            bit (int): ABP bit of the packet.
        - ack_received_from_receiver: Logged when a valid ACK is received from the receiver.
            bit (int): The bit contained in the ACK.

    Input Ports:
        - request_in (int): 1 for allowed, 0 for forbidden.
            protocol: initialization: 0 ; process: updates internal download_allowed flag.
        - queue_packet_in (dict): Packet containing: 'seq' (int), 'bit' (int).
            protocol: initialization: waiting ; process: triggers forwarding logic.
        - queue_empty_status (bool): Status of the sibling queue.
            protocol: initialization: True ; process: used to decide if a pop request should be sent.
        - ack_forward_in (dict): ACK packet containing: 'bit' (int).
            protocol: initialization: waiting ; process: completes the current ABP cycle.

    Output Ports:
        - queue_pop_req (bool): Signal to pop packet.
            protocol: initialization: idle ; process: sent to StorageQueue to fetch next packet.
        - packet_forward_out (dict): Packet containing: 'seq' (int), 'bit' (int).
            protocol: initialization: idle ; process: sends packet to the receiver.
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
        self.add_in_port(Port(int, "request_in"))
        self.add_in_port(Port(dict, "queue_packet_in"))
        self.add_in_port(Port(bool, "queue_empty_status"))
        self.add_in_port(Port(dict, "ack_forward_in"))

        self.add_out_port(Port(bool, "queue_pop_req"))
        self.add_out_port(Port(dict, "packet_forward_out"))

        # Internal State Variables
        self.download_allowed = False
        self.queue_is_empty = True
        self.waiting_for_ack = False
        self.pending_close = False
        self.close_packet_in_flight = False

        # Payload buffers for lambdaf
        self.next_pop_req = None
        self.next_packet_to_forward = None

        # State initialization
        self.hold_in("IDLE", float("inf"))

    def initialize(self):
        self.download_allowed = False
        self.queue_is_empty = True
        self.waiting_for_ack = False
        self.pending_close = False
        self.close_packet_in_flight = False
        self.next_pop_req = None
        self.next_packet_to_forward = None
        self.hold_in("IDLE", float("inf"))

    def _log_valve_change(self):
        self.logger.info(
            {
                "timestamp_ms": get_current_time(),
                "model": self.name,
                "type": "download_valve_change",
                "val": {"allowed": self.download_allowed},
            },
            log_type="PROCESS",
        )

    def deltext(self, e: float):
        # Handle request_in
        for val in self.input["request_in"].values:
            new_allowed = val == 1
            if new_allowed != self.download_allowed:
                if not new_allowed and (
                    self.waiting_for_ack
                    or self.phase in ["SENDING_PKT", "WAITING_FOR_PKT"]
                ):
                    # Finish draining at most one already-admitted packet before closing the valve.
                    self.pending_close = True
                else:
                    self.pending_close = False
                    self.close_packet_in_flight = False
                    self.download_allowed = new_allowed
                    self._log_valve_change()

        # Handle queue_empty_status
        for status in self.input["queue_empty_status"].values:
            self.queue_is_empty = status

        # Handle queue_packet_in
        for pkt in self.input["queue_packet_in"].values:
            if self.phase == "WAITING_FOR_PKT":
                self.next_packet_to_forward = pkt
                self.hold_in("SENDING_PKT", 0)
                return

        # Handle ack_forward_in
        for ack in self.input["ack_forward_in"].values:
            if self.waiting_for_ack:
                self.logger.info(
                    {
                        "timestamp_ms": get_current_time(),
                        "model": self.name,
                        "type": "ack_received_from_receiver",
                        "val": {"bit": ack["bit"]},
                    },
                    log_type="PROCESS",
                )
                self.waiting_for_ack = False
                if self.pending_close and self.close_packet_in_flight:
                    self.pending_close = False
                    self.close_packet_in_flight = False
                    self.download_allowed = False
                    self._log_valve_change()
                # After ACK, check if we can continue
                break

        # Decision Logic for next state
        if (
            not self.waiting_for_ack
            and self.download_allowed
            and not self.queue_is_empty
            and self.phase not in ["SENDING_PKT", "SENDING_POP"]
        ):
            self.next_pop_req = True
            self.hold_in("SENDING_POP", 0)
        elif self.phase == "SENDING_PKT":
            self.hold_in("SENDING_PKT", self.ta() - e)
        elif self.phase == "SENDING_POP":
            self.hold_in("SENDING_POP", self.ta() - e)
        elif self.waiting_for_ack:
            self.hold_in("WAITING_FOR_ACK", float("inf"))
        else:
            self.hold_in("IDLE", float("inf"))

    def deltint(self):
        if self.phase == "SENDING_POP":
            self.next_pop_req = None
            self.hold_in("WAITING_FOR_PKT", float("inf"))
        elif self.phase == "SENDING_PKT":
            self.logger.info(
                {
                    "timestamp_ms": get_current_time(),
                    "model": self.name,
                    "type": "packet_forwarded",
                    "val": {
                        "seq": self.next_packet_to_forward["seq"],
                        "bit": self.next_packet_to_forward["bit"],
                    },
                },
                log_type="PROCESS",
            )
            if self.pending_close:
                self.close_packet_in_flight = True
            self.next_packet_to_forward = None
            self.waiting_for_ack = True
            self.hold_in("WAITING_FOR_ACK", float("inf"))
        else:
            self.hold_in("IDLE", float("inf"))

    def lambdaf(self):
        if self.phase == "SENDING_POP":
            self.output["queue_pop_req"].add(self.next_pop_req)
        elif self.phase == "SENDING_PKT":
            self.output["packet_forward_out"].add(self.next_packet_to_forward)

    def deltcon(self):
        # Process internal (finish sending) then external (new requests/status)
        self.deltint()
        self.deltext(0)

    def exit(self):
        pass
