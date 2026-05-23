# Simulators

This directory contains the simulator catalog for DEVS-Gen.

Each simulator item uses the same layout:

```text
simulators/<name>/
  README.md
  simulator/
  godot/          # optional
```

- `README.md` is the human-facing summary for that simulator item.
- `simulator/` contains the runnable generated package, including its original generated README, entrypoint, and `devs_project/` implementation.
- `godot/` is optional and contains a visualization project that subscribes to the simulator's event stream.

## Expected structure of each simulator README

Each simulator README should summarize the contract of the simulator itself rather than repeat generation details. At minimum, it should contain:

1. A short description of the simulated system.
2. The input interface:
  - command-line arguments;
  - stdin format, if the simulator consumes stdin.
3. The output contract:
  - the top-level output schema;
  - the main required event families or final-state fields.
4. A minimal local run example.
5. A short note on repository contents:
  - `simulator/` always;
  - `godot/` only when a visualization is included.

## Available simulator items

- `ABP` - Reliable stop-and-wait packet transfer with deterministic channel loss.
- `IOBS` - Online banking authentication and transaction workflow.
- `OTrain` - Single-train light rail simulation with passenger generation and station queues.
- `SA` - Strategic airlift logistics with an optional Godot visualization.
- `SEIRD` - SEIRD epidemic compartment model.
- `barbershop` - Barbershop queueing workflow with reception, inspection, and cutting stages.
- `oft` - Dropbox-like upload/download synchronization through a buffered server.
