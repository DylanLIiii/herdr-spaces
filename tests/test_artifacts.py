import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from herdr_projects import artifacts
from herdr_projects.store import Store, ProjectError


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'ledger')
        self.addCleanup(self.store.close)
        p = self.store.create('one', 'One', 'Research evidence', self.root)
        with self.store.transaction():
            p = self.store.get('one')
            p['main'].update(state='running', generation=1, token='main')
            self.store.save(p)
        self.identity = dict(role='main', project='one', main=p['main']['id'], generation=1, token='main')
        self.counter = 0
        self.apply('todo.add', id='task', title='Research', sourceRef='user')
        self.source = self.root / 'execution'
        self.source.mkdir()
        self.files = []
        for role in ('plan', 'draft', 'cited', 'brief', 'provenance'):
            (self.source / (role + '.md')).write_text(role + ': durable coordination evidence')
            self.files.append(dict(path=role + '.md', role=role))

    def apply(self, op, **fields):
        self.counter += 1
        return self.store.apply('one', self.store.get('one')['revision'], dict(requestId=f'req-{self.counter}', op=op, **fields), self.identity)

    def publish(self, artifact_id='report', **overrides):
        bundle = dict(root=str(self.source), files=self.files, entrypoint='brief.md', workflow='deepresearch',
                      claims=[dict(id='claim-1', text='Durable inbox survives restart', verification='verified',
                                   note='Compared source implementation and tests', limitations=['Single project machine'],
                                   sources=[dict(reference='https://example.org/source', locator='commit:123 / inbox.ts:10', accessedAt='2026-11-11')])])
        bundle.update(overrides.pop('bundle', {}))
        return self.apply('artifact.add', id=artifact_id, workItemId='task', title='Coordination study', kind='research',
                          sourceRef='primary source', bundle=bundle, **overrides)

    def artifact(self, index=0):
        return self.store.get('one')['artifacts'][index]

    def test_published_bundle_survives_execution_cleanup(self):
        self.publish()
        a = self.artifact()
        self.assertEqual('managed', a['storage'])
        self.assertEqual('review', a['status'])
        shutil.rmtree(self.source)
        result = self.store.read_artifact('one', 'report')
        self.assertIn('durable coordination', result['text'])
        self.assertEqual(5, len(result['files']))
        self.assertEqual('claim-1', result['claims'][0]['id'])
        self.apply('artifact.review', id='report', status='accepted', note='Checked key source evidence')
        self.apply('artifact.disposition', id='report', disposition='declined', note='Correct report; approach unsuitable for this deployment')
        a = self.artifact()
        self.assertEqual('accepted', a['status'])
        self.assertEqual('declined', a['disposition'])
        self.assertEqual(['report'], self.store.get('one')['decisions'][0]['artifactRefs'])

    def test_changed_member_blocks_acceptance_and_marks_preview(self):
        self.publish()
        a = self.artifact()
        (Path(a['path']).parent / 'brief.md').write_text('tampered')
        self.assertTrue(self.store.read_artifact('one', 'report')['changed'])
        with self.assertRaisesRegex(ProjectError, 'changed'):
            self.apply('artifact.review', id='report', status='accepted', note='Check')

    def test_changed_manifest_cannot_redirect_preview(self):
        self.publish()
        a = self.artifact(); path = Path(a['path'])
        value = json.loads(path.read_text()); value['entrypoint'] = '../../elsewhere'
        path.write_text(json.dumps(value))
        result = self.store.read_artifact('one', 'report')
        self.assertTrue(result['changed'])
        self.assertEqual('', result['text'])

    def test_interrupted_publication_does_not_register_partial_bundle(self):
        original = shutil.copyfile
        def fail(source, target):
            if str(source).endswith('cited.md'):
                raise OSError('Simulated interrupted copy')
            return original(source, target)
        with patch.object(artifacts.shutil, 'copyfile', side_effect=fail):
            with self.assertRaises(OSError): self.publish()
        self.assertEqual([], self.store.get('one')['artifacts'])
        self.publish()
        artifacts.verify(self.artifact())

    def test_orphan_publication_from_rolled_back_transaction_can_be_retried(self):
        with patch.object(self.store, 'event', side_effect=ProjectError('Transaction interrupted')):
            with self.assertRaises(ProjectError): self.publish()
        self.assertEqual([], self.store.get('one')['artifacts'])
        self.publish()
        artifacts.verify(self.artifact())

    def test_versions_and_followup_are_explicit_and_reused(self):
        self.publish(familyId='study')
        (self.source / 'brief.md').write_text('A revised finding')
        self.publish('report-v2', familyId='study', previousVersionId='report', version='2')
        self.apply('artifact.validity', id='report', validity='superseded', supersededBy='report-v2', note='New evidence')
        self.apply('artifact.followup', id='report-v2', title='Verify revised finding')
        self.apply('artifact.followup', id='report-v2', title='Duplicate request')
        p = self.store.get('one')
        self.assertEqual(2, len(p['items']))
        self.assertEqual(['report-v2'], p['items'][1]['inputArtifactRefs'])
        self.assertEqual('open', p['items'][1]['status'])
        self.assertEqual([], p['runs'])
        self.assertEqual('superseded', p['artifacts'][0]['validity'])
        self.assertIn('brief:', self.store.read_artifact('one', 'report')['text'])

    def test_research_requires_process_and_provenance(self):
        with self.assertRaisesRegex(ProjectError, 'required files'):
            self.publish(bundle=dict(files=[dict(path='brief.md', role='brief')]))
        self.assertEqual([], self.store.get('one')['artifacts'])
        roles = ('summary', 'benchmark', 'iterations', 'changelog', 'brief', 'provenance')
        files = []
        for role in roles:
            name = role + '.txt'
            (self.source / name).write_text('baseline, keep, revert and failed attempts')
            files.append(dict(path=name, role=role))
        self.publish(bundle=dict(files=files, entrypoint='brief.txt', workflow='autoresearch'))
        self.assertEqual('autoresearch', self.artifact()['workflow'])

    def test_traversal_symlink_and_unknown_member_rejected(self):
        outside = self.root / 'outside.md'; outside.write_text('outside')
        (self.source / 'linked.md').symlink_to(outside)
        for name in ('../outside.md', 'linked.md', '/outside.md'):
            with self.assertRaises(ProjectError):
                self.publish(bundle=dict(files=[dict(path=name, role='brief')], entrypoint=name))
        self.publish()
        with self.assertRaises(ProjectError): self.store.read_artifact('one', 'report', '../outside.md')
        with self.assertRaises(ProjectError): self.store.read_artifact('one', 'report', 'unknown.md')

    def test_utf8_pagination_is_complete(self):
        content = '研究报告' * 10000
        (self.source / 'brief.md').write_text(content)
        self.publish()
        output, offset = '', 0
        while True:
            page = self.store.read_artifact('one', 'report', offset=offset)
            output += page['text']
            if page['nextOffset'] is None: break
            offset = page['nextOffset']
        self.assertEqual(content, output)

    def test_search_reads_published_text_without_semantic_index(self):
        self.publish()
        self.assertEqual(['report'], [a['id'] for a in artifacts.search(self.store.get('one'), 'coordination')])
        self.assertEqual([], artifacts.search(self.store.get('one'), 'unrelated'))

    def test_external_data_requires_explicit_verification_and_identity(self):
        external = [dict(location='machine:/datasets/v1', size=10**12, contentId='sha256:abc', status='unverified', note='Not downloaded')]
        self.publish(bundle=dict(external=external))
        self.assertEqual(external, self.store.read_artifact('one', 'report')['external'])


if __name__ == '__main__':
    unittest.main()
