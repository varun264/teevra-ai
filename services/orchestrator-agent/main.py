"""TEEVRA Orchestrator Agent - ADK agent coordinating safety + breakdown workflows.

Routes requests over A2A to Breakdown Recovery Agent and Heat Guardian Agent.
Produces a unified operational status. Never modifies safety thresholds or
invents metrics.
"""

from __future__ import annotations

from google.adk.agents import Agent

INSTRUCTION = """You are the TEEVRA Orchestrator Agent.
You coordinate safety and breakdown workflows across the factory.
You route requests to the Breakdown Recovery Agent and Heat Guardian Agent over
real A2A HTTP. You produce a unified operational status.
You do NOT modify safety thresholds and you do not invent metrics.
All binding scheduling/safety decisions come from the deterministic CP-SAT
solver and the heat policy engine, never from you.
"""

orchestrator_agent = Agent(
    name="teevra_orchestrator",
    model="gemini-1.5-flash-002",
    instruction=INSTRUCTION,
    description="Coordinates TEEVRA safety and breakdown workflows over A2A.",
)

root_agent = orchestrator_agent
