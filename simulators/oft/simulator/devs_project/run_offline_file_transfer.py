import argparse
import sys
from xdevs.sim import Coordinator, SimulationClock
from devs_project.devs_utils.devs_context import set_global_clock
from devs_project.devs_utils.inject import ReliableInjectionSystem, get_raw_input_content

# Target Model import
from .Offline_File_Transfer import Offline_File_Transfer

def parse_schedule(raw_text: str) -> list[dict]:
    """
    Parses stdin content in the format: HH:MM:SS:mmm type value
    Example: 00:00:10:000 control 1
    Returns a list of event dicts for the ReliableInjectionSystem.
    """
    events = []
    if not raw_text:
        return events
    
    lines = raw_text.strip().splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        try:
            parts = line.split()
            if len(parts) < 3:
                continue
            
            time_str, event_type, value_str = parts[0], parts[1], parts[2]
            
            # Parse HH:MM:SS[:mmm] to milliseconds
            time_parts = time_str.split(':')
            hours = int(time_parts[0])
            minutes = int(time_parts[1])
            seconds = int(time_parts[2])
            milliseconds = int(time_parts[3]) if len(time_parts) > 3 else 0
            
            total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000.0 + milliseconds
            
            # Map event_type to model input ports
            # control -> control_in
            # request -> request_in
            port_map = {
                "control": "control_in",
                "request": "request_in"
            }
            
            if event_type in port_map:
                events.append({
                    "time": float(total_ms),
                    "port": port_map[event_type],
                    "payload": int(value_str)
                })
            else:
                print(f"Warning: Unknown event type '{event_type}' at line {i+1}", file=sys.stderr)
                
        except (ValueError, IndexError) as e:
            print(f"Skipping invalid line {i+1} [{line}]: {e}", file=sys.stderr)
            
    return events

if __name__ == "__main__":
    # 1. Parameter Configuration (ArgParse)
    parser = argparse.ArgumentParser(description="Run Offline_File_Transfer simulation")
    
    # simulation_time is specified in the scenario as float, default 10,000,000.0 ms
    parser.add_argument(
        "--simulation_time", 
        type=float, 
        default=10000000.0, 
        help="Total simulation duration in milliseconds"
    )
    
    args = parser.parse_args()
    
    # 2. Input Parsing
    # Read scenario from stdin using the secure utility
    raw_content = get_raw_input_content()
    injection_events = parse_schedule(raw_content)
    
    # 3. Initialization
    # Create and register the global simulation clock
    clock = SimulationClock()
    set_global_clock(clock)
    
    # Instantiate the core model
    # Note: Offline_File_Transfer requires (name, parent, simulation_time)
    core_model = Offline_File_Transfer(
        name="offline_transfer_system",
        parent=None,
        simulation_time=args.simulation_time
    )
    
    # Wrap with the ReliableInjectionSystem to handle the parsed events
    harness = ReliableInjectionSystem(
        name="harness",
        parent=None,
        core_model=core_model,
        events=injection_events
    )
    
    # Create the Coordinator with the harness as the root
    sim = Coordinator(harness, clock)
    
    # 4. Simulation Execution
    try:
        sim.initialize()
        
        # Run with a tiny epsilon to ensure all events at exactly simulation_time are processed
        effective_end = float(args.simulation_time) + 1e-9
        sim.simulate_time(effective_end)
        
    except Exception as e:
        print(f"Simulation Error: {e}", file=sys.stderr)
    finally:
        sim.exit()