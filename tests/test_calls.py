import pytest

from teammate import calls
from teammate.meeting import CallBrain, format_utterances
from teammate.persona import Persona
from teammate.workspace import Workspace

from fakes import FakeClaude, FakeMeeting, response, seg, text, tool_use

BRIEF = {
    "title": "Fix login timeout",
    "goal": "Sessions expire after 5 minutes instead of 60.",
    "done_criteria": ["Session lasts 60 minutes", "Test covers it"],
    "constraints": ["Don't touch the auth provider"],
    "context": "Bug reported by support.",
    "eta_minutes": 30,
}


@pytest.fixture
def fast(monkeypatch):
    """Make CallBrain poll instantly so tests don't wait on real silences."""
    original = CallBrain.__init__

    def init(self, *a, **kw):
        original(self, *a, **kw)
        self.silence_seconds = 0
        self.idle_timeout_seconds = 0.05

    monkeypatch.setattr(CallBrain, "__init__", init)


async def test_briefing_saves_task_books_followup_and_leaves(tmp_path, monkeypatch, fast):
    claude = FakeClaude(
        response(text("Hi Sam, I'm Alex, your AI teammate. What are we working on?")),
        response(text("Got it. I'll write that up."), tool_use("finalize_task", BRIEF)),
        response(text("Talk soon.")),
    )
    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda: claude)
    meeting = FakeMeeting([[seg("Login times out after five minutes, fix it.")]])
    ws = Workspace(tmp_path)

    await calls.briefing_call(meeting, "https://meet.example/abc", ws, Persona())

    assert meeting.joined == ("https://meet.example/abc", "Alex (AI teammate)")
    assert meeting.left
    assert meeting.spoken == [
        "Hi Sam, I'm Alex, your AI teammate. What are we working on?",
        "Got it. I'll write that up.",
        "Talk soon.",
    ]
    task = ws.task_path.read_text()
    assert "# Fix login timeout" in task and "- [ ] Test covers it" in task
    assert "LOCATION:https://meet.example/abc" in ws.followup_path.read_text()
    # The tool result went back to Claude before its goodbye.
    last_user = claude.requests[-1]["messages"][-1]
    assert last_user["content"][0]["type"] == "tool_result"
    assert list(tmp_path.glob(".teammate/call-briefing-*.json"))


async def test_report_call_uses_report_and_ends_on_tool(tmp_path, monkeypatch, fast):
    ws = Workspace(tmp_path)
    ws.dir.mkdir()
    ws.task_path.write_text("# Fix login timeout")
    ws.report_path.write_text("## Summary\nFixed it.")
    claude = FakeClaude(
        response(text("Hey, the fix is in."), tool_use("post_in_chat", {"message": "Summary: fixed"}, id="a")),
        response(text("Anything else?")),
        response(tool_use("end_meeting", {"notes": "Ship it Friday"})),
        response(text("Bye!")),
    )
    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda: claude)
    meeting = FakeMeeting([[seg("Great, that's all.")]])

    await calls.report_call(meeting, "https://zoom.example/1", ws, Persona())

    assert "Fixed it." in claude.requests[0]["system"]
    assert meeting.chat == ["Summary: fixed"]
    assert meeting.spoken[-1] == "Bye!"
    assert "Ship it Friday" in ws.worklog_path.read_text()


async def test_refusal_is_spoken_politely(monkeypatch, fast):
    claude = FakeClaude(response(stop_reason="refusal"))
    meeting = FakeMeeting()
    brain = CallBrain(meeting, "sys", client=claude)
    await brain.respond("something")
    assert meeting.spoken == ["Sorry, that's not something I can help with."]


async def test_tool_errors_are_returned_to_claude(fast):
    claude = FakeClaude(response(tool_use("nope", {})), response(text("Okay.")))
    brain = CallBrain(FakeMeeting(), "sys", client=claude)
    await brain.respond("hi")
    result = claude.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "Unknown tool" in result["content"]


async def test_silent_reply_speaks_nothing(fast):
    meeting = FakeMeeting()
    brain = CallBrain(meeting, "sys", client=FakeClaude(response(text(""))))
    await brain.respond("(background chatter)")
    assert meeting.spoken == []


async def test_wait_for_turn_collects_until_pause(fast):
    meeting = FakeMeeting([[seg("First part,", start=1)], [seg("second part.", start=2)]])
    brain = CallBrain(meeting, "sys", client=FakeClaude())
    heard = await brain.wait_for_turn(poll_seconds=0)
    assert heard == "Sam: First part, second part."


async def test_wait_for_turn_gives_up_when_idle(fast):
    brain = CallBrain(FakeMeeting(), "sys", client=FakeClaude())
    assert await brain.wait_for_turn(poll_seconds=0.01) is None


def test_format_utterances_merges_same_speaker():
    out = format_utterances([seg("a", "Sam"), seg("b", "Sam"), seg("c", None)])
    assert out == "Sam: a b\nSomeone: c"


async def test_camera_shows_thinking_then_busy_then_clears(fast):
    meeting = FakeMeeting()
    claude = FakeClaude(response(tool_use("post_in_chat", {"message": "x"})), response(text("Done.")))
    await CallBrain(meeting, "sys", client=claude).respond("hi")
    assert meeting.statuses == ["thinking", None, "busy", None, "thinking", None]
