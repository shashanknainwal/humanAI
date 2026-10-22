"""Doing the work between calls, with the Claude Agent SDK (Claude Code as a library)."""

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from .persona import Persona, worker_prompt
from .workspace import Workspace

WORK_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "WebSearch", "WebFetch"]


def _describe_tool_use(block: ToolUseBlock) -> str:
    detail = block.input.get("command") or block.input.get("file_path") or block.input.get("pattern") or ""
    return f"{block.name} {detail}".strip()


async def do_task(
    ws: Workspace,
    persona: Persona,
    *,
    max_budget_usd: float = 5.0,
    model: str | None = None,
) -> ResultMessage | None:
    if not ws.task_path.exists():
        raise FileNotFoundError(f"No task brief at {ws.task_path}. Run a briefing first.")

    report_rel = ws.report_path.relative_to(ws.root)
    options = ClaudeAgentOptions(
        cwd=str(ws.root),
        system_prompt={"type": "preset", "preset": "claude_code"},
        allowed_tools=WORK_TOOLS,
        permission_mode="acceptEdits",
        max_budget_usd=max_budget_usd,
        model=model,
        setting_sources=["project"],
    )
    ws.log("Started work.")
    result = None
    async for message in query(prompt=worker_prompt(persona, ws.read(ws.task_path), str(report_rel)), options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    ws.log(block.text)
                elif isinstance(block, ToolUseBlock):
                    ws.log(f"-> {_describe_tool_use(block)}")
        elif isinstance(message, ResultMessage):
            result = message

    if result is not None:
        cost = f"${result.total_cost_usd:.2f}" if result.total_cost_usd is not None else "unknown cost"
        ws.log(f"Finished: {result.subtype}, {result.num_turns} turns, {cost}.")
    if not ws.report_path.exists():
        # The report call must never pretend; leave an honest stub.
        summary = (result.result if result and result.result else "The work session ended without a summary.")
        ws.report_path.write_text(
            "## Summary\nI did not finish writing a full report. "
            f"Here is where the work session ended:\n\n{summary}\n"
        )
    return result
