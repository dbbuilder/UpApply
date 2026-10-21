"""Every Anthropic messages.create(...) call passes only kwargs the installed SDK accepts.

anthropic>=1.13 removed `temperature` (and similar) from messages.create; passing one raises
TypeError before any request is sent, which silently broke legacy cover letters in prod.
"""
import ast
import inspect
import pathlib

import anthropic

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
ACCEPTED = set(inspect.signature(anthropic.AsyncAnthropic(api_key="x").messages.create).parameters)


def _anthropic_create_calls():
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "messages"
            ):
                yield path.relative_to(APP.parent), node


def test_messages_create_calls_exist():
    assert list(_anthropic_create_calls()), "scanner found no Anthropic calls; the test is not looking at the code"


def test_messages_create_kwargs_are_accepted_by_the_installed_sdk():
    bad = [
        f"{path}:{node.lineno} {kw.arg}"
        for path, node in _anthropic_create_calls()
        for kw in node.keywords
        if kw.arg is not None and kw.arg not in ACCEPTED
    ]
    assert not bad, f"kwargs the Anthropic SDK rejects (use extra_body): {bad}"
