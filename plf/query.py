from .schema import PLFFile, PLFEntry


def get_entries(plf: PLFFile, track: str | None = None, **filters) -> list[PLFEntry]:
    results = []
    for entry in plf.timeline:
        if track and entry.track != track:
            continue
        match = True
        for key, value in filters.items():
            if entry.fields.get(key) != value:
                match = False
                break
        if match:
            results.append(entry)
    return results


def get_entries_at(plf: PLFFile, seconds: float) -> list[PLFEntry]:
    results = []
    for entry in plf.timeline:
        if entry.i <= seconds < entry.o:
            results.append(entry)
    return results


def get_scene_at(plf: PLFFile, seconds: float) -> str | None:
    for entry in plf.timeline:
        if entry.track == "SCN" and entry.i <= seconds < entry.o:
            scene_id = entry.fields.get("id", "")
            for scene in plf.scenes:
                if scene.id == scene_id:
                    return scene.desc
            return scene_id
    return None


def get_shots_in_range(plf: PLFFile, start: float, end: float) -> list[PLFEntry]:
    results = []
    for entry in plf.timeline:
        if entry.track == "SH" and entry.i < end and entry.o > start:
            results.append(entry)
    return results


def get_dialogue_text(plf: PLFFile, start: float | None = None, end: float | None = None) -> str:
    words = []
    for entry in plf.timeline:
        if entry.track == "W":
            if start is not None and entry.i < start:
                continue
            if end is not None and entry.o > end:
                continue
            word = entry.fields.get("_word", "")
            if word:
                words.append(word)
    return " ".join(words)
