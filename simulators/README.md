# Simulators

This directory contains the simulator catalog for DEVS-Gen.

Each simulator item uses the same layout:

```text
simulators/<name>/
  README.md
  simulator/
  godot/          # optional
```

- `README.md` explains what the simulator is, how to run it, and whether a Godot visualization is available.
- `simulator/` contains the self-contained generated package, including its original generated README, entrypoint, and `devs_project/` implementation.
- `godot/` is optional and contains a visualization project that subscribes to the simulator's event stream.

## Available simulator items

- `ABP` - Alternating Bit Protocol
- `IOBS` - Island Observing Station
- `OTrain` - Ottawa O-Train light rail system
- `SA` - Strategic Airlift with Godot visualization
- `SEIRD` - Epidemiological compartment model
- `barbershop` - Barber shop queueing benchmark
- `oft` - Offline file transfer benchmark

The simulator packages in this repository are generated with DEVS-Gen from the separate implementation repository:

- https://github.com/czyarl/devs_gen_code
