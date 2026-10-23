"""Golden-set eval harness: blind pairing and scoring (pure functions)."""
import csv
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select, text

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval_generation.py"
spec = importlib.util.spec_from_file_location("eval_generation", SCRIPT)
eval_generation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_generation)


def test_assign_sides_is_deterministic_and_randomised():
    ids = [f"job{i}" for i in range(20)]
    first = eval_generation.assign_sides(ids, seed=7)
    assert first == eval_generation.assign_sides(ids, seed=7)
    assert {s["A"] for s in first.values()} == {"new", "old"}
    for s in first.values():
        assert {s["A"], s["B"]} == {"new", "old"}


def test_render_pairs_is_blind():
    jobs = [{"id": "j1", "title": "Azure move", "description": "Post text", "chris_letter": "Chris text"}]
    outputs = {"j1": {"old": "OLD LETTER", "new": "NEW LETTER"}}
    md = eval_generation.render_pairs_markdown(jobs, outputs, {"j1": {"A": "new", "B": "old"}})
    assert md.index("NEW LETTER") < md.index("OLD LETTER")
    assert "Chris text" in md and "Post text" in md
    lowered = md.lower()
    for leak in ("legacy", "v2", "old letter (", "new letter ("):
        assert leak not in lowered


def test_write_score_sheet(tmp_path):
    path = tmp_path / "scores.csv"
    eval_generation.write_score_sheet(path, ["j1", "j2"])
    rows = list(csv.DictReader(path.open()))
    assert [r["job_id"] for r in rows] == ["j1", "j2"]
    assert rows[0]["preferred"] == ""


JOBS = [f"j{i}" for i in range(1, 17)]  # 16 golden jobs; new letter on side A for odd jobs


def _key(new_meta):
    return {
        "sides": {j: ({"A": "new", "B": "old"} if i % 2 else {"A": "old", "B": "new"})
                  for i, j in enumerate(JOBS, 1)},
        "new_meta": new_meta,
    }


GOOD_META = {j: {"warnings": [], "fact_ids_used": ["a", "b"]} for j in JOBS}


def _rows(new_wins, judged=None):
    """First `new_wins` jobs prefer new, the rest of the judged jobs prefer old, the remainder blank."""
    judged = len(JOBS) if judged is None else judged
    rows = []
    for i, j in enumerate(JOBS, 1):
        new_side, old_side = ("A", "B") if i % 2 else ("B", "A")
        pref = new_side if i <= new_wins else old_side if i <= judged else ""
        rows.append({"job_id": j, "preferred": pref})
    return rows


def test_score_passes_at_75_percent_with_clean_drafts():
    result = eval_generation.score(_rows(12), _key(GOOD_META))
    assert result["judged"] == 16
    assert result["new_preferred"] == 12
    assert result["preference"] == 0.75
    assert result["passed"] is True
    assert eval_generation.score(_rows(11), _key(GOOD_META))["passed"] is False


def test_score_ties_count_against_new_and_blank_rows_are_ignored():
    rows = _rows(13)
    rows[0]["preferred"] = "tie"
    rows[1]["preferred"] = ""
    result = eval_generation.score(rows, _key(GOOD_META))
    assert result["judged"] == 15
    assert result["new_preferred"] == 11
    assert result["passed"] is False


def test_score_requires_every_pair_judged():
    result = eval_generation.score(_rows(1, judged=1), _key(GOOD_META))
    assert result["preference"] == 1.0
    assert result["unjudged"] == 15
    assert result["passed"] is False


def test_score_requires_at_least_15_golden_jobs():
    key = _key({j: GOOD_META[j] for j in JOBS[:4]})
    key["sides"] = {j: key["sides"][j] for j in JOBS[:4]}
    rows = [r for r in _rows(4, judged=4)[:4]]
    result = eval_generation.score(rows, key)
    assert result["preference"] == 1.0
    assert result["passed"] is False


def test_golden_exclusions_cover_every_id_the_golden_job_carries():
    job = {"id": "p-123", "proposal_id": "uuid-1", "upwork_proposal_id": "up-9", "title": "t"}
    assert sorted(eval_generation.golden_exclusions(job)) == ["p-123", "up-9", "uuid-1"]
    assert eval_generation.golden_exclusions({"id": "p-1"}) == ["p-1"]


def test_score_fails_on_unsupported_claims_or_thin_drafts():
    meta = dict(GOOD_META)
    meta["j1"] = {"warnings": ["Unsupported claim: $2M (no fact)"], "fact_ids_used": ["a"]}
    rows = _rows(16)
    result = eval_generation.score(rows, _key(meta))
    assert result["preference"] == 1.0
    assert result["unsupported_claims"] == 1
    assert result["drafts_under_2_facts"] == ["j1"]
    assert result["passed"] is False


def test_score_fails_when_claim_check_was_skipped():
    from app.services.generation.verify import CLAIM_CHECK_SKIPPED

    meta = dict(GOOD_META)
    meta["j3"] = {"warnings": [CLAIM_CHECK_SKIPPED], "fact_ids_used": ["a", "b"]}
    rows = _rows(16)
    result = eval_generation.score(rows, _key(meta))
    assert result["preference"] == 1.0
    assert result["unsupported_claims"] == 0
    assert result["claim_check_skipped"] == ["j3"]
    assert result["passed"] is False


