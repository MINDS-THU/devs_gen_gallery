# SA

Airfreight logistics simulation with pallet generation, queue expiration, fleet assignment, and aircraft cycling.

## Simulated system

This simulator models a cargo facility that continuously generates pallets, a loading queue with deadline-based expiration, a fleet coordinator that assigns queued pallets to idle aircraft, and aircraft that cycle through loading, flight, unloading, return, and maintenance phases. Successful delivery is recorded only when unloading completes.

This item also includes a Godot visualization that subscribes to the simulator event stream through MQTT.

## Inputs

### Command-line arguments

| Argument | Type | Default | Meaning |
| :--- | :--- | :--- | :--- |
| `--duration` | float | `10000.0` | Total simulation time |
| `--num_aircraft` | int | `2` | Number of aircraft in the system |
| `--pallet_interval` | float | `25.0` | Time between pallet generations |
| `--pallet_expiration_time` | float | `150.0` | Queue lifetime before a pallet expires |
| `--flight_time` | float | `30.0` | Outbound flight duration |
| `--unload_time` | float | `2.0` | Unloading duration |
| `--return_time` | float | `30.0` | Return flight duration |
| `--maintenance_time` | float | `10.0` | Maintenance duration after return |

### Standard input

This simulator does not consume stdin.

## Output schema

The simulator writes JSON Lines to stdout. Each record follows this top-level schema:

```json
{"time": <float>, "entity": <string>, "event": <string>, "payload": <object>}
```

Required event families include:

- facility events: `pallet_generated`
- queue events: `pallet_queued`, `pallet_expired`
- coordinator events: `assignment_created`
- aircraft events: `depart`, `return`, `maintenance_start`, `maintenance_end`
- destination events: `pallet_delivered`

Representative payload shapes:

```json
{"pallet_id": 12, "expiration_time": 175.0}
{"aircraft_id": 1, "pallet_id": 12}
{"pallet_id": 12, "aircraft_id": 1, "latency": 62.0}
```

## Run example

```bash
cd simulator
python run.py --duration 300 --num_aircraft 2 --pallet_interval 25 --pallet_expiration_time 150
```

## Run with the Godot visualization

<video controls preload="metadata" width="100%">
	<source src="https://minds-thu.github.io/devs_gen/static/videos/SA.mp4" type="video/mp4">
	Your browser does not support the video tag. You can watch the demo at https://minds-thu.github.io/devs_gen/static/videos/SA.mp4.
</video>

1. Start an MQTT broker on `127.0.0.1:1883`.
2. In `simulator/`, install the publisher dependency and start the MQTT bridge:

```bash
cd simulator
pip install -r requirements-mqtt.txt
python mqtt_publish_sim.py -- --duration 300 --pallet_interval 25 --pallet_expiration_time 150
```

3. Open `godot/project.godot` in Godot 4.6 and run `scenes/main.tscn`.

The visualization listens to topic `sa/airfreight/events` by default.

## Repository contents

- `simulator/` - runnable SA simulator package and MQTT publisher
- `godot/` - Godot 4.6 visualization project

The original generated package notes are preserved in `simulator/README.md`, and the visualization-specific notes are preserved in `godot/README.md`.
