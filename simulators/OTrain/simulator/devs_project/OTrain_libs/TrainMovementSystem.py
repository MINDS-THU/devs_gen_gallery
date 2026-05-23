import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class TrainMovementSystem(Atomic):
    """
    Function:
        - Owns train route state and arrival scheduling for the single train.
        - Maintains fixed station mapping {1:"Bayview",2:"Carling",3:"Carleton",4:"Confed",5:"Greenboro"} for use in logging train_arrival events.
        - Maintains the fixed repeating route sequence of (station_id, direction):
          [(1,0),(2,0),(3,0),(4,0),(5,1),(4,1),(3,1),(2,1)] and repeats cyclically.
        - States and Output at the end of the state:
            - EMIT_ARRIVAL: When the state is over, outputs one train arrival notification on train_arrival_out and logs a JSONL train_arrival event.

    Logging in this model:
        - event: Model Created
          log_type: PROCESS
          msg (dict):
            event (str): "Model Created".
            travel_time_seconds (float): Constant travel time between consecutive stations.
            route_sequence (list[dict]): Fixed route sequence.
                - (dict): One route step.
                    station_id (int): Station ID (1..5).
                    direction (int): 0 southbound, 1 northbound.
            station_map (dict): Station ID to name mapping.
                1 (str): "Bayview"
                2 (str): "Carling"
                3 (str): "Carleton"
                4 (str): "Confed"
                5 (str): "Greenboro"
            time (float): Current simulation time in seconds.
        - event: Model Initialized
          log_type: PROCESS
          msg (dict):
            event (str): "Model Initialized".
            initial_route_index (int): Initial route index (0).
            time (float): Current simulation time in seconds.
        - event: train_arrival (JSONL event object required by system)
          log_type: PROCESS
          msg (dict):
            time (float): Simulation timestamp in seconds.
            event (str): Always "train_arrival".
            entity_type (str): Always "train".
            station_id (int): Station ID (1..5).
            station (str): Station name matching station_id.
            payload (dict): Event-specific payload.
                station (int): Same as station_id.
                direction (int): 0 (Southbound) or 1 (Northbound).
        - event: Model Finalized
          log_type: RESULT
          msg (dict):
            event (str): "Model Finalized".
            total_arrivals_emitted (int): Total number of arrivals emitted by this model.
            time (float): Current simulation time in seconds.

    Input Ports:
        - None

    Output Ports:
        - train_arrival_out (dict): Train arrival notification to downstream station service logic.
            structure:
                station_id (int): Station ID where the train arrives (1..5).
                direction (int): 0 for Southbound (Bayview→Greenboro), 1 for Northbound (Greenboro→Bayview).
            protocol: initialize: emits at T=0.0 with {'station_id':1,'direction':0} ; process: emits every travel_time_seconds following the fixed cyclic route.
    """

    def __init__(
        self, name: str, parent: Coupled | None, travel_time_seconds: float = 225.0
    ):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            travel_time_seconds (float): Constant travel time between consecutive stations. Default 225.0.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match specification)
        self.add_out_port(Port(dict, "train_arrival_out"))

        # Internal hardcoded parameters
        self.param = {
            "station_map": {
                1: "Bayview",
                2: "Carling",
                3: "Carleton",
                4: "Confed",
                5: "Greenboro",
            },
            "route_sequence": [
                {"station_id": 1, "direction": 0},
                {"station_id": 2, "direction": 0},
                {"station_id": 3, "direction": 0},
                {"station_id": 4, "direction": 0},
                {"station_id": 5, "direction": 1},
                {"station_id": 4, "direction": 1},
                {"station_id": 3, "direction": 1},
                {"station_id": 2, "direction": 1},
            ],
        }

        # Config
        self.travel_time_seconds = float(travel_time_seconds)

        # State
        self.route_index = 0
        self._next_out_payload = None  # dict | None
        self.total_arrivals_emitted = 0

        self.logger.info(
            {
                "event": "Model Created",
                "travel_time_seconds": self.travel_time_seconds,
                "route_sequence": self.param["route_sequence"],
                "station_map": self.param["station_map"],
                "time": get_current_time(),
            },
            log_type="PROCESS",
        )

    def initialize(self):
        # Initial state: train is at station 1, direction 0, and must emit at t=0.0
        self.route_index = 0
        step = self.param["route_sequence"][self.route_index]
        self._next_out_payload = {
            "station_id": int(step["station_id"]),
            "direction": int(step["direction"]),
        }

        self.logger.info(
            {
                "event": "Model Initialized",
                "initial_route_index": int(self.route_index),
                "time": get_current_time(),
            },
            log_type="PROCESS",
        )

        # Schedule immediate emission for initial_signal
        self.hold_in("EMIT_ARRIVAL", 0.0)

    def lambdaf(self):
        # Output only: send prepared payload and log required JSONL event object
        if self.phase == "EMIT_ARRIVAL" and isinstance(self._next_out_payload, dict):
            self.output["train_arrival_out"].add(self._next_out_payload)

            station_id = int(self._next_out_payload["station_id"])
            direction = int(self._next_out_payload["direction"])
            station_name = self.param["station_map"].get(station_id, "")

            self.logger.info(
                {
                    "time": float(get_current_time()),
                    "event": "train_arrival",
                    "entity_type": "train",
                    "station_id": station_id,
                    "station": str(station_name),
                    "payload": {"station": station_id, "direction": direction},
                },
                log_type="PROCESS",
            )

    def deltint(self):
        # Internal transition: after emitting, schedule next arrival
        if self.phase == "EMIT_ARRIVAL":
            self.total_arrivals_emitted += 1

            # Move to next route step cyclically
            route_len = len(self.param["route_sequence"])
            self.route_index = (int(self.route_index) + 1) % route_len

            next_step = self.param["route_sequence"][self.route_index]
            self._next_out_payload = {
                "station_id": int(next_step["station_id"]),
                "direction": int(next_step["direction"]),
            }

            # Schedule next emission after travel time
            sigma = max(0.0, float(self.travel_time_seconds))
            self.hold_in("EMIT_ARRIVAL", sigma)
        else:
            # Should not happen; keep passive
            self.hold_in("PASSIVE", float("inf"))

    def deltext(self, e: float):
        # No input ports; just continue current schedule (deduct elapsed time)
        remaining = float(self.ta()) - float(e)
        if remaining < 0.0:
            remaining = 0.0
        self.hold_in(self.phase, remaining)

    def exit(self):
        self.logger.info(
            {
                "event": "Model Finalized",
                "total_arrivals_emitted": int(self.total_arrivals_emitted),
                "time": get_current_time(),
            },
            log_type="RESULT",
        )
