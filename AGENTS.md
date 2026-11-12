# Gateway

## Design constraint

Gateway is a human-in-the-loop interface, not an autonomous agent. Do not add autonomous LLM behavior — no scheduled or self-initiated LLM calls. Imperative, deterministic triggers (e.g. reacting to a geofence transition event with a push notification) are fine.

## Calendar conventions

- "CO" = Charlie O'Hara
- "AC" = Wifey (Charlie's wife)
