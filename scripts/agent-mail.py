#!/usr/bin/env python3
"""Store same-user agent mail outside worktrees. All cooperating clients use this CLI."""

import argparse
import fcntl
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path


MAIL_FIELDS = {
    'assign': ('goal', 'scope', 'acceptance'),
    'blocked': ('problem', 'evidence', 'help'),
    'needs-decision': ('question', 'recommendation', 'tradeoff'),
    'decision': ('action', 'limits'),
    'result': ('outcome', 'verification', 'remaining'),
}


def parse_body(raw, reply_to):
    def unique_fields(pairs):
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError('duplicate message fields')
        return fields

    body = json.loads(raw, object_pairs_hook=unique_fields)
    kind = body.get('kind') if isinstance(body, dict) else None
    if not isinstance(kind, str) or kind not in MAIL_FIELDS:
        raise ValueError('expected a JSON object with kind: ' + ', '.join(MAIL_FIELDS))
    fields = MAIL_FIELDS[kind]
    if set(body) != {'kind', *fields} or any(
            not isinstance(body[key], str) or not body[key].strip() for key in fields):
        raise ValueError(
            f'{kind} requires exactly these nonempty text fields: ' + ', '.join(fields)
        )
    if kind in ('decision', 'result') and not reply_to:
        raise ValueError(f'{kind} requires --reply-to')
    if kind == 'assign' and reply_to:
        raise ValueError('assign starts a new request; omit --reply-to')
    return body


def identifier(value):
    if str(uuid.UUID(value)) != value:
        raise ValueError('expected a canonical UUID')
    return value


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(path, data, staging=None):
    staging = staging or path.parent
    with tempfile.NamedTemporaryFile(dir=staging, prefix='.new-', delete=False) as out:
        tmp = Path(out.name)
        try:
            out.write(json.dumps(data, ensure_ascii=False).encode())
            out.flush()
            os.fsync(out.fileno())
            os.replace(tmp, path)
            sync_dir(path.parent)
            if staging != path.parent:
                sync_dir(staging)
        finally:
            tmp.unlink(missing_ok=True)


def pending(box):
    ids = []
    for path in (box / 'pending').glob('*.json'):
        try:
            ids.append(identifier(path.stem))
        except ValueError:
            continue
    return sorted(ids)


def native_identity(args):
    harness, session = args.harness, args.session_id
    if harness is None and session is None:
        for name, env in (('pi', 'PI_SESSION_ID'), ('claude', 'AGENT_MAIL_CLAUDE_SESSION_ID')):
            if os.environ.get(env):
                harness, session = name, os.environ[env]
                break
    if not (harness and session):
        raise ValueError('use a native agent shell or pass both --harness and --session-id')
    return {'harness': harness, 'session': identifier(session)}


def bind(box, claim):
    owner = box / 'owner.json'
    if owner.exists():
        if json.loads(owner.read_text()) != claim:
            raise ValueError('recipient already bound to another session')
    else:
        publish(owner, claim)


def descriptor(root, run, recipient):
    folder = root / run
    inbox = folder / recipient / 'pending'
    if (folder / 'closed').exists() or not inbox.is_dir():
        return None
    return {'run': run, 'recipient': recipient, 'inbox': str(inbox)}


def session_command(root, args):
    claim = native_identity(args)
    key = root / '.sessions' / f"{claim['harness']}-{claim['session']}.json"
    current = None
    if key.is_file():
        saved = json.loads(key.read_text())
        run, recipient = identifier(saved['run']), identifier(saved['recipient'])
        current = descriptor(root, run, recipient)
        if current and json.loads((root / run / recipient / 'owner.json').read_text()) != claim:
            raise ValueError('session index does not match mailbox owner')
    if args.command == 'session':
        return {**claim, 'mailbox': current}
    if current:
        if current['run'] != args.run or args.recipient not in (None, current['recipient']):
            raise ValueError('session already enrolled in an open run')
        return current
    folder = root / args.run
    if not folder.is_dir() or (folder / 'closed').exists():
        raise ValueError('unknown or closed run')
    recipient = args.recipient
    if recipient is None:
        # Recover the same mailbox if interrupted before publishing the index.
        recipient = str(uuid.uuid5(uuid.UUID(args.run), key.stem))
        box = folder / recipient
        box.mkdir(exist_ok=True)
        for state in ('handled', 'pending'):
            (box / state).mkdir(exist_ok=True)
        sync_dir(box)
        sync_dir(folder)
    info = descriptor(root, args.run, recipient)
    if not info:
        raise ValueError('unknown recipient')
    bind(folder / recipient, claim)
    key.parent.mkdir(exist_ok=True)
    sync_dir(root)
    publish(key, {'run': args.run, 'recipient': recipient})
    return info


