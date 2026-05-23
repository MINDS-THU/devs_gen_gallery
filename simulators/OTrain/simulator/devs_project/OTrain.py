"""
OTrain coupled model (system container).

This file defines the top-level Coupled DEVS model `OTrain` that wires together:
- PassengerGenerationSystem (passenger creation)
- StationQueueSystem (per-station FIFO queues)
- TrainMovementSystem (train arrival schedule)
- StationServiceSystem (orchestrates alighting/boarding and train load store)

Per project standards, this coupled model is a pure structural container: it only implements __init__.
"""

from xdevs.models import Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

# Relative imports for sub-models
from .OTrain_libs.PassengerGenerationSystem import PassengerGenerationSystem
from .OTrain_libs.StationQueueSystem import StationQueueSystem
from .OTrain_libs.TrainMovementSystem import TrainMovementSystem
from .OTrain_libs.StationServiceSystem import StationServiceSystem


class OTrain(Coupled):
    """
    Function:
      - Top-level O-Train light rail simulation container (pure wiring).
      - Composes passenger generation, station queues, train movement scheduling, and station service orchestration.
      - Sub-models:
        - PassengerGenerationSystem: name=passenger_generation. Generates passenger records for 5 stations.
        - StationQueueSystem: name=station_queue. Maintains per-station FIFO waiting queues.
        - TrainMovementSystem: name=train_movement. Emits cyclic train arrival notifications.
        - StationServiceSystem: name=station_service. Orchestrates dequeue requests and train load (alight/board).

    Logging in this model:
      - {'event': 'Model Created', 'travel_time_seconds': float, 'service_time_seconds': float,
         'gen_mean_minutes': float, 'gen_std_minutes': float, 'gen_min_minutes': float, 'gen_max_minutes': float,
         'init_passenger_time_seconds': float, 'param': dict, 'time': float}
        log_type=PROCESS
        param (dict):
          station_map (dict):
            1 (str): "Bayview"
            2 (str): "Carling"
            3 (str): "Carleton"
            4 (str): "Confed"
            5 (str): "Greenboro"

    Input Ports:
      - None

    Output Ports:
      - None

    Notes:
      - This coupled model does not directly emit the required JSONL simulation events; those are emitted by submodels
        (e.g., TrainMovementSystem emits 'train_arrival', passenger generators emit 'passenger_generated', etc.).
      - This model only wires message flow among submodels.
    """

    def __init__(
        self,
        name: str,
        parent: Coupled | None,
        travel_time_seconds: float = 225.0,
        service_time_seconds: float = 0.025,
        gen_mean_minutes: float = 5.0,
        gen_std_minutes: float = 5.0,
        gen_min_minutes: float = 1.0,
        gen_max_minutes: float = 9.0,
        init_passenger_time_seconds: float = 0.5,
    ):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            travel_time_seconds (float): Constant travel time between consecutive stations (seconds).
            service_time_seconds (float): Per-passenger boarding/alighting service time (seconds).
            gen_mean_minutes (float): Passenger inter-arrival Normal mean (minutes).
            gen_std_minutes (float): Passenger inter-arrival Normal std (minutes).
            gen_min_minutes (float): Clamp lower bound for inter-arrival (minutes).
            gen_max_minutes (float): Clamp upper bound for inter-arrival (minutes).
            init_passenger_time_seconds (float): Time to create initialization passengers at all stations (seconds).
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Hardcoded internal parameters (not passed via __init__)
        self.param: dict = {
            "station_map": {
                "1": "Bayview",
                "2": "Carling",
                "3": "Carleton",
                "4": "Confed",
                "5": "Greenboro",
            }
        }

        # No system boundary ports for this top-level model per specification.
        # (Submodels handle logging of JSONL events; this model is a pure container.)

        # Instantiate sub-components
        passenger_generation = PassengerGenerationSystem(
            name="passenger_generation",
            parent=self,
            gen_mean_minutes=float(gen_mean_minutes),
            gen_std_minutes=float(gen_std_minutes),
            gen_min_minutes=float(gen_min_minutes),
            gen_max_minutes=float(gen_max_minutes),
            init_passenger_time_seconds=float(init_passenger_time_seconds),
        )

        station_queue = StationQueueSystem(
            name="station_queue",
            parent=self,
        )

        train_movement = TrainMovementSystem(
            name="train_movement",
            parent=self,
            travel_time_seconds=float(travel_time_seconds),
        )

        station_service = StationServiceSystem(
            name="station_service",
            parent=self,
            service_time_seconds=float(service_time_seconds),
        )

        # Register components
        self.add_component(passenger_generation)
        self.add_component(station_queue)
        self.add_component(train_movement)
        self.add_component(station_service)

        # Couplings
        # Passenger generation -> Station queues
        self.add_coupling(passenger_generation.output["passenger_out"], station_queue.input["passenger_in"])

        # Train movement -> Station service (arrival triggers service orchestration)
        self.add_coupling(train_movement.output["train_arrival_out"], station_service.input["train_arrival_in"])

        # Station service <-> Station queue (dequeue request/response loop)
        self.add_coupling(station_service.output["dequeue_request_out"], station_queue.input["dequeue_request_in"])
        self.add_coupling(station_queue.output["dequeue_response_out"], station_service.input["dequeue_response_in"])

        # Note: station_service.input["alight_complete_in"] is intentionally left uncoupled here.
        # The StationServiceSystem/ServiceOrchestrator may be able to operate without an external alight-complete signal,
        # or this can be wired by a higher-level model if needed. This top-level model has no parent/siblings.

        self.logger.info(
            {
                "event": "Model Created",
                "travel_time_seconds": float(travel_time_seconds),
                "service_time_seconds": float(service_time_seconds),
                "gen_mean_minutes": float(gen_mean_minutes),
                "gen_std_minutes": float(gen_std_minutes),
                "gen_min_minutes": float(gen_min_minutes),
                "gen_max_minutes": float(gen_max_minutes),
                "init_passenger_time_seconds": float(init_passenger_time_seconds),
                "param": self.param,
                "time": float(get_current_time()),
            },
            log_type="PROCESS",
        )