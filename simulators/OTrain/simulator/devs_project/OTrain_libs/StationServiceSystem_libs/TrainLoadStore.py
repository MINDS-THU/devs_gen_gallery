### BEGIN: General Import
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time
### END


class TrainLoadStore(Atomic):
    """
    Function:
        - Own and maintain the in-train passenger storage grouped by destination:
          train_load[destination_station_id] as FIFO lists for destination_station_id in 1..5.
        - Provide FIFO access to train_load[k] for a given station k.
        - States and Output at the end of the state:
            - IDLE: Waiting for commands. No output.
            - RESPOND_ALIGHT_COUNT: After processing an alight_start_in, outputs alight_count_out once, then returns to IDLE.
            - RESPOND_POP_EXITING: After processing a pop_exiting_in, outputs exiting_passenger_out once, then returns to IDLE.

    Logging in this model:
        - event: Model Created
            log_type: PROCESS
            msg (dict):
                event (str): "Model Created".
                model (str): Model name.
                param (dict): Internal hardcoded parameters.
                    station_ids (list[int]): Station IDs supported by this store.
        - event: Model Initialized
            log_type: PROCESS
            msg (dict):
                event (str): "Model Initialized".
                train_load_size (dict): Current sizes per station_id.
                    1 (int): Count of passengers destined to station 1.
                    2 (int): Count of passengers destined to station 2.
                    3 (int): Count of passengers destined to station 3.
                    4 (int): Count of passengers destined to station 4.
                    5 (int): Count of passengers destined to station 5.
        - event: Alight Start Processed
            log_type: PROCESS
            msg (dict):
                event (str): "Alight Start Processed".
                cmd (dict): The alight_start_in command.
                    station_id (int): Station ID (1..5).
                    arrival_time (float): Train arrival simulation time (seconds).
                count (int): Snapshot count of passengers to alight for station_id.
        - event: Pop Exiting Processed
            log_type: PROCESS
            msg (dict):
                event (str): "Pop Exiting Processed".
                cmd (dict): The pop_exiting_in command.
                    station_id (int): Station ID (1..5).
                result (dict): The exiting_passenger_out response structure.
                    station_id (int): Station ID (1..5).
                    has_passenger (bool): Whether a passenger was popped.
                    passenger (dict): Passenger dict or {} if none.
                        passenger_id (int): Passenger ID.
                        passenger_num (int): Passenger sequence number.
                        origin (int): Origin station ID (1..5).
                        destination (int): Destination station ID (1..5).
        - event: Boarded Appended
            log_type: PROCESS
            msg (dict):
                event (str): "Boarded Appended".
                passenger (dict): Passenger appended.
                    passenger_id (int): Passenger ID.
                    passenger_num (int): Passenger sequence number.
                    origin (int): Origin station ID (1..5).
                    destination (int): Destination station ID (1..5).
                new_count (int): New count in train_load[destination] after append.
        - event: Model Finalized
            log_type: RESULT
            msg (dict):
                event (str): "Model Finalized".
                train_load_size (dict): Final sizes per station_id.
                    1 (int): Count of passengers destined to station 1.
                    2 (int): Count of passengers destined to station 2.
                    3 (int): Count of passengers destined to station 3.
                    4 (int): Count of passengers destined to station 4.
                    5 (int): Count of passengers destined to station 5.

    Input Ports:
      - alight_start_in (dict): Alighting start command from [Sibling-ServiceOrchestrator: alight_start_out].
        structure:
            station_id (int): Station ID (1..5).
            arrival_time (float): Train arrival simulation time (seconds).
        protocol: initialize: train_load[1..5] all empty at T=0; ready to accept alight/board commands ;
                  process: snapshot current count in train_load[station_id] and respond via alight_count_out.

      - pop_exiting_in (dict): Command to pop the next exiting passenger for station k from [Sibling-ServiceOrchestrator: pop_exiting_out].
        structure:
            station_id (int): Station ID (1..5).
        protocol: initialize: no pending pop operations at T=0 ;
                  process: pop FIFO head from train_load[station_id] and respond via exiting_passenger_out.

      - append_boarded_in (dict): Command to append a boarded passenger into train_load by destination from
        [Sibling-ServiceOrchestrator: boarded_passenger_out].
        structure:
            passenger (dict): Passenger to append.
                passenger_id (int): Unique passenger ID.
                passenger_num (int): Sequential passenger counter.
                origin (int): Origin station ID (1..5).
                destination (int): Destination station ID (1..5, != origin).
        protocol: initialize: ready to accept boarded passengers at T=0 ;
                  process: append passenger to train_load[passenger['destination']] FIFO.

    Output Ports:
      - alight_count_out (dict): Alighting count response to [Sibling-ServiceOrchestrator: alight_count_in].
        structure:
            station_id (int): Station ID (1..5).
            count (int): Number of passengers currently in train_load[station_id] (>=0).
        protocol: initialize: no pending responses at T=0 ;
                  process: output once per received alight_start_in.

      - exiting_passenger_out (dict): Next exiting passenger popped from train_load to [Sibling-ServiceOrchestrator].
        structure:
            station_id (int): Station ID (1..5).
            has_passenger (bool): True if a passenger was popped, else False.
            passenger (dict): Passenger dict if has_passenger else {}.
                passenger_id (int): Unique passenger ID.
                passenger_num (int): Sequential passenger counter.
                origin (int): Origin station ID (1..5).
                destination (int): Destination station ID (1..5).
        protocol: initialize: no pending exiting passenger messages at T=0 ;
                  process: output once per received pop_exiting_in.
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
        self.add_in_port(Port(dict, "alight_start_in"))
        self.add_in_port(Port(dict, "pop_exiting_in"))
        self.add_in_port(Port(dict, "append_boarded_in"))

        self.add_out_port(Port(dict, "alight_count_out"))
        self.add_out_port(Port(dict, "exiting_passenger_out"))

        # Internal hardcoded parameters
        self.param = {
            "station_ids": [1, 2, 3, 4, 5]
        }

        # Internal state
        # train_load (dict[int, list[dict]]): destination_station_id -> FIFO list of passenger dicts
        self.train_load = {sid: [] for sid in self.param["station_ids"]}

        # Prepared payload for next lambdaf (only one output per internal event)
        self._pending_out_port = ""
        self._pending_out_payload = {}

        self.logger.info(
            {"event": "Model Created", "model": self.name, "param": self.param},
            log_type="PROCESS"
        )

    def initialize(self):
        # Initial state per specification: empty train_load and no initial signal
        self.train_load = {sid: [] for sid in self.param["station_ids"]}
        self._pending_out_port = ""
        self._pending_out_payload = {}

        self.logger.info(
            {
                "event": "Model Initialized",
                "train_load_size": {str(sid): int(len(self.train_load[sid])) for sid in self.param["station_ids"]},
            },
            log_type="PROCESS"
        )

        self.hold_in("IDLE", float("inf"))

    def _is_valid_station_id(self, station_id: int) -> bool:
        return isinstance(station_id, int) and station_id in self.train_load

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
        if passenger["origin"] == passenger["destination"]:
            return False
        if not self._is_valid_station_id(passenger["origin"]):
            return False
        if not self._is_valid_station_id(passenger["destination"]):
            return False
        return True

    def lambdaf(self):
        # Output only; do not mutate state here
        if self.phase == "RESPOND_ALIGHT_COUNT" and self._pending_out_port == "alight_count_out":
            self.output["alight_count_out"].add(self._pending_out_payload)
        elif self.phase == "RESPOND_POP_EXITING" and self._pending_out_port == "exiting_passenger_out":
            self.output["exiting_passenger_out"].add(self._pending_out_payload)

    def deltint(self):
        # Internal transition after output has been emitted
        if self.phase in ("RESPOND_ALIGHT_COUNT", "RESPOND_POP_EXITING"):
            # Clear pending output and return to idle
            self._pending_out_port = ""
            self._pending_out_payload = {}
            self.hold_in("IDLE", float("inf"))
        else:
            # Should not happen; remain idle
            self.hold_in("IDLE", float("inf"))

    def deltext(self, e: float):
        # External transition: handle commands; schedule immediate internal event only if an output is needed.
        # Maintain DEVS semantics: if no internal event is scheduled, keep IDLE; if scheduled, reduce by e.
        _ = e  # elapsed time not used for this instantaneous command handler

        # 1) Append boarded passengers (no output)
        for msg in self.input["append_boarded_in"].values:
            if not isinstance(msg, dict) or "passenger" not in msg:
                self.logger.info(
                    {"event": "Boarded Appended", "passenger": {}, "new_count": -1},
                    log_type="ERROR"
                )
                continue

            passenger = msg.get("passenger")
            if not self._is_valid_passenger(passenger):
                self.logger.info(
                    {"event": "Boarded Appended", "passenger": passenger if isinstance(passenger, dict) else {}, "new_count": -1},
                    log_type="ERROR"
                )
                continue

            dest = passenger["destination"]
            self.train_load[dest].append(passenger)
            self.logger.info(
                {
                    "event": "Boarded Appended",
                    "passenger": passenger,
                    "new_count": int(len(self.train_load[dest])),
                },
                log_type="PROCESS"
            )

        # 2) Alight start commands (output count). If multiple arrive in same time, last one wins (single output per cycle).
        alight_cmd = None
        for msg in self.input["alight_start_in"].values:
            alight_cmd = msg

        if isinstance(alight_cmd, dict) and "station_id" in alight_cmd and "arrival_time" in alight_cmd:
            station_id = alight_cmd.get("station_id")
            arrival_time = alight_cmd.get("arrival_time")

            valid = self._is_valid_station_id(station_id) and isinstance(arrival_time, float)
            if not valid:
                self.logger.info(
                    {"event": "Alight Start Processed", "cmd": alight_cmd, "count": -1},
                    log_type="ERROR"
                )
            else:
                count = int(len(self.train_load[station_id]))
                self._pending_out_port = "alight_count_out"
                self._pending_out_payload = {"station_id": int(station_id), "count": count}

                self.logger.info(
                    {"event": "Alight Start Processed", "cmd": alight_cmd, "count": count},
                    log_type="PROCESS"
                )

                # Schedule immediate output
                self.hold_in("RESPOND_ALIGHT_COUNT", 0.0)
                return

        # 3) Pop exiting commands (output passenger). If multiple arrive in same time, last one wins.
        pop_cmd = None
        for msg in self.input["pop_exiting_in"].values:
            pop_cmd = msg

        if isinstance(pop_cmd, dict) and "station_id" in pop_cmd:
            station_id = pop_cmd.get("station_id")
            if not self._is_valid_station_id(station_id):
                self.logger.info(
                    {"event": "Pop Exiting Processed", "cmd": pop_cmd, "result": {"station_id": -1, "has_passenger": False, "passenger": {}}},
                    log_type="ERROR"
                )
            else:
                if len(self.train_load[station_id]) > 0:
                    passenger = self.train_load[station_id].pop(0)
                    result = {
                        "station_id": int(station_id),
                        "has_passenger": True,
                        "passenger": passenger,
                    }
                else:
                    result = {
                        "station_id": int(station_id),
                        "has_passenger": False,
                        "passenger": {},
                    }

                self._pending_out_port = "exiting_passenger_out"
                self._pending_out_payload = result

                self.logger.info(
                    {"event": "Pop Exiting Processed", "cmd": pop_cmd, "result": result},
                    log_type="PROCESS"
                )

                self.hold_in("RESPOND_POP_EXITING", 0.0)
                return

        # No output needed; remain idle
        self.hold_in("IDLE", float("inf"))

    def exit(self):
        self.logger.info(
            {
                "event": "Model Finalized",
                "train_load_size": {str(sid): int(len(self.train_load[sid])) for sid in self.param["station_ids"]},
            },
            log_type="RESULT"
        )