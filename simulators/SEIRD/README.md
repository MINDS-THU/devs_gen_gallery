# SEIRD

SEIRD epidemic compartment model with discrete-time state updates.

## Simulated system

This simulator models infectious disease spread in a closed population using five compartments: susceptible, exposed, infective, recovered, and deceased. State updates occur at fixed time intervals and follow the standard SEIRD transition structure with configurable transmission, incubation, infectivity, and mortality parameters.

## Inputs

### Command-line arguments

| Argument | Type | Default | Meaning |
| :--- | :--- | :--- | :--- |
| `--test_name` | string | required | Name of the test case |
| `--mortality` | float | `10.0` | Mortality rate in percent |
| `--infectivity_period` | float | `14.0` | Average infectious period in days |
| `--dt` | float | `0.1` | Integration time step in days |
| `--incubation_period` | float | `5.0` | Average incubation period in days |
| `--total_population` | int | `1000` | Total population size |
| `--initial_infective` | int | `10` | Initial infected population |
| `--transmission_rate` | float | `2.5` | Transmission rate per day |
| `--simulation_time` | float | `10.0` | Total simulation time in days |

### Standard input

This simulator does not consume stdin.

## Output schema

The simulator emits a final JSONL record with the terminal compartment counts:

```json
{
	"time": <float>,
	"susceptible": <float>,
	"exposed": <float>,
	"infective": <float>,
	"recovered": <float>,
	"deceased": <float>
}
```

All compartment values are floating-point counts, typically reported to two decimal places.

## Run example

```bash
cd simulator
python run.py --test_name demo --simulation_time 30 --total_population 1000 --initial_infective 10
```

## Repository contents

- `simulator/` - runnable SEIRD simulator package

The original generated package notes are preserved in `simulator/README.md`.