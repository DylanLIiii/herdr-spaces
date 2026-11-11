"""Checkpoint scheduling plus read compatibility for the retired PM inbox.

Core owns delivery and lifecycle notifications. No ordinary-message ack protocol.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

from .store import ProjectError, identifier, now, strings, text, uid

KINDS = ('progress', 'question', 'blocked', 'submitted', 'failed')
WAITING_ON = ('pm', 'user', 'dependency', 'environment')


def timestamp(value, label):
    if value is None:
        return None
    value = text(value, label, 80)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ProjectError(f'{label} must be an ISO 8601 timestamp') from exc
    if parsed.tzinfo is None:
        raise ProjectError(f'{label} must include a timezone')
    return parsed.astimezone(timezone.utc).isoformat()


def progress_fields(request):
    result = {}
    for key in ('phase', 'nextAction'):
        if key in request:
            result[key] = text(request[key], key, 2000)
    if 'checkpointAt' in request:
        result['checkpointAt'] = timestamp(request['checkpointAt'], 'checkpointAt')
    if 'waitingOn' in request:
        value = request['waitingOn']
        if value is not None and value not in WAITING_ON:
            raise ProjectError('waitingOn must be pm, user, dependency, environment or null')
        result['waitingOn'] = value
    if 'question' in request:
        question = request['question']
        if question is not None:
            if not isinstance(question, dict) or question.get('recipient') not in ('pm', 'user'):
                raise ProjectError('question needs a text and recipient (pm or user)')
            question = dict(text=text(question.get('text'), 'question', 2000), recipient=question['recipient'])
            if request['question'].get('recommendation'):
                question['recommendation'] = text(request['question']['recommendation'], 'recommendation', 2000)
            if 'waitingOn' in result and result['waitingOn'] != question['recipient']:
                raise ProjectError('question recipient must match waitingOn')
            result['waitingOn'] = question['recipient']
        result['question'] = question
    return result


def report_fields(request):
    kind = request.get('kind', 'submitted' if request.get('submitted') is True else 'progress')
    if kind not in KINDS:
        raise ProjectError('Unknown report kind')
    if request.get('submitted') is True and kind != 'submitted':
        raise ProjectError('submitted=true conflicts with report kind')
    result = progress_fields(request)
    if kind == 'question' and not result.get('question'):
        raise ProjectError('A question report needs a structured question')
    if kind in ('failed', 'blocked'):
        result.setdefault('waitingOn', 'pm')
    if kind == 'submitted':
        result.update(waitingOn='pm', question=None, checkpointAt=None)
    return dict(kind=kind, **result)


def enqueue(store, project, kind, body, item_id=None, run_id=None, event_id=None):
    """Compatibility name used by business writes; record once, no inbox state."""
    from .collaboration import record
    notify = kind in ('submitted', 'question', 'checkpoint', 'dependency') or bool(body.get('question'))
    # blocked/error/exit are reported by Core. Task facts remain in reports.
    return record(store, project, kind, body, item_id, run_id, event_id,
                  recipients=['pm'] if notify else [], author='checkpoint-service' if kind=='checkpoint' else None)


def inbox(store, project_id, after=0, include_handled=False, limit=100):
    store.get(project_id)
    rows = store.db.execute('SELECT * FROM inbox WHERE project_id=? AND seq>? ' +
                           ('' if include_handled else "AND state!='handled' ") + 'ORDER BY seq LIMIT ?',
                           (project_id, after, limit + 1)).fetchall()
    entries = []
    for row in rows[:limit]:
        data = dict(row)
        data['body'] = json.loads(data['body'])
        data['receipt'] = json.loads(data['receipt']) if data['receipt'] else []
        entries.append(data)
    pending = store.db.execute("SELECT COUNT(*) FROM inbox WHERE project_id=? AND state!='handled'", (project_id,)).fetchone()[0]
    return dict(entries=entries, pending=pending, nextAfter=entries[-1]['seq'] if len(rows) > limit else None)


def inbox_operation(store, project, request):
    ids = strings(request.get('ids'), 'ids', True)
    if len(set(ids)) != len(ids):
        raise ProjectError('Duplicate inbox ids')
    op, generation = request['op'], project['main']['generation']
    note = text(request.get('note'), 'handling note') if op != 'inbox.acknowledge' else None
    for event_id in ids:
        identifier(event_id)
        row = store.db.execute('SELECT * FROM inbox WHERE id=? AND project_id=?', (event_id, project['id'])).fetchone()
        if not row:
            raise ProjectError('Unknown inbox event')
        if row['state'] == 'handled':
            if op == 'inbox.handle':
                continue
            raise ProjectError('This event is already handled')
        if op == 'inbox.handle':
            if row['state'] != 'acknowledged' or row['generation'] != generation:
                raise ProjectError('Read and acknowledge this event in the current PM generation first')
            state = 'handled'
        elif op == 'inbox.retry':
            raise ProjectError('Legacy inbox delivery is retired; inspect the terminal and use hc send for a deliberate follow-up')
        else:
            state = 'acknowledged'
        store.db.execute('UPDATE inbox SET state=?,generation=?,handled_note=?,updated_at=? WHERE id=?',
                         (state, generation, note, now(), event_id))


def handoff(store, project):
    """Retain transport history; the successor reads current business attention."""
    # Do not retarget or replay old messages into a new PM session.
    return None


def due_checkpoints(store, project_id):
    created = []
    with store.transaction():
        p = store.get(project_id)
        for item in p['items']:
            when = item.get('checkpointAt')
            if item['status'] not in ('running', 'blocked') or not when or timestamp(when, 'checkpointAt') > now():
                continue
            event_id = 'checkpoint-' + hashlib.sha256((project_id + ':' + item['id'] + ':' + str(item.get('activeRunId')) + ':' + when).encode()).hexdigest()[:32]
            if store.db.execute('SELECT 1 FROM collaboration WHERE id=?', (event_id,)).fetchone():
                continue
            created.append(event_id)
            enqueue(store, p, 'checkpoint', dict(text='Checkpoint reached; inspect the existing execution before deciding what to do.',
                                               checkpointAt=when, lastProgressAt=item.get('lastProgressAt')),
                    item['id'], item.get('activeRunId'), event_id)
    return created


def notify_pm(store, project_id):
    """Old entry point retained without reviving the former notification queue."""
    return 'retired'


def recover_sends(store):
    # Keep legacy evidence intact; new sends are reserved as uncertain before I/O.
    return None


def service_status(store):
    row = store.db.execute("SELECT body FROM service_state WHERE name='coordinator'").fetchone()
    state = json.loads(row[0]) if row else dict(state='stopped', wanted=False)
    try:
        from .runtime import lock
        with lock(store, 'coordinator-service'):
            state['live'] = False
    except ProjectError:
        state['live'] = True
    return state


def save_service(store, value):
    store.db.execute("INSERT INTO service_state(name,body) VALUES('coordinator',?) ON CONFLICT(name) DO UPDATE SET body=excluded.body",
                     (json.dumps(value, ensure_ascii=False),))


def service_tick(store):
    results = {}
    for row in store.db.execute('SELECT id FROM projects ORDER BY id').fetchall():
        p = store.get(row['id'])
        if not p.get('configuration', {}).get('followup', {}).get('enabled'):
            continue
        try:
            from .collaboration import deliver
            posts = due_checkpoints(store, p['id'])
            receipts = [deliver(store, p['id'], post_id, system=True) for post_id in posts]
            results[p['id']] = dict(state='checked', checkpoints=len(posts), deliveries=receipts)
        except (ProjectError, OSError) as exc:
            results[p['id']] = dict(state='unavailable', error=str(exc))
    return results


def service_run(store, interval=5):
    from .runtime import lock
    stopped = threading.Event()
    previous = {}
    with lock(store, 'coordinator-service'):
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, lambda *_: stopped.set())
        run_id = uid('service')
        with store.transaction():
            save_service(store, dict(state='running', wanted=True, pid=os.getpid(), runId=run_id, startedAt=now()))
        recover_sends(store)
        try:
            backoff = interval
            while not stopped.is_set():
                results = service_tick(store)
                with store.transaction():
                    row = store.db.execute("SELECT body FROM service_state WHERE name='coordinator'").fetchone()
                    current = json.loads(row[0])
                    if not current.get('wanted'):
                        break
                    current.update(lastCheckAt=now(), projects=results)
                    save_service(store, current)
                failing = any(value['state'] == 'unavailable' for value in results.values())
                backoff = min(60, backoff * 2) if failing else interval
                stopped.wait(backoff)
        finally:
            with store.transaction():
                row = store.db.execute("SELECT body FROM service_state WHERE name='coordinator'").fetchone()
                current = json.loads(row[0])
                current.update(state='stopped', wanted=False, stoppedAt=now())
                save_service(store, current)
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    return dict(state='stopped')


def service_start(store):
    from .runtime import ENTRY, lock
    with lock(store, 'coordinator-launch'):
        state = service_status(store)
        if state['live']:
            return state
        # A launch receipt is deliberately not a claim that the process is ready.
        directory = store.home / 'logs'
        directory.mkdir(exist_ok=True)
        with open(directory / 'coordinator.log', 'ab') as output:
            process = subprocess.Popen([sys.executable, str(ENTRY), '--home', str(store.home), 'service', 'run'],
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                       start_new_session=True, close_fds=True)
        return dict(state='starting', pid=process.pid, log=str(directory / 'coordinator.log'))


def service_stop(store):
    with store.transaction():
        row = store.db.execute("SELECT body FROM service_state WHERE name='coordinator'").fetchone()
        value = json.loads(row[0]) if row else dict(state='stopped')
        value['wanted'] = False
        save_service(store, value)
    return dict(state='stop-requested')
