# Draft-safe agent mail

## Why

Direct terminal submissions can send an unfinished operator draft.
Idle recipients must wake without operator reminders.

## What Changes

Keep Herdr lifecycle controls. Replace interactive peer prompts with private, acknowledged local mail.
Pair opposite flagship models for planning and final review; use cheaper workers between those gates.

## Approach and tradeoffs

Keep one immutable record per message.
Use native wake signals without sending payloads through the editor.
Reject typed reminders: checking editor state cannot prevent concurrent human typing.
Use manual recovery when native delivery fails, never automatic input injection.

### Fable plan review

Bind recipients to native session identities, never pane names.
Check pending mail before arming each watcher.
Use Pi custom messages, not user messages. Use Claude Stop hooks, not StopFailure.
Coalesce concurrent arrivals and bound retries. A wake never acknowledges a message.
Test installed versions in disposable sessions before enabling either adapter.
Existing sessions require explicit enrollment; startup alone cannot prove their watchers are armed.

## Capabilities

- `agent-mail`: durable local delivery, native wakes, guarded cleanup, and draft preservation.

## Impact

The operator approved implementation and isolated verification.
Roll out each receiver only after live draft tests.
Other harnesses remain unsupported; mailbox records survive disabled adapters.
