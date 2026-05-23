"""
PassengerStochasticGenerator (Coupled DEVS)

This file defines a coupled model that aggregates five independent per-station stochastic
passenger generation atomic models (one per station) and exposes a single output port
that emits passenger records.

Whitelist imports only.
"""

from xdevs.models import Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

# Relative import strictly follows the folder structure
from .PassengerStochasticGenerator_libs.PerStationStochasticProcess import PerStationStochasticProcess


class PassengerStochasticGenerator(Coupled):
    """
    Function:
      - Container for 5 independent stochastic passenger generation processes (stations 1..5).
      - Delegates actual stochastic timing, destination selection, passenger_id computation, and
        passenger_generated RESULT logging to sub-models.
      - Sub-models:
        - PerStationStochasticProcess: name=gen_station_1. Generates passengers originating at station_id=1.
        - PerStationStochasticProcess: name=gen_station_2. Generates passengers originating at station_id=2.
        - PerStationStochasticProcess: name=gen_station_3. Generates passengers originating at station_id=3.
        - PerStationStochasticProcess: name=gen_station_4. Generates passengers originating at station_id=4.
        - PerStationStochasticProcess: name=gen_station_5. Generates passengers originating at station_id=5.

    Logging in this model:
      - PROCESS: event='Model Created'
        msg (dict):
          event (str): 'Model Created'.
          gen_mean_minutes (float): Mean inter-arrival time in minutes.
          gen_std_minutes (float): Std inter-arrival time in minutes.
          gen_min_minutes (float): Clamp lower bound (minutes).
          gen_max_minutes (float): Clamp upper bound (minutes).
          init_passenger_time_seconds (float): Start gate time in seconds for each per-station process.
          stations (list[int]): Station ids instantiated (always [1,2,3,4,5]).
          time (float): Current simulation time in seconds.

    Input Ports:
      - None

    Output Ports:
      - passenger_out (dict): Passenger record emitted by any station generator.
        structure:
          passenger_id (int): Computed as passenger_num*100 + origin*10 + destination.
          passenger_num (int): Per-origin sequential counter (>=1 for this generator; init passengers are not produced here).
          origin (int): Origin station id in [1..5].
          destination (int): Destination station id in [1..5] and != origin.
        protocol: initialize: no output at t=0 ; process: forwards each per-station generated passenger record as it occurs.
    """

    def __init__(
        self,
        name: str,
        parent: Coupled | None,
        gen_mean_minutes: float,
        gen_std_minutes: float,
        gen_min_minutes: float,
        gen_max_minutes: float,
        init_passenger_time_seconds: float,
    ):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            gen_mean_minutes (float): Passenger inter-arrival normal mean in minutes.
            gen_std_minutes (float): Passenger inter-arrival normal std in minutes.
            gen_min_minutes (float): Clamp lower bound for inter-arrival minutes.
            gen_max_minutes (float): Clamp upper bound for inter-arrival minutes.
            init_passenger_time_seconds (float): Time after which ongoing generation processes are considered to start.

        Notes on types (recursive schema):
            - passenger_out (dict): Passenger record.
                passenger_id (int): Unique passenger id.
                passenger_num (int): Per-station sequence number (>=1 here).
                origin (int): Origin station id (1..5).
                destination (int): Destination station id (1..5, != origin).
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Internal hardcoded parameters (none required for behavior; stored for standardization)
        self.param = {
            "station_ids": [1, 2, 3, 4, 5],
        }

        # Define system boundary ports
        self.add_out_port(Port(dict, "passenger_out"))

        # Instantiate sub-components (one per station)
        gen_station_1 = PerStationStochasticProcess(
            name="gen_station_1",
            parent=self,
            origin_station_id=1,
            gen_mean_minutes=gen_mean_minutes,
            gen_std_minutes=gen_std_minutes,
            gen_min_minutes=gen_min_minutes,
            gen_max_minutes=gen_max_minutes,
            init_passenger_time_seconds=init_passenger_time_seconds,
        )
        gen_station_2 = PerStationStochasticProcess(
            name="gen_station_2",
            parent=self,
            origin_station_id=2,
            gen_mean_minutes=gen_mean_minutes,
            gen_std_minutes=gen_std_minutes,
            gen_min_minutes=gen_min_minutes,
            gen_max_minutes=gen_max_minutes,
            init_passenger_time_seconds=init_passenger_time_seconds,
        )
        gen_station_3 = PerStationStochasticProcess(
            name="gen_station_3",
            parent=self,
            origin_station_id=3,
            gen_mean_minutes=gen_mean_minutes,
            gen_std_minutes=gen_std_minutes,
            gen_min_minutes=gen_min_minutes,
            gen_max_minutes=gen_max_minutes,
            init_passenger_time_seconds=init_passenger_time_seconds,
        )
        gen_station_4 = PerStationStochasticProcess(
            name="gen_station_4",
            parent=self,
            origin_station_id=4,
            gen_mean_minutes=gen_mean_minutes,
            gen_std_minutes=gen_std_minutes,
            gen_min_minutes=gen_min_minutes,
            gen_max_minutes=gen_max_minutes,
            init_passenger_time_seconds=init_passenger_time_seconds,
        )
        gen_station_5 = PerStationStochasticProcess(
            name="gen_station_5",
            parent=self,
            origin_station_id=5,
            gen_mean_minutes=gen_mean_minutes,
            gen_std_minutes=gen_std_minutes,
            gen_min_minutes=gen_min_minutes,
            gen_max_minutes=gen_max_minutes,
            init_passenger_time_seconds=init_passenger_time_seconds,
        )

        # Register components
        self.add_component(gen_station_1)
        self.add_component(gen_station_2)
        self.add_component(gen_station_3)
        self.add_component(gen_station_4)
        self.add_component(gen_station_5)

        # Define couplings (EOC only: sub-model outputs -> system output)
        self.add_coupling(gen_station_1.output["passenger_out"], self.output["passenger_out"])
        self.add_coupling(gen_station_2.output["passenger_out"], self.output["passenger_out"])
        self.add_coupling(gen_station_3.output["passenger_out"], self.output["passenger_out"])
        self.add_coupling(gen_station_4.output["passenger_out"], self.output["passenger_out"])
        self.add_coupling(gen_station_5.output["passenger_out"], self.output["passenger_out"])

        # Log creation (container-level)
        self.logger.info(
            {
                "event": "Model Created",
                "gen_mean_minutes": float(gen_mean_minutes),
                "gen_std_minutes": float(gen_std_minutes),
                "gen_min_minutes": float(gen_min_minutes),
                "gen_max_minutes": float(gen_max_minutes),
                "init_passenger_time_seconds": float(init_passenger_time_seconds),
                "stations": list(self.param["station_ids"]),
                "time": float(get_current_time()),
            },
            log_type="PROCESS",
        )