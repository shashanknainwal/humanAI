"""teammate CLI: brief, work, report, or run the whole loop."""

import argparse
import asyncio
import logging
from pathlib import Path

from .calls import briefing_call, report_call
from .meeting import JoinlyMeeting
from .persona import Persona
from .worker import do_task
from .workspace import Workspace


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="teammate", description=__doc__)
    p.add_argument("--repo", type=Path, default=Path("."), help="Repository the teammate works in.")
    p.add_argument("--name", default="Alex", help="Teammate's name.")
    p.add_argument("--joinly", default="http://localhost:8000/mcp/", help="joinly MCP server URL.")
    p.add_argument("--model", default=None, help="Claude model for calls and work.")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("brief", help="Join a call and take a task briefing.")
    b.add_argument("meeting_url")
    b.add_argument("--followup-url", help="Meeting link to put on the follow-up invite.")

    w = sub.add_parser("work", help="Do the briefed task.")
    w.add_argument("--budget", type=float, default=5.0, help="Max spend in USD.")

    r = sub.add_parser("report", help="Join a call and report back.")
    r.add_argument("meeting_url")

    run = sub.add_parser("run", help="Brief, work, then call back to report.")
    run.add_argument("meeting_url")
    run.add_argument("--report-url", help="Meeting link for the report (default: same link).")
    run.add_argument("--budget", type=float, default=5.0)
    return p


async def _main(args: argparse.Namespace) -> None:
    ws = Workspace(args.repo)
    persona = Persona(name=args.name)
    settings = {"name": persona.display_name}

    if args.command in ("brief", "run"):
        followup = getattr(args, "followup_url", None) or getattr(args, "report_url", None)
        async with JoinlyMeeting(args.joinly, settings) as meeting:
            await briefing_call(meeting, args.meeting_url, ws, persona, followup_url=followup, model=args.model)
        print(f"Brief saved: {ws.task_path}\nFollow-up invite: {ws.followup_path}")

    if args.command in ("work", "run"):
        print(f"{persona.name} is working. Live log: {ws.worklog_path}")
        await do_task(ws, persona, max_budget_usd=args.budget, model=args.model)
        print(f"Report: {ws.report_path}")

    if args.command in ("report", "run"):
        url = args.meeting_url if args.command == "report" else (args.report_url or args.meeting_url)
        async with JoinlyMeeting(args.joinly, settings) as meeting:
            await report_call(meeting, url, ws, persona, model=args.model)


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
