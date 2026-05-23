import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class PassengerEventLogger(Atomic):
    """
    Function:
        - Receives internal scheduler events for passenger boarding and passenger exiting, and emits JSONL-compatible
          event objects via the simulation logger (one log call per event).
        - States and Output at the end of the state:
            - IDLE: Waits indefinitely for external events. No output ports.
            - (No other phases) This model does not schedule internal events and does not emit via output ports.

    Logging in this model:
        - event: Model Created
            log_type: PROCESS
            msg (dict):
                event (str): "Model Created"
                model (str): Model name.
                param (dict): Internal hardcoded parameters (e.g., station mapping).
        - event: Model Initialized
            log_type: PROCESS
            msg (dict):
                event (str): "Model Initialized"
                model (str): Model name.
        - event: passenger_boarding (JSONL event object)
            log_type: RESULT
            msg (dict): JSONL schema required by the system goal.
                time (float): Simulation timestamp provided by the input event.
                event (str): "passenger_boarding"
                entity_type (str): "station_queue"
                station_id (int): 1..5
                station (str): Station name mapped from station_id.
                payload (dict): Passenger fields.
                    passenger_id (int): Unique passenger id.
                    passenger_num (int): Sequential passenger number.
                    origin (int): Origin station id (1..5).
                    destination (int): Destination station id (1..5), != origin.
        - event: passenger_exiting (JSONL event object)
            log_type: RESULT
            msg (dict): JSONL schema required by the system goal.
                time (float): Simulation timestamp provided by the input event.
                event (str): "passenger_exiting"
                entity_type (str): "train_queue"
                station_id (int): 1..5
                station (str): Station name mapped from station_id.
                payload (dict): Passenger fields.
                    passenger_id (int): Unique passenger id.
                    passenger_num (int): Sequential passenger number.
                    origin (int): Origin station id (1..5).
                    destination (int): Destination station id (1..5), != origin.
        - event: Invalid Input Dropped
            log_type: ERROR
            msg (dict):
                event (str): "Invalid Input Dropped"
                reason (str): Validation failure reason.
                port (str): Port name that received the invalid message.
                raw (dict): The raw received message.

    Input Ports:
      - exiting_event_in (dict): Internal exiting log event from [Sibling-AlightingScheduler: exiting_event_out].
        structure:
            time (float): Simulation time at which the exit occurred (provided by scheduler).
            station_id (int): Station id where the exit occurred (1..5).
            direction (int): Train direction (0 southbound, 1 northbound). Not included in JSONL output.
            passenger (dict): Passenger information.
                passenger_id (int): Passenger id.
                passenger_num (int): Passenger sequence number.
                origin (int): Origin station id (1..5).
                destination (int): Destination station id (1..5).
        protocol: initialize: Ready to log at T=0, no initial signal ; process: for each received event, log one JSONL
                  passenger_exiting object exactly as specified (direction is ignored in JSONL).

      - boarding_event_in (dict): Internal boarding log event from [Sibling-BoardingScheduler: boarding_event_out].
        structure:
            time (float): Simulation time at which the boarding occurred (provided by scheduler).
            station_id (int): Station id where the boarding occurred (1..5).
            direction (int): Train direction (0 southbound, 1 northbound). Not included in JSONL output.
            passenger (dict): Passenger information.
                passenger_id (int): Passenger id.
                passenger_num (int): Passenger sequence number.
                origin (int): Origin station id (1..5).
                destination (int): Destination station id (1..5).
        protocol: initialize: Ready to log at T=0, no initial signal ; process: for each received event, log one JSONL
                  passenger_boarding object exactly as specified (direction is ignored in JSONL).

    Output Ports:
      - (none)
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

        # Ports (must match specification)
        self.add_in_port(Port(dict, "exiting_event_in"))
        self.add_in_port(Port(dict, "boarding_event_in"))

        # Internal hardcoded parameters
        self.param = {
            "station_name_by_id": {
                1: "Bayview",
                2: "Carling",
                3: "Carleton",
                4: "Confed",
                5: "Greenboro",
            }
        }

        # No internal scheduling; keep passive/idle
        self.hold_in("IDLE", float("inf"))

        self.logger.info(
            {
                "event": "Model Created",
                "model": self.name,
                "param": self.param,
            },
            log_type="PROCESS",
        )

    def initialize(self):
        # Ready at T=0, no initial signal required.
        self.hold_in("IDLE", float("inf"))
        self._pending_result_events = []
        self.logger.info(
            {
                "event": "Model Initialized",
                "model": self.name,
            },
            log_type="PROCESS",
        )

    def _is_valid_passenger(self, passenger: dict) -> bool:
        if not isinstance(passenger, dict):
            return False
        required_keys = ["passenger_id", "passenger_num", "origin", "destination"]
        for k in required_keys:
            if k not in passenger:
                return False
        if not isinstance(passenger["passenger_id"], int):
            return False
        if not isinstance(passenger["passenger_num"], int):
            return False
        if not isinstance(passenger["origin"], int):
            return False
        if not isinstance(passenger["destination"], int):
            return False
        return True

    def _is_valid_internal_event(self, msg: dict) -> bool:
        if not isinstance(msg, dict):
            return False
        required_keys = ["time", "station_id", "direction", "passenger"]
        for k in required_keys:
            if k not in msg:
                return False
        if not isinstance(msg["time"], float):
            return False
        if not isinstance(msg["station_id"], int):
            return False
        if not isinstance(msg["direction"], int):
            return False
        if msg["station_id"] not in self.param["station_name_by_id"]:
            return False
        if msg["direction"] not in (0, 1):
            return False
        if not self._is_valid_passenger(msg["passenger"]):
            return False
        return True

    def deltext(self, e: float):
        # This model does not use elapsed time e for scheduling; it only logs received events.
        # Keep IDLE with infinite sigma.
        _ = e
        pending_events = []

        # Process exiting events
        for msg in self.input["exiting_event_in"].values:
            if not self._is_valid_internal_event(msg):
                self.logger.info(
                    {
                        "event": "Invalid Input Dropped",
                        "reason": "invalid_exiting_event_schema",
                        "port": "exiting_event_in",
                        "raw": msg if isinstance(msg, dict) else {"raw": str(msg)},
                    },
                    log_type="ERROR",
                )
                continue

            station_id = msg["station_id"]
            station_name = self.param["station_name_by_id"][station_id]
            passenger = msg["passenger"]

            pending_events.append(
                {
                    "time": msg["time"],
                    "event": "passenger_exiting",
                    "entity_type": "train_queue",
                    "station_id": station_id,
                    "station": station_name,
                    "payload": {
                        "passenger_id": passenger["passenger_id"],
                        "passenger_num": passenger["passenger_num"],
                        "origin": passenger["origin"],
                        "destination": passenger["destination"],
                    },
                }
            )

        # Process boarding events
        for msg in self.input["boarding_event_in"].values:
            if not self._is_valid_internal_event(msg):
                self.logger.info(
                    {
                        "event": "Invalid Input Dropped",
                        "reason": "invalid_boarding_event_schema",
                        "port": "boarding_event_in",
                        "raw": msg if isinstance(msg, dict) else {"raw": str(msg)},
                    },
                    log_type="ERROR",
                )
                continue

            station_id = msg["station_id"]
            station_name = self.param["station_name_by_id"][station_id]
            passenger = msg["passenger"]

            pending_events.append(
                {
                    "time": msg["time"],
                    "event": "passenger_boarding",
                    "entity_type": "station_queue",
                    "station_id": station_id,
                    "station": station_name,
                    "payload": {
                        "passenger_id": passenger["passenger_id"],
                        "passenger_num": passenger["passenger_num"],
                        "origin": passenger["origin"],
                        "destination": passenger["destination"],
                    },
                }
            )

        self._pending_result_events.extend(pending_events)
        self._pending_result_events.sort(
            key=lambda ev: (
                float(ev["time"]),
                0 if ev["event"] == "passenger_exiting" else 1,
                int(ev["payload"]["passenger_id"]),
            )
        )
        for jsonl_event in self._pending_result_events:
            self.logger.info(jsonl_event, log_type="RESULT")
        self._pending_result_events.clear()

        self.hold_in("IDLE", float("inf"))

    def lambdaf(self):
        # No output ports. Logging is performed in deltext as required by specification.
        return

    def deltint(self):
        # No internal events are scheduled; remain idle.
        self.hold_in("IDLE", float("inf"))

    def exit(self):
        # No KPI aggregation required; just a finalization log.
        self.logger.info(
            {
                "event": "Model Finalized",
                "model": self.name,
                "time": float(get_current_time()),
            },
            log_type="RESULT",
        )
