from xdevs.models import Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

# Relative imports for sub-models
from .StrategicAirlift_D0_libs.PalletFacility import PalletFacility
from .StrategicAirlift_D0_libs.PalletQueue import PalletQueue
from .StrategicAirlift_D0_libs.FleetCoordinator import FleetCoordinator
from .StrategicAirlift_D0_libs.Aircraft import Aircraft

class StrategicAirlift_D0(Coupled):
    """
    Function: 
      - Simulates an airfreight logistics system including cargo generation, queuing, coordination, and aircraft delivery cycles.
      - Manages the end-to-end flow from pallet creation at a facility to delivery at a destination.
      - Sub-models: 
        - PalletFacility: name=facility. Generates pallets at regular intervals.
        - PalletQueue: name=queue. Manages FIFO storage and active expiration of pallets.
        - FleetCoordinator: name=coordinator. Matches available aircraft with queued pallets.
        - Aircraft: name=aircraft_{i}. Represents individual transport units (1 to num_aircraft).

    Logging in this model:
      - event: Model Created
        log_type: PROCESS
        msg (dict): Configuration parameters of the system.
          num_aircraft (int): Number of aircraft.
          pallet_interval (float): Time between pallet generations.
          pallet_expiration_time (float): Lifespan of pallet in queue.
          flight_time (float): Outbound duration.
          unload_time (float): Unloading duration.
          return_time (float): Return duration.
          maintenance_time (float): Maintenance duration.

    Input Ports:
      - None (Root model)

    Output Ports:
      - None (Root model)
    """

    def __init__(
        self, 
        name: str, 
        parent: Coupled | None, 
        num_aircraft: int, 
        pallet_interval: float, 
        pallet_expiration_time: float, 
        flight_time: float, 
        unload_time: float, 
        return_time: float, 
        maintenance_time: float
    ):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent model (None for root).
            num_aircraft (int): Total number of aircraft to simulate.
            pallet_interval (float): Seconds between pallet generations.
            pallet_expiration_time (float): Seconds until a pallet expires in the queue.
            flight_time (float): Seconds for the flying phase.
            unload_time (float): Seconds for the unloading phase.
            return_time (float): Seconds for the returning phase.
            maintenance_time (float): Seconds for the maintenance phase.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # 1. Instantiate Sub-models
        facility = PalletFacility(
            name="facility",
            parent=self,
            pallet_interval=pallet_interval,
            pallet_expiration_time=pallet_expiration_time
        )
        self.add_component(facility)

        queue = PalletQueue(
            name="queue",
            parent=self
        )
        self.add_component(queue)

        coordinator = FleetCoordinator(
            name="coordinator",
            parent=self,
            num_aircraft=num_aircraft
        )
        self.add_component(coordinator)

        # Dynamic Aircraft instantiation
        aircraft_list = []
        for i in range(1, num_aircraft + 1):
            ac = Aircraft(
                name=f"aircraft_{i}",
                parent=self,
                aircraft_id=i,
                flight_time=flight_time,
                unload_time=unload_time,
                return_time=return_time,
                maintenance_time=maintenance_time
            )
            self.add_component(ac)
            aircraft_list.append(ac)

        # 2. Define Couplings (IC - Internal Couplings)
        
        # Facility -> Queue
        self.add_coupling(facility.output["pallet_out"], queue.input["pallet_in"])

        # Queue -> Coordinator
        self.add_coupling(queue.output["queue_status"], coordinator.input["queue_size_in"])
        self.add_coupling(queue.output["pallet_out"], coordinator.input["pallet_in"])

        # Coordinator -> Queue
        self.add_coupling(coordinator.output["queue_request"], queue.input["request_pallet"])

        # Coordinator <-> Aircraft (Dynamic Ports)
        for i, ac in enumerate(aircraft_list, start=1):
            # Coordinator assigns pallet to specific aircraft
            self.add_coupling(
                coordinator.output[f"assign_to_aircraft_{i}"], 
                ac.input["assignment_in"]
            )
            # Aircraft notifies coordinator when ready (init and post-maintenance)
            self.add_coupling(
                ac.output["ready_out"], 
                coordinator.input[f"aircraft_ready_{i}"]
            )

        # 3. Log Model Creation
        self.logger.info({
            "event": "Model Created",
            "num_aircraft": num_aircraft,
            "pallet_interval": pallet_interval,
            "pallet_expiration_time": pallet_expiration_time,
            "flight_time": flight_time,
            "unload_time": unload_time,
            "return_time": return_time,
            "maintenance_time": maintenance_time
        }, log_type="PROCESS")