"""The two calls in the loop: the briefing and the report-back."""

from datetime import datetime

from .followup import book_followup
from .meeting import CallBrain, Meeting, tool_def
from .persona import Persona, briefing_prompt, report_prompt
from .workspace import TaskBrief, Workspace

_STR_LIST = {"type": "array", "items": {"type": "string"}}

FINALIZE_TASK = tool_def(
    "finalize_task",
    "Save the agreed task brief and book the follow-up call. Call once the plan "
    "and the report-back time are agreed.",
    {
        "title": {"type": "string", "description": "Short task title, under 60 characters."},
        "goal": {"type": "string", "description": "What to achieve and why, in a few sentences."},
        "done_criteria": {**_STR_LIST, "description": "Checkable conditions for done."},
        "constraints": {**_STR_LIST, "description": "Things to avoid or keep in mind. Empty if none."},
        "context": {"type": "string", "description": "Anything else said in the briefing that matters for the work."},
        "eta_minutes": {"type": "integer", "description": "Agreed minutes until the report-back call."},
    },
)

END_MEETING = tool_def(
    "end_meeting",
    "End the report-back call once the conversation is wrapping up.",
    {"notes": {"type": "string", "description": "Decisions or feedback from this call worth remembering."}},
)


def _task_saver(brain: CallBrain, ws: Workspace, followup_url: str | None, *, ends_call: bool):
    async def save(args: dict) -> str:
        brief = TaskBrief(
            title=args["title"],
            goal=args["goal"],
            done_criteria=args["done_criteria"],
            constraints=args["constraints"],
            context=args["context"],
            eta_minutes=max(5, int(args["eta_minutes"])),
        )
        ws.save_task(brief)
        start = book_followup(ws.followup_path, brief.title, brief.eta_minutes, meeting_url=followup_url)
        local = start.astimezone().strftime("%H:%M")
        if ends_call:
            brain.done = True
        return f"Saved the brief. Follow-up booked for {local}; invite at {ws.followup_path}."

    return save


async def briefing_call(
    meeting: Meeting,
    meeting_url: str,
    ws: Workspace,
    persona: Persona,
    *,
    followup_url: str | None = None,
    model: str | None = None,
) -> list[dict]:
    brain = CallBrain(meeting, briefing_prompt(persona), **({"model": model} if model else {}))
    brain.add_tool(FINALIZE_TASK, _task_saver(brain, ws, followup_url or meeting_url, ends_call=True))
    now = datetime.now().astimezone().strftime("%A %H:%M")
    transcript = await brain.run(
        meeting_url,
        persona.display_name,
        f"(You just joined the call. It is {now}. Say a brief hello and invite them to walk you through the task.)",
    )
    ws.save_transcript("briefing", transcript)
    return transcript


async def report_call(
    meeting: Meeting,
    meeting_url: str,
    ws: Workspace,
    persona: Persona,
    *,
    model: str | None = None,
) -> list[dict]:
    system = report_prompt(
        persona,
        ws.read(ws.task_path, "(no task brief found)"),
        ws.read(ws.report_path, "(no report was written; say so honestly)"),
        ws.worklog_tail(),
    )
    brain = CallBrain(meeting, system, **({"model": model} if model else {}))
    brain.add_tool(FINALIZE_TASK, _task_saver(brain, ws, meeting_url, ends_call=False))

    async def end(args: dict) -> str:
        if args["notes"].strip():
            ws.log(f"Notes from report call: {args['notes']}")
        brain.done = True
        return "Ending the call after your goodbye."

    brain.add_tool(END_MEETING, end)
    transcript = await brain.run(
        meeting_url,
        persona.display_name,
        "(You just rejoined the call to report back. Greet them and give your summary.)",
    )
    ws.save_transcript("report", transcript)
    return transcript
