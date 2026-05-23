# AirfreightSim (Godot 4.6)

2D discrete-event airfreight logistics simulation demo scene.
No C#/.NET dependency is required to run the scene.

## What this demo shows

- Continuous pallet generation at origin loading facility.
- FIFO loading queue with active expiration while waiting in queue.
- Fleet coordinator assignment when queue has cargo and aircraft is idle.
- Aircraft cycle: `Idle -> InFlight -> Unloading -> Returning -> Maintenance -> Idle`.
- Delivery is recorded only when unload completes.
- Live metrics: generated, queued, delivered, expired, avg latency, utilization.
- A visually explicit center transit corridor so planes are clearly in-flight between airports.

## Project layout

- `scenes/main.tscn` - main simulation scene.
- `scripts/MainSimulation.cs` - scene drawing and orchestration.
- `scripts/LoadingQueue.cs` - FIFO queue + expiration.
- `scripts/FleetCoordinator.cs` - assignment logic.
- `scripts/AircraftAgent.cs` - aircraft finite-state machine.
- `scripts/PalletSource.cs` - periodic generation.
- `scripts/MetricsPanel.cs` / `scripts/EventLogPanel.cs` - HUD.
- `design/` - generated reference images.

## Run (No .NET required)

1. Open this folder in Godot 4.6+.
2. Run `scenes/main.tscn`.

## Scenario defaults

- Pallet interval: `10s`
- Queue expiration: `20s`
- Flight: `30s`
- Unload: `2s`
- Return: `30s`
- Maintenance: `10s`
- Aircraft count: `2`
- Sim duration: `120s`
- Time scale: `5x`

Tune values in `scripts/SimulationConfig.cs`.

## Optional: C# sources

The `scripts/*.cs` files are kept as a reference implementation, but the runnable scene uses `scripts/main_simulation.gd`.

## MQTT-driven visualization

By default, `scripts/main_simulation.gd` does not advance the SA model locally. It subscribes to JSON events published by the Python DEVS simulation in `../SA`.

1. Start an MQTT broker on `127.0.0.1:1883`.
2. Open this project in Godot 4.6+ and run `scenes/main.tscn`.
3. From `../SA`, install the publisher dependency and stream simulation events:

```bat
pip install -r requirements-mqtt.txt
python mqtt_publish_sim.py -- --duration 300 --pallet_interval 25 --pallet_expiration_time 150
```

The publisher and Godot scene both default to topic `sa/airfreight/events`. Override with `--mqtt-host`, `--mqtt-port`, and `--mqtt-topic`, or set `mqtt_host`, `mqtt_port`, and `mqtt_topic` on `SimulationLayer` in the editor.

To use the built-in GDScript simulation loop instead of MQTT, disable `use_mqtt_events` on `SimulationLayer`.

## Temporary image generation with OpenRouter (no secret persisted)

Windows CMD session example:

```bat
set http_proxy=socks5://127.0.0.1:10808
set https_proxy=socks5://127.0.0.1:10808
set OPENAI_API_KEY=your_temporary_key_here
```

Then run image generation command(s) from repo root and write outputs to `airfreight_sim_godot46/design/`.
