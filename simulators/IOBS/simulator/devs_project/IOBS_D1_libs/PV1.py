from xdevs.models import Atomic, Coupled, Port

from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time

from .PV1_libs.PVServiceController import PVServiceController
from .PV1_libs.PVVerificationEmitter import PVVerificationEmitter


class PV1(Coupled):
    """
    Function:
      - Implements the PV1 (PasswordVerifier) stage as a coupled DEVS model.
      - Owns a single-server FIFO service controller with fixed service time, followed by a verification emitter.
      - Sub-models:
        - PVServiceController: name=service_controller. Queues requests and applies the fixed service delay.
        - PVVerificationEmitter: name=verification_emitter. Samples geometric attempts (p=0.5), logs PV1.verification, and forwards to BPM.

    Logging in this model:
      - PROCESS / "created": emitted once during construction.
        msg (dict):
          time (float): Current simulation time from get_current_time().
          model (str): This coupled model name.
          event (str): "created".
          data (dict): Creation parameters.
            processing_delay (float): Fixed service time per request (seconds).
            submodels (dict): Submodel instance names.
              service_controller (str): Instance name.
              verification_emitter (str): Instance name.

    Input Ports:
      - request_in (dict): Login request entering PV1 from upstream (e.g., ANV).
        structure:
          valid (int): Compatibility flag (typically 1).
          invalid (int): 0 for valid login, 1 for invalid login.
        protocol: initialize: passive ; process: enqueue into internal FIFO and, if idle, begin service immediately.

    Output Ports:
      - to_bpm (dict): Forwarded request leaving PV1 to downstream (BPM), unchanged.
        structure:
          valid (int): Compatibility flag (typically 1).
          invalid (int): 0 or 1.
        protocol: initialize: empty ; process: emitted immediately after PV service completion (verification emitter forwards without added delay).
    """

    def __init__(self, name: str, parent: Coupled | None, processing_delay: float = 10.0):
        """
        Args:
            name (str): The unique name of the model.
            parent (Coupled | None): The parent model. If None, the model is a root model.
            processing_delay (float): Fixed service time (seconds) per request.
        """
        super().__init__(name)
        self.parent = parent
        self.logger = get_sim_logger(self)

        self.param: dict = {}

        # System boundary ports
        # request_in/to_bpm messages are dict with:
        #   valid (int): compatibility flag
        #   invalid (int): 0 or 1
        self.add_in_port(Port(dict, "request_in"))
        self.add_out_port(Port(dict, "to_bpm"))

        # Sub-models
        service_controller = PVServiceController(
            name="service_controller",
            parent=self,
            processing_delay=float(processing_delay),
        )
        verification_emitter = PVVerificationEmitter(
            name="verification_emitter",
            parent=self,
        )

        self.add_component(service_controller)
        self.add_component(verification_emitter)

        # Couplings
        # EIC: PV1.request_in -> service_controller.request_in
        self.add_coupling(self.input["request_in"], service_controller.input["request_in"])

        # IC: service_controller.service_done -> verification_emitter.service_done_in
        self.add_coupling(service_controller.output["service_done"], verification_emitter.input["service_done_in"])

        # EOC: verification_emitter.to_bpm -> PV1.to_bpm
        self.add_coupling(verification_emitter.output["to_bpm"], self.output["to_bpm"])

        # Creation log (container-level)
        self.logger.info(
            {
                "time": float(get_current_time()),
                "model": str(self.name),
                "event": "created",
                "data": {
                    "processing_delay": float(processing_delay),
                    "submodels": {
                        "service_controller": str(service_controller.name),
                        "verification_emitter": str(verification_emitter.name),
                    },
                },
            },
            log_type="PROCESS",
        )