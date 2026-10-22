# teammate

**An AI teammate you manage over video calls.**

Brief it on Zoom, Google Meet or Teams like you'd brief a colleague. It asks the
questions a good engineer would ask, goes and does the work in your repo, books
the follow-up on your calendar, then calls back to tell you what it did.

It joins as **"Alex (AI teammate)"**. It is an AI and says so. It doesn't
pretend to be a person; it just works like a good one.

```
 you ──brief on a call──▶ Alex asks questions ──▶ writes .teammate/task.md
                                                  books follow-up (.ics)
                                                        │
                                                        ▼
 you ◀──calls back, reports, posts summary in chat── does the work (Claude Code)
```

## Quickstart (about 10 minutes)

You need Docker, Python 3.11+, the Claude Code CLI, and an Anthropic API key.

1. Start the meeting server (joinly handles joining calls, speech-to-text and
   text-to-speech, all locally):
   ```bash
   docker run -p 127.0.0.1:8000:8000 ghcr.io/joinly-ai/joinly:latest
   ```
2. Install teammate:
   ```bash
   pip install git+https://github.com/<you>/teammate
   export ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Open a Google Meet, Zoom or Teams call, then run this from your repo:
   ```bash
   teammate run "https://meet.google.com/abc-defg-hij"
   ```
4. Admit "Alex (AI teammate)" into the call and tell it what you need.

## Commands

| Command | What happens |
|---|---|
| `teammate brief <url>` | Joins the call, takes the briefing, saves `.teammate/task.md`, writes the follow-up invite `.teammate/followup.ics` |
| `teammate work` | Does the task in the repo and writes `.teammate/report.md`; live log in `.teammate/worklog.md` |
| `teammate report <url>` | Rejoins, gives a spoken summary, posts details in chat, answers questions, offers to take the next task |
| `teammate run <url>` | All three in a row (`--report-url` to call back on a different link) |

Options: `--name Sam` renames the teammate, `--budget 10` caps work spend in
USD (default 5), `--repo path/` picks the repo.

## How it works

- **On the call:** [joinly](https://github.com/joinly-ai/joinly) puts a browser
  participant in the meeting and exposes it over MCP. teammate listens to the
  live transcript, waits for you to pause, and uses Claude to decide what to say.
  It can look at your shared screen and post in the chat.
- **Doing the work:** the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk)
  (Claude Code as a library) works in your repo: it reads code, edits files,
  runs tests. File edits are auto-approved; spend is capped by `--budget`.
- **Honesty rules:** it never claims to be human, never claims results it
  doesn't have, and if the work session ends without a report it says so on the
  call.

## Safety

- The teammate edits files and runs commands in the repo you point it at. Use a
  branch or a throwaway clone.
- The joinly server has no auth. Keep it bound to `127.0.0.1` as shown above.
- Call audio is transcribed locally by default (Whisper in the joinly container).
  The transcript text is sent to the Claude API.

## Roadmap

- [ ] Animated avatar on camera (clearly AI, not a deepfake face)
- [ ] Real calendar invites (Google Calendar or Outlook), not just `.ics`
- [ ] Screen-share its own work during the report
- [ ] A team: several teammates with different roles
- [ ] Wait for the booked time before calling back, instead of calling straight away

## License

MIT
