import argparse
import sys
import time
import random

from xdevs.sim import Coordinator, SimulationClock
from devs_project.devs_utils.devs_context import set_global_clock

from .OTrain import OTrain


def parse_hhmmssmmm_to_seconds(value: str) -> float:
    """
    Parse "HH:MM:SS:mmm" into seconds (float with millisecond precision).
    Example: "00:01:00:000" -> 60.0
    """
    try:
        parts = value.strip().split(":")
        if len(parts) != 4:
            raise ValueError("Expected exactly 4 colon-separated fields: HH:MM:SS:mmm")

        hh = int(parts[0])
        mm = int(parts[1])
        ss = int(parts[2])
        mmm = int(parts[3])

        if hh < 0 or mm < 0 or ss < 0 or mmm < 0:
            raise ValueError("Negative time fields are not allowed")
        if mm >= 60 or ss >= 60 or mmm >= 1000:
            raise ValueError("Out-of-range fields: MM<60, SS<60, mmm<1000")

        return float(hh * 3600 + mm * 60 + ss) + (float(mmm) / 1000.0)
    except Exception as e:
        raise ValueError(f"Invalid simulate_time '{value}': {e}") from e


if __name__ == "__main__":
    # Seed RNG using system time (scenario requirement).
    seed = time.time_ns()
    random.seed(seed)

    # --- BEGIN: Parameter Configuration (ArgParse) ---
    parser = argparse.ArgumentParser(description="Run OTrain simulation")

    # Scenario-specified argument (name must match exactly)
    parser.add_argument(
        "--simulate_time",
        type=str,
        default="00:01:00:000",
        help='Simulation duration in "HH:MM:SS:mmm" (default: 00:01:00:000)',
    )

    # OTrain __init__ parameters (defaults from scenario / model spec)
    parser.add_argument("--travel_time_seconds", type=float, default=225.0, help="Travel time between stations (seconds)")
    parser.add_argument("--service_time_seconds", type=float, default=0.025, help="Per-passenger service time (seconds)")
    parser.add_argument("--gen_mean_minutes", type=float, default=5.0, help="Passenger generation mean (minutes)")
    parser.add_argument("--gen_std_minutes", type=float, default=5.0, help="Passenger generation std (minutes)")
    parser.add_argument("--gen_min_minutes", type=float, default=1.0, help="Passenger generation min clamp (minutes)")
    parser.add_argument("--gen_max_minutes", type=float, default=9.0, help="Passenger generation max clamp (minutes)")
    parser.add_argument(
        "--init_passenger_time_seconds",
        type=float,
        default=0.5,
        help="Time to create initialization passengers at all stations (seconds)",
    )

    args = parser.parse_args()

    try:
        simulate_time = parse_hhmmssmmm_to_seconds(args.simulate_time)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
    # --- END: Parameter Configuration (ArgParse) ---

    # --- BEGIN: Initialization ---
    clock = SimulationClock()
    set_global_clock(clock)

    otrain_instance = OTrain(
        name="OTrain",
        parent=None,
        travel_time_seconds=float(args.travel_time_seconds),
        service_time_seconds=float(args.service_time_seconds),
        gen_mean_minutes=float(args.gen_mean_minutes),
        gen_std_minutes=float(args.gen_std_minutes),
        gen_min_minutes=float(args.gen_min_minutes),
        gen_max_minutes=float(args.gen_max_minutes),
        init_passenger_time_seconds=float(args.init_passenger_time_seconds),
    )

    model = otrain_instance
    sim = Coordinator(model, clock)
    # --- END: Initialization ---

    # --- BEGIN: Simulation Execution ---
    sim.initialize()
    sim.simulate_time(simulate_time)
    sim.exit()
    # --- END: Simulation Execution ---