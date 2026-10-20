"""Client for driving FilmCraft's headless engine over its JSONL command channel.

FilmCraft exposes every engine command through ``filmcraft-cli``. The cleanest
way to drive it from a script is a *single* CLI session that replays a JSONL
script:

    filmcraft-cli --project p.fcproj --save run -   # <- JSONL on stdin

Each input line is ``{"id": "<command.id>", "params": {...}}``; each output line
is the same envelope with ``ok``/``result``/``error``. A session keeps state
(the active sequence, imported items) across lines, so the whole bridge flow
must be issued as one session — separate ``exec`` calls each start fresh and
lose the open sequence.

This client wraps that: build a list of commands, then :meth:`run` them in one
invocation and collect the typed results.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# FilmCraft's exact-time base: integer ticks, 254016000000 per second. We
# convert once at the boundary (single rounding) and keep integers after.
TICKS_PER_SECOND = 254_016_000_000

DEFAULT_CLI = (
    "/Users/rafaelolivares/Documents/GitHub/filmcraft/target/release/filmcraft-cli"
)


class BridgeError(RuntimeError):
    """A FilmCraft command failed, or the CLI itself could not be run."""


@dataclass
class Command:
    """One engine command to execute (``id`` is the command, e.g. ``file.import``)."""

    id: str
    params: dict = field(default_factory=dict)


@dataclass
class CommandResult:
    """The engine's reply for one command."""

    id: str
    ok: bool
    result: object = None
    error: str | None = None

    @property
    def value(self):
        """The result payload; raises if the command failed."""
        if not self.ok:
            raise BridgeError(f"{self.id}: {self.error}")
        return self.result


class FilmCraftClient:
    """Runs a batch of commands against FilmCraft in one CLI session.

    Parameters
    ----------
    project:
        Path to the ``.fcproj`` to open (and, with ``save=True``, write back).
    cli_path:
        Path to the ``filmcraft-cli`` binary.
    save:
        Persist the project when the session ends (``--save``).
    """

    def __init__(
        self,
        project: str | Path,
        cli_path: str = DEFAULT_CLI,
        save: bool = True,
    ):
        self.project = str(project)
        self.cli_path = cli_path
        self.save = save

    def ensure_cli(self) -> None:
        if not shutil.which(self.cli_path) and not Path(self.cli_path).exists():
            raise BridgeError(
                f"filmcraft-cli not found at {self.cli_path!r}. Build FilmCraft "
                "and pass cli_path=..., or edit DEFAULT_CLI."
            )

    def new_project(self, name: str = "PLF") -> None:
        """Create an empty .fcproj at ``self.project`` (via --save-as)."""
        self.ensure_cli()
        if Path(self.project).exists():
            Path(self.project).unlink()
        # file.newProject opens an in-memory project; --save-as writes it out.
        cmd = [
            self.cli_path,
            "exec",
            "file.newProject",
            f"name={name}",
            "--save-as",
            self.project,
        ]
        self._exec(cmd, "file.newProject")

    def run(self, commands: list[Command]) -> list[CommandResult]:
        """Execute ``commands`` in a single session and return their results.

        Raises :class:`BridgeError` if the CLI exits non-zero. Individual
        command failures are returned in the results (``ok=False``) rather than
        raised, so callers can decide whether one bad command is fatal.
        """
        self.ensure_cli()
        stdin = "".join(
            json.dumps({"id": c.id, "params": c.params}) + "\n" for c in commands
        )
        cmd = [self.cli_path]
        if self.project:
            cmd += ["--project", self.project]
        if self.save:
            cmd += ["--save"]
        cmd += ["run", "-"]

        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            raise BridgeError(
                f"filmcraft-cli failed (exit {proc.returncode}): {proc.stderr.strip()}"
            )

        results: list[CommandResult] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                raise BridgeError(f"non-JSON output from filmcraft-cli: {line!r}") from e
            results.append(
                CommandResult(
                    id=data.get("id", ""),
                    ok=bool(data.get("ok")),
                    result=data.get("result"),
                    error=data.get("error"),
                )
            )
        return results

    def _exec(self, cmd: list[str], label: str) -> str:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise BridgeError(f"{label} failed: {proc.stderr.strip() or proc.stdout.strip()}")
        return proc.stdout

    def inspect(self) -> dict:
        """Return the project tree + active sequence as a dict (``inspect``)."""
        self.ensure_cli()
        cmd = [self.cli_path]
        if self.project:
            cmd += ["--project", self.project]
        cmd += ["inspect"]
        out = self._exec(cmd, "inspect")
        return json.loads(out)
