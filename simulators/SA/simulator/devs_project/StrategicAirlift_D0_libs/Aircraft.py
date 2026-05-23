from xdevs.models import Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

# Relative imports for sub-models
from .Aircraft_libs.MissionController import MissionController
from .Aircraft_libs.FlightTimer import FlightTimer

class Aircraft(Coupled):
    """
    Function: 
      - Represents a single aircraft entity in the logistics system.
      - Manages the flight cycle: Loading -> Flying -> Unloading -> Returning -> Maintenance.
      - Sub-models: 
        - MissionController: name=controller. Manages operational states and business logic.
        - FlightTimer: name=timer. Handles timed durations for flight phases.

    Logging in this model:
      - event: Model Created
        log_type: PROCESS
        msg (dict): Initialization parameters.
          aircraft_id (int): Unique identifier for the aircraft.
          flight_time (float): Duration of outbound flight.
          unload_time (float): Duration of unloading.
          return_time (float): Duration of return flight.
          maintenance_time (float): Duration of maintenance.

    Input Ports:
      - assignment_in (dict): Pallet info received from the Coordinator.
        structure:
          pallet_id (int): Unique ID of the pallet.
          expiration_time (float): Absolute simulation time when pallet expires.
          generation_time (float): Absolute simulation time when pallet was created.
        protocol: initialize: idle ; process: receive assignment and start loading/flight cycle.

    Output Ports:
      - ready_out (str): Signals aircraft availability to the Coordinator.
        structure:
          - (str): The aircraft_id string.
        protocol: initialize: sends aircraft_id at T=0 ; process: sends aircraft_id after maintenance completion.
    """

    def __init__(
        self, 
        name: str, 
        parent: Coupled | None, 
        aircraft_id: int, 
        flight_time: float, 
        unload_time: float, 
        return_time: float, 
        maintenance_time: float
    ):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent model.
            aircraft_id (int): Unique integer ID assigned to the aircraft.
            flight_time (float): Duration for the FLYING phase.
            unload_time (float): Duration for the UNLOADING phase.
            return_time (float): Duration for the RETURNING phase.
            maintenance_time (float): Duration for the MAINTENANCE phase.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Register Ports
        self.add_in_port(Port(dict, "assignment_in"))
        self.add_out_port(Port(str, "ready_out"))

        # Instantiate Components
        controller = MissionController(
            name="controller",
            parent=self,
            aircraft_id=aircraft_id,
            flight_time=flight_time,
            unload_time=unload_time,
            return_time=return_time,
            maintenance_time=maintenance_time
        )

        timer = FlightTimer(
            name="timer",
            parent=self,
            flight_time=flight_time,
            unload_time=unload_time,
            return_time=return_time,
            maintenance_time=maintenance_time
        )

        self.add_component(controller)
        self.add_component(timer)

        # Define Couplings
        
        # EIC: External Input -> Sub-model Input
        self.add_coupling(self.input["assignment_in"], controller.input["assignment_in"])

        # IC: Internal Sub-model Couplings
        # Controller commands Timer to start
        self.add_coupling(controller.output["start_timer"], timer.input["start_timer"])
        # Timer notifies Controller when duration elapses
        self.add_coupling(timer.output["timeout"], controller.input["timer_done"])

        # EOC: Sub-model Output -> External Output
        self.add_coupling(controller.output["ready_out"], self.output["ready_out"])

        # Logging creation
        self.logger.info({
            "event": "Model Created", 
            "aircraft_id": aircraft_id,
            "flight_time": flight_time,
            "unload_time": unload_time,
            "return_time": return_time,
            "maintenance_time": maintenance_time
        }, log_type="PROCESS")