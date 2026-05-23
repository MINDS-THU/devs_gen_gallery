### BEGIN: General Import
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time
### END


class StationQueueSystem(Atomic):
    """
    Function:
        - Owns and maintains per-station FIFO waiting queues queue[station_id] for station_id in 1..5.
        - Receives passenger records and enqueues them into queue[origin] after validation.
        - Receives dequeue requests for a station and immediately responds with either:
            - has_passenger=true and the dequeued head-of-line passenger (FIFO), or
            - has_passenger=false and an empty passenger dict {}.
        - States and Output at the end of the state:
            - IDLE: Waiting for external events; no output.
            - RESPOND: After processing a dequeue request, outputs one dequeue_response_out, then returns to IDLE.

    Logging in this model:
        - event: Model Created
            log_type: PROCESS
            msg (dict):
                event (str): "Model Created"
                model (str): Model name
                param (dict): Internal hardcoded parameters
                    station_ids (list[int]): Station IDs managed by this model (always [1,2,3,4,5])
        - event: Model Initialized
            log_type: PROCESS
            msg (dict):
                event (str): "Model Initialized"
                station_queue_lengths (dict): Current queue lengths per station (all zeros at init)
                    1 (int): Queue length for station 1
                    2 (int): Queue length for station 2
                    3 (int): Queue length for station 3
                    4 (int): Queue length for station 4
                    5 (int): Queue length for station 5
        - event: Passenger Enqueued
            log_type: PROCESS
            msg (dict): Enqueue action summary
                station_id (int): Station whose queue was enqueued (equals passenger.origin)
                passenger (dict): Passenger record (same structure as input passenger_in)
                    passenger_id (int): Passenger unique ID
                    passenger_num (int): Sequential passenger counter
                    origin (int): Origin station id (1..5)
                    destination (int): Destination station id (1..5, != origin)
                new_length (int): New queue length after enqueue
        - event: Passenger Rejected
            log_type: PROCESS
            msg (dict): Rejection summary (does not emit core JSONL events)
                reason (str): Reason code
                passenger (dict): Passenger record received (same structure as input passenger_in)
                    passenger_id (int): Passenger unique ID
                    passenger_num (int): Sequential passenger counter
                    origin (int): Origin station id (1..5)
                    destination (int): Destination station id (1..5)
        - event: Dequeue Request Processed
            log_type: PROCESS
            msg (dict): Dequeue processing summary
                station_id (int): Station requested (1..5)
                has_passenger (bool): Whether a passenger was dequeued
                passenger (dict): Dequeued passenger if any; otherwise {}
                    passenger_id (int): Passenger unique ID
                    passenger_num (int): Sequential passenger counter
                    origin (int): Origin station id (1..5)
                    destination (int): Destination station id (1..5, != origin)
                new_length (int): New queue length after dequeue (or unchanged if empty)
        - event: Model Finalized
            log_type: RESULT
            msg (dict):
                event (str): "Model Finalized"
                station_queue_lengths (dict): Final queue lengths per station
                    1 (int): Queue length for station 1
                    2 (int): Queue length for station 2
                    3 (int): Queue length for station 3
                    4 (int): Queue length for station 4
                    5 (int): Queue length for station 5

    Input Ports:
      - passenger_in (dict): Passenger record to enqueue.
        structure:
            passenger_id (int): Unique ID.
            passenger_num (int): Sequential counter (0 for initial, >=1 for others).
            origin (int): Station ID (1..5).
            destination (int): Station ID (1..5), must be != origin.
        protocol: initialize: all station queues empty at T=0 ; process: validate and enqueue into queue[origin] (FIFO)

      - dequeue_request_in (dict): Request to dequeue one passenger for boarding.
        structure:
            station_id (int): Station ID (1..5).
        protocol: initialize: ready to accept dequeue requests at T=0 ; process: if queue non-empty, pop FIFO and respond immediately

    Output Ports:
      - dequeue_response_out (dict): Response to a dequeue request.
        structure:
            station_id (int): Station ID (1..5).
            has_passenger (bool): True if a passenger was dequeued, else False.
            passenger (dict): Passenger record if has_passenger is True, else {}.
                passenger_id (int): Unique ID.
                passenger_num (int): Sequential counter.
                origin (int): Station ID (1..5).
                destination (int): Station ID (1..5), != origin.
        protocol: initialize: no pending responses at T=0 ; process: output one response per request immediately
    """

    # Internal hardcoded parameters defined in self.param
    param = {
        "station_ids": [1, 2, 3, 4, 5]
    }

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
        self.add_in_port(Port(dict, "passenger_in"))
        self.add_in_port(Port(dict, "dequeue_request_in"))
        self.add_out_port(Port(dict, "dequeue_response_out"))

        # Internal state
        self.queue_by_station = {sid: [] for sid in self.param["station_ids"]}  # dict[int, list[dict]]
        self._pending_response = None  # dict | None

        # Start passive; initialize() will set proper phase/sigma
        self.hold_in("IDLE", float("inf"))

        self.logger.info(
            {"event": "Model Created", "model": self.name, "param": self.param},
            log_type="PROCESS"
        )

    def initialize(self):
        # Reset queues and pending response
        self.queue_by_station = {sid: [] for sid in self.param["station_ids"]}
        self._pending_response = None

        self.logger.info(
            {
                "event": "Model Initialized",
                "station_queue_lengths": {str(sid): len(self.queue_by_station[sid]) for sid in self.param["station_ids"]},
            },
            log_type="PROCESS"
        )

        # No initial signal
        self.hold_in("IDLE", float("inf"))

    def _is_valid_station_id(self, station_id: int) -> bool:
        return isinstance(station_id, int) and station_id in self.queue_by_station

    def _validate_passenger(self, p: dict) -> tuple[bool, str]:
        # Required keys
        for k in ["passenger_id", "passenger_num", "origin", "destination"]:
            if k not in p:
                return False, "missing_key_" + str(k)

        # Type checks (only primitives allowed)
        if not isinstance(p["passenger_id"], int):
            return False, "bad_type_passenger_id"
        if not isinstance(p["passenger_num"], int):
            return False, "bad_type_passenger_num"
        if not isinstance(p["origin"], int):
            return False, "bad_type_origin"
        if not isinstance(p["destination"], int):
            return False, "bad_type_destination"

        # Range and constraints
        if not self._is_valid_station_id(p["origin"]):
            return False, "origin_out_of_range"
        if not self._is_valid_station_id(p["destination"]):
            return False, "destination_out_of_range"
        if p["destination"] == p["origin"]:
            return False, "destination_equals_origin"

        return True, "ok"

    def deltext(self, e: float):
        # External transition: handle enqueues and dequeue requests.
        # Maintain remaining time if already scheduled
        remaining = self.ta() - e
        if remaining < 0.0:
            remaining = 0.0

        # 1) Handle passenger enqueues (can be multiple)
        for passenger in self.input["passenger_in"].values:
            valid, reason = self._validate_passenger(passenger)
            if not valid:
                self.logger.info(
                    {"event": "Passenger Rejected", "reason": reason, "passenger": passenger},
                    log_type="PROCESS"
                )
                continue

            origin = passenger["origin"]
            self.queue_by_station[origin].append(
                {
                    "passenger_id": passenger["passenger_id"],
                    "passenger_num": passenger["passenger_num"],
                    "origin": passenger["origin"],
                    "destination": passenger["destination"],
                }
            )
            self.logger.info(
                {
                    "event": "Passenger Enqueued",
                    "station_id": origin,
                    "passenger": passenger,
                    "new_length": len(self.queue_by_station[origin]),
                },
                log_type="PROCESS"
            )

        # 2) Handle dequeue requests (can be multiple). For each request, we respond.
        # Since we only have one output per internal event, we schedule immediate RESPOND
        # for the last processed request if multiple arrive simultaneously.
        last_response = None
        for req in self.input["dequeue_request_in"].values:
            station_id = req.get("station_id", None)
            if not isinstance(station_id, int) or not self._is_valid_station_id(station_id):
                # Invalid request -> respond as empty (safe behavior)
                last_response = {"station_id": int(station_id) if isinstance(station_id, int) else -1,
                                 "has_passenger": False,
                                 "passenger": {}}
                self.logger.info(
                    {
                        "event": "Dequeue Request Processed",
                        "station_id": last_response["station_id"],
                        "has_passenger": False,
                        "passenger": {},
                        "new_length": -1,
                    },
                    log_type="PROCESS"
                )
                continue

            if len(self.queue_by_station[station_id]) > 0:
                passenger = self.queue_by_station[station_id].pop(0)
                last_response = {
                    "station_id": station_id,
                    "has_passenger": True,
                    "passenger": passenger
                }
                self.logger.info(
                    {
                        "event": "Dequeue Request Processed",
                        "station_id": station_id,
                        "has_passenger": True,
                        "passenger": passenger,
                        "new_length": len(self.queue_by_station[station_id]),
                    },
                    log_type="PROCESS"
                )
            else:
                last_response = {
                    "station_id": station_id,
                    "has_passenger": False,
                    "passenger": {}
                }
                self.logger.info(
                    {
                        "event": "Dequeue Request Processed",
                        "station_id": station_id,
                        "has_passenger": False,
                        "passenger": {},
                        "new_length": 0,
                    },
                    log_type="PROCESS"
                )

        # Scheduling: if we have a response to emit, do it immediately.
        if last_response is not None:
            self._pending_response = last_response
            self.hold_in("RESPOND", 0.0)
        else:
            # No output required; keep current phase timing (or go idle)
            if self.phase == "RESPOND":
                # If we were about to respond but got interrupted without new response, keep it immediate.
                self.hold_in("RESPOND", 0.0)
            else:
                self.hold_in("IDLE", float("inf") if self.phase == "IDLE" else remaining)

    def lambdaf(self):
        # Output only; no state changes here
        if self.phase == "RESPOND" and isinstance(self._pending_response, dict):
            self.output["dequeue_response_out"].add(self._pending_response)

    def deltint(self):
        # Internal transition: after responding, clear pending response and go idle
        if self.phase == "RESPOND":
            self._pending_response = None
            self.hold_in("IDLE", float("inf"))
        else:
            self.hold_in("IDLE", float("inf"))

    def exit(self):
        self.logger.info(
            {
                "event": "Model Finalized",
                "station_queue_lengths": {str(sid): len(self.queue_by_station[sid]) for sid in self.param["station_ids"]},
                "time": get_current_time(),
            },
            log_type="RESULT"
        )