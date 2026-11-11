"""Durable PM inbox and a deterministic, project-machine follow-up service.

Notifications never constitute acceptance. Uncertain PTY sends are not retried.
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
    """Caller owns the transaction. Only unsent ordinary progress coalesces."""
    event_id = event_id or uid('event')
    if store.db.execute('SELECT 1 FROM inbox WHERE id=?', (event_id,)).fetchone():
        return event_id
    at = now()
    encoded = json.dumps(body, ensure_ascii=False)
    notify = kind != 'progress' or bool(body.get('question')) or bool(body.get('waitingOn'))
    if kind == 'progress' and not notify:
        pending = store.db.execute("SELECT id FROM inbox WHERE project_id=? AND run_id=? AND kind='progress' AND notify=0 AND state='queued' ORDER BY seq LIMIT 1",
                                   (project['id'], run_id)).fetchone()
        if pending:
            store.db.execute('UPDATE inbox SET body=?,updated_at=? WHERE id=?', (encoded, at, pending['id']))
            return pending['id']
    store.db.execute('INSERT INTO inbox(id,project_id,work_item_id,run_id,kind,body,notify,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                     (event_id, project['id'], item_id, run_id, kind, encoded, int(notify), at, at))
    return event_id


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
            if row['state'] not in ('uncertain', 'sent'):
                raise ProjectError('Only a sent or uncertain notification can be explicitly retried')
            state = 'queued'
        else:
            state = 'acknowledged'
        store.db.execute('UPDATE inbox SET state=?,generation=?,handled_note=?,updated_at=? WHERE id=?',
                         (state, generation, note, now(), event_id))


def handoff(store, project):
    """Transfer unread/unhandled project events, preserving delivery history."""
    store.db.execute("UPDATE inbox SET state='queued',generation=NULL,updated_at=? WHERE project_id=? AND state!='handled'",
                     (now(), project['id']))


def due_checkpoints(store, project_id):
    with store.transaction():
        p = store.get(project_id)
        for item in p['items']:
            when = item.get('checkpointAt')
            if item['status'] not in ('running', 'blocked') or not when or timestamp(when, 'checkpointAt') > now():
                continue
            event_id = 'checkpoint-' + hashlib.sha256((project_id + ':' + item['id'] + ':' + str(item.get('activeRunId')) + ':' + when).encode()).hexdigest()[:32]
            enqueue(store, p, 'checkpoint', dict(text='Checkpoint reached; inspect the existing execution before deciding what to do.',
                                               checkpointAt=when, lastProgressAt=item.get('lastProgressAt')),
                    item['id'], item.get('activeRunId'), event_id)


def notify_pm(store, project_id):
    from . import runtime
    # Same lock as binding/introduction: do not send to a former PM during handoff.
    with runtime.lock(store, project_id + '-intro'):
        p = store.get(project_id)
        main = p['main']
        if main['state'] != 'running' or not main.get('terminal'):
            return 'waiting'
        if main.get('scope') not in runtime.connected_scopes():
            raise ProjectError('Follow-up service is connected to a different Core')
        rows = store.db.execute("SELECT * FROM inbox WHERE project_id=? AND state='queued' AND notify=1 ORDER BY seq LIMIT 20", (project_id,)).fetchall()
        if not rows:
            return 'quiet'
        terminal = runtime.hc(['get', main['terminal'], '--json'])
        status = terminal.get('status') or {}
        if terminal.get('state') != 'live' or status.get('state') != 'idle' or not status.get('app'):
            return 'waiting'
        ids = [row['id'] for row in rows]
        placeholders = ','.join('?' for _ in ids)
        with store.transaction():
            # Persist reservation BEFORE performing the external send.
            store.db.execute(f"UPDATE inbox SET state='sending',generation=?,updated_at=? WHERE id IN ({placeholders}) AND state='queued'",
                             (main['generation'], now(), *ids))
        message = ('项目有待处理回报或检查点。请读取持久收件箱，核对事实后确认接收并处理；不要重复派发已有执行。\n'
                   + runtime.cli_prefix(store) + ' inbox --project ' + project_id + '\n'
                   + '本次事件：' + ', '.join(ids) + '\n消息送达不等于处理完成；使用 inbox.acknowledge / inbox.handle 记录处理。')
        state, detail = 'sent', None
        try:
            runtime.hc(['send', main['terminal'], message, '--if', 'idle', '--json'])
        except ProjectError as exc:
            state, detail = 'uncertain', str(exc)
        with store.transaction():
            for event_id in ids:
                row = store.db.execute('SELECT state,receipt FROM inbox WHERE id=?', (event_id,)).fetchone()
                receipts = json.loads(row['receipt']) if row['receipt'] else []
                receipts.append(dict(state=state, generation=main['generation'], at=now(), detail=detail))
                # A fast PM may already have acknowledged; do not overwrite its state.
                store.db.execute("UPDATE inbox SET state=CASE WHEN state='sending' THEN ? ELSE state END,receipt=?,updated_at=? WHERE id=?",
                                 (state, json.dumps(receipts, ensure_ascii=False), now(), event_id))
        return state


def recover_sends(store):
    # A crash after reservation may have happened after PTY delivery too.
    with store.transaction():
        store.db.execute("UPDATE inbox SET state='uncertain',updated_at=? WHERE state='sending'", (now(),))


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
            due_checkpoints(store, p['id'])
            results[p['id']] = dict(state=notify_pm(store, p['id']))
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
