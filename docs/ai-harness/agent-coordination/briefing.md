# Brief a worker

Back to [agent coordination](README.md). Used by [spawning](spawning.md) step 5.

**The first message to any agent follows the [prompting guide](/docs/prompting.md).** Its AIM
template names the actor, input, mission, actions, constraints, output, clarification, and
verification, one Markdown header each.
Save the brief under the session’s scratch directory. Name its mission and path at worker launch.

```markdown
# <Mission in one line>

## Actor
You are the worker `<name>`, an <role>. Your lead is `<lead-name>` (Herdr agent name).

## Input
- Files and directories to read, with paths.
- The lead's draft or position to challenge, when one exists.

## Mission
<Outcome> for <audience>. Why it matters, in one sentence.

## Actions
Allowed operations and tools.

## Constraints
- Directories that must not be edited. Sentences of at most 17 words.
- House conventions that apply.

## Output
Write `<path>` containing <format>. Answer first, then rationale and evidence.

## Clarification
Ask the lead about missing information that would change the result. Name assumptions.

## Verification
Support each major claim with a source the lead can open.

## Reply and stop
Write the result to the agreed output path or recipient inbox. Then stop.
Never type a reminder into the lead’s session.
```

**A worker in a fresh worktree has no dependencies.** Say in Actions that it may install them
there, or it stops at the first test run.

- Mission, Output, and Stop condition are mandatory. Prune fields that cannot change the result.
- The lead closes the worker's workspace after verification; the stop condition ends the worker's
  turn, not its container.
- Keep approval boundaries explicit: a worker never gains the lead's Git, publication, or model
  authority.
- Reuse focused context for follow-ups; do not resend the whole history.
