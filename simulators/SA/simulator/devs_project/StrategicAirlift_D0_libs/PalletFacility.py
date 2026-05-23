import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

class PalletFacility(Atomic):
    """
    Function: 
        - Generates a cargo pallet every 'pallet_interval' seconds.
        - Each pallet is assigned a unique 'pallet_id', an absolute 'expiration_time', and 'generation_time'.
        - Transitions from IDLE to GENERATING to schedule pallet creation, then cycles back to GENERATING.
    
    Logging in this model:
        - pallet_generated: Triggered when a new pallet is created.
            time (float): Absolute simulation time.
            entity (str): "facility".
            event (str): "pallet_generated".
            payload (dict):
                pallet_id (int): Unique ID of the generated pallet.
                expiration_time (float): Absolute simulation time when pallet expires.

    Input Ports:
        None

    Output Ports:
        - pallet_out (dict): Pallet info dictionary.
            structure:
                pallet_id (int): Unique ID of the pallet.
                expiration_time (float): Absolute simulation time (Deadline).
                generation_time (float): Absolute simulation time of creation.
            protocol: 
                initialize: Starts in IDLE, schedules first generation at t=0.
                process: Sends a pallet dictionary to PalletQueue every pallet_interval.
    """

    def __init__(self, name: str, parent: Coupled | None, pallet_interval: float, pallet_expiration_time: float):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent model.
            pallet_interval (float): Time interval between generations.
            pallet_expiration_time (float): Relative duration until a pallet expires in queue.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Configuration Parameters
        self.params = {
            "pallet_interval": pallet_interval,
            "pallet_expiration_time": pallet_expiration_time
        }

        # Ports
        self.add_out_port(Port(dict, "pallet_out"))

        # Internal State Variables
        self.next_pallet_id = 0
        self.prepared_pallet = None

        # Log creation
        self.logger.info({
            "event": "Model Created",
            "entity": "facility",
            "params": self.params,
            "time": get_current_time()
        }, log_type="PROCESS")

    def initialize(self):
        """
        Initialize the facility. 
        According to the scenario, generation starts at t=0.
        """
        self.next_pallet_id = 0
        self.prepared_pallet = None
        
        # Schedule the first pallet generation immediately at t=0
        self.hold_in("GENERATING", 0.0)
        
        self.logger.info({
            "event": "Model Initialized",
            "entity": "facility",
            "time": get_current_time()
        }, log_type="PROCESS")

    def lambdaf(self):
        """
        Output the prepared pallet.
        """
        if self.phase == "GENERATING":
            # Prepare the pallet data for the output port
            current_time = get_current_time()
            pallet_id = self.next_pallet_id
            expiration_time = current_time + self.params["pallet_expiration_time"]
            
            self.prepared_pallet = {
                "pallet_id": pallet_id,
                "expiration_time": expiration_time,
                "generation_time": current_time
            }
            
            self.output["pallet_out"].add(self.prepared_pallet)

    def deltint(self):
        """
        Internal transition: Log the generation and schedule the next one.
        """
        if self.phase == "GENERATING":
            # Log the event that just happened (output sent in lambdaf)
            self.logger.info({
                "time": get_current_time(),
                "entity": "facility",
                "event": "pallet_generated",
                "payload": {
                    "pallet_id": self.prepared_pallet["pallet_id"],
                    "expiration_time": self.prepared_pallet["expiration_time"]
                }
            }, log_type="PROCESS")
            
            # Increment ID for next time
            self.next_pallet_id += 1
            self.prepared_pallet = None
            
            # Schedule next generation
            self.hold_in("GENERATING", self.params["pallet_interval"])

    def deltext(self, e: float):
        """
        No input ports defined for this model.
        """
        self.hold_in(self.phase, self.ta() - e)

    def exit(self):
        """
        Cleanup and final logging.
        """
        self.logger.info({
            "event": "Simulation Finished",
            "entity": "facility",
            "total_generated": self.next_pallet_id,
            "time": get_current_time()
        }, log_type="RESULT")