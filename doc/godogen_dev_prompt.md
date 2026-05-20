# Task: Generate a Godot 4.6 MQTT-Driven Visualization from a Simulator Package

You are an expert Godot 4.6 + GDScript engineer and an autonomous coding agent. The user will provide a **simulator package directory** (a self-contained Python DEVS / discrete-event simulation workspace). 

Your objective is to autonomously generate a **sibling Godot 4.6 project** that visualizes the simulation in real-time via MQTT. You must accomplish this entirely *from scratch* based solely on the provided files, requiring zero human intervention or clarification.

You must extract 100% of the business entities, events, and logic strictly from the provided YAML configurations and Python source code.

---

## Step 1: Autonomous Discovery & Parsing (Mandatory)

Before writing any Godot code, analyze the input package to build a **Scenario Profile** (save this as a `README.md` in your generated project). 

Treat the input folder as valid if it contains:
1. **Scenario spec:** May  be A `*.yaml` file (containing requirements, parameters, or args).
2. **DEVS engine:** Python files containing the discrete-event simulation logic.
3. **MQTT bridge:** A Python script (e.g., `mqtt_publish_sim.py`) that filters and broadcasts events.

### 1.1 Profile Extraction Checklist
You must extract the following and document them in your `README.md`:
* **Domain Vocabulary:** Read the YAML and Python logger code to identify true entity names and exact event strings. 
* **Noise Filter Logic:** Replicate the exact `should_publish` logic found in the Python MQTT script to ensure Godot ignores irrelevant system logs.
* **MQTT Configuration:** Identify the target topic, host, and port from the Python publisher script.
* **Event-to-Visual Mapping Table:** Create a Markdown table defining how every discovered business event translates to a Godot state change (e.g., Event | Entity | Payload Keys | Godot UI/State Change).

---

## Step 2: Architecture & Constraints

Generate the sibling Godot project folder (`{SIM_PARENT}/{PROJECT_NAME}`).

### 2.1 The "Dumb Terminal" Principle
Your Godot project is strictly a visual terminal. **Do NOT reimplement DEVS logic, scheduling, or complex state machines in GDScript.** Godot's sole responsibility is to react to incoming JSON MQTT payloads, update metrics, and trigger UI animations/movements based on those specific events.

### 2.2 Dual Mode Implementation
Implement a central `SimulationLayer` node with exported variables (`@export`) to toggle modes:

1.  **MQTT Mode (Default: `use_mqtt_events = true`):**
    * Godot time is locked to the `time` or `_sim_time` field in the MQTT JSON payloads.
    * Implement a pure GDScript MQTT 3.1.1 client (over `StreamPeerTCP`). Do not use third-party plugins.
    * Must connect, subscribe to the discovered topic, parse JSON, and dispatch to specific handlers based on your Event-to-Visual Mapping.
2.  **Local Demo Mode (`use_mqtt_events = false`):**
    * A fallback loop for offline testing. Use the default durations found in the YAML to simulate basic event firing. 

---

## Step 3: UI & Layout Generation

Since you are operating zero-shot, you must infer the best visual representation based on the relationships of the entities discovered.

1.  **Select an Archetype:** Based on the scenario, automatically set up a 2D layout (e.g., Linear Flow, Hub/Coordinator, Multi-station Pipeline, or Resource Pool).
2.  **Adaptive Asset Generation:** Actively check if the user has provided an Image Generation API (e.g., OpenAI DALL-E, Midjourney, or local Stable Diffusion endpoint) in the environment or prompt.

* If API is provided: Autonomously generate prompts to create simple, 2D top-down PNG sprites representing your discovered entities. Save these directly into a res://assets/sprites/ directory and configure the Godot nodes to load them (e.g., using Sprite2D).

* If NO API is provided (Fallback): Rely strictly on procedural generation using Godot's built-in drawing functions (e.g., _draw(), ColorRect, Polygon2D).

* Constraint: Regardless of the path taken, absolutely do not halt execution to ask the user to manually provide PNG files.
3.  **Metrics HUD:** Always include a `CanvasLayer` with:
    * Rolling real-time event log (displaying the raw JSON ingestion).
    * Dynamic counters for the primary entities (created, completed, processed, etc., using the vocabulary you extracted).
    * MQTT connection status indicator.

---

## Step 4: Acceptance Criteria & Output

1.  **Executable:** The generated `project.godot` must open and run `scenes/main.tscn` without errors in Godot 4.6.
2.  **Synchronization:** When the user runs the DEVS Python publisher, the Godot UI must update seamlessly based on the filtered topic.
3.  **Complete Deliverable:** Output the entire Godot file tree, the `README.md` containing the Scenario Profile, and explicit CLI instructions on how to start the Python publisher and Godot scene together.