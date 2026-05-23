import argparse
import sys
import json
import random
import time
from xdevs.sim import Coordinator, SimulationClock
from devs_project.devs_utils.devs_context import set_global_clock
from devs_project.devs_utils.inject import ReliableInjectionSystem, get_raw_input_content

from .IOBS_D1 import IOBS_D1


def _parse_hhmmssmmm_to_seconds(ts: str) -> float:
    # Format: HH:MM:SS:mmm
    parts = ts.strip().split(":")
    if len(parts) != 4:
        raise ValueError(f"Invalid timestamp format (expected HH:MM:SS:mmm): {ts!r}")
    hh, mm, ss, mmm = parts
    return (int(hh) * 3600) + (int(mm) * 60) + int(ss) + (int(mmm) / 1000.0)


def parse_iobs_schedule(raw_text: str) -> list[dict]:
    """
    Input lines (stdin):
      HH:MM:SS:mmm valid invalid
    Example:
      00:00:10:000 1 0
      00:00:25:500 1 1
    """
    events: list[dict] = []
    if not raw_text:
        return events

    lines = raw_text.splitlines()
    for i, line in enumerate(lines, start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Allow inline comments after '#'
        if "#" in line:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue

        try:
            parts = line.split()
            if len(parts) != 3:
                raise ValueError("Expected 3 fields: HH:MM:SS:mmm valid invalid")

            ts_str, valid_str, invalid_str = parts
            t = _parse_hhmmssmmm_to_seconds(ts_str)
            valid = int(valid_str)
            invalid = int(invalid_str)

            events.append(
                {
                    "time": float(t),
                    "port": "request_in",
                    "payload": {"valid": valid, "invalid": invalid},
                }
            )
        except Exception as e:
            print(f"Skipping invalid line {i}: {line!r} ({e})", file=sys.stderr)

    # Stable sort by time (preserve input order for equal timestamps)
    events.sort(key=lambda ev: ev["time"])
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run IOBS_D1 simulation (xdevs)")

    parser.add_argument(
        "--simulation_time",
        type=float,
        default=1000000.0,
        help="Total simulation time in seconds.",
    )

    # IOBS_D1 init args (defaults per scenario/model)
    parser.add_argument(
        "--processing_delay",
        type=float,
        default=10.0,
        help="Fixed per-stage processing delay (seconds).",
    )
    parser.add_argument(
        "--initial_balance",
        type=int,
        default=3000,
        help="Initial authoritative balance for TPM1 (and BPM1 snapshot).",
    )
    parser.add_argument(
        "--bill_min",
        type=int,
        default=0,
        help="Minimum bill amount (inclusive) for BPM1.",
    )
    parser.add_argument(
        "--bill_max",
        type=int,
        default=40,
        help="Maximum bill amount (inclusive) for BPM1 before clipping by balance.",
    )

    args = parser.parse_args()

    simulation_time = float(args.simulation_time)
    processing_delay = float(args.processing_delay)
    initial_balance = int(args.initial_balance)
    bill_min = int(args.bill_min)
    bill_max = int(args.bill_max)

    # Seed RNGs with system time
    seed = time.time_ns()
    random.seed(seed)

    # Read and parse injected events from stdin (secure utility)
    raw_text = get_raw_input_content()
    injection_events = parse_iobs_schedule(raw_text)

    clock = SimulationClock()
    set_global_clock(clock)

    core = IOBS_D1(
        name="IOBS_D1",
        parent=None,
        processing_delay=processing_delay,
        initial_balance=initial_balance,
        bill_min=bill_min,
        bill_max=bill_max,
    )

    model = ReliableInjectionSystem(
        name="harness",
        parent=None,
        core_model=core,
        events=injection_events,
    )

    sim = Coordinator(model, clock)

    sim.initialize()
    effective_end = float(simulation_time) + 1e-9
    sim.simulate_time(effective_end)
    sim.exit()