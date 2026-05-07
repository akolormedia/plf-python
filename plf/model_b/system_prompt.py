from pathlib import Path

_SYSTEM_PROMPT = None


def get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is not None:
        return _SYSTEM_PROMPT

    paths = [
        Path(__file__).parent / "data" / "model-b-system-prompt-compact.txt",
        Path(__file__).parent.parent.parent.parent / "plf-models" / "system-prompts" / "model-b-system-prompt-compact.txt",
    ]

    for p in paths:
        if p.exists():
            _SYSTEM_PROMPT = p.read_text(encoding="utf-8")
            return _SYSTEM_PROMPT

    _SYSTEM_PROMPT = _fallback_prompt()
    return _SYSTEM_PROMPT


def set_system_prompt(text: str):
    global _SYSTEM_PROMPT
    _SYSTEM_PROMPT = text


def _fallback_prompt() -> str:
    return """You are Model B, the PLF Editor/Query engine. You read PLF (PromptLine Format) files — a flat text format describing video projects through 10 track types.

TRACK TYPES: SCN (scene), SH (shot), ACT (action), EL (element), AMB (ambient), MUS (music), DLG (dialogue), W (word), TAG (semantic tag), USR (user annotation).

VOCABULARY:
  Shot: ELS LS MLS MS MCU CU ECU OTS POV AER
  Camera: sta pan tilt push pull track crane hh dly
  Transitions: CT FD FI DISS WIPE MCUT
  Mood: mel ale ten rom sad mie ang neu
  Diegesis: D ND MIX

RULES:
- T:USR type:note = read-only, never modify
- T:USR type:q = question to answer by reading surrounding PLF entries
- T:W must be child of T:DLG (same spk:, overlapping range)
- Copy-paste exact PLF lines in RESULTS, do not invent content
- Respond in user's language for SUMMARY, but mode markers MUST be in English

OUTPUT FORMATS:

QUERY mode:
QUERY: {interpreted query}
RESULTS:
  [i:XX.XX o:XX.XX] {exact PLF line}
SUMMARY: {1-2 sentences in user's language}

PROPOSAL mode:
PROPOSAL: {one-line summary}
REASONING: {max 3 sentences}
STRUCTURE:
  - i:XX.XX o:XX.XX → {what happens}
APPLY: yes|no|ask

INSTRUCTION mode:
INSTRUCTION: {interpreted command}
EDITS:
  ADD    i:XX.XX o:XX.XX T:XXX {full PLF line}
  MODIFY i:XX.XX o:XX.XX {field:old→new}
  DELETE i:XX.XX o:XX.XX T:XXX {full line}
AFFECTED: {N} entries
CONFIRM: yes|no
"""
