from xdevs.models import Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

# Sub-models relative imports
from .Offline_File_Transfer_libs.Sender import Sender
from .Offline_File_Transfer_libs.Server import Server
from .Offline_File_Transfer_libs.Receiver import Receiver
from .Offline_File_Transfer_libs.Subnet import Subnet

class Offline_File_Transfer(Coupled):
    """
    Function: 
      - Simulates a "Dropbox-like" synchronization flow using two independent ABP loops.
      - Loop 1 (Upload): Sender -> Subnet_A1 -> Server -> Subnet_A2 -> Sender.
      - Loop 2 (Download): Server -> Subnet_B1 -> Receiver -> Subnet_B2 -> Server.
      - Sub-models: 
        - Sender: name=sender. Implements ABP upload logic with 10s preparation and 20s timeout.
        - Server: name=server. Acts as a buffer/forwarder with 3s processing delay.
        - Receiver: name=receiver. Final destination with 10s processing delay.
        - Subnet: name=subnet_a1. Link from Sender to Server (3s delay).
        - Subnet: name=subnet_a2. Link from Server to Sender (3s delay).
        - Subnet: name=subnet_b1. Link from Server to Receiver (3s delay).
        - Subnet: name=subnet_b2. Link from Receiver to Server (3s delay).

    Logging in this model:
      - event: Model Created
        log_type: PROCESS
        msg (dict): Initialization parameters.
          simulation_time (float): Total simulation duration in ms.

    Input Ports:
      - control_in (int): Number of packets N to add to the upload queue.
        structure: int
        protocol: initialize: 0 ; process: Increments Sender's queue.
      - request_in (int): Download valve control (1=Allow, 0=Forbid).
        structure: int
        protocol: initialize: 0 ; process: Toggles Server's download permission.

    Output Ports:
      None
    """

    def __init__(self, name: str, parent: Coupled | None, simulation_time: float):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent model.
            simulation_time (float): Total simulation duration in milliseconds.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Define System Boundary Ports
        self.add_in_port(Port(int, "control_in"))
        self.add_in_port(Port(int, "request_in"))

        # Internal parameters (Hardcoded as per specification)
        self.params = {
            "subnet_delay": 3000.0,
            "server_proc_delay": 3000.0
        }

        # Instantiate Sub-Components
        sender = Sender(name="sender", parent=self)
        
        server = Server(
            name="server", 
            parent=self, 
            processing_delay=self.params["server_proc_delay"]
        )
        
        receiver = Receiver(name="receiver", parent=self)

        # Subnets for Loop 1 (Upload)
        subnet_a1 = Subnet(name="subnet_a1", parent=self, delay=self.params["subnet_delay"])
        subnet_a2 = Subnet(name="subnet_a2", parent=self, delay=self.params["subnet_delay"])

        # Subnets for Loop 2 (Download)
        subnet_b1 = Subnet(name="subnet_b1", parent=self, delay=self.params["subnet_delay"])
        subnet_b2 = Subnet(name="subnet_b2", parent=self, delay=self.params["subnet_delay"])

        # Add components to the container
        self.add_component(sender)
        self.add_component(server)
        self.add_component(receiver)
        self.add_component(subnet_a1)
        self.add_component(subnet_a2)
        self.add_component(subnet_b1)
        self.add_component(subnet_b2)

        # --- Define Couplings ---

        # 1. EIC (External Input Couplings)
        self.add_coupling(self.input["control_in"], sender.input["control_in"])
        self.add_coupling(self.input["request_in"], server.input["request_in"])

        # 2. IC (Internal Couplings)
        
        # Loop 1: Upload Path
        # Sender -> Subnet A1 -> Server
        self.add_coupling(sender.output["packet_out"], subnet_a1.input["in"])
        self.add_coupling(subnet_a1.output["out"], server.input["packet_in"])
        
        # Server -> Subnet A2 -> Sender (ACKs)
        self.add_coupling(server.output["ack_out"], subnet_a2.input["in"])
        self.add_coupling(subnet_a2.output["out"], sender.input["ack_in"])

        # Loop 2: Download Path
        # Server -> Subnet B1 -> Receiver
        self.add_coupling(server.output["packet_forward_out"], subnet_b1.input["in"])
        self.add_coupling(subnet_b1.output["out"], receiver.input["packet_in"])
        
        # Receiver -> Subnet B2 -> Server (ACKs)
        self.add_coupling(receiver.output["ack_out"], subnet_b2.input["in"])
        self.add_coupling(subnet_b2.output["out"], server.input["ack_forward_in"])

        # 3. EOC (External Output Couplings) - None defined for this model

        self.logger.info({
            "event": "Model Created", 
            "simulation_time": simulation_time
        }, log_type="PROCESS")