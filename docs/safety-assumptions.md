# TEEVR AI — Safety Assumptions

- Heat Guardian is a safety-support / early-warning aid, NOT a certified occupational-health instrument.
- ISO 7243:2017 is a screening approach. Dry-bulb + humidity alone do NOT give an exact standards-compliant indoor WBGT.
- Indoor WBGT = 0.7·natural wet-bulb + 0.3·globe temperature; outdoor adds dry-bulb solar term.
- Thresholds (27/29/31/32 °C WBGT) are explicitly labeled SIMULATION policy values — not certified regulatory limits.
- Missing/stale/faulty sensors → UNKNOWN / NEEDS ASSESSMENT, never false SAFE.
- STOP_WORK is a hard feasibility gate: incompatible scheduling is rejected.
- LLM agents cannot authorize exceptions to hard safety constraints; solver values are never touched by an LLM.
- No GPS tracking. Worker IDs pseudonymous in analytics; emergency routing uses minimal necessary identity under supervisor-only authorization.
- Explicit voice consent; raw voice audio not stored by default; retention limits supported.
- Not a substitute for existing on-site emergency procedures.
