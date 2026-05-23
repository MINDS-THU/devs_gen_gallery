import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class BoardingScheduler(Atomic):
    """
    Function:
        - Implements the boarding phase timing for each train arrival after alighting is complete.
        - For each arrival context (station_id k, arrival_time t, direction d):
            - Wait until alight_done_in is received for (k, t) to satisfy deterministic ordering constraints.
            - Then schedule boarding attempts at times t + service_time_seconds * m for m=1.. until station queue is empty.
            - At each scheduled boarding time:
                - Send dequeue_request_out {'station_id': k} to StationQueueSystem.
                - Wait for dequeue_response_in for station k:
                    - If has_passenger is true:
                        - Forward passenger to TrainLoadStore via boarded_passenger_out.
                        - Forward a boarding_event_out to PassengerEventLogger with the scheduled time.
                        - Schedule the next attempt at +service_time_seconds.
                    - If has_passenger is false:
                        - Stop boarding attempts for this arrival.

        - States and Output at the end of the state:
            - IDLE: No pending internal actions; outputs nothing.
            - SEND_DEQUEUE: When this state ends, outputs dequeue_request_out for the active station_id.
            - WAIT_DEQUEUE_RESPONSE: No output; waits for dequeue_response_in.
            - EMIT_BOARDING: When this state ends, outputs boarded_passenger_out and boarding_event_out for the passenger.

    Logging in this model:
        - event: Model Created
            log_type: PROCESS
            msg (dict):
                event (str): "Model Created"
                service_time_seconds (float): Configured per-passenger boarding time.
                param (dict): Internal hardcoded parameters.
                    eps_time (float): Small epsilon used for time comparisons.
        - event: Model Initialized
            log_type: PROCESS
            msg (dict):
                event (str): "Model Initialized"
                service_time_seconds (float): Configured per-passenger boarding time.
        - event: Arrival Context Received
            log_type: PROCESS
            msg (dict): Same structure as arrival_ctx_in.
                station_id (int): 1..5
                arrival_time (float): Arrival timestamp (seconds)
                direction (int): 0 or 1
        - event: Alight Done Gate Received
            log_type: PROCESS
            msg (dict): Same structure as alight_done_in.
                station_id (int): 1..5
                arrival_time (float): Arrival timestamp (seconds)
        - event: Dequeue Requested
            log_type: PROCESS
            msg (dict): Same structure as dequeue_request_out.
                station_id (int): 1..5
        - event: Dequeue Response Processed
            log_type: PROCESS
            msg (dict): Same structure as dequeue_response_in.
                station_id (int): 1..5
                has_passenger (bool): Whether a passenger was dequeued
                passenger (dict): Passenger data or {} if none
                    passenger_id (int): Encoded passenger id
                    passenger_num (int): Sequential number
                    origin (int): 1..5
                    destination (int): 1..5
        - event: Boarding Emitted
            log_type: PROCESS
            msg (dict):
                event (str): "Boarding Emitted"
                station_id (int): 1..5
                arrival_time (float): Arrival timestamp (seconds)
                direction (int): 0 or 1
                scheduled_time (float): Scheduled boarding time for this passenger
                passenger (dict): Passenger data
                    passenger_id (int): Encoded passenger id
                    passenger_num (int): Sequential number
                    origin (int): 1..5
                    destination (int): 1..5
        - event: Model Finalized
            log_type: RESULT
            msg (dict):
                event (str): "Model Finalized"
                total_boarded (int): Total boarded passengers forwarded.
                total_arrivals_seen (int): Total arrival contexts received.

    Input Ports:
      - arrival_ctx_in (dict): Arrival context from [Sibling-ArrivalPhaseCoordinator: board_start_ctx_out].
        structure:
            station_id (int): Station ID (1..5).
            arrival_time (float): Train arrival time in seconds.
            direction (int): Direction (0 southbound, 1 northbound).
        protocol: initialize: no active boarding schedules at T=0 ; process: enqueue arrival contexts and wait for alight_done gate.

      - alight_done_in (dict): Gate signal indicating alighting is complete for an arrival from
        [Sibling-ArrivalPhaseCoordinator: alight_done_out].
        structure:
            station_id (int): Station ID (1..5).
            arrival_time (float): Train arrival time in seconds.
        protocol: initialize: no gates released at T=0 ; process: release boarding for matching (station_id, arrival_time).

      - dequeue_response_in (dict): Response from station queue system (wired from StationQueueSystem).
        structure:
            station_id (int): Station ID (1..5).
            has_passenger (bool): True if a passenger was dequeued.
            passenger (dict): Passenger data if has_passenger else {}.
                passenger_id (int): Encoded passenger id.
                passenger_num (int): Sequential passenger number.
                origin (int): Origin station id (1..5).
                destination (int): Destination station id (1..5).
        protocol: initialize: no pending responses at T=0 ; process: completes the pending dequeue request for the active station.

    Output Ports:
      - dequeue_request_out (dict): Request to dequeue one passenger for boarding (to StationQueueSystem).
        structure:
            station_id (int): Station ID (1..5).
        protocol: initialize: no outstanding requests at T=0 ; process: sent at each scheduled boarding time after alight gate.

      - boarded_passenger_out (dict): Command to append a boarded passenger into train_load by destination (to TrainLoadStore).
        structure:
            passenger (dict): Passenger data.
                passenger_id (int): Encoded passenger id.
                passenger_num (int): Sequential passenger number.
                origin (int): Origin station id (1..5).
                destination (int): Destination station id (1..5), must differ from origin.
        protocol: initialize: no boarded passengers to forward at T=0 ; process: sent after successful dequeue response.

      - boarding_event_out (dict): Internal event for logging a boarding passenger (to PassengerEventLogger).
        structure:
            time (float): Boarding event time (must equal scheduled boarding time).
            station_id (int): Station ID (1..5).
            direction (int): Direction (0 or 1).
            passenger (dict): Passenger data.
                passenger_id (int): Encoded passenger id.
                passenger_num (int): Sequential passenger number.
                origin (int): Origin station id (1..5).
                destination (int): Destination station id (1..5).
        protocol: initialize: no pending boarding log events at T=0 ; process: sent when has_passenger=true at the scheduled time.
    """

    def __init__(
        self, name: str, parent: Coupled | None, service_time_seconds: float = 0.025
    ):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            service_time_seconds (float): Per-passenger boarding time in seconds.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match specification)
        self.add_in_port(Port(dict, "arrival_ctx_in"))
        self.add_in_port(Port(dict, "alight_done_in"))
        self.add_in_port(Port(dict, "dequeue_response_in"))

        self.add_out_port(Port(dict, "dequeue_request_out"))
        self.add_out_port(Port(dict, "boarded_passenger_out"))
        self.add_out_port(Port(dict, "boarding_event_out"))

        # Config
        self.service_time_seconds = float(service_time_seconds)

        # Internal hardcoded parameters
        self.param = {"eps_time": 1e-9}

        # Internal state
        self._pending_arrivals = []  # list[dict] of arrival_ctx_in
        self._gated = {}  # dict[str,bool] keyed by arrival_key -> gate released
        self._active_arrival = None  # dict | None
        self._attempt_index = 0  # int, m starting from 1
        self._pending_dequeue_station_id = None  # int | None
        self._pending_dequeue_key = ""  # str
        self._scheduled_time = None  # float | None

        # Payloads prepared for lambdaf
        self._out_dequeue_req = None  # dict | None
        self._out_boarded = None  # dict | None
        self._out_boarding_event = None  # dict | None

        # KPIs
        self._total_boarded = 0
        self._total_arrivals_seen = 0

        self.logger.info(
            {
                "event": "Model Created",
                "service_time_seconds": self.service_time_seconds,
                "param": self.param,
            },
            log_type="PROCESS",
        )

    def initialize(self):
        self._pending_arrivals = []
        self._gated = {}
        self._active_arrival = None
        self._attempt_index = 0
        self._pending_dequeue_station_id = None
        self._pending_dequeue_key = ""
        self._scheduled_time = None

        self._out_dequeue_req = None
        self._out_boarded = None
        self._out_boarding_event = None

        self._total_boarded = 0
        self._total_arrivals_seen = 0

        self.logger.info(
            {
                "event": "Model Initialized",
                "service_time_seconds": self.service_time_seconds,
            },
            log_type="PROCESS",
        )
        self.hold_in("IDLE", float("inf"))

    def _arrival_key(self, station_id: int, arrival_time: float) -> str:
        # Use a stable string key; arrival_time is expected deterministic in this simulation.
        return f"{int(station_id)}@{float(arrival_time):.9f}"

    def _select_next_active_arrival(self) -> bool:
        """
        Select the next gated arrival to process, FIFO by arrival_time then insertion order.
        Returns True if one is selected.
        """
        if self._active_arrival is not None:
            return True

        if not self._pending_arrivals:
            return False

        # Find earliest gated arrival (stable)
        best_idx = -1
        best_time = None
        for i, ctx in enumerate(self._pending_arrivals):
            key = self._arrival_key(int(ctx["station_id"]), float(ctx["arrival_time"]))
            if not self._gated.get(key, False):
                continue
            t = float(ctx["arrival_time"])
            if best_idx < 0 or t < float(best_time):
                best_idx = i
                best_time = t

        if best_idx < 0:
            return False

        self._active_arrival = self._pending_arrivals.pop(best_idx)
        self._attempt_index = 0
        return True

    def _schedule_next_dequeue(self):
        """
        Prepare next dequeue request for the active arrival and schedule internal event at the correct time.
        """
        if self._active_arrival is None:
            self._out_dequeue_req = None
            self.hold_in("IDLE", float("inf"))
            return

        self._attempt_index += 1
        station_id = int(self._active_arrival["station_id"])
        arrival_time = float(self._active_arrival["arrival_time"])

        scheduled_time = arrival_time + self.service_time_seconds * float(
            self._attempt_index
        )
        self._scheduled_time = scheduled_time

        now = float(get_current_time())
        sigma = scheduled_time - now
        if sigma < 0.0 and abs(sigma) <= float(self.param["eps_time"]):
            sigma = 0.0
        elif sigma < 0.0:
            # If simulation time already passed due to ordering, execute immediately.
            sigma = 0.0

        self._pending_dequeue_station_id = station_id
        self._pending_dequeue_key = self._arrival_key(station_id, arrival_time)
        self._out_dequeue_req = {"station_id": station_id}

        self.hold_in("SEND_DEQUEUE", float(sigma))

    def deltext(self, e: float):
        # Maintain remaining time unless we reschedule explicitly
        remaining = self.ta() - float(e)
        if remaining < 0.0:
            remaining = 0.0

        # Process arrival contexts
        for ctx in self.input["arrival_ctx_in"].values:
            # Expected keys: station_id, arrival_time, direction
            self._pending_arrivals.append(
                {
                    "station_id": int(ctx["station_id"]),
                    "arrival_time": float(ctx["arrival_time"]),
                    "direction": int(ctx["direction"]),
                }
            )
            self._total_arrivals_seen += 1
            self.logger.info(
                {
                    "event": "Arrival Context Received",
                    "station_id": int(ctx["station_id"]),
                    "arrival_time": float(ctx["arrival_time"]),
                    "direction": int(ctx["direction"]),
                },
                log_type="PROCESS",
            )

        # Process alight done gates
        for gate in self.input["alight_done_in"].values:
            station_id = int(gate["station_id"])
            arrival_time = float(gate["arrival_time"])
            key = self._arrival_key(station_id, arrival_time)
            self._gated[key] = True
            self.logger.info(
                {
                    "event": "Alight Done Gate Received",
                    "station_id": station_id,
                    "arrival_time": arrival_time,
                },
                log_type="PROCESS",
            )

        # Process dequeue responses (only meaningful in WAIT_DEQUEUE_RESPONSE)
        for resp in self.input["dequeue_response_in"].values:
            station_id = int(resp["station_id"])
            has_passenger = bool(resp["has_passenger"])
            passenger = resp.get("passenger", {})
            if passenger is None:
                passenger = {}

            self.logger.info(
                {
                    "event": "Dequeue Response Processed",
                    "station_id": station_id,
                    "has_passenger": has_passenger,
                    "passenger": passenger,
                },
                log_type="PROCESS",
            )

            if self.phase != "WAIT_DEQUEUE_RESPONSE":
                # Ignore unexpected responses (should not happen in correct wiring)
                continue

            if self._pending_dequeue_station_id is None or station_id != int(
                self._pending_dequeue_station_id
            ):
                # Ignore responses for other stations while waiting for current one
                continue

            if has_passenger:
                # Prepare outputs for lambdaf; time must equal scheduled boarding time
                self._out_boarded = {"passenger": passenger}
                self._out_boarding_event = {
                    "time": float(self._scheduled_time)
                    if self._scheduled_time is not None
                    else float(get_current_time()),
                    "station_id": int(self._active_arrival["station_id"])
                    if self._active_arrival
                    else station_id,
                    "direction": int(self._active_arrival["direction"])
                    if self._active_arrival
                    else 0,
                    "passenger": passenger,
                }
                self.hold_in("EMIT_BOARDING", 0.0)
                return
            else:
                # Stop boarding for this arrival
                self._active_arrival = None
                self._attempt_index = 0
                self._pending_dequeue_station_id = None
                self._pending_dequeue_key = ""
                self._scheduled_time = None
                self._out_dequeue_req = None
                self._out_boarded = None
                self._out_boarding_event = None

                # Try to start next gated arrival immediately
                if self._select_next_active_arrival():
                    self._schedule_next_dequeue()
                else:
                    self.hold_in("IDLE", float("inf"))
                return

        # If idle and a gated arrival is available, start it
        if self.phase == "IDLE":
            if self._select_next_active_arrival():
                self._schedule_next_dequeue()
            else:
                self.hold_in("IDLE", float("inf"))
            return

        # Otherwise, if we didn't explicitly reschedule above, keep current phase with reduced remaining time
        if self.phase in ("SEND_DEQUEUE", "WAIT_DEQUEUE_RESPONSE", "EMIT_BOARDING"):
            # If we are waiting for response, keep waiting.
            # If we are counting down to send dequeue, keep countdown.
            # If we are about to emit boarding (sigma 0), keep it.
            self.hold_in(self.phase, float(remaining))
        else:
            self.hold_in("IDLE", float("inf"))

    def lambdaf(self):
        # Output only; no state changes here
        if self.phase == "SEND_DEQUEUE" and self._out_dequeue_req is not None:
            self.output["dequeue_request_out"].add(self._out_dequeue_req)
        elif self.phase == "EMIT_BOARDING":
            if self._out_boarded is not None:
                self.output["boarded_passenger_out"].add(self._out_boarded)
            if self._out_boarding_event is not None:
                self.output["boarding_event_out"].add(self._out_boarding_event)

    def deltint(self):
        old_phase = self.phase

        if old_phase == "SEND_DEQUEUE":
            # After sending request, wait for response
            if self._out_dequeue_req is not None:
                self.logger.info(
                    {
                        "event": "Dequeue Requested",
                        "station_id": int(self._out_dequeue_req["station_id"]),
                    },
                    log_type="PROCESS",
                )
            # Clear prepared request payload (already sent)
            self._out_dequeue_req = None
            self.hold_in("WAIT_DEQUEUE_RESPONSE", float("inf"))
            return

        if old_phase == "EMIT_BOARDING":
            # Boarding outputs already emitted; update KPIs and schedule next attempt
            passenger = None
            if self._out_boarding_event is not None:
                passenger = self._out_boarding_event.get("passenger", {})
                self.logger.info(
                    {
                        "event": "Boarding Emitted",
                        "station_id": int(self._out_boarding_event["station_id"]),
                        "arrival_time": float(self._active_arrival["arrival_time"])
                        if self._active_arrival
                        else -1.0,
                        "direction": int(self._out_boarding_event["direction"]),
                        "scheduled_time": float(self._out_boarding_event["time"]),
                        "passenger": passenger,
                    },
                    log_type="PROCESS",
                )

            self._total_boarded += 1
            self._out_boarded = None
            self._out_boarding_event = None

            # Keep same active arrival; schedule next dequeue attempt
            self._schedule_next_dequeue()
            return

        if old_phase == "WAIT_DEQUEUE_RESPONSE":
            # Should not timeout; remain waiting
            self.hold_in("WAIT_DEQUEUE_RESPONSE", float("inf"))
            return

        # IDLE or unknown: try to start next gated arrival
        if self._select_next_active_arrival():
            self._schedule_next_dequeue()
        else:
            self.hold_in("IDLE", float("inf"))

    def exit(self):
        self.logger.info(
            {
                "event": "Model Finalized",
                "total_boarded": int(self._total_boarded),
                "total_arrivals_seen": int(self._total_arrivals_seen),
            },
            log_type="RESULT",
        )
