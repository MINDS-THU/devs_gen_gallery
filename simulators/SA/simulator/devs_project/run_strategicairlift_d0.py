import argparse
import sys
import json
from xdevs.sim import Coordinator, SimulationClock
from devs_project.devs_utils.devs_context import set_global_clock

# Target Model import - Relative import as per requirements
from .StrategicAirlift_D0 import StrategicAirlift_D0

def run_simulation():
    # 1. Configuration (ArgParse)
    parser = argparse.ArgumentParser(description="Run StrategicAirlift_D0 simulation")
    
    # Parameters based on Model Specification and Scenario Defaults
    parser.add_argument("--duration", type=float, default=10000.0, 
                        help="Total simulation time in time units.")
    parser.add_argument("--num_aircraft", type=int, default=2, 
                        help="Number of aircraft in the system.")
    parser.get_default("--num_aircraft")
    parser.add_argument("--pallet_interval", type=float, default=25.0, 
                        help="Time interval between pallet generations.")
    parser.add_argument("--pallet_expiration_time", type=float, default=150.0, 
                        help="Time window for pallet expiration.")
    parser.add_argument("--flight_time", type=float, default=30.0, 
                        help="Flight duration for aircraft transport.")
    parser.add_argument("--unload_time", type=float, default=2.0, 
                        help="Time required for unloading cargo.")
    parser.add_argument("--return_time", type=float, default=30.0, 
                        help="Return flight duration for aircraft.")
    parser.add_argument("--maintenance_time", type=float, default=10.0, 
                        help="Duration of maintenance phase for aircraft.")
    
    args = parser.parse_args()

    # 2. Initialization
    # Create the simulation clock
    clock = SimulationClock()
    # Register the clock globally before model instantiation
    set_global_clock(clock)
    
    # Instantiate the StrategicAirlift_D0 model
    # Note: No injection system is used here as the scenario describes a self-generating 
    # system (PalletFacility) and no external input ports are defined in the spec.
    model_instance = StrategicAirlift_D0(
        name="StrategicAirlift_D0",
        parent=None,
        num_aircraft=args.num_aircraft,
        pallet_interval=args.pallet_interval,
        pallet_expiration_time=args.pallet_expiration_time,
        flight_time=args.flight_time,
        unload_time=args.unload_time,
        return_time=args.return_time,
        maintenance_time=args.maintenance_time
    )
    
    # Create the Simulator Coordinator
    sim = Coordinator(model_instance, clock)
    
    # 3. Simulation Execution
    try:
        sim.initialize()
        
        # Run simulation until duration. 
        # Adding a tiny epsilon to ensure internal events at the boundary are processed.
        effective_end = float(args.duration) + 1e-9
        sim.simulate_time(effective_end)
        
    except Exception as e:
        print(f"Simulation Error: {e}", file=sys.stderr)
    finally:
        sim.exit()

if __name__ == "__main__":
    run_simulation()