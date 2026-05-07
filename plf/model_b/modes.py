import re
from dataclasses import dataclass, field


@dataclass
class QueryResult:
    interpreted_query: str = ""
    results: list[str] = field(default_factory=list)
    summary: str = ""
    raw_output: str = ""


@dataclass
class ProposalResult:
    proposal: str = ""
    reasoning: str = ""
    structure: list[str] = field(default_factory=list)
    apply: str = "ask"
    raw_output: str = ""


@dataclass
class InstructionEdit:
    action: str = ""        # ADD, MODIFY, DELETE
    i: float = 0.0
    o: float = 0.0
    track: str = ""
    line: str = ""
    old_value: str = ""
    new_value: str = ""


@dataclass
class InstructionResult:
    instruction: str = ""
    edits: list[InstructionEdit] = field(default_factory=list)
    affected: int = 0
    confirm: bool = False
    raw_output: str = ""


def parse_query(output: str) -> QueryResult:
    result = QueryResult(raw_output=output)

    query_match = re.search(r"QUERY:\s*(.+?)(?:\n|$)", output)
    if query_match:
        result.interpreted_query = query_match.group(1).strip()

    summary_match = re.search(r"SUMMARY:\s*(.+?)(?:\n|$)", output, re.DOTALL)
    if summary_match:
        result.summary = summary_match.group(1).strip()

    in_results = False
    for line in output.split("\n"):
        if line.strip() == "RESULTS:":
            in_results = True
            continue
        if in_results:
            stripped = line.strip()
            if stripped.startswith("SUMMARY:"):
                in_results = False
                continue
            if stripped:
                result.results.append(stripped)

    return result


def parse_proposal(output: str) -> ProposalResult:
    result = ProposalResult(raw_output=output)

    prop_match = re.search(r"PROPOSAL:\s*(.+?)(?:\n|$)", output)
    if prop_match:
        result.proposal = prop_match.group(1).strip()

    reason_match = re.search(r"REASONING:\s*(.+?)(?=\n(?:STRUCTURE|APPLY):)", output, re.DOTALL)
    if reason_match:
        result.reasoning = reason_match.group(1).strip()

    apply_match = re.search(r"APPLY:\s*(yes|no|ask)", output)
    if apply_match:
        result.apply = apply_match.group(1)

    in_structure = False
    for line in output.split("\n"):
        stripped = line.strip()
        if stripped.startswith("STRUCTURE:"):
            in_structure = True
            continue
        if stripped.startswith("APPLY:"):
            in_structure = False
            continue
        if in_structure and stripped.startswith("-"):
            result.structure.append(stripped.lstrip("- ").strip())

    return result


def parse_instruction(output: str) -> InstructionResult:
    result = InstructionResult(raw_output=output)

    inst_match = re.search(r"INSTRUCTION:\s*(.+?)(?:\n|$)", output)
    if inst_match:
        result.instruction = inst_match.group(1).strip()

    affected_match = re.search(r"AFFECTED:\s*(\d+)", output)
    if affected_match:
        result.affected = int(affected_match.group(1))

    confirm_match = re.search(r"CONFIRM:\s*(yes|no)", output)
    if confirm_match:
        result.confirm = confirm_match.group(1) == "yes"

    in_edits = False
    for line in output.split("\n"):
        stripped = line.strip()
        if stripped.startswith("EDITS:"):
            in_edits = True
            continue
        if stripped.startswith(("AFFECTED:", "CONFIRM:")):
            in_edits = False
            continue
        if in_edits and stripped:
            edit = _parse_edit_line(stripped)
            if edit:
                result.edits.append(edit)

    return result


def _parse_edit_line(line: str) -> InstructionEdit | None:
    if line.startswith("ADD"):
        parts = line.split(None, 1)
        if len(parts) < 2:
            return None
        rest = parts[1]
        edit = InstructionEdit(action="ADD", line=rest)

        i_match = re.search(r"i:([\d.]+)", rest)
        o_match = re.search(r"o:([\d.]+)", rest)
        t_match = re.search(r"T:(\w+)", rest)

        if i_match:
            edit.i = float(i_match.group(1))
        if o_match:
            edit.o = float(o_match.group(1))
        if t_match:
            edit.track = t_match.group(1)

        return edit

    elif line.startswith("MODIFY"):
        rest = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else ""
        i_match = re.search(r"i:([\d.]+)", rest)
        o_match = re.search(r"o:([\d.]+)", rest)
        arrow_match = re.search(r"(\w+):(\S+)→(\S+)", rest)

        edit = InstructionEdit(action="MODIFY")
        if i_match:
            edit.i = float(i_match.group(1))
        if o_match:
            edit.o = float(o_match.group(1))
        if arrow_match:
            edit.old_value = arrow_match.group(2)
            edit.new_value = arrow_match.group(3)
        edit.line = rest

        return edit

    elif line.startswith("DELETE"):
        rest = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else ""
        edit = InstructionEdit(action="DELETE", line=rest)

        i_match = re.search(r"i:([\d.]+)", rest)
        o_match = re.search(r"o:([\d.]+)", rest)
        t_match = re.search(r"T:(\w+)", rest)

        if i_match:
            edit.i = float(i_match.group(1))
        if o_match:
            edit.o = float(o_match.group(1))
        if t_match:
            edit.track = t_match.group(1)

        return edit

    return None
