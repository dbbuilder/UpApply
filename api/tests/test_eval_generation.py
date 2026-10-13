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


def _key(new_meta):
    return {
        "sides": {"j1": {"A": "new", "B": "old"}, "j2": {"A": "old", "B": "new"},
                  "j3": {"A": "new", "B": "old"}, "j4": {"A": "old", "B": "new"}},
        "new_meta": new_meta,
    }


GOOD_META = {j: {"warnings": [], "fact_ids_used": ["a", "b"]} for j in ("j1", "j2", "j3", "j4")}


def test_score_passes_at_75_percent_with_clean_drafts():
    rows = [{"job_id": "j1", "preferred": "A"}, {"job_id": "j2", "preferred": "b"},
            {"job_id": "j3", "preferred": "A"}, {"job_id": "j4", "preferred": "A"}]
    result = eval_generation.score(rows, _key(GOOD_META))
    assert result["judged"] == 4
    assert result["new_preferred"] == 3
    assert result["preference"] == 0.75
    assert result["passed"] is True


def test_score_ties_count_against_new_and_blank_rows_are_ignored():
    rows = [{"job_id": "j1", "preferred": "A"}, {"job_id": "j2", "preferred": "tie"},
            {"job_id": "j3", "preferred": ""}, {"job_id": "j4", "preferred": "B"}]
    result = eval_generation.score(rows, _key(GOOD_META))
    assert result["judged"] == 3
    assert result["new_preferred"] == 2
    assert result["passed"] is False


def test_score_fails_on_unsupported_claims_or_thin_drafts():
    meta = dict(GOOD_META)
    meta["j1"] = {"warnings": ["Unsupported claim: $2M (no fact)"], "fact_ids_used": ["a"]}
    rows = [{"job_id": j, "preferred": s} for j, s in (("j1", "A"), ("j2", "B"), ("j3", "A"), ("j4", "B"))]
    result = eval_generation.score(rows, _key(meta))
    assert result["preference"] == 1.0
    assert result["unsupported_claims"] == 1
    assert result["drafts_under_2_facts"] == ["j1"]
    assert result["passed"] is False
