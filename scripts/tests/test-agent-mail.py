"""Exercise the mail transport through separate CLI processes in disposable state."""

import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid


def assignment(goal):
    return dict(kind='assign', goal=goal, scope='Fixture mailbox', acceptance='Verify delivery')


def completed(outcome):
    return dict(kind='result', outcome=outcome, verification='Fixture checked', remaining='None')


class MailTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name)
        self.env = dict(os.environ, XDG_STATE_HOME=tmp.name)
        self.run_id = self.call('create')
        self.sender = self.call('enroll', self.run_id)
        self.box = self.call('enroll', self.run_id)

    def call(self, *args, body=''):
        script = Path(__file__).resolve().parents[1] / 'agent-mail.py'
        result = subprocess.run([sys.executable, script, *args], env=self.env, input=body,
                                text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def send(self, sender, recipient, value, reply_to=None, mid=None):
        mid = mid or str(uuid.uuid4())
        flags = ['--reply-to', reply_to] if reply_to else []
        return self.call(
            'send', self.run_id, recipient, mid, sender, *flags, body=json.dumps(value),
        )

    def test_all_five_kinds_round_trip_as_objects(self):
        def check(value, sender, recipient, reply_to=None):
            mid = self.send(sender, recipient, value, reply_to=reply_to)
            self.assertIn(mid, self.call('pending', self.run_id, recipient))
            self.assertEqual(self.call('read', self.run_id, recipient, mid), dict(
                id=mid, sender=sender, recipient=recipient, run=self.run_id,
                body=value, reply_to=reply_to,
            ))
            return mid

        task = check(assignment('Inspect the fixture'), self.sender, self.box)
        check(dict(
            kind='blocked', problem='Missing fixture', evidence='Empty directory',
            help='Restore the fixture',
        ), self.box, self.sender)
        question = check(dict(
            kind='needs-decision', question='Which fixture?',
            recommendation='Use the smaller fixture', tradeoff='Less coverage',
        ), self.box, self.sender)
        check(dict(kind='decision', action='Use the smaller fixture', limits='Read only'),
              self.sender, self.box, reply_to=question)
        check(completed('Inspection passed'), self.box, self.sender, reply_to=task)

    def test_rejected_sends_do_not_mutate_mailbox(self):
        value = assignment('Inspect the fixture')
        handled = self.send(self.sender, self.box, value)
        self.call('ack', self.run_id, self.box, handled)
        pending = self.send(self.sender, self.box, value)
        decision = dict(kind='decision', action='Use the fixture', limits='Read only')
        cases = [
            ('plain text', 'inspect the fixture', None),
            ('JSON string', json.dumps('inspect the fixture'), None),
            ('JSON array', json.dumps([value]), None),
            ('JSON null', 'null', None),
            ('unknown kind', json.dumps(dict(value, kind='note')), None),
            ('incorrect kind type', json.dumps(dict(value, kind=['assign'])), None),
            ('extra field', json.dumps(dict(value, priority='high')), None),
            ('incorrect field name', json.dumps(dict(
                kind='assign', goal=value['goal'], scope=value['scope'], criteria='Verify delivery',
            )), None),
            ('assign with reply', json.dumps(value), pending),
            ('decision without reply', json.dumps(decision), None),
            ('result without reply', json.dumps(completed('Done')), None),
        ]
        cases.extend(
            (f'missing {field}', json.dumps({k: v for k, v in value.items() if k != field}), None)
            for field in value
        )
        cases.extend(
            (f'invalid goal {invalid!r}', json.dumps(dict(value, goal=invalid)), None)
            for invalid in (False, 7, None, [], {}, '', ' \t\n')
        )

        def contents():
            return {p.relative_to(self.state): p.read_bytes() if p.is_file() else None
                    for p in self.state.rglob('*')}

        before = contents()
        for label, raw, reply_to in cases:
            with self.subTest(case=label):
                args = ['--reply-to', reply_to] if reply_to else []
                with self.assertRaises(subprocess.CalledProcessError):
                    self.call('send', self.run_id, self.box, str(uuid.uuid4()), self.sender,
                              *args, body=raw)
                self.assertEqual(contents(), before)
                self.assertEqual([pending], self.call('pending', self.run_id, self.box))

    def test_native_session_binding_is_idempotent_and_exclusive(self):
        bind = ('bind', self.run_id, self.box)
        for _ in range(2):
            self.assertEqual('bound', self.call(*bind, 'pi', 'original'))
        for harness, session in [('pi', 'replacement'), ('claude', 'original')]:
            with self.assertRaises(subprocess.CalledProcessError):
                self.call(*bind, harness, session)

    def test_concurrent_and_replayed_mail(self):
        ids = [str(uuid.uuid4()) for _ in range(20)]
        value = assignment('two\nlines')

        def send(mid):
            return self.send(self.sender, self.box, value, mid=mid)

        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            list(pool.map(send, ids))
        self.assertEqual(sorted(ids), self.call('pending', self.run_id, self.box))
        mid = ids[0]
        self.assertEqual(self.call('read', self.run_id, self.box, mid)['body'], value)
        self.call('ack', self.run_id, self.box, mid)
        send(mid)
        self.assertNotIn(mid, self.call('pending', self.run_id, self.box))
        with self.assertRaisesRegex(subprocess.CalledProcessError, 'non-zero') as failure:
            self.send(self.sender, self.box, assignment('changed'), mid=mid)
        self.assertIn('message ID conflict', failure.exception.stderr)

    def test_two_leads_reconcile_their_own_teams(self):
        main = self.sender
        leads = [self.box, self.call('enroll', self.run_id)]

        def branch(lead):
            request = self.send(main, lead, assignment('Coordinate two leaves'))
            children = [self.call('enroll', self.run_id) for _ in range(2)]
            for child in children:
                task = self.send(lead, child, assignment('Inspect'))
                self.assertEqual([task], self.call('pending', self.run_id, child))
                value = completed('Verified')
                reply = self.send(child, lead, value, reply_to=task)
                record = self.call('read', self.run_id, lead, reply)
                self.assertEqual(
                    (child, task, value), (record['sender'], record['reply_to'], record['body']),
                )
                self.call('ack', self.run_id, child, task)
                self.call('ack', self.run_id, lead, reply)
            self.call('ack', self.run_id, lead, request)
            return self.send(lead, main, completed('Two verified'), reply_to=request)

        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            summaries = list(pool.map(branch, leads))
        self.assertEqual(sorted(summaries), self.call('pending', self.run_id, main))
        self.call('close', self.run_id)
        for mid in summaries:
            self.assertEqual([], self.call('gc'))
            self.call('ack', self.run_id, main, mid)
        self.assertEqual([self.run_id], self.call('gc'))

    def test_cleanup_preserves_unread(self):
        value = assignment('Verify unread mail is preserved')
        mid = self.send(self.sender, self.box, value)
        self.call('close', self.run_id)
        self.assertEqual([], self.call('gc'))
        with self.assertRaises(subprocess.CalledProcessError) as failure:
            self.send(self.sender, self.box, value)
        self.assertIn('run closed', failure.exception.stderr)
        self.call('ack', self.run_id, self.box, mid)
        self.assertEqual([self.run_id], self.call('gc'))
        self.assertEqual([], self.call('gc'))


if __name__ == '__main__':
    unittest.main()