def _row(i, **kw):
    base = {"id": f"p{i}", "upwork_proposal_id": f"u{i}", "job_title": f"Job {i}",
            "job_text": "Need help. " * 30, "cover_letter_text": "Real letter. " * 40,
            "author": "chris", "outcome": None, "screening_answers": None, "created_at": i}
    base.update(kw)
    return base


def test_select_golden_keeps_only_chris_written_complete_rows():
    rows = [
        _row(1),
        _row(2, author="ai"),                 # ChatGPT/AI letter: not a reference
        _row(3, job_text=None),               # no job post to generate from
        _row(4, cover_letter_text="short"),   # truncated scrape
        _row(5, author="chris_edited_ai"),
    ]
    assert [g["id"] for g in eval_generation.select_golden(rows, n=20)] == ["p5", "p1"]


def test_select_golden_weights_toward_responses_then_newest_and_dedupes_titles():
    rows = [
        _row(1, outcome="declined"), _row(2, outcome="viewed"), _row(3, outcome="replied"),
        _row(4, outcome="hired"), _row(5), _row(6, outcome="interviewed", job_title="Job 3"),
    ]
    got = [g["id"] for g in eval_generation.select_golden(rows, n=4)]
    # Tiers: hired/interviewed/replied, then viewed, then unknown/no_response, then declined;
    # newest first within a tier. p3 shares p6's title and ranks lower, so it is dropped.
    assert got == ["p6", "p4", "p2", "p5"]


def test_select_golden_emits_harness_format_with_exclusion_ids_and_questions():
    row = _row(7, outcome="replied", screening_answers=[{"question": "Q1?", "answer": "A"}])
    [g] = eval_generation.select_golden([row], n=20)
    assert g == {
        "id": "p7", "proposal_id": "p7", "upwork_proposal_id": "u7", "title": "Job 7",
        "description": row["job_text"].strip(), "skills": [], "questions": ["Q1?"],
        "chris_letter": row["cover_letter_text"].strip(), "outcome": "replied",
    }
    assert eval_generation.golden_exclusions(g)  # harness will exclude its own letter


LETTER = ("Taking a physical product from finished invention to actual commercial business is where most "
          "hardware startups stall, and the founder needs manufacturing relationships and channel strategy.")
POST = ("I have a physical electronic technology device that now needs to be manufactured, marketed and sold. "
        "I need a consultant who can connect me with the right people to get startup support.")


def test_drop_golden_examples_removes_the_jobs_own_proposal_and_leaking_memories():
    job = {"id": "p-1", "upwork_proposal_id": "up-1", "chris_letter": LETTER, "description": POST}
    past = [{"id": "p-1", "cover_letter_text": LETTER}, {"id": "p-2", "cover_letter_text": "other"}]
    memories = [
        {"title": "Past Proposal: Startup", "content": "JOB POSTING: " + POST + " PROPOSAL WRITTEN: x"},
        {"title": "Past Proposal: letter", "content": "PROPOSAL WRITTEN: " + LETTER},
        {"title": "Bio", "content": "Led a 160-server Azure migration."},
    ]
    kept_past, kept_memories = eval_generation.drop_golden_examples(job, past, memories)
    assert [p["id"] for p in kept_past] == ["p-2"]
    assert [m["title"] for m in kept_memories] == ["Bio"]


def test_drop_golden_examples_keeps_everything_when_nothing_leaks():
    job = {"id": "p-9", "chris_letter": LETTER, "description": POST}
    past = [{"id": "p-2"}]
    memories = [{"title": "Bio", "content": "Led a 160-server Azure migration."}]
    assert eval_generation.drop_golden_examples(job, past, memories) == (past, memories)



@pytest.mark.asyncio
async def test_golden_facts_delete_hides_facts_sourced_from_the_golden_proposal(client):
    from app.models.fact import Fact
    from app.models.user import User
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as s:
        u = User(email="eval-golden@example.com", hashed_password="x")
        s.add(u)
        await s.flush()

        def mk(st, ref, sources):
            return Fact(user_id=u.id, kind="project", statement=st, status="approved",
                        source_type="upwork_proposal", source_ref=ref, sources=sources)

        s.add_all([
            mk("own", "p-1", [{"source_type": "upwork_proposal", "source_ref": "p-1"}]),
            mk("merged", "p-7", [{"source_type": "upwork_proposal", "source_ref": "p-7"},
                                 {"source_type": "upwork_proposal", "source_ref": "up-1"}]),
            mk("other", "p-8", [{"source_type": "upwork_proposal", "source_ref": "p-8"}]),
        ])
        await s.commit()
        await s.execute(text(eval_generation.GOLDEN_FACTS_DELETE), {"uid": u.id, "ids": ["p-1", "up-1"]})
        left = sorted((await s.execute(select(Fact.statement).where(Fact.user_id == u.id))).scalars())
        await s.rollback()
    assert left == ["other"]
