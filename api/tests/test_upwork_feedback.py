"""Client feedback parsed from an Upwork profile's work history (pasted text)."""
from pathlib import Path

from app.services.facts import _is_client_sourced as is_client_sourced
from app.services.upwork_feedback import parse_work_history, to_candidates

SAMPLE = (Path(__file__).parent / "fixtures" / "upwork_profile_work_history.txt").read_text()


def test_every_job_on_the_page_is_parsed_with_rating_and_dates():
    items = parse_work_history(SAMPLE)
    assert len(items) == 10
    azure = next(i for i in items if i.title == "Azure server - setting up connections")
    assert azure.rating == 5.0 and azure.start == "Sep 28, 2025" and azure.end == "Apr 7, 2026"
    assert azure.endorsements == ["Solution Oriented", "Clear Communicator", "Accountable for Outcomes", "Detail Oriented"]
    assert azure.quote.startswith("Chris has good communication") and not azure.truncated


def test_quotes_become_review_only_candidates_without_pay():
    cands = to_candidates(parse_work_history(SAMPLE))
    assert len(cands) == 5
    assert all(c.kind == "client_quote" and c.source_type == "client_feedback" for c in cands)
    assert all(is_client_sourced(c) for c in cands)  # never auto-approved
    blob = " ".join(c.statement + " " + (c.detail or "") for c in cands)
    assert "$" not in blob and "/hr" not in blob and " hours" not in blob


def test_shortened_quotes_are_marked():
    cands = {c.source_snippet[:20]: c for c in to_candidates(parse_work_history(SAMPLE))}
    triage = next(c for k, c in cands.items() if k.startswith("Chris was great"))
    assert triage.statement.endswith('…"') and "full text is on Upwork" in triage.detail


def test_endorsement_only_jobs_are_opt_in_and_money_is_scrubbed_from_titles():
    plain = to_candidates(parse_work_history(SAMPLE))
    with_endorsements = to_candidates(parse_work_history(SAMPLE), include_endorsements=True)
    assert len(with_endorsements) == len(plain) + 1  # the Access barcode job
    text = 'USD 100 To Move A SQL Database\nRating is 5.0 out of 5.\n5.0\n"Fast and clear."\n'
    assert "USD" not in to_candidates(parse_work_history(text))[0].statement
