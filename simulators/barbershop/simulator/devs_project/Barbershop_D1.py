from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger

from .Barbershop_D1_libs.Reception import Reception
from .Barbershop_D1_libs.CheckHair import CheckHair
from .Barbershop_D1_libs.CutHair import CutHair


class Barbershop_D1(Coupled):
    """
    Function:
      - Coupled DEVS container model for the Barbershop_D1 workflow.
      - Routes external customer arrival tokens to the internal reception module.
      - Wires the internal modules to implement the workflow: reception -> checkhair -> cuthair -> checkhair -> reception.
      - Sub-models:
        - Reception: name=reception. Reception boundary that manages waiting/check-in and emits customers to checkhair.
        - CheckHair: name=checkhair. Consultation/coordinator between reception and cuthair.
        - CutHair: name=cuthair. Performs cutting service and emits completion.

    Logging in this model:
      - event: "Model Created" (one-time, at end of __init__)
        log_type: "PROCESS"
        msg (dict):
          event (str): Literal "Model Created".
          model (str): Literal "Barbershop_D1".
          param (dict): Internal fixed parameters.
            model_scope (str): Literal "Barbershop_D1".
            capacity (int): Waiting area capacity (fixed to 8).
            checkin_time (float): Reception check-in time (fixed to 5.0).
            consult_time (float): CheckHair consult time (fixed to 7.0).
            cut_time (float): CutHair cut time (fixed to 20.0).

    Input Ports:
      - in_newcust (str): External arrival token routed to reception.
        structure: str
        protocol: initialize: no initial signal ; process: forward literal token "newcust" to internal reception.in_newcust

    Output Ports:
      - (none)
    """

    def __init__(self, name: str, parent: Coupled | None):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        # Internal fixed parameters (scenario constants)
        self.param = {
            "model_scope": "Barbershop_D1",
            "capacity": 8,
            "checkin_time": 5.0,
            "consult_time": 7.0,
            "cut_time": 20.0,
        }

        # System boundary ports
        self.add_in_port(Port(str, "in_newcust"))

        # Sub-model instances
        reception = Reception(
            name="reception",
            parent=self,
            capacity=int(self.param["capacity"]),
            checkin_time=float(self.param["checkin_time"]),
        )
        checkhair = CheckHair(
            name="checkhair",
            parent=self,
            consult_time=float(self.param["consult_time"]),
        )
        cuthair = CutHair(
            name="cuthair",
            parent=self,
            cut_time=float(self.param["cut_time"]),
        )

        # Register components
        self.add_component(reception)
        self.add_component(checkhair)
        self.add_component(cuthair)

        # Couplings (EIC, IC)
        # EIC: external arrivals -> reception
        self.add_coupling(self.input["in_newcust"], reception.input["in_newcust"])

        # IC: reception -> checkhair
        self.add_coupling(reception.output["cust"], checkhair.input["in_cust"])

        # IC: checkhair -> cuthair
        self.add_coupling(checkhair.output["to_cut"], cuthair.input["in_newcust"])

        # IC: cuthair -> checkhair
        self.add_coupling(cuthair.output["out"], checkhair.input["in_done"])

        # IC: checkhair -> reception (availability/done notification)
        self.add_coupling(checkhair.output["to_reception"], reception.input["in_done"])

        self.logger.info(
            {
                "event": "Model Created",
                "model": "Barbershop_D1",
                "param": {
                    "model_scope": str(self.param["model_scope"]),
                    "capacity": int(self.param["capacity"]),
                    "checkin_time": float(self.param["checkin_time"]),
                    "consult_time": float(self.param["consult_time"]),
                    "cut_time": float(self.param["cut_time"]),
                },
            },
            log_type="PROCESS",
        )