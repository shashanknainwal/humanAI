from datetime import UTC, datetime

from claude_agent_sdk import ResultMessage

from teammate import worker
from teammate.followup import book_followup, build_invite
from teammate.persona import Persona
from teammate.workspace import TaskBrief, Workspace


def test_invite_is_valid_ics_with_escaping():
    ics = build_invite("Sync; part 1, final", datetime(2026, 10, 22, 15, 0, tzinfo=UTC), meeting_url="https://x.example")
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "SUMMARY:Sync\\; part 1\\, final" in ics
    assert "DTSTART:20261022T150000Z" in ics and "DTEND:20261022T151500Z" in ics


def test_followup_starts_after_eta_plus_buffer(tmp_path):
    start = book_followup(tmp_path / "f.ics", "Task", 30, now=datetime(2026, 1, 1, 9, 0, tzinfo=UTC))
    assert start == datetime(2026, 1, 1, 9, 35, tzinfo=UTC)
    assert (tmp_path / "f.ics").exists()


def _result(text):
    return ResultMessage(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
        num_turns=3, session_id="s", total_cost_usd=0.42, result=text,
    )


async def test_worker_writes_honest_stub_when_no_report(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ws.save_task(TaskBrief("T", "G", ["done"]))

    async def fake_query(prompt, options):
        assert "# T" in prompt and options.cwd == str(tmp_path.resolve())
        yield _result("Ran out of budget halfway.")

    monkeypatch.setattr(worker, "query", fake_query)
    await worker.do_task(ws, Persona())

    report = ws.report_path.read_text()
    assert "did not finish writing a full report" in report and "halfway" in report
    assert "3 turns, $0.42" in ws.worklog_path.read_text()


async def test_new_task_clears_previous_report(tmp_path):
    ws = Workspace(tmp_path)
    ws.save_task(TaskBrief("A", "G", ["x"]))
    ws.report_path.write_text("old")
    ws.save_task(TaskBrief("B", "G", ["x"]))
    assert not ws.report_path.exists()
