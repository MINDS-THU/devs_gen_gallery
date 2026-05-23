import random
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class PassengerInitGenerator(Atomic):
    """
    Function:
        - Responsible for the special initialization passenger generation at init_passenger_time_seconds for all 5 stations.
        - States and Output at the end of the state:
            - WAIT_INIT: Waits until init_passenger_time_seconds; when the state is over, emits 5 passenger_out messages
              (one per station 1..5) and logs 5 passenger_generated JSONL events (one per station).
            - DONE: No further outputs; remains passive forever.

    Logging in this model:
        - event: Model Created
            log_type: PROCESS
            msg (dict):
                event (str): "Model Created".
                init_passenger_time_seconds (float): Time to create initialization passengers.
                stations (list[int]): Station IDs to generate initialization passengers for.
        - event: Model Initialized
            log_type: PROCESS
            msg (dict):
                event (str): "Model Initialized".
                init_passenger_time_seconds (float): Time to create initialization passengers.
        - passenger_generated (required JSONL event schema)
            log_type: PROCESS
            msg (dict):
                time (float): Simulation timestamp in seconds.
                event (str): Always "passenger_generated".
                entity_type (str): Always "passenger_generator".
                station_id (int): Origin station ID (1..5).
                station (str): Station name mapped from station_id.
                payload (dict): Passenger record.
                    passenger_id (int): Always 0 for initialization passengers.
                    passenger_num (int): Always 0 for initialization passengers.
                    origin (int): Origin station ID (1..5).
                    destination (int): Destination station ID (1..5), != origin.
        - event: Model Finalized
            log_type: RESULT
            msg (dict):
                event (str): "Model Finalized".
                total_init_passengers_emitted (int): Total number of initialization passengers emitted (expected 5).

    Input Ports:
        - None

    Output Ports:
        - passenger_out (dict): Passenger record for initialization passengers.
            structure:
                passenger_id (int): Always 0.
                passenger_num (int): Always 0.
                origin (int): Station ID in [1..5].
                destination (int): Station ID in [1..5] and destination != origin.
            protocol: initialize: no buffered passengers at T=0; process: at T=init_passenger_time_seconds, emits 5
                      passenger_out messages (one per station 1..5), then stops emitting.
    """

    def __init__(
        self,
        name: str,
        parent: Coupled | None,
        init_passenger_time_seconds: float = 0.5,
    ):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            init_passenger_time_seconds (float): Time to create initialization passengers at all stations. Default 0.5.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        self.add_out_port(Port(dict, "passenger_out"))

        self.init_passenger_time_seconds = float(init_passenger_time_seconds)

        self.param = {
            "station_id_to_name": {
                1: "Bayview",
                2: "Carling",
                3: "Carleton",
                4: "Confed",
                5: "Greenboro",
            },
            "stations": [1, 2, 3, 4, 5],
        }

        self._pending_outputs: list[dict] = []
        self._emitted_total: int = 0

        self.logger.info(
            {
                "event": "Model Created",
                "init_passenger_time_seconds": self.init_passenger_time_seconds,
                "stations": list(self.param["stations"]),
            },
            log_type="PROCESS",
        )

    def initialize(self):
        self._pending_outputs = []
        self._emitted_total = 0

        self.logger.info(
            {
                "event": "Model Initialized",
                "init_passenger_time_seconds": self.init_passenger_time_seconds,
            },
            log_type="PROCESS",
        )

        # Schedule the required initial signal at T=init_passenger_time_seconds
        self.hold_in("WAIT_INIT", self.init_passenger_time_seconds)

    def _choose_destination(self, origin_station_id: int) -> int:
        candidates = [s for s in self.param["stations"] if s != origin_station_id]
        return int(random.choice(candidates))

    def _build_passenger_record(
        self, origin_station_id: int, destination_station_id: int
    ) -> dict:
        return {
            "passenger_id": 0,
            "passenger_num": 0,
            "origin": int(origin_station_id),
            "destination": int(destination_station_id),
        }

    def lambdaf(self):
        if self.phase == "WAIT_INIT":
            for msg in self._pending_outputs:
                self.output["passenger_out"].add(msg)

                station_id = int(msg["origin"])
                station_name = self.param["station_id_to_name"].get(
                    station_id, "UNKNOWN"
                )
                self.logger.info(
                    {
                        "time": float(get_current_time()),
                        "event": "passenger_generated",
                        "entity_type": "passenger_generator",
                        "station_id": station_id,
                        "station": str(station_name),
                        "payload": msg,
                    },
                    log_type="PROCESS",
                )

    def deltint(self):
        if self.phase == "WAIT_INIT":
            # Outputs were already sent in lambdaf; now finalize and go passive.
            self._pending_outputs = []
            self.hold_in("DONE", float("inf"))
            return

        self.hold_in("DONE", float("inf"))

    def deltext(self, e: float):
        # No input ports; keep current schedule (deduct elapsed time).
        remaining = self.ta() - float(e)
        if remaining < 0.0:
            remaining = 0.0
        self.hold_in(self.phase, remaining)

    def exit(self):
        self.logger.info(
            {
                "event": "Model Finalized",
                "total_init_passengers_emitted": int(self._emitted_total),
            },
            log_type="RESULT",
        )

    # ---- Preparation of outputs for WAIT_INIT ----
    # In DEVS, lambdaf uses payload prepared in initialize/deltint/deltext.
    # Here we prepare the 5 passengers in initialize by scheduling WAIT_INIT,
    # but we must prepare payload before lambdaf executes at the timeout.
    # Therefore, we prepare payload immediately when entering WAIT_INIT (i.e., in initialize).
    def hold_in(self, phase: str, sigma: float):
        # Intercept transition into WAIT_INIT to prepare payload once.
        super().hold_in(phase, sigma)
        if phase == "WAIT_INIT":
            # Prepare exactly 5 initialization passengers (one per station).
            self._pending_outputs = []
            for station_id in self.param["stations"]:
                dest = self._choose_destination(station_id)
                passenger = self._build_passenger_record(station_id, dest)

                # Validate constraints
                if passenger["origin"] != station_id:
                    self.logger.info(
                        {
                            "event": "Validation Error",
                            "reason": "origin_mismatch",
                            "station_id": int(station_id),
                            "passenger": passenger,
                        },
                        log_type="ERROR",
                    )
                    continue
                if passenger["destination"] == passenger["origin"]:
                    self.logger.info(
                        {
                            "event": "Validation Error",
                            "reason": "destination_equals_origin",
                            "station_id": int(station_id),
                            "passenger": passenger,
                        },
                        log_type="ERROR",
                    )
                    continue

                self._pending_outputs.append(passenger)
                self._emitted_total += 1
