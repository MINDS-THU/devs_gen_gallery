import argparse
import sys
import json
import logging
from collections import defaultdict, deque
import random

from xdevs.sim import Coordinator, SimulationClock
from devs_project.devs_utils.devs_context import set_global_clock
from devs_project.devs_utils.inject import ReliableInjectionSystem, get_raw_input_content

from .Barbershop_D1 import Barbershop_D1


def _parse_time_hhmmssff(t_str: str) -> float:
    """
    Parse time in format: HH:MM:SS:mm
    Interprets the last field `mm` as centiseconds (1/100 second).
    Returns absolute simulation time in seconds since 00:00:00:00.
    """
    parts = t_str.strip().split(":")
    if len(parts) != 4:
        raise ValueError(f"Invalid time format (expected HH:MM:SS:mm): {t_str!r}")
    hh, mm, ss, ff = (int(p) for p in parts)
    if hh < 0 or mm < 0 or ss < 0 or ff < 0:
        raise ValueError(f"Negative values not allowed in time: {t_str!r}")
    if mm >= 60 or ss >= 60:
        raise ValueError(f"Minutes/seconds out of range in time: {t_str!r}")
    # centiseconds
    return hh * 3600.0 + mm * 60.0 + ss * 1.0 + (ff / 100.0)


def parse_schedule(raw_text: str) -> list[dict]:
    """
    Input (stdin) format: one event per line
      HH:MM:SS:mm EventName
    Where EventName is only: newcust

    Output: list of injection events:
      [{"time": float, "port": "in_newcust", "payload": "newcust"}, ...]
    """
    events: list[dict] = []
    if not raw_text:
        return events

    lines = raw_text.splitlines()
    for i, line in enumerate(lines, start=1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue

        try:
            # Split into 2 fields: time and event name
            t_part, ev_part = s.split(None, 1)
            ev_name = ev_part.strip()
            if ev_name != "newcust":
                print(
                    f"Skipping line {i}: unsupported event name {ev_name!r} (only 'newcust' is allowed).",
                    file=sys.stderr,
                )
                continue

            t = _parse_time_hhmmssff(t_part)
            events.append({"time": float(t), "port": "in_newcust", "payload": "newcust"})
        except ValueError as e:
            print(f"Skipping invalid line {i}: {s!r}. Reason: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Skipping invalid line {i}: {s!r}. Reason: {e}", file=sys.stderr)

    events.sort(key=lambda x: x["time"])
    return events


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Barbershop_D1 simulation (xdevs)")

    # Model init args (as per specification)
    parser.add_argument(
        "--name",
        type=str,
        default="Barbershop_D1",
        help="Instance name for the Barbershop_D1 coupled model",
    )

    # Scenario-specified argument name (must match exactly)
    parser.add_argument(
        "--simulation_time",
        type=float,
        default=1000000.0,
        help="Total simulation time horizon in seconds",
    )

    args = parser.parse_args()
    model_name = args.name
    simulation_time = float(args.simulation_time)

    # Read and parse stdin fully before starting the simulation
    raw_text = get_raw_input_content()
    injection_events = parse_schedule(raw_text)

    clock = SimulationClock()
    set_global_clock(clock)

    core = Barbershop_D1(name=model_name, parent=None)

    model = ReliableInjectionSystem(
        name="harness",
        parent=None,
        core_model=core,
        events=injection_events,
    )

    sim = Coordinator(model, clock)

    sim.initialize()
    effective_end = simulation_time + 1e-9
    sim.simulate_time(effective_end)
    sim.exit()