def execute(root, args):
    cmd = args.command
    if cmd in ('session', 'invite'):
        return session_command(root, args)
    if cmd == 'observe':
        info = descriptor(root, args.run, args.recipient)
        if info is not None and args.scan:
            info['pending'] = pending(Path(info['inbox']).parent)
        return info
    if cmd == 'create':
        run = root / str(uuid.uuid4())
        run.mkdir()
        sync_dir(root)
        return run.name
    if cmd == 'gc':
        removed = []
        for run in root.iterdir():
            if not (run / 'closed').is_file():
                continue
            if any(run.glob('*/pending/*.json')):
                continue
            identifier(run.name)
            shutil.rmtree(run)
            removed.append(run.name)
        return removed
    run = root / args.run
    if not run.is_dir():
        raise ValueError('unknown run')
    if cmd == 'close':
        if not (run / 'closed').exists():
            publish(run / 'closed', True, staging=root)
        return 'closed'
    if cmd in ('enroll', 'send', 'bind') and (run / 'closed').exists():
        raise ValueError('run closed')
    if cmd == 'enroll':
        box = run / str(uuid.uuid4())
        box.mkdir()
        for state in ('handled', 'pending'):
            (box / state).mkdir()
        sync_dir(box)
        sync_dir(run)
        return box.name
    box = run / args.recipient
    if not (box / 'pending').is_dir():
        raise ValueError('unknown recipient')
    if cmd == 'bind':
        claim = {'harness': args.harness, 'session': args.session}
        bind(box, claim)
        return 'bound'
    if cmd == 'pending':
        return pending(box)
    entry = box / 'pending' / (args.id + '.json')
    handled = box / 'handled' / entry.name
    if cmd == 'send':
        if not (run / args.sender / 'pending').is_dir():
            raise ValueError('unknown sender')
        record = dict(id=args.id, sender=args.sender, recipient=args.recipient,
                      run=args.run, body=args.body, reply_to=args.reply_to)
        existing = handled if handled.exists() else entry
        if existing.exists():
            if json.loads(existing.read_text()) != record:
                raise ValueError('message ID conflict')
        else:
            # The inbox watch sees the final rename, not temporary writes.
            publish(entry, record, staging=box)
        return args.id
    if cmd == 'read':
        return json.loads((entry if entry.exists() else handled).read_text())
    if not handled.exists():
        entry.rename(handled)
        sync_dir(handled.parent)
        sync_dir(entry.parent)
    return 'handled'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for cmd in ('create', 'enroll', 'bind', 'pending', 'send', 'read', 'ack', 'close', 'gc'):
        sub = subs.add_parser(cmd)
        if cmd not in ('create', 'gc'):
            sub.add_argument('run', type=identifier)
        if cmd in ('bind', 'pending', 'send', 'read', 'ack'):
            sub.add_argument('recipient', type=identifier)
        if cmd == 'bind':
            sub.add_argument('harness', choices=('pi', 'claude'))
            sub.add_argument('session')
        if cmd in ('send', 'read', 'ack'):
            sub.add_argument('id', type=identifier)
        if cmd == 'send':
            sub.add_argument('sender', type=identifier)
            sub.add_argument('--reply-to', type=identifier)
    for command, help_text in (
        ('session', 'show native session identity and active mailbox'),
        ('invite', 'enroll a native session in an open run'),
    ):
        sub = subs.add_parser(command, help=help_text)
        sub.add_argument('--harness', choices=('pi', 'claude'))
        sub.add_argument('--session-id', type=identifier)
        if command == 'invite':
            sub.add_argument('run', type=identifier)
            sub.add_argument('--recipient', type=identifier, help='bind an existing recipient')
    observe = subs.add_parser('observe', help='resolve an open mailbox for a local watcher')
    observe.add_argument('run', type=identifier)
    observe.add_argument('recipient', type=identifier)
    observe.add_argument('--scan', action='store_true')
    launch = subs.add_parser('launch', help='start an enrolled interactive agent (legacy)')
    launch.add_argument('--run', type=identifier, help='join this open run instead of creating one')
    launch.add_argument('harness', choices=('pi', 'claude'))
    launch.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == 'send':
        args.body = sys.stdin.read(65537)
        if len(args.body) > 65536:
            parser.exit(1, 'message exceeds 65536 characters\n')
        try:
            args.body = parse_body(args.body, args.reply_to)
        except (ValueError, RecursionError) as error:
            parser.exit(1, f'agent-mail: invalid message: {error}\n')
    os.umask(0o077)
    root = Path(os.getenv('XDG_STATE_HOME') or Path.home() / '.local/state') / 'agent-mail'
    if not root.is_absolute():
        parser.exit(1, 'absolute state root required\n')
    try:
        if args.command in ('session', 'observe') and not root.exists() and not root.is_symlink():
            print(json.dumps(execute(root, args)))
            return
        root.mkdir(parents=True, exist_ok=True)
        info = root.stat()
        if root.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('private, user-owned state directory required')
        with (root / '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.command != 'launch':
                print(json.dumps(execute(root, args)))
                return
            run = args.run or execute(root, argparse.Namespace(command='create'))
            recipient = execute(root, argparse.Namespace(command='enroll', run=run))
        # Never retain the store lock across an interactive session.
        print(f'Agent mail: run={run} recipient={recipient}', file=sys.stderr, flush=True)
        os.execvpe(
            args.harness, [args.harness, *args.arguments],
            dict(os.environ, AGENT_MAIL_RUN=run, AGENT_MAIL_RECIPIENT=recipient),
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'agent-mail: {error}\n')


if __name__ == '__main__':
    main()
