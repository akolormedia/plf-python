from pathlib import Path
from .schema import VectorEntry


def entry_to_text(entry) -> str:
    track = entry.track
    fields = entry.fields
    i = entry.i
    o = entry.o

    if track == "SH":
        shot_id = fields.get("id", "?")
        shot_type = fields.get("shot", "MS")
        loc = fields.get("loc", "")
        cam = fields.get("cam", "static")
        mood = fields.get("mood", "neutral")
        trans = fields.get("trans_i", "")
        parts = [f"Shot {shot_id}: {shot_type}"]
        if loc:
            parts.append(f"Location: {loc}")
        parts.append(f"Camera: {cam}. Mood: {mood}")
        if trans and trans != "CT":
            parts.append(f"Transition: {trans}")
        return ". ".join(parts) + "."

    elif track == "ACT":
        subj = fields.get("subj", "")
        act = fields.get("act", "")
        arc = fields.get("arc", "")
        parts = [f"Action: {subj} does {act}"]
        if arc:
            parts.append(f"Arc: {arc}")
        parts.append(f"Duration: {o - i:.0f} seconds")
        return ". ".join(parts) + "."

    elif track == "DLG":
        spk = fields.get("spk", "")
        tone = fields.get("tone", "")
        parts = [f"Dialogue: speaker {spk}"]
        if tone:
            parts.append(f"Tone: {tone}")
        parts.append(f"Duration: {o - i:.0f} seconds")
        return ". ".join(parts) + "."

    elif track == "EL":
        shot_ref = fields.get("sh", "")
        subj = fields.get("subj", "")
        obj = fields.get("obj", "")
        attr = fields.get("attr", "")
        what = subj if subj else obj
        parts = [f"Element: {what} ({attr})"]
        if shot_ref:
            parts.append(f"In shot {shot_ref}")
        return ". ".join(parts) + "."

    elif track == "TAG":
        labels = fields.get("lbl", "")
        return f"Tag: {labels}. Range: {i:.2f}-{o:.2f}s."

    elif track == "MUS":
        src = fields.get("src", "")
        mood = fields.get("mood", "")
        key = fields.get("key", "")
        parts = [f"Music: {src}"]
        if mood:
            parts.append(f"Mood: {mood}")
        if key:
            parts.append(f"Key: {key}")
        return ". ".join(parts) + "."

    elif track == "AMB":
        src = fields.get("src", "")
        mood = fields.get("mood", "")
        parts = [f"Ambient sound: {src}"]
        if mood:
            parts.append(f"Mood: {mood}")
        return ". ".join(parts) + "."

    elif track == "USR":
        usr_type = fields.get("type", "")
        text = fields.get("_text", "")
        return f"User annotation ({usr_type}): {text}"

    elif track == "SCN":
        scene_id = fields.get("id", "")
        return f"Scene {scene_id}: duration {o - i:.0f} seconds."

    return f"PLF entry type {track} at {i:.2f}-{o:.2f}."


def embed_entries(plf, batch_size: int = 32) -> list[VectorEntry]:
    entries = []

    for entry in plf.timeline:
        text = entry_to_text(entry)
        scene_id = _find_scene(plf, entry.i)

        entries.append(VectorEntry(
            id=f"{entry.track}_{entry.i:.2f}",
            track=entry.track,
            i=entry.i,
            o=entry.o,
            text=text,
            plf_line=entry._raw_line,
            scene_id=scene_id,
            proj=plf.proj,
            src=plf.src,
        ))

    return entries


def _find_scene(plf, seconds: float) -> str:
    for entry in plf.timeline:
        if entry.track == "SCN" and entry.i <= seconds < entry.o:
            return entry.fields.get("id", "")
    return ""
