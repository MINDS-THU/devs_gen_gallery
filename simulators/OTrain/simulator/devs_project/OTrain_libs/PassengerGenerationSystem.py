"""
PassengerGenerationSystem (Coupled DEVS)

This file defines the PassengerGenerationSystem coupled model, which composes:
- PassengerInitGenerator: one-time initialization passenger emission at t=init_passenger_time_seconds.
- PassengerStochasticGenerator: ongoing per-station stochastic passenger generation (5 independent processes).

The model exposes a single output port passenger_out that forwards passenger records to downstream systems
(e.g., StationQueueSystem.passenger_in).
"""

### BEGIN: General Import (whitelist)
from xdevs.models import Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time
### END

### BEGIN: Model import (relative imports)
from .PassengerGenerationSystem_libs.PassengerInitGenerator import PassengerInitGenerator
from .PassengerGenerationSystem_libs.PassengerStochasticGenerator import PassengerStochasticGenerator
### END


class PassengerGenerationSystem(Coupled):
    """
    Function:
      - Owns all passenger generation logic for all 5 stations by composing:
        (1) a one-time initialization passenger generator at t=init_passenger_time_seconds, and
        (2) ongoing independent per-station stochastic generation processes.
      - Forwards all generated passenger records through a single system-boundary output port.
      - Sub-models:
        - PassengerInitGenerator: name=init_generator. Emits exactly one initialization passenger per station (intended 5 total).
        - PassengerStochasticGenerator: name=stochastic_generator. Emits ongoing passengers from 5 independent station processes.

    Logging in this model:
      - PROCESS: {"event": "Model Created", "gen_mean_minutes": float, "gen_std_minutes": float,
                 "gen_min_minutes": float, "gen_max_minutes": float, "init_passenger_time_seconds": float,
                 "time": float}
        Notes:
          - time is the current simulation time from get_current_time().
          - This model does not log passenger_generated events itself; those are logged by sub-models.

    Input Ports:
      - None

    Output Ports:
      - passenger_out (dict): Passenger record to be enqueued at its origin station.
        structure:
          passenger_id (int): Unique passenger id. For initialization passengers, always 0.
          passenger_num (int): Sequential counter per origin (0 for initialization, >=1 for ongoing).
          origin (int): Origin station id in [1..5].
          destination (int): Destination station id in [1..5] and must be != origin.
        protocol: initialize: no output at t=0 ; process: forwards passenger records emitted by submodels unchanged.
    """

    def __init__(
        self,
        name: str,
        parent: Coupled | None,
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
            gen_mean_minutes (float): Passenger inter-arrival normal mean in minutes. Default 5.0.
            gen_std_minutes (float): Passenger inter-arrival normal std in minutes. Default 5.0.
            gen_min_minutes (float): Clamp lower bound for inter-arrival minutes. Default 1.0.
            gen_max_minutes (float): Clamp upper bound for inter-arrival minutes. Default 9.0.
            init_passenger_time_seconds (float): Time to create initialization passengers at all stations. Default 0.5.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Store internal hardcoded parameters (not passed via __init__)
        self.param = {
            "stations": [1, 2, 3, 4, 5],
            "station_names": {
                1: "Bayview",
                2: "Carling",
                3: "Carleton",
                4: "Confed",
                5: "Greenboro",
            },
        }

        # System boundary ports
        self.add_out_port(Port(dict, "passenger_out"))

        # Submodels
        init_generator = PassengerInitGenerator(
            name="init_generator",
            parent=self,
            init_passenger_time_seconds=float(init_passenger_time_seconds),
        )

        stochastic_generator = PassengerStochasticGenerator(
            name="stochastic_generator",
            parent=self,
            gen_mean_minutes=float(gen_mean_minutes),
            gen_std_minutes=float(gen_std_minutes),
            gen_min_minutes=float(gen_min_minutes),
            gen_max_minutes=float(gen_max_minutes),
            init_passenger_time_seconds=float(init_passenger_time_seconds),
        )

        # Register components
        self.add_component(init_generator)
        self.add_component(stochastic_generator)

        # Couplings (EOC only): submodel outputs -> system output
        self.add_coupling(init_generator.output["passenger_out"], self.output["passenger_out"])
        self.add_coupling(stochastic_generator.output["passenger_out"], self.output["passenger_out"])

        # Creation log
        self.logger.info(
            {
                "event": "Model Created",
                "gen_mean_minutes": float(gen_mean_minutes),
                "gen_std_minutes": float(gen_std_minutes),
                "gen_min_minutes": float(gen_min_minutes),
                "gen_max_minutes": float(gen_max_minutes),
                "init_passenger_time_seconds": float(init_passenger_time_seconds),
                "time": float(get_current_time()),
            },
            log_type="PROCESS",
        )