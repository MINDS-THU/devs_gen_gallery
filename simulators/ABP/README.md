# ABP

Reliable stop-and-wait packet transfer with deterministic packet loss on the forward and backward channels.

## Simulated system

This simulator models an Alternating Bit Protocol sender, receiver, and two uni-directional subnets. The sender transmits packets sequentially, waits for a matching ACK, and retransmits on timeout. Each subnet applies deterministic loss using an internal noise update rule, so successful delivery depends on protocol behavior rather than a perfect channel.

## Inputs

### Command-line arguments

| Argument | Type | Default | Meaning |
| :--- | :--- | :--- | :--- |
| `--total_packets` | int | required | Number of packets to send in the session |
| `--seed` | int | `42` | Initial seed for the deterministic subnet noise process |
| `--timeout` | int | `20` | Sender timeout in milliseconds |
| `--sender_delay` | int | `10` | Per-packet sender preparation delay in milliseconds |
| `--receiver_delay` | int | `10` | Receiver processing delay in milliseconds |
| `--channel_delay` | int | `3` | Per-subnet transmission delay in milliseconds |
| `--simulate_time` | int | `1000` | Total simulation time in milliseconds |

### Standard input

This simulator does not consume stdin.

## Output schema

The simulator writes JSON Lines to stdout. Each record follows this top-level schema:

```json
{"time": <float>, "entity": <string>, "event": <string>, "payload": <object>}
```

Required event families include:

- sender events: `delay_start`, `packet_sent`, `ack_received`
- receiver events: `delay_start`, `packet_received`
- subnet events: `packet_get`

For subnet events, `payload` contains the packet fate and channel metadata:

```json
{"behavior": "drop" | "pass", "channel": "forward" | "backward", "noise_value": <int>}
```

## Run example

```bash
cd simulator
python run.py --total_packets 8 --seed 42 --simulate_time 1000
```

## Repository contents

- `simulator/` - runnable ABP simulator package

The original generated package notes are preserved in `simulator/README.md`.
