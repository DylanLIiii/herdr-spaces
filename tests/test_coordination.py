import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from herdr_projects import coordination as c, collaboration as board, runtime, onboarding
from herdr_projects.store import Store, ProjectError


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=Store(self.root/'ledger');self.addCleanup(self.store.close)
        p=self.store.create('one','One','Goal',self.root)
        self.main=dict(role='main',project='one',main=p['main']['id'],generation=1,token='main-test')
        with self.store.transaction():
            p=self.store.get('one');p['main'].update(state='running',generation=1,terminal='t1',scope='core:test',token='main-test');self.store.save(p)
        self.counter=0
        for task,run,terminal in [('work','run-one','t2'),('peer','run-peer','t3')]:
            self.apply('todo.add',id=task,title=task,sourceRef='user')
            self.apply('todo.promote',id=task,brief='scope',acceptanceCriteria=['evidence'])
            with self.store.transaction():
                p=self.store.get('one');p['runs'].append(dict(id=run,workItemId=task,state='running',token=run,terminal=terminal,scope='core:test',reports=[]));self.store.item(p,task).update(status='running',activeRunId=run);self.store.save(p)
        self.worker=dict(role='worker',project='one',run='run-one',token='run-one')

    def apply(self,op,**kw):
        self.counter+=1
        return self.store.apply('one',self.store.get('one')['revision'],dict(requestId='r-'+str(self.counter),op=op,**kw),self.main)

    def report(self,id='report',**kw):
        return self.store.report('one',dict(requestId=id,text='progress',**kw),self.worker)

    def post(self,**kw):
        return board.post(self.store,'one',dict(requestId='post-1',workItemId='work',kind='review',text='Check this finding',recipients=['run-peer'],**kw),self.worker)

    def terminal(self,args):
        return dict(address=args[1],state='live',status=dict(state='working',app='opencode')) if args[0]=='get' else dict(ok=True)

    def test_migration_keeps_schema2_inbox_and_identity(self):
        self.store.db.execute("INSERT INTO inbox(id,project_id,kind,body,state,notify,created_at,updated_at) VALUES('old','one','submitted','{}','acknowledged',1,'old','old')")
        old=self.store.get('one');self.store.db.execute('PRAGMA user_version=2')
        other=Store(self.store.home)
        try:
            self.assertEqual(old,other.get('one'))
            self.assertEqual('acknowledged',other.db.execute('SELECT state FROM inbox').fetchone()[0])
            self.assertEqual(3,other.db.execute('PRAGMA user_version').fetchone()[0])
            other.db.execute('PRAGMA user_version=99')
            with self.assertRaises(ProjectError):Store(self.store.home)
        finally:other.close()

    def test_reports_record_once_without_new_inbox(self):
        self.report(kind='submitted');self.assertTrue(self.report(kind='submitted')['replayed'])
        self.assertEqual(1,len(self.store.get('one')['runs'][0]['reports']))
        self.assertEqual(1,len([e for e in board.read(self.store,'one')['entries'] if e['kind']=='submitted']))
        self.assertEqual([],c.inbox(self.store,'one')['entries'])
        self.assertEqual('review',board.attention(self.store.get('one'))['items'][0]['status'])

    def test_invalid_report_rolls_back_record(self):
        before=len(board.read(self.store,'one')['entries'])
        with self.assertRaises(OSError):self.report(kind='submitted',artifacts=[dict(id='ev',path=str(self.root/'missing'))])
        self.assertEqual(before,len(board.read(self.store,'one')['entries']))
        self.assertEqual([],self.store.get('one')['runs'][0]['reports'])

    def test_structured_questions_and_submission(self):
        self.report(kind='question',question=dict(text='Which scope?',recipient='user'))
        self.assertEqual('user',board.attention(self.store.get('one'))['items'][0]['waitingOn'])
        self.report('second',kind='submitted')
        item=self.store.item(self.store.get('one'),'work');self.assertIsNone(item['question']);self.assertEqual('review',item['status'])

    def test_invalid_progress_rejected(self):
        for values in [dict(kind='question'),dict(waitingOn='anybody'),dict(checkpointAt='tomorrow'),dict(checkpointAt='2030-01-01T00:00:00'),dict(kind='progress',submitted=True)]:
            with self.assertRaises(ProjectError):self.report(**values)

    def test_checkpoints_are_once_and_do_not_reschedule(self):
        self.report(checkpointAt='2020-01-01T00:00:00Z')
        self.assertEqual(1,len(c.due_checkpoints(self.store,'one')))
        self.assertEqual([],c.due_checkpoints(self.store,'one'))
        self.assertEqual(2,len(self.store.get('one')['runs']))

    @patch.object(runtime,'connected_scopes',return_value=['core:test'])
    def test_direct_peer_delivery_uses_hc_with_guard_and_deduplicates(self,scopes):
        post=self.post()['postId']
        with patch.object(runtime,'hc',side_effect=self.terminal) as hc:
            self.assertEqual('sent',board.deliver(self.store,'one',post,self.worker)[0]['state'])
            self.assertEqual('sent',board.deliver(self.store,'one',post,self.worker)[0]['state'])
            sends=[v.args[0] for v in hc.call_args_list if v.args[0][0]=='send']
            self.assertEqual(1,len(sends));self.assertEqual('t3',sends[0][1]);self.assertIn('--if',sends[0]);self.assertNotIn('--force',sends[0])
        self.assertEqual('running',self.store.item(self.store.get('one'),'peer')['status'])

    @patch.object(runtime,'connected_scopes',return_value=['core:test'])
    def test_unknown_delivery_and_blocked_terminal_never_auto_retry(self,scopes):
        post=self.post()['postId']
        def uncertain(args):
            if args[0]=='send':raise ProjectError('response lost')
            return self.terminal(args)
        with patch.object(runtime,'hc',side_effect=uncertain):self.assertEqual('uncertain',board.deliver(self.store,'one',post,self.worker)[0]['state'])
        with patch.object(runtime,'hc') as hc:
            self.assertEqual('uncertain',board.deliver(self.store,'one',post,self.worker)[0]['state']);hc.assert_not_called()
        post=board.post(self.store,'one',dict(requestId='q2',workItemId='work',text='Question',recipients=['pm']),self.worker)['postId']
        with patch.object(runtime,'hc',return_value=dict(state='live',status=dict(state='blocked',app='pi'))) as hc:
            self.assertEqual('unavailable',board.deliver(self.store,'one',post,self.worker)[0]['state']);self.assertEqual(1,hc.call_count)

    def test_workers_cannot_assign_accept_or_post_as_peers(self):
        for override in [dict(kind='assignment'),dict(workItemId='peer'),dict(recipients=['all']),dict(artifactRefs=['missing'])]:
            request=dict(requestId='bad',workItemId='work',text='Text',recipients=['pm']);request.update(override)
            with self.assertRaises(ProjectError):board.post(self.store,'one',request,self.worker)
        request=dict(requestId='valid',workItemId='work',text='Fact',recipients=['pm'])
        first=board.post(self.store,'one',request,self.worker)
        self.assertEqual(first['postId'],board.post(self.store,'one',request,self.worker)['postId'])
        with self.assertRaises(ProjectError):board.post(self.store,'one',dict(request,text='changed'),self.worker)

    @patch.object(runtime,'connected_scopes',return_value=['core:test'])
    def test_handoff_keeps_history_and_new_pm_derives_attention(self,scopes):
        self.report(kind='submitted');history=board.read(self.store,'one')
        with patch.object(runtime,'hc',side_effect=self.terminal):onboarding.bind(self.store,'t4','core:test','one',replace_generation=1)
        self.assertEqual(history,board.read(self.store,'one'))
        self.assertEqual('review',board.attention(self.store.get('one'))['items'][0]['status'])
        with self.assertRaises(ProjectError):self.apply('project.update',summary='Old PM')
        self.assertEqual([],c.inbox(self.store,'one')['entries'])

    def test_service_only_runs_due_checkpoints_not_generic_reports(self):
        self.report(kind='submitted')
        with self.store.transaction():
            p=self.store.get('one');p['configuration']['followup']['enabled']=True;self.store.save(p)
        with patch.object(runtime,'hc') as hc:
            result=c.service_tick(self.store);self.assertEqual(0,result['one']['checkpoints']);hc.assert_not_called()

    def test_closed_business_state_leaves_history_without_pending_messages(self):
        self.report(kind='question',question=dict(text='Q',recipient='pm'))
        self.apply('item.update',id='work',waitingOn=None,question=None)
        self.assertEqual([],board.attention(self.store.get('one'))['items'])
        self.assertTrue(any(e['kind']=='question' for e in board.read(self.store,'one')['entries']))


if __name__=='__main__':unittest.main()
