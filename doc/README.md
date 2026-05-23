# Visualization Docs

This directory contains the guidance for turning a generated simulator package into a Godot visualization that subscribes to its event stream.

## Files

- `Agent_Godogen_Setup_Guide.md` - practical setup and run instructions for building and launching a Godot visualization from a simulator package
- `godogen_dev_prompt.md` - the prompt specification used by the coding agent to generate the Godot project

## Intended workflow

1. Generate a simulator package with DEVS-Gen from the separate implementation repository:
   https://github.com/czyarl/devs_gen_code
2. Copy the simulator package into a Godogen workspace.
3. Use the setup guide and prompt in this directory to generate a Godot project that subscribes to the simulator's MQTT event stream.
4. Store the resulting `simulator/` and optional `godot/` folders together under one item in `simulators/`.