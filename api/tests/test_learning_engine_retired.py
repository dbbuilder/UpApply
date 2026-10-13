"""The corpus-memory win path is retired in favour of fact crediting (spec §3.3)."""
import agent.learning_engine as learning_engine
import app.api.v1.job_queue as job_queue


def test_winning_proposal_to_memory_removed():
    assert not hasattr(learning_engine, "winning_proposal_to_memory")
    assert not hasattr(job_queue, "winning_proposal_to_memory")


def test_remaining_mechanisms_still_exported():
    assert callable(learning_engine.contribute_signal)
    assert callable(learning_engine.apply_cold_start)
