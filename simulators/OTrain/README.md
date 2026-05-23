# OTrain

Single-train light rail simulation with passenger generation, station queues, boarding, and alighting.

## Simulated system

This simulator models the Ottawa O-Train as a single train moving back and forth across five fixed stations. Passengers are generated stochastically at stations, join FIFO queues, board when the train arrives, and later exit at their encoded destinations. The simulator emits events for passenger generation, train arrivals, boarding, and exiting.

## Inputs

### Command-line arguments

| Argument | Type | Default | Meaning |
| :--- | :--- | :--- | :--- |
| `--simulate_time` | string | `00:01:00:000` | Total simulation duration in `HH:MM:SS:mmm` format |

### Standard input

This simulator does not consume stdin.

## Output schema

The simulator writes JSON Lines to stdout. Each record contains these top-level fields:

```json
{
	"time": <float>,
	"event": <string>,
	"entity_type": <string>,
	"station_id": <int>,
	"station": <string>,
	"payload": <object>
}
```

Required event types are:

- `passenger_generated`
- `train_arrival`
- `passenger_boarding`
- `passenger_exiting`

The `payload` fields include station, direction, passenger identity, origin, and destination metadata depending on the event type.

## Run example

```bash
cd simulator
python run.py --simulate_time 00:10:00:000
```

## Repository contents

- `simulator/` - runnable OTrain simulator package

The original generated package notes are preserved in `simulator/README.md`.
