"""
ServiceOrchestrator coupled DEVS model (xdevs.py).

This file defines only the coupled container that wires together the atomic sub-models:
- ArrivalPhaseCoordinator
- AlightingScheduler
- BoardingScheduler
- PassengerEventLogger
"""

from xdevs.models import Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger

# Relative imports strictly follow the folder structure
from .ServiceOrchestrator_libs.ArrivalPhaseCoordinator import ArrivalPhaseCoordinator
from .ServiceOrchestrator_libs.AlightingScheduler import AlightingScheduler
from .ServiceOrchestrator_libs.BoardingScheduler import BoardingScheduler
from .ServiceOrchestrator_libs.PassengerEventLogger import PassengerEventLogger


class ServiceOrchestrator(Coupled):
    """
    Function:
      - Orchestrate station servicing on each train arrival by composing atomic coordinators/schedulers.
      - Provide a system boundary that routes: train arrivals -> (alighting start + arrival contexts) -> alighting completion -> boarding gate,
        and forwards passenger boarding/exiting events to a JSONL logger sub-model.
      - Sub-models:
        - ArrivalPhaseCoordinator: name=arrival_phase_coordinator. Emits alight start + arrival contexts; releases boarding gate on alight completion.
        - AlightingScheduler: name=alighting_scheduler. Schedules pop-exiting commands and emits exit events + alight completion.
        - BoardingScheduler: name=boarding_scheduler. Schedules dequeue requests and emits boarded passenger + boarding events.
        - PassengerEventLogger: name=passenger_event_logger. Validates and logs passenger_boarding / passenger_exiting JSONL RESULT events.

    Logging in this model:
      - {'event': 'Model Created', 'service_time_seconds': <float>, 'param': {'wiring_version': <str>}}
        log_type: PROCESS
        Description: Emitted once in __init__ after ports, sub-models, and couplings are created.

    Input Ports:
      - train_arrival_in (dict): Train arrival notification.
        structure:
          station_id (int): Station ID in [1..5].
          direction (int): 0 (Southbound) or 1 (Northbound).
        protocol: initialize: no initial signal ; process: forwarded to ArrivalPhaseCoordinator.train_arrival_in.

      - alight_count_in (dict): Alighting count response (from TrainLoadStore).
        structure:
          station_id (int): Station ID in [1..5].
          count (int): Number of passengers to alight (>=0).
        protocol: initialize: no initial signal ; process: forwarded to AlightingScheduler.alight_count_in.

      - exiting_passenger_in (dict): Next exiting passenger popped from train load (from TrainLoadStore).
        structure:
          station_id (int): Station ID in [1..5].
          has_passenger (bool): True if a passenger was popped.
          passenger (dict): Passenger payload if has_passenger else {}.
            passenger_id (int): Encoded passenger ID.
            passenger_num (int): Sequential passenger number.
            origin (int): Origin station ID in [1..5].
            destination (int): Destination station ID in [1..5].
        protocol: initialize: no initial signal ; process: forwarded to AlightingScheduler.exiting_passenger_in.

      - dequeue_response_in (dict): Response from StationQueueSystem for a dequeue request.
        structure:
          station_id (int): Station ID in [1..5].
          has_passenger (bool): True if a passenger was dequeued.
          passenger (dict): Passenger payload if has_passenger else {}.
            passenger_id (int): Encoded passenger ID.
            passenger_num (int): Sequential passenger number.
            origin (int): Origin station ID in [1..5].
            destination (int): Destination station ID in [1..5].
        protocol: initialize: no initial signal ; process: forwarded to BoardingScheduler.dequeue_response_in.

      - alight_complete_in (dict): Alighting completion notification (from AlightingScheduler or external, depending on parent wiring).
        structure:
          station_id (int): Station ID in [1..5].
          arrival_time (float): Arrival simulation time (seconds) for which alighting is complete.
        protocol: initialize: no initial signal ; process: forwarded to ArrivalPhaseCoordinator.alight_complete_in.

      Notes:
        - This coupled model exposes a superset of ports needed to connect to sibling systems (TrainLoadStore, StationQueueSystem, TrainMovementSystem).
        - The internal atomic sub-models define the actual orchestration behavior and JSONL logging.

    Output Ports:
      - alight_start_out (dict): Alighting start command to TrainLoadStore.
        structure:
          station_id (int): Station ID in [1..5].
          arrival_time (float): Arrival simulation time (seconds).
        protocol: initialize: no initial signal ; process: emitted by ArrivalPhaseCoordinator.alight_start_out.

      - pop_exiting_out (dict): Command to pop an exiting passenger from TrainLoadStore.
        structure:
          station_id (int): Station ID in [1..5].
        protocol: initialize: no initial signal ; process: emitted by AlightingScheduler.pop_exiting_out.

      - dequeue_request_out (dict): Dequeue request to StationQueueSystem.
        structure:
          station_id (int): Station ID in [1..5].
        protocol: initialize: no initial signal ; process: emitted by BoardingScheduler.dequeue_request_out.

      - boarded_passenger_out (dict): Forward boarded passenger to TrainLoadStore.
        structure:
          passenger (dict): Passenger payload to append by destination.
            passenger_id (int): Encoded passenger ID.
            passenger_num (int): Sequential passenger number.
            origin (int): Origin station ID in [1..5].
            destination (int): Destination station ID in [1..5].
        protocol: initialize: no initial signal ; process: emitted by BoardingScheduler.boarded_passenger_out.
    """

    def __init__(self, name: str, parent: Coupled | None, service_time_seconds: float):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            service_time_seconds (float): Per-passenger boarding/alighting time in seconds.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Internal hardcoded parameters (not passed via __init__)
        self.param: dict = {
            "wiring_version": "1.0"
        }

        # System boundary ports (superset required to integrate with siblings)
        self.add_in_port(Port(dict, "train_arrival_in"))
        self.add_in_port(Port(dict, "alight_count_in"))
        self.add_in_port(Port(dict, "exiting_passenger_in"))
        self.add_in_port(Port(dict, "dequeue_response_in"))
        self.add_in_port(Port(dict, "alight_complete_in"))

        self.add_out_port(Port(dict, "dequeue_request_out"))
        self.add_out_port(Port(dict, "alight_start_out"))
        self.add_out_port(Port(dict, "pop_exiting_out"))
        self.add_out_port(Port(dict, "boarded_passenger_out"))

        # Sub-model instances
        arrival_phase_coordinator = ArrivalPhaseCoordinator(
            name="arrival_phase_coordinator",
            parent=self,
            service_time_seconds=float(service_time_seconds),
        )

        alighting_scheduler = AlightingScheduler(
            name="alighting_scheduler",
            parent=self,
            service_time_seconds=float(service_time_seconds),
        )

        boarding_scheduler = BoardingScheduler(
            name="boarding_scheduler",
            parent=self,
            service_time_seconds=float(service_time_seconds),
        )

        passenger_event_logger = PassengerEventLogger(
            name="passenger_event_logger",
            parent=self,
        )

        # Register components
        self.add_component(arrival_phase_coordinator)
        self.add_component(alighting_scheduler)
        self.add_component(boarding_scheduler)
        self.add_component(passenger_event_logger)

        # Couplings
        # EIC: external inputs -> internal components
        self.add_coupling(self.input["train_arrival_in"], arrival_phase_coordinator.input["train_arrival_in"])
        self.add_coupling(self.input["alight_complete_in"], arrival_phase_coordinator.input["alight_complete_in"])

        self.add_coupling(self.input["alight_count_in"], alighting_scheduler.input["alight_count_in"])
        self.add_coupling(self.input["exiting_passenger_in"], alighting_scheduler.input["exiting_passenger_in"])

        self.add_coupling(self.input["dequeue_response_in"], boarding_scheduler.input["dequeue_response_in"])

        # IC: internal component -> internal component
        self.add_coupling(arrival_phase_coordinator.output["alight_start_ctx_out"], alighting_scheduler.input["arrival_ctx_in"])
        self.add_coupling(arrival_phase_coordinator.output["board_start_ctx_out"], boarding_scheduler.input["arrival_ctx_in"])
        self.add_coupling(arrival_phase_coordinator.output["alight_done_out"], boarding_scheduler.input["alight_done_in"])

        self.add_coupling(alighting_scheduler.output["alight_complete_out"], arrival_phase_coordinator.input["alight_complete_in"])

        self.add_coupling(alighting_scheduler.output["exiting_event_out"], passenger_event_logger.input["exiting_event_in"])
        self.add_coupling(boarding_scheduler.output["boarding_event_out"], passenger_event_logger.input["boarding_event_in"])

        # EOC: internal outputs -> external outputs
        self.add_coupling(arrival_phase_coordinator.output["alight_start_out"], self.output["alight_start_out"])
        self.add_coupling(alighting_scheduler.output["pop_exiting_out"], self.output["pop_exiting_out"])
        self.add_coupling(boarding_scheduler.output["dequeue_request_out"], self.output["dequeue_request_out"])
        self.add_coupling(boarding_scheduler.output["boarded_passenger_out"], self.output["boarded_passenger_out"])

        self.logger.info(
            {
                "event": "Model Created",
                "service_time_seconds": float(service_time_seconds),
                "param": {
                    "wiring_version": str(self.param["wiring_version"])
                },
            },
            log_type="PROCESS",
        )