import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { join, resolve } from 'node:path';
import { test } from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';

const base = fileURLToPath(new URL('../', import.meta.url));
const cli = join(base, 'agent-mail.py');
assert(process.env.PI_PACKAGE_DIR, 'Set PI_PACKAGE_DIR to the installed Pi package root');
const parentURL = pathToFileURL(resolve(process.env.PI_PACKAGE_DIR, 'package.json')).href;
registerHooks({ resolve(specifier, context, next) {
  return next(specifier, specifier === 'typebox' ? { ...context, parentURL } : context);
} });
const { default: agentMail } = await import('../../home/.pi/agent/extensions/agent-mail.ts');

async function until(predicate) {
  const deadline = Date.now() + 5000;
  while (!predicate()) {
    assert(Date.now() < deadline, 'expected event did not arrive');
    await delay(15);
  }
}

test('Pi scans existing mail, wakes on rename, defers during a turn, and disarms', async () => {
  const state = mkdtempSync(join(base, 'test-pi-'));
  process.env.XDG_STATE_HOME = state;
  const log = join(state, 'queries');
  const wrapper = join(state, 'cli.py');
  writeFileSync(wrapper, [
    'import os, sys',
    `with open(${JSON.stringify(log)}, 'a') as f:`,
    '    print(sys.argv[1], file=f)',
    `os.execv(sys.executable, [sys.executable, ${JSON.stringify(cli)}, *sys.argv[1:]])`,
    '',
  ].join('\n'));
  process.env.AGENT_MAIL_CLI = wrapper;
  delete process.env.AGENT_MAIL_RUN;
  delete process.env.AGENT_MAIL_RECIPIENT;
  const session = randomUUID();
  const mail = (args, input) => JSON.parse(execFileSync('python3', [cli, ...args], {
    input, encoding: 'utf8', timeout: 5000,
  }));
  const handlers = new Map();
  const wakes = [];
  const warnings = [];
  let tool;
  let busy = false;
  agentMail({
    on: (name, fn) => handlers.set(name, fn),
    registerTool: (definition) => { tool = definition; },
    sendMessage: (msg, options) => {
      assert(options.triggerTurn);
      assert.equal(msg.display, false);
      wakes.push(msg.content);
      busy = true;
    },
  });
  const ctx = {
    mode: 'tui',
    sessionManager: { getSessionId: () => session, getSessionFile: () => '/fixture.jsonl' },
    ui: { notify: msg => warnings.push(msg) },
    isIdle: () => !busy,
    hasPendingMessages: () => false,
  };
  try {
    await handlers.get('session_start')({ reason: 'startup' }, ctx);
    assert.equal(readFileSync(log, 'utf8'), 'session\n');
    const run = mail(['create']);
    const sender = mail(['enroll', run]);
    const invite = await tool.execute('test', { run }, undefined, undefined, ctx);
    const recipient = invite.details.mailbox.recipient;
    const body = {
      kind: 'assign', goal: 'PRIVATE', scope: 'Fixture mailbox', acceptance: 'Verify wake',
    };
    const send = () => {
      const id = randomUUID();
      mail(['send', run, recipient, id, sender], JSON.stringify(body));
      return id;
    };
    handlers.get('session_shutdown')();
    const first = send();
    assert.deepEqual(mail(['read', run, recipient, first]).body, body);
    await handlers.get('session_start')({ reason: 'resume' }, ctx);
    await until(() => wakes.length === 1);
    assert(wakes[0].includes(first));
    assert(!wakes[0].includes('PRIVATE'));
    mail(['ack', run, recipient, first]);
    const second = send();
    await delay(300);
    assert.equal(wakes.length, 1);
    busy = false;
    handlers.get('agent_settled')();
    await until(() => wakes.length === 2);
    assert(wakes[1].includes(second));
    mail(['ack', run, recipient, second]);
    busy = false;
    handlers.get('agent_settled')();
    await delay(300);
    const before = readFileSync(log, 'utf8');
    await delay(2100);
    assert.equal(readFileSync(log, 'utf8'), before, 'idle empty mailbox queried');
    const third = send();
    await until(() => wakes.length === 3);
    assert(wakes[2].includes(third));
    handlers.get('session_shutdown')();
    send();
    await delay(200);
    assert.equal(wakes.length, 3);
    assert.deepEqual(warnings, []);
  } finally {
    handlers.get('session_shutdown')();
    rmSync(state, { recursive: true, force: true });
  }
});
