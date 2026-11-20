// Trial roles and read-only editor observations. Do not install this extension.
import { appendFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { Type } from 'typebox';
import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';

export default function fixture(pi: ExtensionAPI) {
  const dir = process.env.MAIL_TRIAL_ROLE_DIR!;
  const cfg = JSON.parse(readFileSync(join(dir, 'role.json'), 'utf8'));
  const run = process.env.AGENT_MAIL_RUN!;
  const box = process.env.AGENT_MAIL_RECIPIENT!;
  const evidence = (kind: string, data = {}) => appendFileSync(
    join(dir, 'events.jsonl'), JSON.stringify({ kind, ...data }) + '\n', { mode: 0o600 },
  );
  function mail(args: string[], body?: string) {
    const result = spawnSync('python3', [process.env.AGENT_MAIL_CLI!, ...args], {
      input: body ?? '', encoding: 'utf8', timeout: 2000,
    });
    if (result.status !== 0) throw new Error('fixture mail command failed: ' + args[0]);
    return JSON.parse(result.stdout);
  }
  const pending = (): string[] => mail(['pending', run, box]);
  const read = (id: string) => mail(['read', run, box, id]);
  const ack = (id: string) => mail(['ack', run, box, id]);
  function reply(id: string, to: string, replyTo: string, outcome: string, verification: string) {
    const body = { kind: 'result', outcome, verification, remaining: 'None' };
    mail(['send', run, to, id, box, '--reply-to', replyTo], JSON.stringify(body));
  }
  const result = (value: unknown) => ({
    content: [{ type: 'text' as const, text: JSON.stringify(value) }],
    details: {},
  });
  pi.registerTool({
    name: 'read_mail',
    label: 'Read fixture mail',
    description: 'Read all pending mail, with message IDs and bodies.',
    parameters: Type.Object({}), async execute() {
      return result(pending().map(read));
    },
  });
  if (cfg.leaves) {
    pi.registerTool({
      name: 'dispatch_leaf',
      label: 'Dispatch a Pi leaf',
      description: 'Launch one of your two leaf roles and deliver its task.',
      parameters: Type.Object({ slot: Type.Union([Type.Literal(1), Type.Literal(2)]) }),
      async execute(_id, { slot }) {
        const child = cfg.leaves[slot - 1];
        writeFileSync(join(dir, `dispatch-${slot}`), child.role, { flag: 'wx', mode: 0o600 });
        if ([1, 2].every((s) => existsSync(join(dir, `dispatch-${s}`)))) ack(cfg.task);
        return result({ accepted: true, slot, recipient: child.box });
      },
    });
    pi.registerTool({
      name: 'send_summary',
      label: 'Send lead summary',
      description: 'Send exact challenge values from both leaf receipts, by slot.',
      parameters: Type.Object({ slot1: Type.String(), slot2: Type.String() }),
      async execute(_id, { slot1, slot2 }) {
        const ids = pending();
        if (!cfg.leaves.every((leaf: { receipt: string }) => ids.includes(leaf.receipt))) {
          throw new Error('both receipts must be pending');
        }
        reply(cfg.summary, cfg.coordinator, cfg.task, 'Collected both leaf challenges',
          `Slot 1: ${slot1}\nSlot 2: ${slot2}`);
        for (const leaf of cfg.leaves) ack(leaf.receipt);
        return result({ sent: true });
      },
    });
  } else {
    pi.registerTool({
      name: 'return_challenge',
      label: 'Return exact leaf challenge',
      description: 'Reply to your lead with the exact challenge from your task.',
      parameters: Type.Object({ challenge: Type.String() }),
      async execute(_id, { challenge }) {
        if (!pending().includes(cfg.task)) throw new Error('task not pending');
        reply(
          cfg.receipt, cfg.lead, cfg.task, `Returned challenge for slot ${cfg.slot}`, challenge,
        );
        ack(cfg.task);
        return result({ sent: true });
      },
    });
  }

  let timer: NodeJS.Timeout | undefined;
  let ready = false;
  pi.on('session_start', (_event, ctx) => {
    if (!ctx.hasUI) throw new Error('trial requires a TUI');
    evidence('ui_ready', { session: ctx.sessionManager.getSessionId() });
    timer = setInterval(() => {
      if (!ready && ctx.ui.getEditorText() === cfg.draft) {
        ready = true;
        evidence('draft_ready');
        clearInterval(timer);
      }
    }, 100);
  });
  pi.on('before_agent_start', (event, ctx) => evidence('start', {
    source: event.messageType,
    customType: event.messageType === 'custom' ? event.message.customType : null,
    draft: ctx.ui.getEditorText() === cfg.draft,
    model: ctx.model && `${ctx.model.provider}/${ctx.model.id}`,
    thinking: pi.getThinkingLevel(),
  }));
  pi.on('agent_end', (event) => {
    const errors = event.messages.filter((m) => m.role === 'assistant' && m.stopReason === 'error');
    if (errors.length) evidence('model_error', { quota: errors.some((m) =>
      m.role === 'assistant' && /429|quota|rate.limit|usage.limit/i.test(m.errorMessage || '')) });
  });
  pi.on('agent_settled', (event, ctx) => evidence('settled', {
    draft: ctx.ui.getEditorText() === cfg.draft, aborted: event.aborted,
  }));
  pi.on('session_shutdown', () => clearInterval(timer));
}
