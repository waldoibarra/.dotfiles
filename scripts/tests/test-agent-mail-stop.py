#!/usr/bin/env python3
"""Fixture tests for agent-mail-stop.py against the real agent-mail.py in isolated state."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOOK = HERE.parent / 'agent-mail-stop.py'
CLI = Path(os.getenv('AGENT_MAIL_CLI_SOURCE') or HERE.parent / 'agent-mail.py')


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / 'state'
        self.state.mkdir(mode=0o700)
        self.env = {'PATH': os.environ['PATH'], 'HOME': self.tmp.name,
                    'XDG_STATE_HOME': str(self.state), 'AGENT_MAIL_CLI': str(CLI),
                    'AGENT_MAIL_MAX_WAIT_SECONDS': '2'}
        self.run_id = self.mail('create')
        self.me = self.mail('enroll', self.run_id)
        self.peer = self.mail('enroll', self.run_id)

    def tearDown(self):
        self.tmp.cleanup()

    def mail(self, *args, body=None):
        done = subprocess.run([sys.executable, str(CLI), *args], input=body, text=True,
                              capture_output=True, env=self.env, check=True)
        return json.loads(done.stdout)

    def send(self, goal='Check the fixture'):
        mid = str(uuid.uuid4())
        body = dict(kind='assign', goal=goal, scope='Fixture mailbox', acceptance='Verify wake')
        self.mail('send', self.run_id, self.me, mid, self.peer, body=json.dumps(body))
        return mid

    def spawn(self, session='sess-1', enrolled=True, **extra):
        env = dict(self.env, **extra)
        if enrolled:
            env.update(AGENT_MAIL_RUN=self.run_id, AGENT_MAIL_RECIPIENT=self.me)
        event = json.dumps({'hook_event_name': 'Stop', 'session_id': session,
                            'stop_hook_active': False})
        proc = subprocess.Popen([sys.executable, str(HOOK)], stdin=subprocess.PIPE, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            self.addCleanup(pipe.close)
        return proc, event

    def fire(self, **kw):
        proc, event = self.spawn(**kw)
        out, err = proc.communicate(event, timeout=30)
        return proc.returncode, out, err


class StopHookTests(Fixture):
    def test_inert_without_enrollment(self):
        self.send()
        self.assertEqual(self.fire(enrolled=False), (0, '', ''))

    def test_inert_with_malformed_ids(self):
        self.send()
        for bad in ('not-a-uuid', self.me.upper(), ''):
            self.env['AGENT_MAIL_RECIPIENT'] = bad
            proc = subprocess.run([sys.executable, str(HOOK)], env=dict(
                self.env, AGENT_MAIL_RUN=self.run_id), input='{"session_id":"s"}',
                text=True, capture_output=True)
            self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, '', ''))

    def test_inert_on_bad_stdin_or_missing_session(self):
        for stdin in ('', 'garbage', '{}', '{"session_id":""}'):
            proc = subprocess.run([sys.executable, str(HOOK)], env=dict(
                self.env, AGENT_MAIL_RUN=self.run_id, AGENT_MAIL_RECIPIENT=self.me),
                input=stdin, text=True, capture_output=True)
            self.assertEqual((proc.returncode, proc.stderr), (0, ''))

    def test_wakes_immediately_for_existing_mail_without_leaking_body(self):
        self.send(goal='SECRET-BODY')
        code, out, err = self.fire()
        self.assertEqual(code, 2)
        self.assertIn('pending', err)
        self.assertIn(self.run_id, err)
        self.assertNotIn('SECRET-BODY', err + out)
        self.assertEqual(out, '')

    def test_state_files_are_private(self):
        self.send()
        self.fire()
        files = list((self.state / 'agent-mail-claude').iterdir())
        self.assertTrue(files)
        self.assertTrue(all(p.stat().st_mode & 0o077 == 0 for p in files))

    def test_wake_does_not_acknowledge(self):
        mid = self.send()
        self.fire()
        self.assertEqual(self.mail('pending', self.run_id, self.me), [mid])

    def test_wakes_when_mail_arrives_while_waiting(self):
        proc, event = self.spawn(AGENT_MAIL_MAX_WAIT_SECONDS='10')
        proc.stdin.write(event)
        proc.stdin.close()
        time.sleep(0.5)
        self.assertIsNone(proc.poll())
        self.send()
        self.assertEqual(proc.wait(timeout=10), 2)

    def test_silent_exit_after_wait_bound(self):
        self.assertEqual(self.fire()[0], 0)

    def test_no_wake_after_ack(self):
        mid = self.send()
        self.mail('ack', self.run_id, self.me, mid)
        self.assertEqual(self.fire()[0], 0)

    def test_reminders_bounded_per_message_then_new_mail_rewakes(self):
        first = self.send()
        codes = [self.fire(AGENT_MAIL_MAX_WAIT_SECONDS='0.3')[0] for _ in range(5)]
        self.assertEqual(codes, [2, 2, 2, 0, 0])
        self.assertEqual(self.mail('pending', self.run_id, self.me), [first])
        self.send()
        self.assertEqual(self.fire(AGENT_MAIL_MAX_WAIT_SECONDS='0.3')[0], 2)

    def test_duplicate_guard_is_exclusive(self):
        procs = []
        for _ in range(4):
            proc, event = self.spawn(AGENT_MAIL_MAX_WAIT_SECONDS='1.5')
            proc.stdin.write(event)
            proc.stdin.close()
            procs.append(proc)
        time.sleep(0.4)
        self.send()
        codes = sorted(p.wait(timeout=10) for p in procs)
        self.assertEqual(codes, [0, 0, 0, 2])  # exactly one watcher wakes the model

    def test_binds_first_session_and_rejects_other_session(self):
        self.send()
        self.assertEqual(self.fire(session='owner')[0], 2)
        owner = json.loads(
            next(self.state.glob(f'agent-mail/{self.run_id}/{self.me}/owner.json')).read_text()
        )
        self.assertEqual(owner, {'harness': 'claude', 'session': 'owner'})
        self.assertEqual(self.fire(session='owner')[0], 2)  # same id repeats
        self.assertEqual(self.fire(session='intruder'), (0, '', ''))

    def test_inert_for_closed_run_and_unknown_recipient(self):
        self.send()
        self.mail('close', self.run_id)
        self.assertEqual(self.fire(), (0, '', ''))
        proc = subprocess.run([sys.executable, str(HOOK)], env=dict(
            self.env, AGENT_MAIL_RUN=self.run_id, AGENT_MAIL_RECIPIENT=str(uuid.uuid4())),
            input='{"hook_event_name":"Stop","session_id":"s"}', text=True, capture_output=True)
        self.assertEqual((proc.returncode, proc.stderr), (0, ''))

    def test_missing_cli_is_silent(self):
        self.send()
        self.assertEqual(self.fire(AGENT_MAIL_CLI='/nonexistent/agent-mail'), (0, '', ''))

    def test_native_invite_and_identity_bridge(self):
        session = str(uuid.uuid4())
        envfile = self.state / 'env'
        done = subprocess.run(
            [sys.executable, str(HOOK)], env=dict(self.env, CLAUDE_ENV_FILE=str(envfile)),
            input=json.dumps({'hook_event_name': 'SessionStart', 'session_id': session}),
            text=True, capture_output=True, check=True,
        )
        self.assertEqual((done.stdout, done.stderr), ('', ''))
        self.assertIn(f'export AGENT_MAIL_CLAUDE_SESSION_ID={session}', envfile.read_text())
        self.env['AGENT_MAIL_CLAUDE_SESSION_ID'] = session
        self.assertIsNone(self.mail('session')['mailbox'])
        self.assertEqual(self.fire(session=session, enrolled=False), (0, '', ''))
        self.assertFalse((self.state / 'agent-mail-claude').exists())
        result = self.mail('invite', self.run_id, '--recipient', self.me)
        self.assertEqual(self.mail('session')['mailbox'], result)
        self.assertEqual(self.mail('invite', self.run_id), result)
        mid = self.send('not in reminder')
        self.assertIn(mid, self.fire(session=session, enrolled=False)[2])

    def test_native_hook_idle_does_not_query_and_close_notifies(self):
        session = str(uuid.uuid4())
        self.mail('invite', self.run_id, '--harness', 'claude', '--session-id', session,
                  '--recipient', self.me)
        log = self.state / 'queries'
        wrapper = self.state / 'cli.py'
        wrapper.write_text(
            f'import os, sys\nwith open({str(log)!r}, "a") as out:\n'
            f'    out.write(sys.argv[1] + "\\n")\n'
            f'os.execv(sys.executable, [sys.executable, {str(CLI)!r}, *sys.argv[1:]])\n'
        )
        proc, event = self.spawn(
            session=session, enrolled=False, AGENT_MAIL_CLI=str(wrapper),
            AGENT_MAIL_MAX_WAIT_SECONDS='15',
        )
        proc.stdin.write(event)
        proc.stdin.close()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if log.exists() and log.read_text().splitlines() == ['session', 'observe']:
                break
            time.sleep(0.02)
        else:
            self.fail('hook never armed')
        time.sleep(2.1)
        self.assertEqual(log.read_text().splitlines(), ['session', 'observe'])
        self.assertIsNone(proc.poll())
        self.mail('close', self.run_id)
        self.assertEqual(proc.wait(timeout=3), 0)
        self.assertEqual(log.read_text().splitlines(), ['session', 'observe', 'observe'])

    def test_config_is_valid_and_async_rewake(self):
        cfg = json.loads((HERE.parents[1] / 'home/.claude/settings.json').read_text())
        hook, = [
            h for group in cfg['hooks']['Stop'] for h in group['hooks']
            if 'agent-mail-stop' in h.get('command', '')
        ]
        self.assertTrue(hook['asyncRewake'])
        self.assertEqual(hook['type'], 'command')
        self.assertNotIn('StopFailure', cfg['hooks'])


if __name__ == '__main__':
    unittest.main()
