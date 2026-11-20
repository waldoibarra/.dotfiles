# Agent coordination

**Run, name, brief, and read agents across Claude Code and Pi from one terminal.**
Herdr is the current terminal backend; the purpose, names, and briefs would survive replacing it.
These pages own the procedures and conventions.
The [shared orchestration
reference](/home/.agents/references/orchestration.md#coordinate-across-harnesses)
owns the coordination rules and approval boundaries; nothing here restates them.
[Agent integrations](/docs/ai-harness/integrations.md#herdr) owns installation and state-reporting
diagnosis.

Read `herdr --skill` before any control command. The skill file is Herdr's own contract.

## Choose a task

| Need | Read |
| --- | --- |
| See every live agent in one table, or a filtered subset | [List agents](listing.md) |
| Pick or change an agent's name, or label a tab or workspace | [Name agents, tabs, and workspaces](naming.md) |
| Start a worker in a disposable workspace, or close one | [Spawn and close a worker](spawning.md) |
| Write the first message a worker receives | [Brief a worker](briefing.md) |
| Fix state reporting or hooks | [Agent integrations](/docs/ai-harness/integrations.md#herdr) |

## Start an enrolled session

Start Pi or Claude normally. The operator does not launch a mailbox or issue reminders.
The lead creates a run with `agent-mail create`, then enrolls with `agent-mail invite RUN`.
Include the run ID and return address in each task brief. Workers enroll during their first turn.
Use `agent-mail session` for the native session’s address. Never route by pane name.
Send with `agent-mail send RUN RECIPIENT MESSAGE_UUID SENDER`, passing the body on standard input.
Send one JSON object containing `kind` and its required nonempty text fields:

| Kind | Fields besides `kind` |
| --- | --- |
| `assign` | `goal`, `scope`, `acceptance` |
| `blocked` | `problem`, `evidence`, `help` |
| `needs-decision` | `question`, `recommendation`, `tradeoff` |
| `decision` | `action`, `limits` |
| `result` | `outcome`, `verification`, `remaining` |

Decisions and results require `--reply-to MESSAGE_UUID`. Assignments start new requests.
Read mail, handle it, then acknowledge by ID. An acknowledgment alone does not prove completion.
Close the run after collecting results. Run `agent-mail gc` to remove closed, drained runs.

Both adapters wait for filesystem notifications rather than polling an empty inbox.
Claude arms after its turn ends. Its 55-minute limit still applies; pending mail survives expiry.
See the [glossary](/GLOSSARY.md#agent-coordination) for acknowledgment and wake notification.

## How it fits

Herdr hosts one agent per pane and reports its lifecycle state: idle, working, blocked, or unknown.
Herdr hosts workers; it does not deliver peer mail. Retrieve results through the agreed output path.
Every command in these pages was exercised on 2026-11-01 or 2026-11-02 with Herdr 0.9.5 unless a
step says "inspected".

**Relation to firstmate.** The spawning convention keeps one workspace per task with one tab per
worker; firstmate's one-task container maps to that workspace. Adopting firstmate replaces
[spawning](spawning.md) and [briefing](briefing.md) with its own scripts and task records; naming
and listing stay ours.
Read the [glossary](/GLOSSARY.md#agent-coordination) for the role names both setups share.
