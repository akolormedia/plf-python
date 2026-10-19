"""Tests for plf.model_b — mode parsers, context builder, and client.

No network calls: the Groq client is never constructed with a real key,
and build_context is tested against the short example files (dur < 1200s,
so the full-timeline path is taken without needing a vector table).
"""

from pathlib import Path

from plf import parse
from plf.model_b.modes import (
    parse_query, parse_proposal, parse_instruction,
    QueryResult, ProposalResult, InstructionResult,
)
from plf.model_b.context import build_context
from plf.model_b.client import ModelBClient

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "plf-spec" / "examples"

QUERY_OUTPUT = """QUERY: Where is Laura alone?
RESULTS:
  [i:92.40 o:187.10] i:92.40 o:187.10 T:SH   id:s17  shot:MS
  [i:92.40 o:104.00] i:92.40 o:104.00 T:ACT  subj:A1  act:waits-alone
SUMMARY: Laura aparece sola en la escena SC03, entre los segundos 92.40 y 187.10.
"""

PROPOSAL_OUTPUT = """PROPOSAL: Emotional arc map from TAG entries
REASONING: The TAG entries mark emotional peaks. Ordering them chronologically reveals the arc.
STRUCTURE:
  - i:0.00 o:30.00 → calm opening
  - i:92.40 o:187.10 → rising tension
APPLY: ask
"""

INSTRUCTION_OUTPUT = """INSTRUCTION: Add TAG lbl:interior to interior shots
EDITS:
  ADD    i:12.00 o:24.50 T:TAG  lbl:interior
  MODIFY i:30.00 o:44.20 mood:neu→ten
  DELETE i:50.00 o:52.00 T:EL   sh:s05 obj:tabla
AFFECTED: 24
CONFIRM: yes
"""


def test_parse_query():
    result = parse_query(QUERY_OUTPUT)
    assert isinstance(result, QueryResult)
    assert result.interpreted_query == "Where is Laura alone?"
    assert len(result.results) == 2
    assert result.results[0].startswith("[i:92.40")
    assert "Laura" in result.summary
    assert result.raw_output == QUERY_OUTPUT


def test_parse_proposal():
    result = parse_proposal(PROPOSAL_OUTPUT)
    assert isinstance(result, ProposalResult)
    assert result.proposal == "Emotional arc map from TAG entries"
    assert "chronologically" in result.reasoning
    assert len(result.structure) == 2
    assert result.apply == "ask"


def test_parse_instruction():
    result = parse_instruction(INSTRUCTION_OUTPUT)
    assert isinstance(result, InstructionResult)
    assert result.instruction.startswith("Add TAG")
    assert result.affected == 24
    assert result.confirm is True
    assert len(result.edits) == 3

    add, modify, delete = result.edits
    assert add.action == "ADD"
    assert add.i == 12.00 and add.o == 24.50
    assert add.track == "TAG"
    assert modify.action == "MODIFY"
    assert modify.old_value == "neu" and modify.new_value == "ten"
    assert delete.action == "DELETE"
    assert delete.track == "EL"


def test_build_context_short_video():
    text = (EXAMPLES_DIR / "sol_en_playa.edit.plf").read_text(encoding="utf-8")
    plf = parse(text)
    ctx = build_context(plf, "¿dónde está Carlos?")

    assert "PLF1.0" in ctx
    assert "CAST:" in ctx
    assert "SCENES:" in ctx
    assert "T:SH" in ctx  # full timeline included for short videos


def test_build_context_falls_back_without_table():
    """A long PLF with no vector table must still return header + timeline."""
    text = (EXAMPLES_DIR / "la_ultima_vez.edit.plf").read_text(encoding="utf-8")
    plf = parse(text)
    plf.dur = 2000.0  # force the > 20 min branch

    ctx = build_context(plf, "query", table=None)
    assert "PLF1.0" in ctx
    assert "T:SH" in ctx


def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    client = ModelBClient(api_key="")
    try:
        client.chat("hola")
        raise AssertionError("Expected ValueError for missing API key")
    except ValueError as e:
        assert "GROQ_API_KEY" in str(e)


def test_system_prompt_loads():
    from plf.model_b.system_prompt import get_system_prompt
    prompt = get_system_prompt()
    assert len(prompt) > 500
    assert "QUERY" in prompt and "INSTRUCTION" in prompt
