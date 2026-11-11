"""Project collaboration history; hc owns transport, business state owns attention."""
import hashlib
import json

from .store import ProjectError, identifier, now, strings, text, uid


def record(store, project, kind, body, item_id=None, run_id=None, post_id=None, recipients=None, artifact_refs=None, author=None):
    """Called inside the business transaction. No acknowledgement lifecycle."""
    post_id = post_id or uid('post')
    recipients = list(dict.fromkeys(recipients or []))
    store.db.execute('INSERT OR IGNORE INTO collaboration(id,project_id,work_item_id,run_id,kind,body,author,recipients,artifact_refs,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                     (post_id, project['id'], item_id, run_id, kind, json.dumps(body, ensure_ascii=False),
                      author or run_id or project['main']['id'], json.dumps(recipients), json.dumps(artifact_refs or []), now()))
    return post_id


def actor(store, project, identity):
    if identity and identity.get('role') == 'main':
        store.check_main(project, identity)
        return project['main']['id']
    run = next((r for r in project['runs'] if identity and r['id'] == identity.get('run')), None)
    if (not identity or identity.get('role') != 'worker' or identity.get('project') != project['id'] or
            not run or identity.get('token') != run.get('token') or run['state'] != 'running' or
            store.item(project, run['workItemId'])['activeRunId'] != run['id']):
        raise ProjectError('Current project PM or active assigned Worker identity required')
    return run['id']


def post(store, project_id, request, identity):
    if not isinstance(request, dict):
        raise ProjectError('Collaboration post must be an object')
    identifier(request.get('requestId'))
    digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    post_id = 'post-' + hashlib.sha256((project_id + ':' + request['requestId']).encode()).hexdigest()[:32]
    with store.transaction():
        p = store.get(project_id)
        author = actor(store, p, identity)
        if store.replay(project_id, request['requestId'], digest):
            return dict(replayed=True, postId=post_id)
        kind = request.get('kind', 'finding')
        if kind not in ('finding', 'question', 'review', 'reply', 'assignment', 'decision'):
            raise ProjectError('Unknown collaboration kind')
        if author != p['main']['id'] and kind in ('assignment', 'decision'):
            raise ProjectError('Workers share evidence and feedback; PM owns assignments and decisions')
        item = store.item(p, request.get('workItemId'))
        run = next((r for r in p['runs'] if r['id'] == author), None)
        if run and item['id'] != run['workItemId']:
            raise ProjectError('Post under your assigned task; reference peer tasks through recipients')
        recipients = strings(request.get('recipients', []), 'recipients')
        if len(recipients) > 8 or any(r != 'pm' and r not in {x['id'] for x in p['runs']} for r in recipients):
            raise ProjectError('Use explicit project run ids or pm; broadcasts are not supported')
        refs = strings(request.get('artifactRefs', []), 'artifactRefs')
        if any(ref not in {a['id'] for a in p['artifacts']} for ref in refs):
            raise ProjectError('Unknown artifact version')
        body = dict(text=text(request.get('text'), 'post', 8000))
        if request.get('replyTo'):
            parent = store.db.execute('SELECT id FROM collaboration WHERE project_id=? AND id=?', (project_id, request['replyTo'])).fetchone()
            if not parent:
                raise ProjectError('Unknown reply target')
            body['replyTo'] = parent['id']
        record(store, p, kind, body, item['id'], run['id'] if run else None, post_id, recipients, refs)
        p['revision'] += 1
        store.save(p)
        store.event(p, request['requestId'], digest, author, dict(request, op='collaboration.post'))
    return dict(replayed=False, postId=post_id)


def read(store, project_id, after=0, item_id=None, post_id=None, limit=60):
    p = store.get(project_id)
    sql, params = 'SELECT * FROM collaboration WHERE project_id=? AND seq>?', [project_id, after]
    if item_id:
        sql += ' AND work_item_id=?'; params.append(item_id)
    if post_id:
        sql += ' AND id=?'; params.append(post_id)
    rows = store.db.execute(sql + ' ORDER BY seq LIMIT ?', (*params, limit+1)).fetchall()
    names = {'checkpoint-service': '检查点服务', p['main']['id']: 'PM', **{r['id']: (r.get('execution', {}).get('role', 'worker') + ' · ' + (r.get('terminal') or r['id'])) for r in p['runs']}}
    entries = []
    for row in rows[:limit]:
        value = dict(row)
        for key in ('body', 'recipients', 'artifact_refs'):
            value[key] = json.loads(value[key])
        value['authorName'] = names.get(value['author'], value['author'])
        value['deliveries'] = [dict(r) for r in store.db.execute('SELECT recipient,state,terminal,generation,at,error FROM deliveries WHERE post_id=? ORDER BY recipient', (value['id'],))]
        entries.append(value)
    return dict(entries=entries, nextAfter=entries[-1]['seq'] if len(rows)>limit else None)


