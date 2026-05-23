import random
from xdevs.models import Atomic, Coupled, Port
from devs_project.devs_utils.devs_logger import get_sim_logger
from devs_project.devs_utils.devs_context import get_current_time


class PVVerificationEmitter(Atomic):
    """
    Function:
        - Owns PV1’s password-attempt stochastic verification output, required logging, and forwarding to BPM.
        - States and Output at the end of the state:
            - IDLE: Waits for completion messages on input port service_done_in (no outputs).
            - EMIT: Immediately (sigma=0) outputs the buffered forwarded requests to to_bpm; after output, returns to IDLE.

    Logging in this model:
        - Required: PV1.verification event when PV finishes its processing at time t (immediately upon receipt).
          Logged as:
            {
              "time": <float>,
              "model": "PV1",
              "event": "verification",
              "data": {
                "success": 1,
                "attempts": <int>
              }
            }

    Input Ports:
      - service_done_in (dict): Completion message carrying login request.
        structure:
            valid (int): Always 1 (compatibility field).
            invalid (int): 0 for valid login, 1 for invalid login.
        protocol: initialize: Idle; waiting for completion messages at T=0. ; process: on receive at time t, generate
                  attempts ~ Geometric(p=0.5), log PV1.verification at time t, and schedule immediate forwarding (sigma=0).

    Output Ports:
      - to_bpm (dict): Request dict forwarded to BPM unchanged.
        structure:
            valid (int): Always 1 (compatibility field).
            invalid (int): 0 for valid login, 1 for invalid login.
        protocol: initialize: Empty; no message in transit at T=0. ; process: after receiving service_done_in at time t,
                  forward the same request immediately to BPM (sigma=0).
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

        # Ports (must match specification)
        self.add_in_port(Port(dict, "service_done_in"))
        self.add_out_port(Port(dict, "to_bpm"))

        # Internal hardcoded parameters
        self.param = {
            "attempt_success_p": 0.5
        }

        # Internal buffers (prepared before lambdaf; emitted in lambdaf)
        self._forward_buffer: list[dict] = []

        # Start in passive state
        self.hold_in("IDLE", float("inf"))

    def initialize(self):
        self._forward_buffer = []
        self.hold_in("IDLE", float("inf"))

    def _sample_attempts_geometric(self, p: float) -> int:
        """
        Samples attempts as a geometric distribution with success probability p:
        the smallest integer k>=1 such that an independent Bernoulli(p) succeeds.
        """
        attempts = 1
        while random.random() >= p:
            attempts += 1
        return attempts

    def deltext(self, e: float):
        # Consume all incoming completion messages
        for req in self.input["service_done_in"].values:
            # req (dict) structure:
            #   valid (int)
            #   invalid (int)

            attempts = self._sample_attempts_geometric(self.param["attempt_success_p"])

            # Required PV event log at the completion time t (immediate at receipt)
            self.logger.info(
                {
                    "time": float(get_current_time()),
                    "model": "PV1",
                    "event": "verification",
                    "data": {
                        "success": 1,
                        "attempts": int(attempts),
                    },
                },
                log_type="RESULT",
            )

            # Forward the request unchanged to BPM
            self._forward_buffer.append(req)

        # Schedule immediate output if anything to forward
        if self._forward_buffer:
            self.hold_in("EMIT", 0.0)
        else:
            # No new work: remain in current phase, discounting elapsed time
            remaining = self.ta() - e
            if remaining < 0.0:
                remaining = 0.0
            self.hold_in(self.phase, remaining)

    def lambdaf(self):
        # Output only; no state updates here
        if self.phase == "EMIT":
            for req in self._forward_buffer:
                self.output["to_bpm"].add(req)

    def deltint(self):
        # Internal transition after output
        if self.phase == "EMIT":
            self._forward_buffer = []
            self.hold_in("IDLE", float("inf"))
        else:
            self.hold_in("IDLE", float("inf"))

    def exit(self):
        # No additional required final logs for this model
        return