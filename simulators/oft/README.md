# oft

Dropbox-like upload/download synchronization through a buffered server with separate upload and download control.

## Simulated system

This simulator models two decoupled Alternating Bit Protocol loops: an upload path from sender to server and a download path from server to receiver. The server buffers uploaded packets and only forwards them when download is enabled. Upload jobs are injected through `control` commands, while download behavior is toggled through `request` commands.

## Inputs

### Command-line arguments

| Argument | Type | Default | Meaning |
| :--- | :--- | :--- | :--- |
| `--simulation_time` | float | `1000000.0` | Total simulation time in milliseconds |

### Standard input

The simulator reads commands from stdin. Each line has one of these forms:

```text
HH:MM:SS type value
HH:MM:SS:mmm type value
```

Supported command types:

- `control` - add packets to the sender upload queue
- `request` - enable or disable downloading at the server sender

Example:

```text
00:00:10:000 control 1
00:01:00:000 request 1
00:02:00:000 request 0
```

## Output schema

The simulator writes JSON Lines to stdout. Each record follows this schema:

```json
{"timestamp_ms": <float>, "model": <string>, "type": <string>, "val": <object>}
```

Required event families include:

- sender input and lifecycle: `control_cmd`, `preparation_started`, `packet_sent`, `ack_received`, `timeout`
- server lifecycle: `download_valve_change`, `packet_received`, `ack_sent_to_sender`, `packet_forwarded`, `ack_received_from_receiver`
- receiver lifecycle: `processing_started`, `ack_sent`

## Run example

```bash
cd simulator
python run.py --simulation_time 1000000 <<'EOF'
00:00:10:000 control 1
00:01:00:000 request 1
00:02:00:000 request 0
EOF
```

## Repository contents

- `simulator/` - runnable offline file transfer simulator package

The original generated package notes are preserved in `simulator/README.md`.
