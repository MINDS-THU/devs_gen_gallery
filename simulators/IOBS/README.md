# IOBS

Online banking authentication and transaction workflow with staged verification and payment processing.

## Simulated system

This simulator models an Internet Online Banking System pipeline:

```text
Input -> AAM -> ANV -> PV -> BPM -> TPM -> Output
```

Requests enter through an input reader, pass through account access checks, account-number verification, password verification, bill generation, and transaction processing. Random outcomes are used in ANV and PV, while TPM maintains the running account balance and completed transaction count.

## Inputs

### Command-line arguments

| Argument | Type | Default | Meaning |
| :--- | :--- | :--- | :--- |
| `--simulation_time` | float | `1000000.0` | Total simulation time in seconds |

### Standard input

The simulator reads request lines from stdin using this format:

```text
HH:MM:SS:mmm valid invalid
```

Example:

```text
00:00:10:000 1 0
00:00:25:500 1 1
```

Here `invalid=0` means a valid login request and `invalid=1` means an invalid login request.

## Output schema

The simulator writes JSON Lines to stdout. Each record follows this schema:

```json
{"time": <float>, "model": <string>, "event": <string>, "data": <object>}
```

Required model/event families include:

- `input_reader1`: `start`, `input`
- `AAM1`: `account_generated`, `logout`
- `ANV1`: `verification`
- `PV1`: `verification`
- `BPM1`: `bill`
- `TPM1`: `transaction`

Representative payload shapes:

```json
{"pass": 1, "fail": 0}
{"success": 1, "attempts": 2}
{"remaining": 2979, "count": 1}
```

## Run example

```bash
cd simulator
python run.py --simulation_time 120 <<'EOF'
00:00:10:000 1 0
00:00:25:500 1 1
EOF
```

## Repository contents

- `simulator/` - runnable IOBS simulator package

The original generated package notes are preserved in `simulator/README.md`.