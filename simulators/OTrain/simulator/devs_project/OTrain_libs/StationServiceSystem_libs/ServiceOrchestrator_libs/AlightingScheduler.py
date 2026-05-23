import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class AlightingScheduler(Atomic):
    """
    Function:
        - Implements the alighting phase timing for each train arrival and coordinates with TrainLoadStore.
        - For each arrival context (station_id k, arrival_time t, direction d):
            - Wait for alight_count_in for station k, then schedule exactly 'count' exit slots at:
              t + service_time_seconds * j, for j=1..count.
            - At each scheduled exit slot:
                - Send pop_exiting_out {'station_id': k} to TrainLoadStore.
                - Wait for exiting_passenger_in response; if has_passenger=true, forward an exiting_event_out
                  containing the scheduled time, station_id, direction, and passenger dict.
            - After all scheduled exit slots have been processed (including the last response),
              emit alight_complete_out {'station_id': k, 'arrival_time': t}.
        - States and Output at the end of the state:
            - IDLE: No active arrival being processed; no output.
            - WAIT_COUNT: Waiting for alight_count_in for the active arrival; no output.
            - POP: At state's end, outputs pop_exiting_out for the active station.
            - WAIT_PASSENGER: Waiting for exiting_passenger_in for the previously issued pop; no output.
            - EMIT_EXIT_EVENT: At state's end, outputs exiting_event_out for the popped passenger (only if has_passenger=true).
            - COMPLETE: At state's end, outputs alight_complete_out for the active arrival, then returns to IDLE.

    Logging in this model:
        - event: Model Created
            log_type: PROCESS
            msg (dict):
                event (str): "Model Created"
                service_time_seconds (float): Per-passenger alighting service time (seconds)
                param (dict): Internal hardcoded parameters
                    eps_time (float): Small epsilon for non-negative scheduling
        - event: Model Initialized
            log_type: PROCESS
            msg (dict):
                event (str): "Model Initialized"
                service_time_seconds (float): Per-passenger alighting service time (seconds)
        - event: Arrival Context Received
            log_type: PROCESS
            msg (dict): Same structure as input port arrival_ctx_in.
        - event: Alight Count Received
            log_type: PROCESS
            msg (dict): Same structure as input port alight_count_in.
        - event: Pop Exiting Command Scheduled
            log_type: PROCESS
            msg (dict):
                event (str): "Pop Exiting Command Scheduled"
                station_id (int): 1..5
                arrival_time (float): Arrival time of the active context
                direction (int): 0 or 1
                slot_index (int): Current slot j (1..count)
                scheduled_time (float): Time at which pop is executed
        - event: Exiting Passenger Received
            log_type: PROCESS
            msg (dict): Same structure as input port exiting_passenger_in.
        - event: Exiting Event Forwarded
            log_type: PROCESS
            msg (dict): Same structure as output port exiting_event_out.
        - event: Alight Complete Emitted
            log_type: PROCESS
            msg (dict): Same structure as output port alight_complete_out.
        - event: Model Finalized
            log_type: RESULT
            msg (dict):
                event (str): "Model Finalized"
                total_arrivals_processed (int): Number of arrival contexts completed
                total_pop_commands_sent (int): Total pop_exiting_out commands sent
                total_exiting_events_forwarded (int): Total exiting_event_out forwarded (has_passenger=true)

    Input Ports:
      - arrival_ctx_in (dict): Arrival context from [Sibling-ArrivalPhaseCoordinator: alight_start_ctx_out].
        structure:
            station_id (int): Station ID (1..5).
            arrival_time (float): Simulation time when train arrived at station.
            direction (int): Direction (0=Southbound, 1=Northbound).
        protocol: initialize: No active alighting schedules at T=0 ; process: starts an alighting cycle and waits for alight_count_in.

      - alight_count_in (dict): Alighting count response from TrainLoadStore via parent wiring.
        structure:
            station_id (int): Station ID (1..5).
            count (int): Number of passengers to alight (>=0).
        protocol: initialize: No pending alight counts at T=0 ; process: schedules exactly 'count' exit slots for the active arrival.

      - exiting_passenger_in (dict): Response from TrainLoadStore after each pop_exiting_out.
        structure:
            station_id (int): Station ID (1..5).
            has_passenger (bool): True if a passenger was popped.
            passenger (dict): Passenger data if has_passenger is True, else {}.
                passenger_id (int): Encoded passenger ID.
                passenger_num (int): Passenger sequence number.
                origin (int): Origin station ID (1..5).
                destination (int): Destination station ID (1..5).
        protocol: initialize: No pending exiting passenger messages at T=0 ; process: forwards exiting_event_out when has_passenger=true.

    Output Ports:
      - pop_exiting_out (dict): Command to pop next exiting passenger for station k.
        structure:
            station_id (int): Station ID (1..5).
        protocol: initialize: No pending pop commands at T=0 ; process: emitted at each scheduled exit time.

      - exiting_event_out (dict): Event forwarded to PassengerEventLogger for JSONL emission.
        structure:
            time (float): Scheduled exit time (arrival_time + service_time_seconds * j).
            station_id (int): Station ID (1..5).
            direction (int): Direction (0 or 1).
            passenger (dict): Passenger data.
                passenger_id (int): Encoded passenger ID.
                passenger_num (int): Passenger sequence number.
                origin (int): Origin station ID (1..5).
                destination (int): Destination station ID (1..5).
        protocol: initialize: No pending exiting log events at T=0 ; process: emitted only when has_passenger=true.

      - alight_complete_out (dict): Completion notification to release boarding deterministically.
        structure:
            station_id (int): Station ID (1..5).
            arrival_time (float): Arrival time of the completed context.
        protocol: initialize: No completion notifications at T=0 ; process: emitted once all scheduled exit slots are processed.
    """

    param = {
        "eps_time": 1e-9
    }

    def __init__(self, name: str, parent: Coupled | None, service_time_seconds: float = 0.025):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            service_time_seconds (float): Per-passenger alighting time in seconds.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports (must match specification)
        self.add_in_port(Port(dict, "arrival_ctx_in"))
        self.add_in_port(Port(dict, "alight_count_in"))
        self.add_in_port(Port(dict, "exiting_passenger_in"))

        self.add_out_port(Port(dict, "pop_exiting_out"))
        self.add_out_port(Port(dict, "exiting_event_out"))
        self.add_out_port(Port(dict, "alight_complete_out"))

        # Config
        self.service_time_seconds = float(service_time_seconds)

        # Active arrival context (or None)
        self.active_arrival_ctx = None  # dict: station_id(int), arrival_time(float), direction(int)

        # Scheduling / progress
        self.expected_count = 0          # int >= 0
        self.next_slot_index = 0         # int, next j to execute (1..expected_count)
        self.waiting_for_passenger = False  # bool

        # Prepared payloads for lambdaf
        self._pending_pop_payload = None         # dict or None
        self._pending_exiting_event_payload = None  # dict or None
        self._pending_complete_payload = None    # dict or None

        # KPIs
        self.total_arrivals_processed = 0
        self.total_pop_commands_sent = 0
        self.total_exiting_events_forwarded = 0

        self.logger.info(
            {
                "event": "Model Created",
                "service_time_seconds": self.service_time_seconds,
                "param": self.param
            },
            log_type="PROCESS"
        )

    def initialize(self):
        self.active_arrival_ctx = None
        self.expected_count = 0
        self.next_slot_index = 0
        self.waiting_for_passenger = False

        self._pending_pop_payload = None
        self._pending_exiting_event_payload = None
        self._pending_complete_payload = None

        self.logger.info(
            {
                "event": "Model Initialized",
                "service_time_seconds": self.service_time_seconds
            },
            log_type="PROCESS"
        )
        self.hold_in("IDLE", float("inf"))

    def lambdaf(self):
        if self.phase == "POP" and self._pending_pop_payload is not None:
            self.output["pop_exiting_out"].add(self._pending_pop_payload)
        elif self.phase == "EMIT_EXIT_EVENT" and self._pending_exiting_event_payload is not None:
            self.output["exiting_event_out"].add(self._pending_exiting_event_payload)
        elif self.phase == "COMPLETE" and self._pending_complete_payload is not None:
            self.output["alight_complete_out"].add(self._pending_complete_payload)

    def deltint(self):
        old_phase = self.phase

        if old_phase == "POP":
            # pop command has been emitted in lambdaf; now we wait for response
            self.total_pop_commands_sent += 1
            self._pending_pop_payload = None
            self.waiting_for_passenger = True
            self.hold_in("WAIT_PASSENGER", float("inf"))
            return

        if old_phase == "EMIT_EXIT_EVENT":
            # exiting event has been emitted in lambdaf; proceed to next slot or completion
            self.total_exiting_events_forwarded += 1
            self._pending_exiting_event_payload = None
            self._schedule_next_slot_or_complete()
            return

        if old_phase == "COMPLETE":
            # completion emitted; reset cycle
            self.total_arrivals_processed += 1
            self._pending_complete_payload = None
            self.active_arrival_ctx = None
            self.expected_count = 0
            self.next_slot_index = 0
            self.waiting_for_passenger = False
            self.hold_in("IDLE", float("inf"))
            return

        # For IDLE/WAIT_COUNT/WAIT_PASSENGER: no internal events should normally occur
        self.hold_in(old_phase, float("inf"))

    def deltext(self, e: float):
        # Default keep remaining time if any internal event is pending
        remaining = self.ta()
        if math.isinf(remaining):
            remaining = float("inf")
        else:
            remaining = max(0.0, remaining - float(e))

        # Handle arrival context
        for ctx in self.input["arrival_ctx_in"].values:
            # ctx structure:
            #   station_id (int), arrival_time (float), direction (int)
            self.logger.info({"event": "Arrival Context Received", **ctx}, log_type="PROCESS")

            # This scheduler is designed for sequential arrivals (single train).
            # If a new arrival comes while one is active, we ignore it and log error.
            if self.active_arrival_ctx is not None:
                self.logger.info(
                    {
                        "event": "Arrival Context Ignored",
                        "reason": "active_arrival_in_progress",
                        "incoming": ctx,
                        "active": self.active_arrival_ctx
                    },
                    log_type="ERROR"
                )
                continue

            self.active_arrival_ctx = {
                "station_id": int(ctx.get("station_id", 0)),
                "arrival_time": float(ctx.get("arrival_time", 0.0)),
                "direction": int(ctx.get("direction", 0))
            }
            self.expected_count = 0
            self.next_slot_index = 0
            self.waiting_for_passenger = False

            # Wait for alight_count_in
            self.hold_in("WAIT_COUNT", float("inf"))
            remaining = self.ta()

        # Handle alight count
        for cnt_msg in self.input["alight_count_in"].values:
            # cnt_msg structure:
            #   station_id (int), count (int)
            self.logger.info({"event": "Alight Count Received", **cnt_msg}, log_type="PROCESS")

            if self.active_arrival_ctx is None:
                self.logger.info(
                    {
                        "event": "Alight Count Ignored",
                        "reason": "no_active_arrival",
                        "incoming": cnt_msg
                    },
                    log_type="ERROR"
                )
                continue

            station_id = int(cnt_msg.get("station_id", 0))
            if station_id != int(self.active_arrival_ctx["station_id"]):
                self.logger.info(
                    {
                        "event": "Alight Count Ignored",
                        "reason": "station_mismatch",
                        "incoming": cnt_msg,
                        "active_station_id": int(self.active_arrival_ctx["station_id"])
                    },
                    log_type="ERROR"
                )
                continue

            self.expected_count = max(0, int(cnt_msg.get("count", 0)))
            self.next_slot_index = 1

            if self.expected_count == 0:
                # Complete immediately (no initial signal allowed; but this is in response to input)
                self._pending_complete_payload = {
                    "station_id": int(self.active_arrival_ctx["station_id"]),
                    "arrival_time": float(self.active_arrival_ctx["arrival_time"])
                }
                self.logger.info(
                    {"event": "Alight Complete Emitted", **self._pending_complete_payload},
                    log_type="PROCESS"
                )
                self.hold_in("COMPLETE", 0.0)
            else:
                self._schedule_pop_for_current_slot()

            remaining = self.ta()

        # Handle exiting passenger response
        for resp in self.input["exiting_passenger_in"].values:
            # resp structure:
            #   station_id (int), has_passenger (bool), passenger (dict or {})
            self.logger.info({"event": "Exiting Passenger Received", **resp}, log_type="PROCESS")

            if self.active_arrival_ctx is None:
                self.logger.info(
                    {
                        "event": "Exiting Passenger Ignored",
                        "reason": "no_active_arrival",
                        "incoming": resp
                    },
                    log_type="ERROR"
                )
                continue

            if self.phase != "WAIT_PASSENGER" or not self.waiting_for_passenger:
                self.logger.info(
                    {
                        "event": "Exiting Passenger Ignored",
                        "reason": "not_waiting_for_passenger",
                        "incoming": resp,
                        "phase": self.phase
                    },
                    log_type="ERROR"
                )
                continue

            station_id = int(resp.get("station_id", 0))
            if station_id != int(self.active_arrival_ctx["station_id"]):
                self.logger.info(
                    {
                        "event": "Exiting Passenger Ignored",
                        "reason": "station_mismatch",
                        "incoming": resp,
                        "active_station_id": int(self.active_arrival_ctx["station_id"])
                    },
                    log_type="ERROR"
                )
                continue

            self.waiting_for_passenger = False

            has_passenger = bool(resp.get("has_passenger", False))
            if has_passenger:
                passenger = resp.get("passenger", {})
                if not isinstance(passenger, dict):
                    passenger = {}

                scheduled_time = self._slot_scheduled_time(self.next_slot_index)
                self._pending_exiting_event_payload = {
                    "time": float(scheduled_time),
                    "station_id": int(self.active_arrival_ctx["station_id"]),
                    "direction": int(self.active_arrival_ctx["direction"]),
                    "passenger": {
                        "passenger_id": int(passenger.get("passenger_id", 0)),
                        "passenger_num": int(passenger.get("passenger_num", 0)),
                        "origin": int(passenger.get("origin", 0)),
                        "destination": int(passenger.get("destination", 0))
                    }
                }
                self.logger.info(
                    {"event": "Exiting Event Forwarded", **self._pending_exiting_event_payload},
                    log_type="PROCESS"
                )
                # Emit immediately at current sim time (which should be the scheduled slot time)
                self.hold_in("EMIT_EXIT_EVENT", 0.0)
            else:
                # No passenger returned; still counts as a processed slot.
                self._schedule_next_slot_or_complete()

            remaining = self.ta()

        # If nothing changed phase explicitly above, maintain phase with remaining time
        if self.phase in ["IDLE", "WAIT_COUNT", "WAIT_PASSENGER"] and math.isfinite(remaining):
            self.hold_in(self.phase, remaining)

    def _slot_scheduled_time(self, slot_index: int) -> float:
        arrival_time = float(self.active_arrival_ctx["arrival_time"]) if self.active_arrival_ctx else 0.0
        return arrival_time + self.service_time_seconds * float(slot_index)

    def _schedule_pop_for_current_slot(self):
        # Assumes active_arrival_ctx exists and next_slot_index is valid (1..expected_count)
        station_id = int(self.active_arrival_ctx["station_id"])
        scheduled_time = self._slot_scheduled_time(self.next_slot_index)
        now = float(get_current_time())

        delay = max(0.0, scheduled_time - now)
        if delay < self.param["eps_time"]:
            delay = 0.0

        self._pending_pop_payload = {"station_id": station_id}

        self.logger.info(
            {
                "event": "Pop Exiting Command Scheduled",
                "station_id": station_id,
                "arrival_time": float(self.active_arrival_ctx["arrival_time"]),
                "direction": int(self.active_arrival_ctx["direction"]),
                "slot_index": int(self.next_slot_index),
                "scheduled_time": float(scheduled_time)
            },
            log_type="PROCESS"
        )

        self.hold_in("POP", delay)

    def _schedule_next_slot_or_complete(self):
        # Called after a slot has been fully processed (response received and any event emitted)
        if self.active_arrival_ctx is None:
            self.hold_in("IDLE", float("inf"))
            return

        if self.next_slot_index >= self.expected_count:
            self._pending_complete_payload = {
                "station_id": int(self.active_arrival_ctx["station_id"]),
                "arrival_time": float(self.active_arrival_ctx["arrival_time"])
            }
            self.logger.info(
                {"event": "Alight Complete Emitted", **self._pending_complete_payload},
                log_type="PROCESS"
            )
            self.hold_in("COMPLETE", 0.0)
        else:
            self.next_slot_index += 1
            self._schedule_pop_for_current_slot()

    def exit(self):
        self.logger.info(
            {
                "event": "Model Finalized",
                "total_arrivals_processed": int(self.total_arrivals_processed),
                "total_pop_commands_sent": int(self.total_pop_commands_sent),
                "total_exiting_events_forwarded": int(self.total_exiting_events_forwarded)
            },
            log_type="RESULT"
        )