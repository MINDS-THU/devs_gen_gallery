# SA

Strategic Airlift simulator item.

This item contains both the generated simulator package and a Godot visualization that subscribes to the simulator's event stream.

## Contents

- `simulator/` - self-contained generated simulator package, benchmark YAML, and MQTT publisher
- `godot/` - Godot 4.6 visualization project

## Run the simulator

```bash
cd simulator
python run.py --duration 300 --num_aircraft 2
```

## Run the simulator with the Godot visualization

1. Start an MQTT broker on `127.0.0.1:1883`.
2. In `simulator/`, install the publisher dependency and start the bridge:

```bash
cd simulator
pip install -r requirements-mqtt.txt
python mqtt_publish_sim.py -- --duration 300 --pallet_interval 25 --pallet_expiration_time 150
```

3. Open `godot/project.godot` in Godot 4.6 and run `scenes/main.tscn`.

The simulator publishes business events to topic `sa/airfreight/events` by default.

## How this was generated

- The simulator package was generated with DEVS-Gen from `devs_gen_code`:
  https://github.com/czyarl/devs_gen_code
- The Godot visualization workflow is documented in `../../doc/Agent_Godogen_Setup_Guide.md`.
- The generation prompt used for Godogen is in `../../doc/godogen_dev_prompt.md`.

The original generated package notes are preserved in `simulator/README.md`, and the visualization-specific notes are preserved in `godot/README.md`.
