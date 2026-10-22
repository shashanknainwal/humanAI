"""Being on a call: hearing, speaking, and deciding what to say.

The meeting itself (joining Zoom/Meet/Teams in a browser, speech-to-text and
text-to-speech) is handled by a joinly server (https://github.com/joinly-ai/joinly).
This module talks to it over MCP and runs Claude as the conversational brain.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import anthropic
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
TRANSCRIPT_URI = "transcript://live"


class Meeting(Protocol):
    async def join(self, url: str, name: str) -> None: ...
    async def leave(self) -> None: ...
    async def speak(self, text: str) -> None: ...
    async def post_chat(self, message: str) -> None: ...
    async def snapshot(self) -> tuple[str, str]: ...
    async def new_utterances(self) -> list[dict]: ...


class JoinlyMeeting:
    """A meeting seat provided by a local joinly MCP server."""

    def __init__(self, server: Any, settings: dict[str, Any] | None = None):
        # `server` is the joinly URL, or any transport fastmcp accepts (used in tests).
        if isinstance(server, str):
            server = StreamableHttpTransport(
                url=server, headers={"joinly-settings": json.dumps(settings or {})}
            )
        self._client = Client(transport=server)
        self._last_start = -1.0

    async def __aenter__(self) -> "JoinlyMeeting":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.__aexit__(*exc)

    async def join(self, url: str, name: str) -> None:
        await self._client.call_tool(
            "join_meeting", {"meeting_url": url, "participant_name": name}
        )

    async def leave(self) -> None:
        await self._client.call_tool("leave_meeting", {})

    async def speak(self, text: str) -> None:
        await self._client.call_tool("speak_text", {"text": text})

    async def post_chat(self, message: str) -> None:
        await self._client.call_tool("send_chat_message", {"message": message})

    async def snapshot(self) -> tuple[str, str]:
        result = await self._client.call_tool("get_video_snapshot", {})
        image = next(c for c in result.content if c.type == "image")
        return image.data, image.mime_type

    async def new_utterances(self) -> list[dict]:
        contents = await self._client.read_resource(TRANSCRIPT_URI)
        segments = json.loads(contents[0].text).get("segments", [])
        fresh = [s for s in segments if s["start"] > self._last_start]
        if fresh:
            self._last_start = fresh[-1]["start"]
        return fresh


ToolHandler = Callable[[dict], Awaitable[str | list[dict]]]


def tool_def(name: str, description: str, properties: dict[str, Any]) -> dict:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


def format_utterances(segments: list[dict]) -> str:
    lines = []
    for s in segments:
        speaker = s.get("speaker") or "Someone"
        if lines and lines[-1][0] == speaker:
            lines[-1] = (speaker, f"{lines[-1][1]} {s['text'].strip()}")
        else:
            lines.append((speaker, s["text"].strip()))
    return "\n".join(f"{speaker}: {text}" for speaker, text in lines)


class CallBrain:
    """Runs one call: listens for a turn, asks Claude what to say, says it."""

    def __init__(
        self,
        meeting: Meeting,
        system: str,
        *,
        client: anthropic.AsyncAnthropic | None = None,
        model: str = DEFAULT_MODEL,
        silence_seconds: float = 1.2,
        idle_timeout_seconds: float = 600,
        max_call_seconds: float = 45 * 60,
    ):
        self.meeting = meeting
        self.system = system
        self.client = client or anthropic.AsyncAnthropic()
        self.model = model
        self.silence_seconds = silence_seconds
        self.idle_timeout_seconds = idle_timeout_seconds
        self.max_call_seconds = max_call_seconds
        self.messages: list[dict] = []
        self.transcript: list[dict] = []
        self.tools: list[dict] = []
        self._handlers: dict[str, ToolHandler] = {}
        self.done = False
        self._add_meeting_tools()

    def add_tool(self, definition: dict, handler: ToolHandler) -> None:
        self.tools.append(definition)
        self._handlers[definition["name"]] = handler

    def _add_meeting_tools(self) -> None:
        async def look(_: dict) -> list[dict]:
            data, media_type = await self.meeting.snapshot()
            return [{"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}]

        async def chat(args: dict) -> str:
            await self.meeting.post_chat(args["message"])
            self.transcript.append({"speaker": "assistant (chat)", "text": args["message"]})
            return "Posted."

        self.add_tool(
            tool_def(
                "look_at_shared_screen",
                "See the current meeting video, including anyone's shared screen.",
                {},
            ),
            look,
        )
        self.add_tool(
            tool_def(
                "post_in_chat",
                "Post a message in the meeting chat. Use for links, names, code, or written summaries.",
                {"message": {"type": "string"}},
            ),
            chat,
        )

    async def run(self, meeting_url: str, display_name: str, opening_cue: str) -> list[dict]:
        await self.meeting.join(meeting_url, display_name)
        started = time.monotonic()
        try:
            await self.respond(opening_cue)
            while not self.done:
                if time.monotonic() - started > self.max_call_seconds:
                    await self.respond("(The call has hit its time limit. Wrap up now.)")
                    break
                heard = await self.wait_for_turn()
                if heard is None:
                    log.info("Nobody has spoken for a while; leaving.")
                    break
                await self.respond(heard)
        finally:
            await self.meeting.leave()
        return self.transcript

    async def wait_for_turn(self, poll_seconds: float = 0.3) -> str | None:
        """Collect what people say until they pause, then return it."""
        pending: list[dict] = []
        last_heard = waiting_since = time.monotonic()
        while True:
            fresh = await self.meeting.new_utterances()
            now = time.monotonic()
            if fresh:
                pending += fresh
                last_heard = now
            elif pending and now - last_heard >= self.silence_seconds:
                for s in pending:
                    self.transcript.append({"speaker": s.get("speaker") or "participant", "text": s["text"]})
                return format_utterances(pending)
            elif not pending and now - waiting_since >= self.idle_timeout_seconds:
                return None
            await asyncio.sleep(poll_seconds)

    async def respond(self, heard: str) -> None:
        self.messages.append({"role": "user", "content": heard})
        while True:
            response = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=4000,
                system=self.system,
                tools=self.tools,
                messages=self.messages,
                # Low effort keeps the reply fast enough to feel like conversation.
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                await self._say("Sorry, that's not something I can help with.")
                return

            spoken = " ".join(b.text.strip() for b in response.content if b.type == "text").strip()
            if spoken:
                await self._say(spoken)

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                return
            results = []
            for block in tool_uses:
                results.append(await self._run_tool(block))
            self.messages.append({"role": "user", "content": results})

    async def _say(self, text: str) -> None:
        self.transcript.append({"speaker": "assistant", "text": text})
        await self.meeting.speak(text)

    async def _run_tool(self, block: Any) -> dict:
        handler = self._handlers.get(block.name)
        try:
            if handler is None:
                raise ValueError(f"Unknown tool {block.name}")
            content = await handler(block.input)
            return {"type": "tool_result", "tool_use_id": block.id, "content": content}
        except Exception as e:  # report the failure to Claude instead of crashing the call
            log.exception("Tool %s failed", block.name)
            return {"type": "tool_result", "tool_use_id": block.id, "content": str(e), "is_error": True}
