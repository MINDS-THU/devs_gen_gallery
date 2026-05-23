from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger

from .Reception_libs.WaitingArea import WaitingArea
from .Reception_libs.ReceptionCoordinator import ReceptionCoordinator


class Reception(Coupled):
    """
    Function:
      - Implements the `reception` module boundary for Barbershop_D1 as a coupled/container model.
      - Routes external arrivals to a capacity-limited FIFO waiting area and coordinates check-in + handoff to `checkhair`.
      - Sub-models:
        - WaitingArea: name=waiting_area. Manages the capacity-limited FIFO queue and emits queue length updates.
        - ReceptionCoordinator: name=coordinator. Performs check-in timing (5.0s) and handoff to `checkhair`, and commands dequeues.

    Logging in this model:
      - event: "Model Created"
        log_type: "PROCESS"
        msg (dict):
          event (str): Literal "Model Created".
          model (str): Literal "reception".
          capacity (int): Waiting area capacity (must be 8).
          checkin_time (float): Check-in processing time in seconds (must be 5.0).
          param (dict): Internal fixed parameters for this coupled/container.
            model_scope (str): Literal "Barbershop_D1.Reception".

    Input Ports:
      - in_newcust (str): External arrival token from [Parent: in_newcust].
        structure: literal "newcust".
        protocol: initialize: no initial signal ; process: forwarded to WaitingArea.in_newcust for capacity check/enqueue.
      - in_done (str): Availability notification from [Sibling-checkhair: to_reception] (via parent coupling).
        structure: literal "done".
        protocol: initialize: no initial signal ; process: forwarded to ReceptionCoordinator.in_done.

    Output Ports:
      - cust (str): Customer token sent onward to [Sibling-checkhair: in_cust] (via parent coupling).
        structure: literal "newcust".
        protocol: initialize: no initial signal ; process: emitted by ReceptionCoordinator.cust when handoff occurs.
    """

    def __init__(self, name: str, parent: Coupled | None, capacity: int, checkin_time: float):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent model. If None, the model is a root model.
            capacity (int): Maximum number of customers allowed in the waiting area including any being checked in.
                Structure (int): Must be exactly 8.
            checkin_time (float): Exact check-in processing time in seconds.
                Structure (float): Must be exactly 5.0.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Internal hardcoded parameters (not passed via __init__)
        self.param = {
            "model_scope": "Barbershop_D1.Reception"
        }

        # Enforce scenario constants at the system boundary
        if not isinstance(capacity, int) or capacity != 8:
            raise ValueError("Reception.capacity must be int == 8")
        if not isinstance(checkin_time, float) or float(checkin_time) != 5.0:
            raise ValueError("Reception.checkin_time must be float == 5.0")

        # System boundary ports
        self.add_in_port(Port(str, "in_newcust"))
        self.add_in_port(Port(str, "in_done"))
        self.add_out_port(Port(str, "cust"))

        # Sub-models
        waiting_area = WaitingArea(
            name="waiting_area",
            parent=self,
            capacity=capacity
        )
        coordinator = ReceptionCoordinator(
            name="coordinator",
            parent=self,
            checkin_time=checkin_time
        )

        self.add_component(waiting_area)
        self.add_component(coordinator)

        # Couplings
        # EIC: external arrivals -> waiting area
        self.add_coupling(self.input["in_newcust"], waiting_area.input["in_newcust"])

        # EIC: checkhair done notifications -> coordinator
        self.add_coupling(self.input["in_done"], coordinator.input["in_done"])

        # IC: waiting area queue update -> coordinator
        self.add_coupling(waiting_area.output["queue_update"], coordinator.input["in_queue_update"])

        # IC: coordinator dequeue command -> waiting area
        self.add_coupling(coordinator.output["dequeue_cmd"], waiting_area.input["in_dequeue"])

        # EOC: coordinator customer handoff -> external output
        self.add_coupling(coordinator.output["cust"], self.output["cust"])

        self.logger.info(
            {
                "event": "Model Created",
                "model": "reception",
                "capacity": capacity,
                "checkin_time": float(checkin_time),
                "param": self.param,
            },
            log_type="PROCESS",
        )