import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

class FlightTimer(Atomic):
    """
    Function: 
        - Receives a duration and a phase label from the MissionController.
        - After the specified duration elapses, it outputs the phase label to notify that the operation is complete.
        - States:
            - IDLE: Waiting for a timer request.
            - BUSY: Counting down the duration for a specific flight/ground phase. After BUSY ends, outputs the phase name.

    Logging in this model:
        - No specific operational logging required per specification.

    Input Ports:
      - start_timer (dict): Timer request containing phase and duration.
        structure:
            phase (str): The name of the flight phase (e.g., "flying", "unloading").
            duration (float): The time duration to wait.
        protocol: initialize: idle ; process: starts a countdown based on the duration provided.

    Output Ports:
      - timeout (str): The phase name that just completed.
        structure: str (The name of the phase).
        protocol: initialize: idle ; process: sends the phase name exactly after the requested duration.
    """

    def __init__(self, name: str, parent: Coupled | None, flight_time: float, unload_time: float, return_time: float, maintenance_time: float):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent coupled model.
            flight_time (float): Duration of outbound flight.
            unload_time (float): Duration of unloading.
            return_time (float): Duration of return flight.
            maintenance_time (float): Duration of maintenance.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Register Ports
        self.add_in_port(Port(dict, "start_timer"))
        self.add_out_port(Port(str, "timeout"))

        # Parameter Storage
        self.params = {
            "flight_time": flight_time,
            "unload_time": unload_time,
            "return_time": return_time,
            "maintenance_time": maintenance_time
        }

        # Internal State Variables
        self.active_phase_name = ""
        
        # Initial State
        self.hold_in("IDLE", float('inf'))
        
        self.logger.info({"event": "Model Created", "params": self.params, "time": get_current_time()}, log_type="PROCESS")

    def initialize(self):
        """Initializes the model to IDLE state."""
        self.active_phase_name = ""
        self.hold_in("IDLE", float('inf'))
        self.logger.info({"event": "Model Initialized", "time": get_current_time()}, log_type="PROCESS")

    def deltext(self, e: float):
        """
        Handles external timer requests.
        Receives a dictionary with 'phase' and 'duration'.
        """
        # Process all incoming timer requests (typically one per aircraft cycle step)
        for msg in self.input["start_timer"].values:
            phase_label = msg.get("phase", "unknown")
            duration = msg.get("duration", 0.0)
            
            # Update state to track what we are timing
            self.active_phase_name = phase_label
            # Schedule the timeout
            self.hold_in("BUSY", float(duration))

    def lambdaf(self):
        """Outputs the completed phase name when the timer expires."""
        if self.phase == "BUSY":
            self.output["timeout"].add(self.active_phase_name)

    def deltint(self):
        """Transitions back to IDLE after the timer expires."""
        if self.phase == "BUSY":
            self.active_phase_name = ""
            self.hold_in("IDLE", float('inf'))
        else:
            self.hold_in(self.phase, self.ta())

    def exit(self):
        """Cleanup on simulation end."""
        self.logger.info({"event": "Model Exited", "time": get_current_time()}, log_type="PROCESS")