"""State the teammate keeps between calls, stored in <repo>/.teammate/."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class TaskBrief:
    title: str
    goal: str
    done_criteria: list[str]
    constraints: list[str] = field(default_factory=list)
    context: str = ""
    eta_minutes: int = 60

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", "", "## Goal", self.goal, "", "## Done when"]
        lines += [f"- [ ] {c}" for c in self.done_criteria]
        if self.constraints:
            lines += ["", "## Constraints"] + [f"- {c}" for c in self.constraints]
        if self.context:
            lines += ["", "## Context from the briefing", self.context]
        lines += ["", f"_Estimated time: {self.eta_minutes} minutes._", ""]
        return "\n".join(lines)


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.dir = self.root / ".teammate"

    @property
    def task_path(self) -> Path:
        return self.dir / "task.md"

    @property
    def report_path(self) -> Path:
        return self.dir / "report.md"

    @property
    def worklog_path(self) -> Path:
        return self.dir / "worklog.md"

    @property
    def followup_path(self) -> Path:
        return self.dir / "followup.ics"

    def _ensure(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    def save_task(self, brief: TaskBrief) -> Path:
        self._ensure()
        self.task_path.write_text(brief.to_markdown())
        # A new task starts a fresh report and log.
        self.report_path.unlink(missing_ok=True)
        self.worklog_path.unlink(missing_ok=True)
        return self.task_path

    def read(self, path: Path, default: str = "") -> str:
        return path.read_text() if path.exists() else default

    def log(self, text: str) -> None:
        self._ensure()
        stamp = datetime.now().strftime("%H:%M:%S")
        with self.worklog_path.open("a") as f:
            f.write(f"[{stamp}] {text.strip()}\n")

    def worklog_tail(self, max_chars: int = 6000) -> str:
        return self.read(self.worklog_path)[-max_chars:]

    def save_transcript(self, kind: str, transcript: list[dict]) -> Path:
        self._ensure()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.dir / f"call-{kind}-{stamp}.json"
        path.write_text(json.dumps(transcript, indent=2))
        return path
