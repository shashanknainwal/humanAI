"""JoinlyMeeting against an in-memory MCP server that mimics joinly's tools."""

import json

from fastmcp import FastMCP
from mcp.types import ImageContent

from teammate.meeting import JoinlyMeeting


def fake_joinly():
    mcp = FastMCP("joinly")
    state = {"calls": [], "segments": []}

    @mcp.tool("join_meeting")
    def join_meeting(meeting_url: str | None = None, participant_name: str | None = None) -> str:
        state["calls"].append(("join", meeting_url, participant_name))
        return "Joined meeting."

    @mcp.tool("speak_text")
    def speak_text(text: str) -> str:
        state["calls"].append(("speak", text))
        return "Finished speaking."

    @mcp.tool("send_chat_message")
    def send_chat_message(message: str) -> str:
        state["calls"].append(("chat", message))
        return "Sent message."

    @mcp.tool("leave_meeting")
    def leave_meeting() -> str:
        state["calls"].append(("leave",))
        return "Left the meeting."

    @mcp.tool("get_video_snapshot")
    def get_video_snapshot() -> ImageContent:
        return ImageContent(type="image", data="aW1n", mimeType="image/png")

    @mcp.resource("transcript://live", mime_type="application/json")
    def transcript() -> str:
        return json.dumps({"segments": state["segments"]})

    return mcp, state


async def test_adapter_round_trip():
    server, state = fake_joinly()
    async with JoinlyMeeting(server) as m:
        await m.join("https://meet.example/x", "Alex (AI teammate)")
        await m.speak("Hello")
        await m.post_chat("notes")
        assert await m.snapshot() == ("aW1n", "image/png")

        state["segments"] = [{"text": "hi", "start": 1.0, "end": 2.0, "speaker": "Sam"}]
        assert [s["text"] for s in await m.new_utterances()] == ["hi"]
        assert await m.new_utterances() == []  # already seen
        state["segments"].append({"text": "next", "start": 3.0, "end": 4.0, "speaker": "Sam"})
        assert [s["text"] for s in await m.new_utterances()] == ["next"]

        await m.leave()

    assert state["calls"] == [
        ("join", "https://meet.example/x", "Alex (AI teammate)"),
        ("speak", "Hello"),
        ("chat", "notes"),
        ("leave",),
    ]


async def test_set_status_is_skipped_when_server_lacks_ui_updates():
    server, _ = fake_joinly()
    async with JoinlyMeeting(server) as m:
        await m.set_status("thinking")  # fake server doesn't advertise joinly_ui_update
