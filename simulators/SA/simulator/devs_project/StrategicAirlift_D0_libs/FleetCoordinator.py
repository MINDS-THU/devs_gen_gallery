import math
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

class FleetCoordinator(Atomic):
    """
    Function: 
        - Tracks aircraft states for multiple aircraft instances (IDLE or BUSY).
        - Monitors the loading queue size.
        - Assignment Rule: If (Queue size > 0) AND (at least one Aircraft is IDLE), it sends a 'request_pallet' trigger to the Queue.
        - Upon receiving a pallet from the queue, it assigns it to the first available IDLE aircraft (FIFO selection of aircraft).
        - Transitions:
            - IDLE: Waiting for either a queue update or an aircraft to become ready.
            - REQUESTING: Sending a signal to the queue to release a pallet.
            - ASSIGNING: Sending the received pallet data to a specific aircraft.

    Logging in this model:
        - assignment_created: Triggered when a pallet is dispatched to an aircraft.
            - time (float): Simulation time.
            - entity (str): 'coordinator'
            - payload (dict):
                - aircraft_id (int): ID of the assigned aircraft.
                - pallet_id (int): ID of the assigned pallet.

    Input Ports:
        - queue_size_in (int): Integer representing pallets in queue.
            protocol: initialize: 0 ; process: updates internal queue count.
        - pallet_in (dict): Pallet info.
            structure:
                pallet_id (int): Unique ID.
                expiration_time (float): Absolute deadline.
                generation_time (float): Creation time.
            protocol: initialize: waiting ; process: receives pallet released by queue.
        - aircraft_ready_{i} (str): The aircraft_id of the aircraft that just finished maintenance.
            protocol: initialize: all_ready ; process: marks specific aircraft as IDLE.

    Output Ports:
        - queue_request (bool): Boolean trigger.
            protocol: initialize: idle ; process: sends True to request a pallet.
        - assign_to_aircraft_{i} (dict): Pallet info dispatched to specific aircraft.
            structure:
                pallet_id (int): Unique ID.
                expiration_time (float): Absolute deadline.
                generation_time (float): Creation time.
            protocol: initialize: idle ; process: forwards pallet data.
    """

    def __init__(self, name: str, parent: Coupled | None, num_aircraft: int):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model.
            num_aircraft (int): Total number of aircraft to track.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        self.num_aircraft = num_aircraft
        
        # Define Ports
        self.add_in_port(Port(int, "queue_size_in"))
        self.add_in_port(Port(dict, "pallet_in"))
        
        for i in range(1, num_aircraft + 1):
            self.add_in_port(Port(str, f"aircraft_ready_{i}"))
            self.add_out_port(Port(dict, f"assign_to_aircraft_{i}"))
        
        self.add_out_port(Port(bool, "queue_request"))

        # Internal State
        self.aircraft_states = {i: "IDLE" for i in range(1, num_aircraft + 1)}
        self.current_queue_size = 0
        self.pending_request = False # True if we have sent a request but not received pallet
        
        # Payload buffers for lambdaf
        self.out_payload_request = None
        self.out_payload_assignment = None
        self.target_aircraft_id = None

        self.hold_in("IDLE", float('inf'))

    def initialize(self):
        self.aircraft_states = {i: "IDLE" for i in range(1, self.num_aircraft + 1)}
        self.current_queue_size = 0
        self.pending_request = False
        self.hold_in("IDLE", float('inf'))

    def deltext(self, e: float):
        # Update queue size
        if not self.input["queue_size_in"].empty():
            self.current_queue_size = list(self.input["queue_size_in"].values)[-1]

        # Update aircraft status
        for i in range(1, self.num_aircraft + 1):
            port_name = f"aircraft_ready_{i}"
            if not self.input[port_name].empty():
                # Consume all signals, mark as IDLE
                for _ in self.input[port_name].values:
                    self.aircraft_states[i] = "IDLE"

        # Handle pallet arrival
        if not self.input["pallet_in"].empty():
            pallet = self.input["pallet_in"].get()
            # Assign to first available IDLE aircraft
            for i in range(1, self.num_aircraft + 1):
                if self.aircraft_states[i] == "IDLE":
                    self.target_aircraft_id = i
                    self.out_payload_assignment = pallet
                    self.aircraft_states[i] = "BUSY"
                    self.pending_request = False
                    self.hold_in("ASSIGNING", 0)
                    return

        # Check if we should request a pallet
        # Condition: Queue > 0 AND at least one IDLE aircraft AND no request currently out
        idle_aircraft = [i for i, state in self.aircraft_states.items() if state == "IDLE"]
        if self.current_queue_size > 0 and idle_aircraft and not self.pending_request:
            self.out_payload_request = True
            self.pending_request = True
            self.hold_in("REQUESTING", 0)
        else:
            self.hold_in(self.phase, self.ta() - e)

    def deltint(self):
        if self.phase == "ASSIGNING":
            # Log the assignment that just happened in lambdaf
            self.logger.info({
                "time": get_current_time(),
                "entity": "coordinator",
                "event": "assignment_created",
                "payload": {
                    "aircraft_id": self.target_aircraft_id,
                    "pallet_id": self.out_payload_assignment["pallet_id"]
                }
            }, log_type="PROCESS")
            
            self.out_payload_assignment = None
            self.target_aircraft_id = None
            
            # After assigning, check if we can request another one immediately
            idle_aircraft = [i for i, state in self.aircraft_states.items() if state == "IDLE"]
            if self.current_queue_size > 0 and idle_aircraft and not self.pending_request:
                self.out_payload_request = True
                self.pending_request = True
                self.hold_in("REQUESTING", 0)
            else:
                self.hold_in("IDLE", float('inf'))
        
        elif self.phase == "REQUESTING":
            self.out_payload_request = None
            # Wait for pallet_in to trigger deltext
            self.hold_in("IDLE", float('inf'))
        else:
            self.hold_in("IDLE", float('inf'))

    def lambdaf(self):
        if self.phase == "REQUESTING":
            self.output["queue_request"].add(self.out_payload_request)
        elif self.phase == "ASSIGNING":
            port_name = f"assign_to_aircraft_{self.target_aircraft_id}"
            self.output[port_name].add(self.out_payload_assignment)

    def exit(self):
        pass