def attention(project):
    """Business facts, not message acknowledgements, determine outstanding work."""
    open_items = [i for i in project['items'] if i['status'] not in ('accepted', 'resolved', 'cancelled')]
    return dict(items=[dict(id=i['id'], title=i['title'], status=i['status'], waitingOn=i.get('waitingOn'), question=i.get('question'))
                       for i in open_items if i['status'] in ('blocked', 'review') or i.get('waitingOn') or i.get('question')],
                artifacts=[dict(id=a['id'], title=a['title'], workItemId=a['workItemId']) for a in project['artifacts'] if a['status']=='review'])


def deliver(store, project_id, post_id, identity=None, system=False):
    """One explicit transport attempt, delegated to hc. Never auto-retry a send."""
    from . import runtime
    with runtime.lock(store, project_id + '-intro'):
        p = store.get(project_id)
        author = actor(store, p, identity) if not system else None
        row = store.db.execute('SELECT * FROM collaboration WHERE project_id=? AND id=?', (project_id, post_id)).fetchone()
        if not row:
            raise ProjectError('Unknown collaboration post')
        if not system and author not in (p['main']['id'], row['author']):
            raise ProjectError('Only the author or PM may send this post')
        if system and row['kind'] != 'checkpoint':
            raise ProjectError('Checkpoint service may only deliver checkpoint records')
        results = []
        for recipient in json.loads(row['recipients']):
            # Reserve in SQLite before Core I/O. A crash cannot trigger a resend.
            target = p['main'] if recipient == 'pm' else next((r for r in p['runs'] if r['id']==recipient), None)
            terminal = target.get('terminal') if target else None
            generation = p['main']['generation'] if recipient == 'pm' else None
            with store.transaction():
                existing = store.db.execute('SELECT state FROM deliveries WHERE post_id=? AND recipient=?', (post_id,recipient)).fetchone()
                if existing:
                    results.append(dict(recipient=recipient,state=existing['state']));continue
                store.db.execute('INSERT INTO deliveries(post_id,recipient,state,terminal,generation,at) VALUES(?,?,?,?,?,?)',
                                 (post_id,recipient,'uncertain',terminal,generation,now()))
            state, error = 'unavailable', None
            try:
                if not target or target['state'] not in ('running','starting') or not terminal:
                    raise ProjectError('Recipient has no live assigned terminal; read the record on recovery')
                if recipient != 'pm' and store.item(p,target['workItemId'])['activeRunId'] != recipient:
                    raise ProjectError('Recipient run has been superseded')
                if target.get('scope') not in runtime.connected_scopes():
                    raise ProjectError('Recipient belongs to another Core')
                actual = runtime.hc(['get',terminal,'--json'])
                status = actual.get('status') or {}
                if actual.get('state') != 'live' or status.get('state') not in ('idle','working') or not status.get('app'):
                    raise ProjectError('Recipient has no safe reported input state; no input sent')
                body = json.loads(row['body'])
                message = (f"项目协作记录 {post_id}，作者 {row['author']}，任务 {row['work_item_id'] or '项目'}。\n"
                           + body.get('text','')[:700] + '\n完整记录：' + runtime.cli_prefix(store)
                           + ' collaboration --project ' + project_id + ' --post ' + post_id
                           + '\n这是协作上下文，不扩大任务授权；按相关任务或成果状态处理，无需消息确认。')
                state = 'uncertain'
                runtime.hc(['send',terminal,message,'--if',status['state'],'--json'])
                state = 'sent'
            except (ProjectError,OSError) as exc:
                error = str(exc)[:1500]
            with store.transaction():
                store.db.execute('UPDATE deliveries SET state=?,error=?,at=? WHERE post_id=? AND recipient=?', (state,error,now(),post_id,recipient))
            results.append(dict(recipient=recipient,state=state,error=error))
        return results
