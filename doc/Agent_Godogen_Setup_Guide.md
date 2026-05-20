# Godogen Scene Auto-Generation: Setup and Run Guide

This document explains how to configure a Coding Agent (natively supporting [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview)) and use the `Godogen` conventions to build Godot 2D scenes and close the MQTT communication loop with **zero manual coding**, after you have generated discrete-event simulation (DEVS) Python models with `devs-gen`.

---

## 1. Prerequisites

Before generation and execution, ensure your local environment has the following:

| Component | Description |
|-----------|-------------|
| **Godot Engine** | Version 4.x (4.6 recommended); add `godot` to your system PATH |
| **Python** | Python 3.x with MQTT client: `pip install paho-mqtt` |
| **MQTT Broker** | Install [Mosquitto](https://mosquitto.org/download/) to decouple simulation logic from Godot rendering |
| **Coding Agent** | [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview): `npm install -g @anthropic-ai/claude-code` |

---

## 2. Workspace Initialization

`Godogen` is built around preset development constraints (e.g. `CLAUDE.md` rule files) and context so the model generates scenes to a standard.

1. **Generate a constrained empty workspace**  
   Run Godogen’s initialization script in the target directory to create required spec files (`CLAUDE.md`, etc.) that forbid local physics loops and require MQTT-driven updates.

2. **Inject DEVS simulation context**  
   Copy the full simulation package produced by `devs-gen` (YAML config and matching Python sources) into the workspace root.

3. **Inject generation prompt**  
   Place the standard scene-generation prompt from this repo, [godogen_dev_prompt.md](./godogen_dev_prompt.md), in the workspace root.

---

## 3. Configure and Start the Coding Agent

The agent reads context and generates code automatically. Below is the standard terminal workflow.

### 3.1 API environment

Configure the Claude API key in your terminal. If you use a proxy or third-party gateway, set the Base URL as well:

```powershell
# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-your-api-key"

# If using a relay/proxy API, uncomment and set the actual URL:
# $env:ANTHROPIC_BASE_URL = "https://api.your-proxy.com/v1"
```

```bash
# Linux / macOS (Bash)
export ANTHROPIC_API_KEY="sk-your-api-key"

# If using a relay/proxy API:
# export ANTHROPIC_BASE_URL="https://api.your-proxy.com/v1"
```

### 3.2 Trigger automated generation

From the workspace root, start `claude` with the generation command (replace `[YOUR_DEVS_FOLDER_NAME]` with your actual DEVS source folder name):

```bash
claude "Read the godogen_dev_prompt.md file in this directory and strictly execute its instructions from scratch, using the [YOUR_DEVS_FOLDER_NAME]/ folder as the only simulator package input."
```

> **Generation strategy (API timeouts)**  
> For complex simulations, after the agent ingests tens of thousands of tokens of source, emitting every Godot scene file (`.tscn`, multiple `.gd` scripts) in one shot may hit a single-request timeout. You can steer the agent to output in steps:
>
> 1. `Step 1: Write project.godot and README.md. Wait for my confirmation.`
> 2. `Step 2: Write the MQTT bridge python script and mqtt_client.gd.`
> 3. `Step 3: Generate the remaining UI/Node scripts and main.tscn.`

---

## 4. Mosquitto and MQTT Configuration

Per Godogen, the agent produces a pure UI rendering layer: Godot has no business logic simulation; all state changes come from MQTT messages.

### 4.1 Start Mosquitto

In a new terminal, start the local Mosquitto service:

```bash
mosquitto -v
```

On Windows you can also start it as a service:

```powershell
net start mosquitto
```

### 4.2 Verify the port

Ensure port **1883** is listening.

---

## 5. Closed-Loop Run and Validation

After the agent finishes writing files, the workspace typically contains:

- A Godot project with `scenes` and `scripts`
- A Python data bridge script (e.g. `mqtt_publish_sim.py`)

Start the system in this order.

### 5.1 Startup order

| Step | Action |
|------|--------|
| 1 | Ensure Mosquitto is running in the background |
| 2 | Start Godot visualization (subscriber) |
| 3 | Start the data bridge (publisher) |

### 5.2 Start Godot visualization (subscriber)

Import and open the project in the Godot editor, or run from the command line:

```bash
godot --path ./Your_Generated_Godot_Folder
```

Press **F5** to run. The Godot scene connects to `localhost:1883`, receives live simulation data, and drives 2D visuals and HUD updates.

### 5.3 Start the data bridge (publisher)

From the generated Godot project directory, run the bridge script to start the underlying DEVS simulation and publish events to MQTT:

```bash
python mqtt_publish_sim.py
```

The terminal should begin scrolling JSON event logs.

