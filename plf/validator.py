from dataclasses import dataclass, field
from .schema import PLFFile


SHOT_VOCAB = {"ELS", "LS", "MLS", "MS", "MCU", "CU", "ECU", "OTS", "POV", "AER"}
TRANS_VOCAB = {"CT", "FD", "FI", "DISS", "WIPE", "MCUT"}
CAM_VOCAB = {"sta", "pan", "tilt", "push", "pull", "track", "crane", "hh", "dly"}
DIEG_VOCAB = {"D", "ND", "MIX"}
MOOD_VOCAB = {"mel", "ale", "ten", "rom", "sad", "mie", "ang", "neu"}
USR_TYPES = {"note", "inst", "q"}
VALID_TRACKS = {"SCN", "SH", "ACT", "EL", "AMB", "MUS", "DLG", "W", "TAG", "USR"}


@dataclass
class ValidationError:
    line: str
    message: str
    severity: str = "error"


@dataclass
class ValidationResult:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def validate(plf: PLFFile) -> ValidationResult:
    result = ValidationResult()
    shot_ids = {e.fields.get("id") for e in plf.timeline if e.track == "SH"}
    cast_ids = {c.id for c in plf.cast}
    scene_ids = {s.id for s in plf.scenes}

    _validate_sort_order(plf.timeline, result)
    _validate_range(plf.timeline, result)

    for entry in plf.timeline:
        _validate_entry(entry, shot_ids, cast_ids, scene_ids, result)

    return result


def _validate_sort_order(timeline: list, result: ValidationResult):
    for i in range(1, len(timeline)):
        if timeline[i].i < timeline[i - 1].i:
            result.errors.append(
                ValidationError(
                    line=f"i:{timeline[i].i:.2f}",
                    message=f"Timeline not sorted by i: at position {i} ({timeline[i].i:.2f} < {timeline[i-1].i:.2f})",
                )
            )


def _validate_range(timeline: list, result: ValidationResult):
    for entry in timeline:
        if entry.i >= entry.o:
            result.errors.append(
                ValidationError(
                    line=f"i:{entry.i:.2f} o:{entry.o:.2f}",
                    message=f"i >= o for {entry.track} entry (i={entry.i:.2f} o={entry.o:.2f})",
                )
            )


def _validate_entry(entry, shot_ids: set, cast_ids: set, scene_ids: set, result: ValidationResult):
    fields = entry.fields
    track = entry.track

    if track == "SH":
        shot = fields.get("shot", "")
        if shot and shot not in SHOT_VOCAB:
            result.errors.append(
                ValidationError(
                    line=f"i:{entry.i:.2f} T:SH shot:{shot}",
                    message=f"Invalid shot type: {shot}",
                )
            )
        for tfield in ("trans_i", "trans_o"):
            val = fields.get(tfield, "")
            if val and val not in TRANS_VOCAB:
                result.errors.append(
                    ValidationError(
                        line=f"i:{entry.i:.2f} {tfield}:{val}",
                        message=f"Invalid transition: {val}",
                    )
                )
        cam = fields.get("cam", "")
        if cam and cam not in CAM_VOCAB:
            result.errors.append(
                ValidationError(
                    line=f"i:{entry.i:.2f} cam:{cam}",
                    message=f"Invalid camera movement: {cam}",
                )
            )

    if track in ("AMB", "MUS"):
        dieg = fields.get("dieg", "")
        if dieg and dieg not in DIEG_VOCAB:
            result.errors.append(
                ValidationError(
                    line=f"i:{entry.i:.2f} dieg:{dieg}",
                    message=f"Invalid diegesis: {dieg}",
                )
            )

    if track in ("SH", "AMB", "MUS"):
        mood = fields.get("mood", "")
        if mood and mood not in MOOD_VOCAB:
            result.warnings.append(
                ValidationError(
                    line=f"i:{entry.i:.2f} mood:{mood}",
                    message=f"Unknown mood: {mood}",
                    severity="warning",
                )
            )

    if track == "EL":
        sh_ref = fields.get("sh", "")
        if sh_ref and sh_ref not in shot_ids:
            result.errors.append(
                ValidationError(
                    line=f"i:{entry.i:.2f} T:EL sh:{sh_ref}",
                    message=f"T:EL references non-existent shot: {sh_ref}",
                )
            )

    if track == "SCN":
        scn_id = fields.get("id", "")
        if scn_id and scn_id not in scene_ids:
            result.errors.append(
                ValidationError(
                    line=f"i:{entry.i:.2f} T:SCN id:{scn_id}",
                    message=f"T:SCN references non-existent scene: {scn_id}",
                )
            )

    if track == "USR":
        usr_type = fields.get("type", "")
        if usr_type and usr_type not in USR_TYPES:
            result.errors.append(
                ValidationError(
                    line=f"i:{entry.i:.2f} T:USR type:{usr_type}",
                    message=f"Invalid USR type: {usr_type}",
                )
            )

    subj = fields.get("subj", "")
    if subj and subj not in cast_ids:
        result.errors.append(
            ValidationError(
                line=f"i:{entry.i:.2f} {track} subj:{subj}",
                message=f"subj: references non-existent CAST member: {subj}",
            )
        )

    subj2 = fields.get("subj2", "")
    if subj2 and subj2 not in cast_ids:
        result.errors.append(
            ValidationError(
                line=f"i:{entry.i:.2f} subj2:{subj2}",
                message=f"subj2: references non-existent CAST member: {subj2}",
            )
        )

    spk = fields.get("spk", "")
    if spk and spk not in cast_ids:
        result.errors.append(
            ValidationError(
                line=f"i:{entry.i:.2f} {track} spk:{spk}",
                message=f"spk: references non-existent CAST member: {spk}",
            )
        )


def validate_cross_track(plf: PLFFile) -> ValidationResult:
    result = ValidationResult()

    dlg_entries = [e for e in plf.timeline if e.track == "DLG"]
    w_entries = [e for e in plf.timeline if e.track == "W"]

    for w_entry in w_entries:
        has_parent = False
        for dlg in dlg_entries:
            if (
                dlg.fields.get("spk") == w_entry.fields.get("spk")
                and dlg.i <= w_entry.i
                and dlg.o >= w_entry.o
            ):
                has_parent = True
                break
        if not has_parent:
            result.errors.append(
                ValidationError(
                    line=f"i:{w_entry.i:.2f} T:W spk:{w_entry.fields.get('spk', '')}",
                    message="T:W entry has no parent T:DLG with same spk: and overlapping range",
                )
            )

    return result
