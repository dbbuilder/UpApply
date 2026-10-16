"""Unit tests for scripts/ingest_chatgpt_facts.py (no network)."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ingest_chatgpt_facts.py"
spec = importlib.util.spec_from_file_location("ingest_chatgpt_facts", SCRIPT)
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)


def _node(nid, parent, role, text, children=()):
    return {
        "id": nid, "parent": parent, "children": list(children),
        "message": None if role is None else {"author": {"role": role}, "content": {"parts": [text]}},
    }


def _conv(conv_id="conv-1", title="Azure proposal"):
    mapping = {
        "root": _node("root", None, None, "", ["u1"]),
        "u1": _node("u1", "root", "user", "Here is the job post. I migrated 120 servers.", ["a1"]),
        "a1": _node("a1", "u1", "assistant", "Draft letter v1", ["u2", "u2-alt"]),
        "u2": _node("u2", "a1", "user", "Correction: it was 160 servers, not 120.", ["a2"]),
        "u2-alt": _node("u2-alt", "a1", "user", "ABANDONED BRANCH", []),
        "a2": _node("a2", "u2", "assistant", "Final letter mentioning 160 servers", []),
    }
    return {"id": conv_id, "title": title, "current_node": "a2", "mapping": mapping}


def test_conversation_messages_follows_active_branch():
    msgs = ingest.conversation_messages(_conv())
    assert [r for r, _ in msgs] == ["user", "assistant", "user", "assistant"]
    assert all("ABANDONED" not in t for _, t in msgs)


def test_build_items_uses_user_turns_as_text_and_last_assistant_as_context():
    items = ingest.build_items(_conv())
    assert len(items) == 1
    item = items[0]
    assert item["source_ref"] == "conv-1"
    assert "160 servers, not 120" in item["text"]
    assert "Draft letter" not in item["text"]
    assert "Final letter" not in item["text"]
    assert "Final letter mentioning 160 servers" in item["context"]
    assert "Azure proposal" in item["context"]


def test_build_items_skips_short_or_idless_conversations():
    short = _conv()
    short["mapping"]["u1"]["message"]["content"]["parts"] = ["hi"]
    short["mapping"]["u2"]["message"]["content"]["parts"] = ["ok"]
    assert ingest.build_items(short) == []
    no_id = _conv()
    no_id.pop("id")
    assert ingest.build_items(no_id) == []


def test_chunking_produces_suffixed_refs(monkeypatch):
    monkeypatch.setattr(ingest, "MAX_SOURCE_CHARS", 60)
    conv = _conv()
    conv["mapping"]["u1"]["message"]["content"]["parts"] = ["A" * 50]
    conv["mapping"]["u2"]["message"]["content"]["parts"] = ["B" * 50]
    refs = [i["source_ref"] for i in ingest.build_items(conv)]
    assert refs == ["conv-1#1", "conv-1#2"]


def test_chunk_text_hard_splits_oversized_paragraph():
    chunks = ingest.chunk_text("x" * 25, 10)
    assert chunks == ["x" * 10, "x" * 10, "x" * 5]


def test_load_conversations_reads_both_layouts(tmp_path):
    (tmp_path / "conversations.json").write_text(json.dumps([_conv("a")]))
    assert [c["id"] for c in ingest.load_conversations(tmp_path)] == ["a"]
    split = tmp_path / "split"
    split.mkdir()
    (split / "conversations-000.json").write_text(json.dumps([_conv("b")]))
    (split / "conversations-001.json").write_text(json.dumps([_conv("c")]))
    assert [c["id"] for c in ingest.load_conversations(split)] == ["b", "c"]


def test_dry_run_makes_no_network_calls(tmp_path, monkeypatch, capsys):
    (tmp_path / "conversations.json").write_text(json.dumps([_conv("a"), _conv("b")]))

    def _boom(*a, **k):
        raise AssertionError("network call in dry run")

    monkeypatch.setattr(ingest.requests, "post", _boom)
    ingest.main([str(tmp_path), "--dry-run"])
    out = capsys.readouterr().out
    assert "2 conversations" in out
    assert "2 items" in out


def _personal(conv_id="p-1", title="Ham in 2 Hours", text="How long do I bake a 10 lb ham at 325F? Asking for dinner."):
    mapping = {
        "root": _node("root", None, None, "", ["u1"]),
        "u1": _node("u1", "root", "user", text, []),
    }
    return {"id": conv_id, "title": title, "current_node": "u1", "mapping": mapping}


def test_is_work_conversation_matches_cover_letter_in_title_body_or_career_title():
    assert ingest.is_work_conversation(_conv(title="Azure proposal"))
    assert ingest.is_work_conversation(_personal(title="Cover Letter for SaaS Role"))
    assert ingest.is_work_conversation(_personal(title="MSSQL to PostgreSQL Migration",
                                                 text="Write a cover-letter for this job post about our migration."))
    assert not ingest.is_work_conversation(_personal())
    assert not ingest.is_work_conversation(_personal(title="Semaglutide Sleep Disruption", text="My sleep has changed since the new dose."))


def test_main_filters_personal_conversations_unless_all(tmp_path, monkeypatch, capsys):
    (tmp_path / "conversations.json").write_text(json.dumps([_conv("a"), _personal("p")]))
    monkeypatch.setattr(ingest.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    ingest.main([str(tmp_path), "--dry-run"])
    assert "1 of 2 conversations (work only) -> 1 items" in capsys.readouterr().out
    ingest.main([str(tmp_path), "--dry-run", "--all"])
    assert "2 of 2 conversations (all) -> 2 items" in capsys.readouterr().out
