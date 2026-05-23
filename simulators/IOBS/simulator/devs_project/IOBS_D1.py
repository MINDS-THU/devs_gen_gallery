from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

from .IOBS_D1_libs.InputReader1 import InputReader1
from .IOBS_D1_libs.AAM1 import AAM1
from .IOBS_D1_libs.ANV1 import ANV1
from .IOBS_D1_libs.PV1 import PV1
from .IOBS_D1_libs.BPM1 import BPM1
from .IOBS_D1_libs.TPM1 import TPM1


class IOBS_D1(Coupled):
    """
    Function:
      - Implements the full Internet Online Banking System (IOBS) pipeline as a coupled DEVS container:
        input_reader1 → AAM1 → ANV1 → PV1 → BPM1 → TPM1.
      - Provides system boundary port(s) and routes messages through submodels via EIC/IC couplings.
      - Sub-models:
        - InputReader1: name=input_reader1. Logs start/input and forwards normalized requests to AAM.
        - AAM1: name=AAM1. Processes login requests and forwards valid logins to ANV (or logs logout).
        - ANV1: name=ANV1. Randomly verifies accounts and forwards pass cases to PV.
        - PV1: name=PV1. Verifies password (retries until success) and forwards to BPM.
        - BPM1: name=BPM1. Generates bill amount (clipped by latest balance) and forwards to TPM.
        - TPM1: name=TPM1. Applies transaction to authoritative balance and publishes balance snapshots.

    Logging in this model:
      - PROCESS / created:
        msg (dict):
          time (float): float(get_current_time()).
          model (str): str(self.name).
          event (str): "created".
          data (dict):
            processing_delay (float): Per-stage service delay used for AAM1/ANV1/PV1/BPM1/TPM1.
            initial_balance (int): Initial authoritative balance for TPM1.
            bill_min (int): Minimum bill amount (inclusive) used by BPM1.
            bill_max (int): Maximum bill amount (inclusive) used by BPM1.
            submodels (dict): Instance names for submodels.
              input_reader1 (str): "input_reader1"
              AAM1 (str): "AAM1"
              ANV1 (str): "ANV1"
              PV1 (str): "PV1"
              BPM1 (str): "BPM1"
              TPM1 (str): "TPM1"

    Input Ports:
      - request_in (dict): Injected login request entering the system.
        structure:
          valid (int): Compatibility flag (expected 1).
          invalid (int): 0 for valid login, 1 for invalid login.
        protocol: initialize: no initial input assumed ; process: each dict is routed to input_reader1.request_in.

    Output Ports:
      - (none)
    """

    def __init__(
        self,
        name: str,
        parent: Coupled | None,
        processing_delay: float = 10.0,
        initial_balance: int = 3000,
        bill_min: int = 0,
        bill_max: int = 40,
    ):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): the parent model. If None, the model is a root model.
            processing_delay (float): Fixed service time per stage in seconds.
            initial_balance (int): Initial authoritative balance for TPM1.
            bill_min (int): Minimum bill amount inclusive for BPM1 random generation.
            bill_max (int): Maximum bill amount inclusive for BPM1 random generation (before clipping by balance).
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        self.param = {
            "submodel_instance_names": {
                "input_reader1": "input_reader1",
                "AAM1": "AAM1",
                "ANV1": "ANV1",
                "PV1": "PV1",
                "BPM1": "BPM1",
                "TPM1": "TPM1",
            }
        }

        # System boundary ports
        self.add_in_port(Port(dict, "request_in"))

        # Components
        input_reader1 = InputReader1(name="input_reader1", parent=self)
        aam1 = AAM1(name="AAM1", parent=self, processing_delay=float(processing_delay))
        anv1 = ANV1(name="ANV1", parent=self, processing_delay=float(processing_delay))
        pv1 = PV1(name="PV1", parent=self, processing_delay=float(processing_delay))
        bpm1 = BPM1(
            name="BPM1",
            parent=self,
            processing_delay=float(processing_delay),
            bill_min=int(bill_min),
            bill_max=int(bill_max),
            initial_balance_snapshot=int(initial_balance),
        )
        tpm1 = TPM1(
            name="TPM1",
            parent=self,
            processing_delay=float(processing_delay),
            initial_balance=int(initial_balance),
        )

        self.add_component(input_reader1)
        self.add_component(aam1)
        self.add_component(anv1)
        self.add_component(pv1)
        self.add_component(bpm1)
        self.add_component(tpm1)

        # Couplings
        # EIC: external request injection -> input reader
        self.add_coupling(self.input["request_in"], input_reader1.input["request_in"])

        # IC: pipeline routing
        self.add_coupling(input_reader1.output["to_aam"], aam1.input["request_in"])
        self.add_coupling(aam1.output["to_anv"], anv1.input["request_in"])
        self.add_coupling(anv1.output["to_pv"], pv1.input["request_in"])
        self.add_coupling(pv1.output["to_bpm"], bpm1.input["request_in"])
        self.add_coupling(bpm1.output["to_tpm"], tpm1.input["request_in"])

        # IC: balance feedback (TPM publishes authoritative balance snapshots to BPM)
        self.add_coupling(tpm1.output["balance_out"], bpm1.input["balance_in"])

        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "created",
                "data": {
                    "processing_delay": float(processing_delay),
                    "initial_balance": int(initial_balance),
                    "bill_min": int(bill_min),
                    "bill_max": int(bill_max),
                    "submodels": {
                        "input_reader1": "input_reader1",
                        "AAM1": "AAM1",
                        "ANV1": "ANV1",
                        "PV1": "PV1",
                        "BPM1": "BPM1",
                        "TPM1": "TPM1",
                    },
                },
            },
            log_type="PROCESS",
        )