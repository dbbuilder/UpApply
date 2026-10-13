"""Generation v2 engine: brief → evidence → write → verify (spec §2)."""
from app.services.generation.orchestrator import generate_application

__all__ = ["generate_application"]
