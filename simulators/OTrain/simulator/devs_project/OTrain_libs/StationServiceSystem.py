"""
StationServiceSystem: Coupled DEVS model container for station servicing.

This file defines the StationServiceSystem coupled model, which wires:
- ServiceOrchestrator (coupled): orchestrates alighting/boarding workflow and produces requests/commands.
- TrainLoadStore (atomic): maintains in-train passenger storage and responds to alight/pop commands.

Note: This coupled model is a structural container only; all timing and passenger event JSONL logging
(passenger_boarding, passenger_exiting) are handled by sub-models (e.g., PassengerEventLogger inside
ServiceOrchestrator) per project architecture.
"""

### BEGIN: General Import (whitelist-compliant)
from xdevs.models import Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
### END

### BEGIN: Model import (relative imports)
from .StationServiceSystem_libs.ServiceOrchestrator import ServiceOrchestrator
from .StationServiceSystem_libs.TrainLoadStore import TrainLoadStore
### END


class StationServiceSystem(Coupled):
    """
    Function:
      - Provides the station service system boundary for OTrain: handles station stop servicing by wiring
        orchestration logic (alighting/boarding scheduling) with in-train load storage.
      - Delegates all operational logic to sub-models; this coupled model only defines ports and couplings.
      - Sub-models:
        - ServiceOrchestrator: name=service_orchestrator. Orchestrates arrival phases and produces commands/requests.
        - TrainLoadStore: name=train_load_store. Stores in-train passengers by destination and serves alight/pop/append.

    Logging in this model:
      - event: Model Created
        log_type: PROCESS
        msg (dict):
          event (str): Constant "Model Created".
          service_time_seconds (float): Per-passenger service time forwarded to ServiceOrchestrator.
          param (dict): Internal hardcoded parameters.
            wiring_version (str): Constant "1.0".

    Input Ports:
      - train_arrival_in (dict): Train arrival notification from TrainMovementSystem.
        structure:
          station_id (int): Station ID in [1..5].
          direction (int): 0 (Southbound) or 1 (Northbound).
        protocol: initialize: no initial signal ; process: routed to ServiceOrchestrator.train_arrival_in

      - dequeue_response_in (dict): Dequeue response from StationQueueSystem.
        structure:
          station_id (int): Station ID in [1..5].
          has_passenger (bool): True if a passenger was dequeued.
          passenger (dict): Passenger payload if has_passenger else {}.
            passenger_id (int): Encoded passenger ID.
            passenger_num (int): Sequential passenger number.
            origin (int): Origin station ID in [1..5].
            destination (int): Destination station ID in [1..5].
        protocol: initialize: no initial signal ; process: routed to ServiceOrchestrator.dequeue_response_in

      - alight_complete_in (dict): Alighting completion notification (if provided by parent/sibling system).
        structure:
          station_id (int): Station ID in [1..5].
          arrival_time (float): Arrival simulation time (seconds) for which alighting is complete.
        protocol: initialize: no initial signal ; process: routed to ServiceOrchestrator.alight_complete_in

    Output Ports:
      - dequeue_request_out (dict): Dequeue request to StationQueueSystem.
        structure:
          station_id (int): Station ID in [1..5].
        protocol: initialize: no initial signal ; process: forwarded from ServiceOrchestrator.dequeue_request_out

      - alight_start_out (dict): Alighting start command to TrainLoadStore.
        structure:
          station_id (int): Station ID in [1..5].
          arrival_time (float): Arrival simulation time (seconds).
        protocol: initialize: no initial signal ; process: forwarded from ServiceOrchestrator.alight_start_out

      - pop_exiting_out (dict): Command to pop an exiting passenger from TrainLoadStore.
        structure:
          station_id (int): Station ID in [1..5].
        protocol: initialize: no initial signal ; process: forwarded from ServiceOrchestrator.pop_exiting_out

      - boarded_passenger_out (dict): Boarded passenger message to be appended into TrainLoadStore.
        structure:
          passenger (dict): Passenger payload to append by destination.
            passenger_id (int): Encoded passenger ID.
            passenger_num (int): Sequential passenger number.
            origin (int): Origin station ID in [1..5].
            destination (int): Destination station ID in [1..5].
        protocol: initialize: no initial signal ; process: forwarded from ServiceOrchestrator.boarded_passenger_out

      - alight_count_out (dict): Alighting count response to ServiceOrchestrator (exposed for sibling wiring if needed).
        structure:
          station_id (int): Station ID in [1..5].
          count (int): Number of passengers currently stored for that destination (>=0).
        protocol: initialize: no initial signal ; process: forwarded from TrainLoadStore.alight_count_out

      - exiting_passenger_out (dict): Exiting passenger response to ServiceOrchestrator (exposed for sibling wiring if needed).
        structure:
          station_id (int): Station ID in [1..5].
          has_passenger (bool): True if a passenger was popped.
          passenger (dict): Passenger payload if has_passenger else {}.
            passenger_id (int): Encoded passenger ID.
            passenger_num (int): Sequential passenger number.
            origin (int): Origin station ID in [1..5].
            destination (int): Destination station ID in [1..5].
        protocol: initialize: no initial signal ; process: forwarded from TrainLoadStore.exiting_passenger_out
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

        self.param: dict = {
            "wiring_version": "1.0"
        }

        # System boundary ports (superset to support sibling wiring in OTrain)
        self.add_in_port(Port(dict, "train_arrival_in"))
        self.add_in_port(Port(dict, "dequeue_response_in"))
        self.add_in_port(Port(dict, "alight_complete_in"))

        self.add_out_port(Port(dict, "dequeue_request_out"))
        self.add_out_port(Port(dict, "alight_start_out"))
        self.add_out_port(Port(dict, "pop_exiting_out"))
        self.add_out_port(Port(dict, "boarded_passenger_out"))

        # Expose TrainLoadStore responses as system outputs (optional for higher-level wiring/inspection)
        self.add_out_port(Port(dict, "alight_count_out"))
        self.add_out_port(Port(dict, "exiting_passenger_out"))

        # Sub-models
        service_orchestrator = ServiceOrchestrator(
            name="service_orchestrator",
            parent=self,
            service_time_seconds=float(service_time_seconds),
        )
        train_load_store = TrainLoadStore(
            name="train_load_store",
            parent=self,
        )

        self.add_component(service_orchestrator)
        self.add_component(train_load_store)

        # Couplings
        # EIC: external inputs -> orchestrator
        self.add_coupling(self.input["train_arrival_in"], service_orchestrator.input["train_arrival_in"])
        self.add_coupling(self.input["dequeue_response_in"], service_orchestrator.input["dequeue_response_in"])
        self.add_coupling(self.input["alight_complete_in"], service_orchestrator.input["alight_complete_in"])

        # IC: orchestrator <-> train load store
        # Commands to TrainLoadStore
        self.add_coupling(service_orchestrator.output["alight_start_out"], train_load_store.input["alight_start_in"])
        self.add_coupling(service_orchestrator.output["pop_exiting_out"], train_load_store.input["pop_exiting_in"])
        self.add_coupling(service_orchestrator.output["boarded_passenger_out"], train_load_store.input["append_boarded_in"])

        # Responses from TrainLoadStore back to orchestrator
        self.add_coupling(train_load_store.output["alight_count_out"], service_orchestrator.input["alight_count_in"])
        self.add_coupling(train_load_store.output["exiting_passenger_out"], service_orchestrator.input["exiting_passenger_in"])

        # EOC: orchestrator outputs -> external outputs
        self.add_coupling(service_orchestrator.output["dequeue_request_out"], self.output["dequeue_request_out"])
        self.add_coupling(service_orchestrator.output["alight_start_out"], self.output["alight_start_out"])
        self.add_coupling(service_orchestrator.output["pop_exiting_out"], self.output["pop_exiting_out"])
        self.add_coupling(service_orchestrator.output["boarded_passenger_out"], self.output["boarded_passenger_out"])

        # EOC: TrainLoadStore responses -> external outputs (optional exposure)
        self.add_coupling(train_load_store.output["alight_count_out"], self.output["alight_count_out"])
        self.add_coupling(train_load_store.output["exiting_passenger_out"], self.output["exiting_passenger_out"])

        self.logger.info(
            {
                "event": "Model Created",
                "service_time_seconds": float(service_time_seconds),
                "param": self.param,
            },
            log_type="PROCESS",
        )