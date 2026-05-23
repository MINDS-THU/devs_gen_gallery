import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class MissionController(Atomic):
    """
    Function:
        - Manages the operational cycle of an aircraft: IDLE, LOADING, FLYING, UNLOADING, RETURNING, and MAINTENANCE.
        - IDLE: Waiting for a pallet assignment.
        - LOADING: Instantaneous transition (0s) upon assignment. Triggers 'depart' and starts 'flight' timer.
        - FLYING: Waits for 'flight' timer completion, then starts 'unload' timer.
        - UNLOADING: Waits for 'unload' timer completion, triggers 'pallet_delivered', and starts 'return' timer.
        - RETURNING: Waits for 'return' timer completion, triggers 'return' event, and starts 'maintenance' timer.
        - MAINTENANCE: Waits for 'maintenance' timer completion, triggers 'maintenance_end', and sends 'ready_out'.

    Logging in this model:
        - depart: {time, entity: 'aircraft', payload: {aircraft_id, pallet_id}}
        - pallet_delivered: {time, entity: 'destination', payload: {pallet_id, aircraft_id, latency}}
        - return: {time, entity: 'aircraft', payload: {aircraft_id}}
        - maintenance_start: {time, entity: 'aircraft', payload: {aircraft_id}}
        - maintenance_end: {time, entity: 'aircraft', payload: {aircraft_id}}

    Input Ports:
        - assignment_in (dict): Pallet assignment data from Coordinator.
            pallet_id (int): Unique ID of the pallet.
            expiration_time (float): Absolute expiration time.
            generation_time (float): Time the pallet was created.
            protocol: initialize: idle ; process: transition to LOADING.
        - timer_done (str): Signal from FlightTimer.
            - (str): Phase identifier ('flight', 'unload', 'return', 'maintenance').
            protocol: initialize: waiting ; process: trigger next phase transition.

    Output Ports:
        - start_timer (dict): Command to FlightTimer.
            phase (str): Phase name.
            duration (float): Time to wait.
            protocol: initialize: idle ; process: initiate timed transitions.
        - ready_out (str): Availability signal.
            - (str): The aircraft_id.
            protocol: initial_signal: Sends aircraft_id at T=0.
    """

    param = {}

    def __init__(
        self,
        name: str,
        parent: Coupled | None,
        aircraft_id: int,
        flight_time: float,
        unload_time: float,
        return_time: float,
        maintenance_time: float,
    ):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent model.
            aircraft_id (int): Unique integer ID for the aircraft.
            flight_time (float): Duration of the flight phase.
            unload_time (float): Duration of the unloading phase.
            return_time (float): Duration of the return flight phase.
            maintenance_time (float): Duration of the maintenance phase.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Config parameters
        self.aircraft_id = aircraft_id
        self.flight_time = flight_time
        self.unload_time = unload_time
        self.return_time = return_time
        self.maintenance_time = maintenance_time

        # Ports
        self.add_in_port(Port(dict, "assignment_in"))
        self.add_in_port(Port(str, "timer_done"))
        self.add_out_port(Port(dict, "start_timer"))
        self.add_out_port(Port(str, "ready_out"))

        # Internal State
        self.current_pallet = None
        self.next_output_port = None
        self.next_payload = None

        self.logger.info(
            {"event": "Aircraft Controller Created", "aircraft_id": self.aircraft_id},
            log_type="PROCESS",
        )

    def initialize(self):
        self.current_pallet = None
        # Protocol requirement: Send ready_out at T=0
        self.next_output_port = "ready_out"
        self.next_payload = str(self.aircraft_id)
        self.hold_in("INIT_READY", 0)

    def lambdaf(self):
        if self.next_output_port and self.next_payload is not None:
            self.output[self.next_output_port].add(self.next_payload)

    def deltint(self):
        current_phase = self.phase

        if current_phase == "INIT_READY":
            self.next_output_port = None
            self.next_payload = None
            self.hold_in("IDLE", float("inf"))

        elif current_phase == "LOADING":
            # Logic: Trigger depart event and start flight timer
            self.logger.info(
                {
                    "time": get_current_time(),
                    "entity": "aircraft",
                    "event": "depart",
                    "payload": {
                        "aircraft_id": self.aircraft_id,
                        "pallet_id": self.current_pallet["pallet_id"],
                    },
                },
                log_type="PROCESS",
            )
            self.next_output_port = None
            self.next_payload = None
            self.hold_in("FLYING", float("inf"))

        elif current_phase == "TRANSITION_TO_UNLOAD":
            self.next_output_port = None
            self.next_payload = None
            self.hold_in("UNLOADING", float("inf"))

        elif current_phase == "TRANSITION_TO_RETURN":
            # Logic: Unload finished, deliver pallet
            latency = get_current_time() - self.current_pallet["generation_time"]
            self.logger.info(
                {
                    "time": get_current_time(),
                    "entity": "destination",
                    "event": "pallet_delivered",
                    "payload": {
                        "pallet_id": self.current_pallet["pallet_id"],
                        "aircraft_id": self.aircraft_id,
                        "latency": latency,
                    },
                },
                log_type="PROCESS",
            )
            self.next_output_port = None
            self.next_payload = None
            self.hold_in("RETURNING", float("inf"))

        elif current_phase == "TRANSITION_TO_MAINTENANCE":
            # Logic: Return finished
            self.logger.info(
                {
                    "time": get_current_time(),
                    "entity": "aircraft",
                    "event": "return",
                    "payload": {"aircraft_id": self.aircraft_id},
                },
                log_type="PROCESS",
            )

            # Start Maintenance
            self.logger.info(
                {
                    "time": get_current_time(),
                    "entity": "aircraft",
                    "event": "maintenance_start",
                    "payload": {"aircraft_id": self.aircraft_id},
                },
                log_type="PROCESS",
            )
            self.next_output_port = None
            self.next_payload = None
            self.hold_in("MAINTENANCE", float("inf"))

        elif current_phase == "FINISH_MAINTENANCE":
            self.logger.info(
                {
                    "time": get_current_time(),
                    "entity": "aircraft",
                    "event": "maintenance_end",
                    "payload": {"aircraft_id": self.aircraft_id},
                },
                log_type="PROCESS",
            )
            self.current_pallet = None
            self.next_output_port = None
            self.next_payload = None
            self.hold_in("IDLE", float("inf"))

    def deltext(self, e):
        self.next_output_port = None
        self.next_payload = None

        # Handle assignment
        if not self.input["assignment_in"].empty():
            self.current_pallet = self.input["assignment_in"].get()
            # Loading is instantaneous (0s)
            self.next_output_port = "start_timer"
            self.next_payload = {"phase": "flight", "duration": self.flight_time}
            self.hold_in("LOADING", 0)

        # Handle timer completion
        elif not self.input["timer_done"].empty():
            done_phase = self.input["timer_done"].get()

            if done_phase == "flight":
                self.next_output_port = "start_timer"
                self.next_payload = {"phase": "unload", "duration": self.unload_time}
                self.hold_in("TRANSITION_TO_UNLOAD", 0)
            elif done_phase == "unload":
                self.next_output_port = "start_timer"
                self.next_payload = {"phase": "return", "duration": self.return_time}
                self.hold_in("TRANSITION_TO_RETURN", 0)
            elif done_phase == "return":
                self.next_output_port = "start_timer"
                self.next_payload = {
                    "phase": "maintenance",
                    "duration": self.maintenance_time,
                }
                self.hold_in("TRANSITION_TO_MAINTENANCE", 0)
            elif done_phase == "maintenance":
                self.next_output_port = "ready_out"
                self.next_payload = str(self.aircraft_id)
                self.hold_in("FINISH_MAINTENANCE", 0)
        else:
            self.hold_in(self.phase, self.ta() - e)

    def exit(self):
        self.logger.info(
            {"event": "Aircraft Controller Finalized", "aircraft_id": self.aircraft_id},
            log_type="PROCESS",
        )
