# Firstmate inbox: protect unsent prompts

**Recommendation:** Keep Herdr for worker lifecycle.
Exchange peer messages through local files, never terminal input.

## What Firstmate does

- The [steering inbox][inbox] stores each message in a separate file.
  Writers serialize sequence allocation and publish records by atomic rename.
  Workers move processed records into `handled/`.
- [Worker status logs][status] are append-only.
  A watcher collects actionable changes for the supervising agent.
- The [Herdr backend][herdr] sends a constant reminder through the terminal for ordinary local steering.
  Its composer checks reduce interference. They do not remove terminal input from the protocol.

## What workers are told to send

Firstmate’s [worker brief][brief] says to handle numbered instructions before acknowledging them.
Steering bodies are free text. Status reports use named verbs and meaningful changes, not narration.
`blocked` requests help; `paused` describes a known wait. Keyed decisions retain their identity.
Marked parent requests require the same `corr` token in the reply or its evidence pointer.
The [parent channel][parent] publishes recorded outcomes from scripts; agents supply judgment separately.

**Recommendation:** Validate the message kind and its required fields before publishing.
Generate routing metadata in the transport. Keep prose inside named fields.
Apply the [shared communication rules](/home/.agents/references/communication-rules.md) there.
A receipt acknowledges handling; a result reports the outcome and evidence.

[brief]: https://github.com/kunchenguid/firstmate/blob/427056c4181c41074ad24f051f79919330df0fa5/bin/fm-brief.sh#L470-L492
[parent]: https://github.com/kunchenguid/firstmate/blob/427056c4181c41074ad24f051f79919330df0fa5/docs/secondmate-parent-channel.md#L19-L40

## Prefer native push over mailbox polling

Claude Code already [binds a peer inbox][peer] on supported normal launches.
Eligible peer messages start an idle turn without typing. Local 2.1.329 exceeds the macOS minimum.
Inbound policy still applies; version alone does not establish unattended cross-harness delivery.
Direct delivery from Pi was not established through that documented interface.
The tested cross-harness path instead uses native filesystem notifications on durable inboxes.
A committed message wakes the recipient without an extra socket, broker, or periodic inbox reads.

**Mixed trial:** Pi 1.5.2 initiated a verified round trip in 24.6 seconds.
Claude Code 2.1.329 independently initiated another in 17.5 seconds.
Both recipients returned correlated results. Both initiators verified and acknowledged them.
Neither transcript contained the unsent drafts. Seven idle seconds produced zero mailbox CLI calls.
The test used Pi compatibility enrollment and Claude native-session enrollment in disposable macOS terminals.
A final metadata assertion needed offline replay against those same transcripts.
A follow-up trial used normal interactive launches without mailbox environment variables.
Pi enrolled using its native session tool; Claude enrolled using its SessionStart identity.
Both initiated and verified structured replies. Eight invalid messages never reached an inbox.
Neither draft was submitted. Long-idle recovery was not tested.

[peer]: https://code.claude.com/docs/en/cross-session-messaging#the-sessions-inbox-socket

## Does Pi already support wake notifications?

Pi 1.5.2 exposes a [custom-message API][pi-api] inside its process.
Its documented RPC interface controls a process launched in RPC mode, not another interactive editor.
We found no documented built-in equivalent of Claude’s local peer address for ordinary Pi launches.

- [pi-intercom 0.18.1][intercom] offers a socket broker, a sender CLI, and idle wake notifications.
  Its heartbeat checks connectivity, not mailbox contents. Broker restarts discard its offline queue.
- [pi-claude-link][link] explicitly bridges both harnesses using Claude’s peer protocol.
  The inspected receiver uses `sendUserMessage`, attributing inbound text to the operator.
  Its authors caution against automated inputs. Do not enable it unchanged for our teams.
- [pi-messenger][messenger] offers file-based messaging, planning, and team management.
  That overlaps our delegation policy; its README does not establish Claude Code interoperability.

Retain structured [agent mail](/GLOSSARY.md#agent-coordination) independently of the wake transport.
A package delivery receipt must not replace the recipient’s acknowledgment.

[pi-api]: https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md
[intercom]: https://www.npmjs.com/package/pi-intercom/v/0.18.1
[link]: https://github.com/alonw0/pi-claude-link/blob/7fdccbdffd556f7e76b6a35a8bb545c89c76133a/index.ts#L87-L94
[messenger]: https://github.com/nicobailon/pi-messenger

## Herdr plugins

**Recommendation:** Add no plugin to the delivery path. Consider a read-only status view later.

- [Captain’s Deck](https://github.com/deimantasnork/captains-deck) shows Firstmate’s board.
  Its decision action delegates waking to Firstmate’s keyed-answer intake, not a generic agent inbox.
- [Reviewr](https://github.com/persiyanov/herdr-reviewr) pastes review comments into the selected editor.
  Its explicit Send action is useful for human review, not automatic peer traffic.
- Local Herdr 0.9.5 supports `herdr plugin list --json`. Collie was already enabled.
  No plugin was installed or changed for this investigation.

## Nested delegation trial

Two delegated Sol leads each received two bounded Luna research jobs through headless Pi.
All four leaf outputs arrived. The transport lead corrected a worker’s inaccurate acknowledgment claim.
The plugin lead’s report was inconsistent.
We could not verify its summary reached the parent intact.
Two launches reused output paths, so the mixed summary cannot establish what either lead said.
A later Pi 1.5.2 trial used separate sessions and verified fresh challenges end to end.
Both leads dispatched two leaves. Four receipts and both summaries matched.
All six drafts survived eight native wakes; no user turns were generated.
Claude 2.1.329 separately handled mail while preserving a three-line draft in two enrolled trials.

See the [approved change](/openspec/changes/draft-safe-agent-mail/proposal.md) for implementation decisions.
The [checklist](/openspec/changes/draft-safe-agent-mail/tasks.md) tracks remaining live checks.

[inbox]: https://github.com/kunchenguid/firstmate/blob/427056c4181c41074ad24f051f79919330df0fa5/bin/fm-task-inbox-lib.sh#L1-L55
[status]: https://github.com/kunchenguid/firstmate/blob/427056c4181c41074ad24f051f79919330df0fa5/docs/architecture.md#L130-L143
[herdr]: https://github.com/kunchenguid/firstmate/blob/427056c4181c41074ad24f051f79919330df0fa5/docs/herdr-backend.md#L671-L688
