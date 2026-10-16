"""Golden-set eval harness: blind pairing and scoring (pure functions)."""
import csv
import importlib.util
from pathlib import Path

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
