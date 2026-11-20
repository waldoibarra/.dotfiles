#!/usr/bin/env python3
"""Run one bounded Pi trial. The coordinator is not a model session."""

import argparse
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import secrets
import selectors
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
import uuid

MODEL = 'openai-codex/gpt-5.6-luna'
HERE = Path(__file__).resolve().parent
LEAD_TASK = (
    'You are one lead in a disposable mail trial. Call read_mail when woken. '
    'On the lead task, call dispatch_leaf once for slot 1 and once for slot 2. '
    'Then end your turn. Do not wait, poll, or dispatch again. '
    'On later mail wakes, call read_mail to find leaf receipts. '
    'If only one receipt is present, end the turn without sending anything. '
    'Each receipt names its slot in body.outcome and gives the exact challenge '
    'in body.verification. '
    'When both are present, call send_summary with exact challenge values by slot.'
)
LEAF_TASK = (
    'You are a leaf in a disposable mail trial. Call read_mail. '
    'Call return_challenge with the exact challenge in body.scope, then end the turn.'
)


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def save(path, value):
    with path.open('x', encoding='utf-8') as out:
        json.dump(value, out)
        out.write('\n')


class Trial:
    def __init__(self, args):
        self.args = args
        self.root = Path(tempfile.mkdtemp(prefix='pi-mail-trial-'))
        self.adapter = self.root / 'agent-mail.ts'
        self.cli = self.root / 'agent-mail.py'
        shutil.copyfile(args.extension, self.adapter)
        shutil.copyfile(args.mail, self.cli)
        self.mail_env = {**os.environ, 'XDG_STATE_HOME': str(self.root / 'state')}
        self.sel = selectors.DefaultSelector()
        self.roles = {}
        self.run = None
        self.metrics = dict(
            launched=0, lead_dispatches=0, receipts_verified=0, summaries_verified=0,
            draft_preserved=0, custom_turns=0, user_turns=0, bound_sessions=0,
        )

    def mail(self, *args, body=None):
        result = subprocess.run(['python3', str(self.cli), *args], text=True, capture_output=True,
                                input='' if body is None else json.dumps(body),
                                env=self.mail_env, timeout=4)
        require(result.returncode == 0, f'mail command failed: {args[0]}')
        return json.loads(result.stdout)

    def send(self, source, target, mid, body):
        self.mail('send', self.run, target, mid, source, body=body)

    def role(self, name):
        cfg = dict(
            role=name, box=self.mail('enroll', self.run), task=str(uuid.uuid4()),
            draft=f'Unfinished operator draft {secrets.token_hex(8)}',
        )
        directory = Path(tempfile.mkdtemp(prefix=name + '-', dir=self.root))
        self.roles[name] = {'cfg': cfg, 'dir': directory, 'events': []}
        return cfg

    def launch(self, role):
        cfg, directory = role['cfg'], role['dir']
        require('proc' not in role, 'duplicate role launch')
        save(directory / 'role.json', cfg)
        for subdir in ('home', 'agent', 'sessions', 'cwd', 'tmp', 'config', 'cache', 'data'):
            (directory / subdir).mkdir(mode=0o700)
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL') if key in os.environ}
        env.update(
            HOME=str(directory / 'home'), TMPDIR=str(directory / 'tmp'),
            PI_CODING_AGENT_DIR=str(directory / 'agent'), PI_OFFLINE='1', PI_TELEMETRY='0',
            XDG_CONFIG_HOME=str(directory / 'config'), XDG_DATA_HOME=str(directory / 'data'),
            XDG_CACHE_HOME=str(directory / 'cache'),
            XDG_STATE_HOME=self.mail_env['XDG_STATE_HOME'],
            TERM='xterm-256color', AGENT_MAIL_CLI=str(self.cli), AGENT_MAIL_RUN=self.run,
            AGENT_MAIL_RECIPIENT=cfg['box'], MAIL_TRIAL_ROLE_DIR=str(directory),
        )
        auth = directory / 'agent' / 'auth.json'
        role['auth'] = auth
        shutil.copyfile(self.args.auth, auth)
        save(directory / 'agent' / 'settings.json', {
            'retry': {'enabled': False, 'provider': {'maxRetries': 0}},
            'compaction': {'enabled': False},
        })
        fixture = str(HERE / 'pi-mail-trial.ts')
        command = [
            self.args.pi, '--model', MODEL, '--thinking', 'medium', '--no-approve',
            '--no-extensions', '--no-builtin-tools', '--no-mcp', '--no-skills',
            '--no-prompt-templates', '--no-themes', '--no-context-files',
            '--session-dir', str(directory / 'sessions'), '--extension', fixture,
            '--system-prompt',
            'Read fixture mail on any native wake. Follow the task in that mail. '
            'Use the fixture tools. Do not ask for operator input. Never guess a challenge.',
        ]
        command += ['--extension', str(self.adapter)]
        log = (directory / 'terminal.bin').open('xb', buffering=0)
        role['log'] = log
        master, slave = pty.openpty()
        role['pty'] = master
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 32, 110, 0, 0))
            role['proc'] = subprocess.Popen(command, cwd=directory / 'cwd', env=env,
                                            stdin=slave, stdout=slave, stderr=slave,
                                            start_new_session=True)
        finally:
            os.close(slave)
        self.sel.register(master, selectors.EVENT_READ, role)
        self.metrics['launched'] += 1

    def pump(self):
        for key, _ in self.sel.select(0.07):
            try:
                data = os.read(key.fd, 65536)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                data = b''
            if data:
                key.data['log'].write(data)
                require(key.data['log'].tell() <= 8_000_000, 'terminal output limit reached')
            else:
                self.sel.unregister(key.fd)
        for role in self.roles.values():
            if 'proc' not in role:
                continue
            name = role['cfg']['role']
            path = role['dir'] / 'events.jsonl'
            if path.exists():
                complete = path.read_bytes().split(b'\n')[:-1]
                role['events'] = [json.loads(line) for line in complete]
            events = role['events']
            for event in events:
                kind = event['kind']
                if kind == 'model_error':
                    raise RuntimeError(
                        f"{name}: {'quota or rate limit' if event['quota'] else 'model error'}"
                    )
                if kind == 'start':
                    require(event['source'] == 'custom' and event['customType'] == 'agent-mail',
                            f'{name}: unexpected turn source')
                    require(event['model'] == MODEL and event['thinking'] == 'medium',
                            f'{name}: unexpected model or thinking level')
                if kind in ('start', 'settled'):
                    require(
                        event['draft'] and not event.get('aborted'),
                        f'{name}: draft changed or run aborted',
                    )
            require(role['proc'].poll() is None, f'{name}: Pi exited early')
            if (any(e['kind'] == 'ui_ready' for e in events) and not role.get('typed')
                    and not termios.tcgetattr(role['pty'])[3] & termios.ICANON):
                # This is simulated operator typing, not delivery. Never send Enter.
                draft = role['cfg']['draft'].encode('ascii')
                require(os.write(role['pty'], draft) == len(draft), 'short draft write')
                role['typed'] = True

    def check_message(self, source, target, mid, reply_to, value):
        record = self.mail('read', self.run, target, mid)
        expected = dict(id=mid, sender=source, recipient=target, run=self.run, reply_to=reply_to)
        require(
            all(record[key] == field for key, field in expected.items()),
            'invalid receipt routing',
        )
        require(record['body'] == value, 'incorrect challenge or lead summary')

    def execute(self):
        self.run = self.mail('create')
        coordinator = self.mail('enroll', self.run)
        leads = [self.role(name) for name in ('lead-a', 'lead-b')]
        challenges = {}
        for lead in leads:
            lead.update(coordinator=coordinator, summary=str(uuid.uuid4()), leaves=[])
            for slot in (1, 2):
                leaf = self.role(f"{lead['role']}-leaf-{slot}")
                leaf.update(slot=slot, lead=lead['box'], receipt=str(uuid.uuid4()))
                challenges[leaf['role']] = secrets.token_hex(16)
                lead['leaves'].append(leaf)
        require(len(set(challenges.values())) == 4, 'non-distinct challenges')
        deadline = time.monotonic() + self.args.timeout
        for lead in leads:
            self.launch(self.roles[lead['role']])
        verified = set()
        while time.monotonic() < deadline:
            self.pump()
            for lead in leads:
                home = self.roles[lead['role']]
                for leaf in lead['leaves']:
                    child = self.roles[leaf['role']]
                    request = home['dir'] / f"dispatch-{leaf['slot']}"
                    if (
                        'proc' not in child and request.exists()
                        and request.read_text() == leaf['role']
                    ):
                        require(home.get('delivered'), 'dispatch before task delivery')
                        self.launch(child)
                        self.metrics['lead_dispatches'] += 1
            for role in self.roles.values():
                cfg = role['cfg']
                ready = any(e['kind'] == 'draft_ready' for e in role['events'])
                if ready and not role.get('delivered'):
                    if 'leaves' in cfg:
                        self.send(coordinator, cfg['box'], cfg['task'], dict(
                            kind='assign', goal=LEAD_TASK, scope='Your two leaf slots',
                            acceptance='Send both exact challenges by slot',
                        ))
                    else:
                        self.send(cfg['lead'], cfg['box'], cfg['task'], dict(
                            kind='assign', goal=LEAF_TASK, scope=challenges[cfg['role']],
                            acceptance='Return the exact challenge',
                        ))
                    role['delivered'] = True
            for lead in leads:
                summary = lead['summary']
                if (
                    summary in verified
                    or summary not in self.mail('pending', self.run, coordinator)
                ):
                    continue
                values = {}
                for leaf in lead['leaves']:
                    challenge = challenges[leaf['role']]
                    slot = leaf['slot']
                    self.check_message(
                        leaf['box'], lead['box'], leaf['receipt'], leaf['task'],
                        dict(
                            kind='result', outcome=f'Returned challenge for slot {slot}',
                            verification=challenge, remaining='None',
                        ),
                    )
                    values[slot] = challenge
                    self.metrics['receipts_verified'] += 1
                self.check_message(lead['box'], coordinator, summary, lead['task'], dict(
                    kind='result', outcome='Collected both leaf challenges',
                    verification=f'Slot 1: {values[1]}\nSlot 2: {values[2]}', remaining='None',
                ))
                self.mail('ack', self.run, coordinator, summary)
                self.metrics['summaries_verified'] += 1
                verified.add(summary)
            if len(verified) == 2 and all(self.settled(role) for role in self.roles.values()):
                break
        else:
            raise RuntimeError('trial deadline reached')
        session_ids = set()
        for role in self.roles.values():
            cfg = role['cfg']
            session = next(e['session'] for e in role['events'] if e['kind'] == 'ui_ready')
            session_ids.add(session)
            owner = self.root / 'state' / 'agent-mail' / self.run / cfg['box'] / 'owner.json'
            require(
                json.loads(owner.read_text()) == {'harness': 'pi', 'session': session},
                'invalid binding',
            )
            self.metrics['bound_sessions'] += 1
            require(not self.mail('pending', self.run, cfg['box']), 'unacknowledged role mail')
        require(len(session_ids) == 6, 'duplicate native session identity')
        require(not self.mail('pending', self.run, coordinator), 'unacknowledged lead summary')

    @staticmethod
    def settled(role):
        starts = sum(e['kind'] == 'start' for e in role['events'])
        ends = sum(e['kind'] == 'settled' for e in role['events'])
        return starts == ends and starts > 0

    def close(self):
        for role in self.roles.values():
            proc = role.get('proc')
            if proc and proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
        for role in self.roles.values():
            proc = role.get('proc')
            if proc:
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
            if 'pty' in role:
                os.close(role['pty'])
            if 'log' in role:
                role['log'].close()
            if 'auth' in role:
                role['auth'].unlink(missing_ok=True)
            events = role['events']
            self.metrics['custom_turns'] += sum(
                e['kind'] == 'start' and e['source'] == 'custom' for e in events
            )
            self.metrics['user_turns'] += sum(
                e['kind'] == 'start' and e['source'] == 'user' for e in events
            )
            self.metrics['draft_preserved'] += bool(self.settled(role) and all(
                e['draft'] for e in events if e['kind'] in ('start', 'settled')))
        self.sel.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extension', required=True, type=Path, help='Pi mail adapter under test.')
    parser.add_argument(
        '--mail',
        default=os.environ.get('AGENT_MAIL_CLI', str(Path.home() / '.local/bin/agent-mail')),
    )
    parser.add_argument('--auth', type=Path, default=Path.home() / '.pi/agent/auth.json')
    parser.add_argument(
        '--timeout', type=int, default=180, choices=range(15, 241), metavar='15..240',
    )
    args = parser.parse_args()
    args.pi = shutil.which('pi')
    if not all((args.pi, Path(args.mail).is_file(), args.auth.is_file(), args.extension.is_file())):
        parser.error(
            'installed pi, mail CLI with bind, Pi auth.json, and adapter source are required'
        )
    args.mail = str(Path(args.mail).resolve())
    os.umask(0o077)
    trial = Trial(args)
    reason = None
    try:
        trial.execute()
    except RuntimeError as error:
        reason = str(error)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        reason = type(error).__name__
    finally:
        trial.close()
    result = dict(
        status='failed' if reason else 'passed', reason=reason, model=MODEL, thinking='medium',
        adapter_sha256=hashlib.sha256(trial.adapter.read_bytes()).hexdigest(),
        cli_sha256=hashlib.sha256(trial.cli.read_bytes()).hexdigest(),
        **trial.metrics,
    )
    save(trial.root / 'aggregate.json', result)
    print(json.dumps(result, sort_keys=True), flush=True)
    return int(reason is not None)


if __name__ == '__main__':
    raise SystemExit(main())
