from xdevs.models import Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

# Sub-model imports
from .Server_libs.ServerReceiver import ServerReceiver
from .Server_libs.StorageQueue import StorageQueue
from .Server_libs.ServerSender import ServerSender

class Server(Coupled):
    """
    Function: 
      - Acts as a buffering and forwarding node in a dual-loop ABP system.
      - Decouples the upload process from the download process using an internal FIFO queue.
      - Sub-models: 
        - ServerReceiver: name=server_receiver. Handles ABP ingress and 3s processing delay.
        - StorageQueue: name=storage_queue. FIFO buffer for received packets.
        - ServerSender: name=server_sender. Handles ABP egress and download valve logic.

    Logging in this model:
      - event: Model Created
        log_type: PROCESS
        msg (dict): Initialization parameters.
          processing_delay (float): Delay for the receiver component.

    Input Ports:
      - packet_in (dict): Incoming packet from Subnet A1.
        seq (int): Sequence number.
        bit (int): Alternating bit (0 or 1).
        protocol: initialize: waiting ; process: triggers 3s processing in ServerReceiver.
      - request_in (int): Download valve control signal.
        - (int): 1 for allowed (True), 0 for forbidden (False).
        protocol: initialize: 0 ; process: toggles download_allowed in ServerSender.
      - ack_forward_in (dict): ACK packet from Subnet B2 (Receiver side).
        bit (int): ACK bit value.
        protocol: initialize: waiting ; process: completes ABP cycle in ServerSender.

    Output Ports:
      - ack_out (dict): ACK packet to Subnet A2 (Sender side).
        bit (int): ACK bit value.
        protocol: initialize: idle ; process: sent after ServerReceiver processing.
      - packet_forward_out (dict): Forwarded packet to Subnet B1.
        seq (int): Sequence number.
        bit (int): Alternating bit.
        protocol: initialize: idle ; process: sent when valve is open and queue is non-empty.
    """

    def __init__(self, name: str, parent: Coupled | None, processing_delay: float = 3000.0):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent model.
            processing_delay (float): Fixed delay in ms for processing a packet in the receiver.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # 1. Register Ports
        self.add_in_port(Port(dict, "packet_in"))
        self.add_in_port(Port(int, "request_in"))
        self.add_in_port(Port(dict, "ack_forward_in"))
        
        self.add_out_port(Port(dict, "ack_out"))
        self.add_out_port(Port(dict, "packet_forward_out"))

        # 2. Instantiate Components
        receiver = ServerReceiver(
            name="server_receiver",
            parent=self,
            processing_delay=processing_delay
        )
        
        queue = StorageQueue(
            name="storage_queue",
            parent=self
        )
        
        sender = ServerSender(
            name="server_sender",
            parent=self
        )

        self.add_component(receiver)
        self.add_component(queue)
        self.add_component(sender)

        # 3. Define Couplings
        
        # EIC: External Input Couplings
        self.add_coupling(self.input["packet_in"], receiver.input["packet_in"])
        self.add_coupling(self.input["request_in"], sender.input["request_in"])
        self.add_coupling(self.input["ack_forward_in"], sender.input["ack_forward_in"])

        # IC: Internal Couplings
        # Receiver -> Queue
        self.add_coupling(receiver.output["storage_out"], queue.input["packet_in"])
        
        # Sender <-> Queue (Handshake)
        self.add_coupling(sender.output["queue_pop_req"], queue.input["pop_request"])
        self.add_coupling(queue.output["packet_out"], sender.input["queue_packet_in"])
        self.add_coupling(queue.output["is_empty"], sender.input["queue_empty_status"])

        # EOC: External Output Couplings
        self.add_coupling(receiver.output["ack_out"], self.output["ack_out"])
        self.add_coupling(sender.output["packet_forward_out"], self.output["packet_forward_out"])

        # 4. Log Creation
        self.logger.info({
            "event": "Model Created", 
            "processing_delay": processing_delay
        }, log_type="PROCESS")