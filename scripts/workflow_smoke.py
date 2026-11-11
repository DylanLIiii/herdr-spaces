#!/usr/bin/env python3
"""Real isolated Core/PM/service/worker lifecycle and optional native renders.

Uses deterministic fixture programs, never a model. Runs on macOS or Linux;
Linux GUI verification uses Xvfb. No pointer/keyboard automation on a real display.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.install import install
from herdr_projects.store import Store, ProjectError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', help='Optional herdr-app binary for native screenshots')
    parser.add_argument('--output', default=str(ROOT / 'docs/coordination'))
    args = parser.parse_args()
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='hps-loop-', dir='/tmp')).resolve()
    env = {k:v for k,v in os.environ.items() if not k.startswith(('HC_', 'HERDR_PROJECT', 'HERDR_APP'))}
    env.update(HERDR_APP_HOME=str(scratch / 'app'), HC_SESSION='spaces-loop', HC_SOCKET=str(scratch / 'core.sock'),
               XDG_CONFIG_HOME=str(scratch / 'config'), XDG_DATA_HOME=str(scratch / 'data'),
               XDG_STATE_HOME=str(scratch / 'state'), XDG_CACHE_HOME=str(scratch / 'cache'))
    ledger = scratch / 'ledger'
    checks, window, display = [], None, None
    previous_frontmost = None
    if args.app and sys.platform == 'darwin':
        current = subprocess.run(['osascript','-l','JavaScript','-e',"ObjC.import('AppKit'); $.NSWorkspace.sharedWorkspace.frontmostApplication.processIdentifier"], capture_output=True, text=True)
        if current.returncode == 0 and current.stdout.strip().isdigit():
            previous_frontmost = int(current.stdout.strip())
    project = [sys.executable, str(ROOT / 'project.py'), '--home', str(ledger)]
    def call(argv, ok=True, timeout=30):
        if len(argv)>1 and argv[1]=='shot' and window and sys.platform=='darwin':
            # macOS may retain an old GPU frame for an inactive test window.
            # Activate only our own process; never automate the person's input.
            subprocess.run(['osascript','-l','JavaScript','-e',
                "ObjC.import('AppKit'); $.NSRunningApplication.runningApplicationWithProcessIdentifier("+str(window.pid)+").activateWithOptions(2)"],capture_output=True,text=True,timeout=10)
            time.sleep(.6)
        result = subprocess.run(argv, env=env, text=True, capture_output=True, timeout=timeout)
        if ok and result.returncode:
            raise RuntimeError(f'{argv[:3]}: {result.stderr or result.stdout}')
        return result
    def jcall(argv, **kw): return json.loads(call(argv, **kw).stdout)
    def wait_for(fn, label, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if (scratch / 'error.json').exists():
                raise RuntimeError((scratch / 'error.json').read_text())
            result = fn()
            if result: return result
            time.sleep(.12)
        raise RuntimeError('Timed out: ' + label)
    def check(label, condition):
        if not condition: raise AssertionError(label)
        checks.append(label); print('PASS ' + label, flush=True)
    def launch(name):
        result = jcall(['hc', 'run', '--json', '--bg', '--keep', '--no-parent', '--no-notify', '--cwd', str(ROOT),
            '--label', 'herdr.space=spaces-integration', '--label', 'herdr.tab=' + name,
            '--', sys.executable, str(ROOT / 'tests/workflow_fixture.py'), str(scratch)])
        terminal = result['address']
        wait_for(lambda: (jcall(['hc','get',terminal]).get('status') or {}).get('state') == 'idle', 'fixture idle')
        return terminal
    def send(terminal, action):
        call(['hc','send',terminal,'fixture:' + action,'--if','idle','--json'])
    def p(): return jcall(project + ['show','--project','research-loop'])
    try:
        installed = install(env['HERDR_APP_HOME'], scratch / 'bin', ledger,
                            registry_dir=Path(env['XDG_CONFIG_HOME']) / 'herdr-spaces/runtimes')
        core = jcall(['hc','server','start','--json'])
        scope = 'core:' + core['core']['id']
        first = launch('pm-first')
        bound = jcall(project + ['bind','--project','research-loop','--terminal',first,'--core-scope',scope,
                     '--name','Herdr Spaces · 研究闭环','--goal','验证 PM 配置、持续跟进和研究成果复用','--cwd',str(ROOT)])
        check('Binding does not imply configuration consent', bound['project']['setup']['state'] == 'pending' and bound['project']['setup']['consentAt'] is None)
        notice = jcall(project + ['introduce','--project','research-loop','--core-scope',scope,'--generation','1'])
        check('PM introduction contains setup Skill activation', notice['state'] == 'sent' and '--setup' in notice['message'])
        send(first, 'setup')
        wait_for(lambda: (scratch / 'configured.json').exists(), 'PM configuration flow')
        check('PM resumes deferred setup and preserves answers', p()['setup']['answers']['workflow'] == 'mixed')
        check('Fixture checks cannot claim model readiness', p()['setup']['state'] == 'verifying')
        jcall(project + ['service','start'])
        wait_for(lambda: jcall(project + ['service','status']).get('live'), 'service started')
        jcall(project + ['service','stop'])
        wait_for(lambda: not jcall(project + ['service','status']).get('live'), 'service stopped')
        send(first, 'research')
        wait_for(lambda: (scratch / 'worker-submitted.json').exists(), 'research bundle submission')
        wait_for(lambda: p()['runs'][0]['state'] == 'exited', 'worker exit')
        check('Worker exit leaves research awaiting PM review', p()['items'][0]['status'] == 'review')
        pending = jcall(project + ['collaboration','--project','research-loop'])
        check('Reports persist independently of the checkpoint service', any(e['kind']=='submitted' for e in pending['entries']))
        wait_for(lambda: (scratch / 'notification.json').exists(), 'native hc report notification')
        check('hc notification reaches PM while service is stopped', json.loads((scratch / 'notification.json').read_text())['terminal'] == first)
        check('Delivery is not business acceptance', any(d['state']=='sent' for e in pending['entries'] for d in e['deliveries']) and p()['items'][0]['status']=='review')
        worker_record=p()['runs'][0]
        native=jcall(['hc','get',worker_record['terminal'],'--json'])
        check('Worker is a native Core child without a forced tab', native['parent']==first and not native['labels'].get('herdr.tab'))
        check('Core child lifecycle notifications remain enabled', native['notify'] is True)
        jcall(project + ['service','start'])
        with_store = Store(ledger)
        old = with_store.get('research-loop')
        old_identity = dict(project='research-loop', main=old['main']['id'], role='main', generation=old['main']['generation'], token=old['main']['token'])
        second = launch('pm-successor')
        jcall(project + ['bind','--project','research-loop','--terminal',second,'--core-scope',scope,'--replace-generation','1'])
        current = p()
        jcall(project + ['introduce','--project','research-loop','--core-scope',scope,'--generation','2'])
        check('Handoff preserves stable identity, configuration and active history', current['main']['id']==old['main']['id'] and current['main']['generation']==2 and all(current['setup'].get(k)==v for k,v in old['setup'].items()) and len(current['runs'])==1)
        try:
            with_store.check_main(with_store.get('research-loop'), old_identity)
            old_rejected = False
        except ProjectError:
            old_rejected = True
        with_store.close()
        check('Former PM cannot write after handoff', old_rejected)
        wait_for(lambda: (jcall(['hc','get',second]).get('status') or {}).get('state')=='idle', 'successor idle')
        send(second, 'review')
        wait_for(lambda: (scratch / 'reviewed.json').exists(), 'successor review')
        current = p()
        check('PM review produces acceptance, decision and linked follow-up', current['items'][0]['status']=='accepted' and current['artifacts'][0]['disposition']=='adopted' and current['items'][1]['inputArtifactRefs']==['research-brief'])
        check('Follow-up creation does not automatically launch work', len(current['runs'])==1 and current['items'][1]['status']=='open')
        work = Path(json.loads((scratch / 'worker-submitted.json').read_text())['outputRoot'])
        shutil.rmtree(work)
        reading = jcall(project + ['read','--project','research-loop','--artifact','research-brief','--core-scope',scope,'--ledger-home',str(ledger)])
        check('Published research survives execution directory cleanup', '可靠协调' in reading['text'] and not reading['changed'] and len(reading['files'])==5)
        check('Research is searchable by conclusion', len(jcall(project+['search','--project','research-loop','--query','持久化'])['artifacts'])==1)
        service = jcall(project + ['service','status'])
        os.kill(service['pid'], signal.SIGKILL)
        wait_for(lambda: not jcall(project+['service','status']).get('live'), 'crashed service lock released')
        jcall(project+['service','start'])
        wait_for(lambda: jcall(project+['service','status']).get('live'), 'service crash recovery')
        check('Service crash recovery does not create duplicate runs', len(p()['runs'])==1)
        if args.app:
            app = str(Path(args.app).resolve())
            apphome = Path(env['HERDR_APP_HOME'])
            (apphome/'shared.json').write_text(json.dumps({'frame.welcomed':'skipped'}))
            (apphome/'settings.json').write_text(json.dumps({'appearance':'dark'}))
            if sys.platform.startswith('linux'):
                log = (scratch/'display.log').open('w')
                display = subprocess.Popen(['Xvfb','-displayfd','1','-screen','0','1440x1000x24','-nolisten','tcp'],stdout=subprocess.PIPE,stderr=log,text=True)
                env['DISPLAY']=':'+display.stdout.readline().strip();env['LIBGL_ALWAYS_SOFTWARE']='1'
            # Test-only subclasses invoke the actual production render methods at
            # bounded sizes; they do not send pointer/key events to the desktop.
            driver = apphome/'mods/fixture-view'
            driver.mkdir()
            production = (ROOT/'mods/project/main.js').read_text().replace('export default class Project', 'class Project')
            driver_source = '''\nexport default class Fixture extends Project {
 render(cx) {
  if(this.project&&this.config.scene==='offline')this.error=new Error('Fixture disconnected');
  if(this.project&&this.config.scene==='long'){
   this.file=null;
   this.project.items[1].title='验证跨阶段研究证据与长标题布局 · 多语言边界检查'.repeat(4);
   this.project.items[1].question={recipient:'user',text:'请选择研究成果的长期保存位置',recommendation:'使用项目机器上的持久目录'};
   this.project.items[1].waitingOn='user';
  }
  return div().w(this.config.testWidth||320).h(this.config.testHeight||640).child(super.render(cx));
 }
}
'''
            (driver/'main.js').write_text(production+driver_source)
            for file in ('model.js','transport.js','project.svg'):
                shutil.copy2(ROOT/'mods/project'/file,driver/file)
            (driver/'mod.json').write_text(json.dumps(dict(place='none',focusable=True)))
            setup_driver=apphome/'mods/fixture-setup';setup_driver.mkdir()
            setup_source=(ROOT/'mods/project-setup/main.js').read_text().replace('export default class Setup','class Setup')
            setup_source+='''\nexport default class Fixture extends Setup {
 render(cx){
  if(this.catalog&&!this.prepared){
   this.prepared=true;
   if(this.config.scene==='first'){this.select('new');this.fields.goal.set_value('研究可靠协作与可追溯成果');}
   if(this.config.scene==='handoff'){this.select('research-loop');this.replacing=true;}
   if(this.config.scene==='error')this.error='模拟连接暂不可用。绑定和配置草案已保存，请重试。';
  }
  return div().w(420).h(600).child(super.render(cx));
 }
}
'''
            (setup_driver/'main.js').write_text(setup_source)
            shutil.copy2(ROOT/'mods/project/transport.js',setup_driver/'transport.js')
            (setup_driver/'mod.json').write_text(json.dumps(dict(place='none',focusable=True)))
            log = (scratch/'window.log').open('w')
            window = subprocess.Popen([app],env=env,stdout=log,stderr=log)
            wait_for(lambda: call([app,'status'],ok=False).returncode==0,'isolated native window')
            wait_for(lambda: second in call([app,'ls'],ok=False).stdout,'terminal adoption')
            config=dict(python=sys.executable,entry=str(ROOT/'project.py'),dataHome=str(ledger),panelMod='project',setupMod='project-setup',
                        bootstrap=str(Path(installed['runtime'])/'bootstrap.py'),bundle=str(Path(installed['runtime'])/'runtime-bundle.json'))
            # Main Project view follows the explicit fixture terminal.
            call([app,'do','layout.switch',json.dumps({'name':'projects'})])
            call([app,'do','agent.focus',json.dumps({'terminal':second})])
            call([app,'do','layout.select',json.dumps({'stack':'panel-body','child':'project'})])
            call([app,'do','layout.show',json.dumps({'id':'panel'})])
            time.sleep(1.5)
            call([app,'shot',str(output/'project.png')])
            check('Native project view has no host errors',not jcall([app,'status']).get('errors'))
            for page in ('sessions','files'):
                call([app,'do','project.'+page]);time.sleep(.5)
                call([app,'shot',str(output/(page+'.png'))])
                check('Native '+page+' view has no host errors',not jcall([app,'status']).get('errors'))
            reader=dict(location=dict(machine=None,terminal=second,localTerminal=second,space='spaces-integration'),projectId='research-loop',artifact='research-brief')
            # A separate tab is an actual mod pane with reader context.
            call([app,'do','tab.new',json.dumps(dict(name='Research reader fixture',space='spaces-integration',mod='project',props=dict(config,reader=reader)))])
            time.sleep(1.5);call([app,'shot',str(output/'reader.png')])
            check('Native research reader has no host errors',not jcall([app,'status']).get('errors'))
            call([app,'do','tab.new',json.dumps(dict(name='PM setup fixture',space='spaces-integration',mod='project-setup',props=dict(config,terminal=second)))])
            time.sleep(1.5);call([app,'shot',str(output/'setup.png')])
            check('Native setup summary has no host errors',not jcall([app,'status']).get('errors'))
            (apphome/'settings.json').write_text(json.dumps({'appearance':'light'}))
            call([app,'do','app.theme',json.dumps({'name':'paper'})]);time.sleep(1)
            call([app,'shot',str(output/'setup-light.png')])
            for scene in ('long','offline'):
                call([app,'do','tab.new',json.dumps(dict(name=scene+' fixture',space='spaces-integration',mod='fixture-view',
                    props=dict(config,scene=scene,testWidth=320,testHeight=640,reader=dict(reader,artifact='research-brief'))))])
                time.sleep(1)
                # The fixture uses the real snapshot and production renderer.
                call([app,'shot',str(output/(scene+'-narrow.png'))])
                check('Native '+scene+' narrow view has no host errors',not jcall([app,'status']).get('errors'))
            for scene in ('first','handoff','error'):
                call([app,'do','tab.new',json.dumps(dict(name=scene+' setup fixture',space='spaces-integration',mod='fixture-setup',
                    props=dict(config,scene=scene,terminal=first if scene=='handoff' else second)))])
                time.sleep(1);call([app,'shot',str(output/('setup-'+scene+'-narrow.png'))])
                check('Native setup '+scene+' narrow view has no host errors',not jcall([app,'status']).get('errors'))
            (apphome/'settings.json').write_text(json.dumps({'appearance':'dark'}))
            call([app,'do','app.theme',json.dumps({'name':'graphite'})]);time.sleep(.5)
            call([app,'shot',str(output/'setup-error-dark.png')])
            for mod in ('project','project-setup','projects-agents','projects-tabs'):
                call([app,'check',str(apphome/'mods'/mod)])
            check('Installed native mods pass host check',True)
            import hashlib
            images = list(output.glob('*.png'))
            hashes = {hashlib.sha256(image.read_bytes()).hexdigest() for image in images}
            check('Native captures contain distinct rendered states',len(hashes)>=len(images)-1)
            (output/'status.json').write_text(json.dumps(jcall([app,'status']),ensure_ascii=False,indent=2))
        (output/'result.json').write_text(json.dumps(dict(passed=len(checks),checks=checks,synthetic=True,
            realCore=True,modelCalls=False,native=bool(args.app),platform=sys.platform,scratch=str(scratch)),ensure_ascii=False,indent=2)+'\n')
    finally:
        call(project+['service','stop'],ok=False)
        if window:
            window.terminate()
            try: window.wait(timeout=10)
            except subprocess.TimeoutExpired: window.kill();window.wait(timeout=5)
        call(['hc','server','stop'],ok=False)
        if previous_frontmost:
            subprocess.run(['osascript','-l','JavaScript','-e',"ObjC.import('AppKit'); $.NSRunningApplication.runningApplicationWithProcessIdentifier("+str(previous_frontmost)+").activateWithOptions(2)"],capture_output=True,text=True,timeout=10)
        if display:
            display.terminate()
            try: display.wait(timeout=5)
            except subprocess.TimeoutExpired: display.kill();display.wait(timeout=5)
        for name in ('window.log','display.log'):
            if (scratch/name).exists(): shutil.copy2(scratch/name,output/name)
        print('Fixture workspace: '+str(scratch),flush=True)


if __name__ == '__main__': main()
