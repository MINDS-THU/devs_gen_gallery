import math
import random
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class PerStationStochasticProcess(Atomic):
    """
    Function:
        - Implements the ongoing stochastic passenger generation process for exactly one origin station (1..5),
          starting only after init_passenger_time_seconds.
        - States and Output at the end of the state:
            - WAIT_START: Wait until init_passenger_time_seconds, then schedule the first generation after a sampled interval.
              No output at the end of this state.
            - WAIT_NEXT: Wait for the next sampled inter-arrival time. No output at the end of this state.
            - EMIT: When this state is triggered, output exactly one passenger record on passenger_out, and log a
              passenger_generated JSON event. After output, schedule the next WAIT_NEXT using a newly sampled interval.

    Logging in this model:
        - event: Model Created
            log_type: PROCESS
            msg (dict):
                event (str): "Model Created"
                model (str): Model name
                origin_station_id (int): Origin station id (1..5)
                gen_mean_minutes (float): Normal mean in minutes
                gen_std_minutes (float): Normal std in minutes
                gen_min_minutes (float): Clamp min in minutes
                gen_max_minutes (float): Clamp max in minutes
                init_passenger_time_seconds (float): Start time threshold (seconds)
                time (float): Current simulation time
        - event: Model Initialized
            log_type: PROCESS
            msg (dict):
                event (str): "Model Initialized"
                origin_station_id (int): Origin station id (1..5)
                passenger_num (int): Current local counter (first emitted will be 1)
                time (float): Current simulation time
        - passenger_generated JSONL event (REQUIRED SCHEMA)
            log_type: RESULT
            msg (dict):
                time (float): Simulation timestamp in seconds
                event (str): Always "passenger_generated"
                entity_type (str): Always "passenger_generator"
                station_id (int): 1..5 (origin station for this instance)
                station (str): Station name mapped from station_id
                payload (dict): Passenger data
                    passenger_id (int): passenger_num*100 + origin*10 + destination
                    passenger_num (int): Sequential counter (>=1 for this generator)
                    origin (int): Origin station id (1..5), equals station_id
                    destination (int): Destination station id (1..5), != origin

    Input Ports:
        - (none)

    Output Ports:
        - passenger_out (dict): Passenger record to be enqueued at its origin station.
            structure:
                passenger_id (int): Unique passenger id (passenger_num*100 + origin*10 + destination)
                passenger_num (int): Sequential counter (>=1 for this generator)
                origin (int): Origin station id (1..5), equals this instance's origin_station_id
                destination (int): Destination station id (1..5), != origin
            protocol: initialize: no initial signal; first emission only after init_passenger_time_seconds plus sampled interval ;
                      process: emit one validated passenger record per inter-arrival interval, independent per station instance.
    """

    def __init__(
        self,
        name: str,
        parent: Coupled | None,
        origin_station_id: int,
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
            origin_station_id (int): Origin station id for this instance. Must be in 1..5.
            gen_mean_minutes (float): Passenger inter-arrival normal mean in minutes. Default 5.0.
            gen_std_minutes (float): Passenger inter-arrival normal std in minutes. Default 5.0.
            gen_min_minutes (float): Clamp lower bound for inter-arrival minutes. Default 1.0.
            gen_max_minutes (float): Clamp upper bound for inter-arrival minutes. Default 9.0.
            init_passenger_time_seconds (float): Time after which ongoing generation is considered to start
                (i.e. do not emit before this time). Default 0.5.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Ports
        self.add_out_port(Port(dict, "passenger_out"))

        # Config
        self.origin_station_id = int(origin_station_id)
        self.gen_mean_minutes = float(gen_mean_minutes)
        self.gen_std_minutes = float(gen_std_minutes)
        self.gen_min_minutes = float(gen_min_minutes)
        self.gen_max_minutes = float(gen_max_minutes)
        self.init_passenger_time_seconds = float(init_passenger_time_seconds)

        # Internal hardcoded parameters
        self.param = {
            "station_id_to_name": {
                1: "Bayview",
                2: "Carling",
                3: "Carleton",
                4: "Confed",
                5: "Greenboro",
            }
        }

        # Internal state
        self.passenger_num = 0  # first emitted passenger will have passenger_num=1
        self._next_passenger_payload = None  # dict | None, prepared for lambdaf in EMIT

        # Initial scheduling placeholder; actual initialization in initialize()
        self.hold_in("PASSIVE", float("inf"))

        self.logger.info(
            {
                "event": "Model Created",
                "model": self.name,
                "origin_station_id": self.origin_station_id,
                "gen_mean_minutes": self.gen_mean_minutes,
                "gen_std_minutes": self.gen_std_minutes,
                "gen_min_minutes": self.gen_min_minutes,
                "gen_max_minutes": self.gen_max_minutes,
                "init_passenger_time_seconds": self.init_passenger_time_seconds,
                "time": get_current_time(),
            },
            log_type="PROCESS",
        )

    def initialize(self):
        # Validate configuration
        if self.origin_station_id not in self.param["station_id_to_name"]:
            self.logger.info(
                {
                    "event": "Config Error",
                    "reason": "origin_station_id_out_of_range",
                    "origin_station_id": self.origin_station_id,
                    "time": get_current_time(),
                },
                log_type="ERROR",
            )
            # Keep passive forever to avoid emitting invalid events
            self.hold_in("PASSIVE", float("inf"))
            return

        if self.gen_max_minutes < self.gen_min_minutes:
            self.logger.info(
                {
                    "event": "Config Error",
                    "reason": "gen_max_minutes_less_than_gen_min_minutes",
                    "gen_min_minutes": self.gen_min_minutes,
                    "gen_max_minutes": self.gen_max_minutes,
                    "time": get_current_time(),
                },
                log_type="ERROR",
            )
            self.hold_in("PASSIVE", float("inf"))
            return

        if self.init_passenger_time_seconds < 0.0:
            self.logger.info(
                {
                    "event": "Config Error",
                    "reason": "init_passenger_time_seconds_negative",
                    "init_passenger_time_seconds": self.init_passenger_time_seconds,
                    "time": get_current_time(),
                },
                log_type="ERROR",
            )
            self.hold_in("PASSIVE", float("inf"))
            return

        # Reset local state
        self.passenger_num = 0
        self._next_passenger_payload = None

        self.logger.info(
            {
                "event": "Model Initialized",
                "origin_station_id": self.origin_station_id,
                "passenger_num": self.passenger_num,
                "time": get_current_time(),
            },
            log_type="PROCESS",
        )

        # Schedule start gate; first emission is only after init_passenger_time_seconds + sampled interval
        self.hold_in("WAIT_START", self.init_passenger_time_seconds)

    def _sample_interval_seconds(self) -> int:
        # Sample Normal(mean, std) in minutes, clamp, convert to seconds, round to nearest integer seconds.
        sampled = random.gauss(self.gen_mean_minutes, self.gen_std_minutes)
        clamped = max(self.gen_min_minutes, min(self.gen_max_minutes, sampled))
        interval_seconds = int(round(clamped * 60.0))
        if interval_seconds < 0:
            interval_seconds = 0
        return interval_seconds

    def _choose_destination(self) -> int:
        # Uniform among {1..5} excluding origin_station_id
        candidates = [1, 2, 3, 4, 5]
        if self.origin_station_id in candidates:
            candidates.remove(self.origin_station_id)
        # origin is guaranteed valid by initialize() check
        return int(random.choice(candidates))

    def _prepare_next_passenger(self) -> dict | None:
        # Increment passenger_num and build passenger record; validate before returning.
        self.passenger_num += 1
        destination = self._choose_destination()
        passenger_id = int(self.passenger_num * 100 + self.origin_station_id * 10 + destination)

        payload = {
            "passenger_id": passenger_id,
            "passenger_num": int(self.passenger_num),
            "origin": int(self.origin_station_id),
            "destination": int(destination),
        }

        # Validate as required
        if payload["origin"] != self.origin_station_id:
            return None
        if payload["destination"] == self.origin_station_id:
            return None
        if payload["destination"] < 1 or payload["destination"] > 5:
            return None
        return payload

    def lambdaf(self):
        # Output only; payload must have been prepared before entering EMIT.
        if self.phase == "EMIT" and isinstance(self._next_passenger_payload, dict):
            self.output["passenger_out"].add(self._next_passenger_payload)

            # Required JSONL event schema via logger
            station_name = self.param["station_id_to_name"].get(self.origin_station_id, "UNKNOWN")
            self.logger.info(
                {
                    "time": float(get_current_time()),
                    "event": "passenger_generated",
                    "entity_type": "passenger_generator",
                    "station_id": int(self.origin_station_id),
                    "station": str(station_name),
                    "payload": dict(self._next_passenger_payload),
                },
                log_type="RESULT",
            )

    def deltint(self):
        old_phase = self.phase

        if old_phase == "WAIT_START":
            # Start gate reached; schedule first generation after sampled interval
            interval_seconds = float(self._sample_interval_seconds())
            self._next_passenger_payload = None
            self.hold_in("WAIT_NEXT", interval_seconds)
            return

        if old_phase == "WAIT_NEXT":
            # Time to generate one passenger: prepare payload and emit immediately
            self._next_passenger_payload = self._prepare_next_passenger()
            if self._next_passenger_payload is None:
                # Invalid record should not be emitted; reschedule next attempt
                interval_seconds = float(self._sample_interval_seconds())
                self._next_passenger_payload = None
                self.hold_in("WAIT_NEXT", interval_seconds)
            else:
                self.hold_in("EMIT", 0.0)
            return

        if old_phase == "EMIT":
            # After emitting, schedule the next waiting interval
            interval_seconds = float(self._sample_interval_seconds())
            self._next_passenger_payload = None
            self.hold_in("WAIT_NEXT", interval_seconds)
            return

        # Default safe behavior
        self.hold_in("PASSIVE", float("inf"))

    def deltext(self, e: float):
        # No input ports; just discount elapsed time and keep current schedule.
        remaining = self.ta() - float(e)
        if remaining < 0.0:
            remaining = 0.0
        self.hold_in(self.phase, remaining)

    def exit(self):
        # No KPI required; finalization log only.
        self.logger.info(
            {
                "event": "Model Finalized",
                "origin_station_id": self.origin_station_id,
                "generated_count": int(self.passenger_num),
                "time": get_current_time(),
            },
            log_type="RESULT",
        )