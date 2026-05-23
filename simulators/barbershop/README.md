# barbershop

Barbershop workflow simulation with reception, inspection, and cutting stages.

## Simulated system

This simulator models a barbershop with three functional areas: reception, hair inspection, and hair cutting. Customers arrive according to an external schedule, wait in a reception queue with capacity 8, move into inspection when available, and then proceed to hair cutting. The simulator emits both state-change and inter-module message records.

## Inputs

### Command-line arguments

| Argument | Type | Default | Meaning |
| :--- | :--- | :--- | :--- |
| `--simulation_time` | float | `1000000.0` | Total simulation time in seconds |

### Standard input

The simulator reads an initial event schedule from stdin. Each line uses this format:

```text
HH:MM:SS:mm EventName
```

`EventName` must be `newcust`.

Example:

```text
08:00:00:00 newcust
08:00:10:00 newcust
```

## Output schema

The simulator writes JSON Lines to stdout. Two record families are required:

### State records

```json
{"time": <float>, "type": "state", "model": <string>, "field": <string>, "value": <string|number>}
```

### Message records

```json
{"time": <float>, "type": "message", "model": <string>, "port": <string>, "content": <string>}
```

The three main models are `reception`, `checkhair`, and `cuthair`.

## Run example

```bash
cd simulator
python run.py --simulation_time 400 <<'EOF'
08:00:00:00 newcust
08:00:10:00 newcust
EOF
```

## Repository contents

- `simulator/` - runnable barbershop simulator package

The original generated package notes are preserved in `simulator/README.md`.