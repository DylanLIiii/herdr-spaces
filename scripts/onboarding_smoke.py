#!/usr/bin/env python3
"""Exercise empty state -> left Agent menu -> automatic setup -> existing Leader."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.install import install
from scripts.remote_smoke import BRIDGE
from scripts.x11_fixture import PrivateDisplay


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', required=True)
    parser.add_argument('--output', default=str(ROOT / 'docs/onboarding'))
    args = parser.parse_args()
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='spaces-onboarding-'))
    base = {k:v for k,v in os.environ.items() if not k.startswith(('HC_', 'HERDR_PROJECT'))}
    def environment(name):
        extra = dict(HC_SESSION=name, HC_SOCKET=str(scratch / (name+'.sock')), HERDR_APP_HOME=str(scratch/name/'app'), LIBGL_ALWAYS_SOFTWARE='1')
        for key,part in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_STATE_HOME','state'),('XDG_CACHE_HOME','cache'),('XDG_RUNTIME_DIR','runtime')]:
            extra[key]=str(scratch/name/part);Path(extra[key]).mkdir(parents=True,mode=0o700)
        return base|extra,extra
    client,_ = environment('client'); server,settings = environment('server')
    app = str(Path(args.app).resolve()); pointer=window=display=None;checks=[]
    bridge=scratch/'bridge.py';bridge.write_text(BRIDGE)
    configuration=scratch/'server.json';configuration.write_text(json.dumps(settings))
    gate=scratch/'disconnected'
    def call(argv,env=client,ok=True):
        result=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=20)
        if ok and result.returncode:raise RuntimeError(str(argv[:3])+': '+result.stderr+result.stdout)
        return result
    def jcall(argv,**kw):return json.loads(call(argv,**kw).stdout)
    def do(command,**kw):return call([app,'do',command,json.dumps(kw)])
    def wait_for(fn,label,seconds=30):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            result=fn()
            if result:return result
            time.sleep(.15)
        raise RuntimeError('Timed out: '+label)
    def check(label,value):
        if not value:raise AssertionError(label)
        checks.append(label);print('PASS '+label,flush=True)
    try:
        installed=install(client['HERDR_APP_HOME'],scratch/'client/bin',scratch/'client/ledger',registry_dir=Path(client['XDG_CONFIG_HOME'])/'herdr-spaces/runtimes')
        call(['hc','server','start']);call(['hc','server','start'],env=server)
        call(['hc','machine','add','--name','gpu-fixture','--session','server','--via',shlex.join([sys.executable,str(bridge),str(configuration),str(gate)])])
        fixture=scratch/'server/agent.py';shutil.copy2(ROOT/'tests/attached_fixture.py',fixture)
        terminal=jcall(['hc','run','--bg','--keep','--no-parent','--no-notify','--cwd',str(scratch/'server'),
                        '--label','herdr.space=existing','--label','herdr.tab=agent','--',sys.executable,str(fixture),str(scratch/'server')],env=server)['address']
        registry=Path(server['XDG_CONFIG_HOME'])/'herdr-spaces/runtimes/projects.json'
        check('Existing remote Agent starts without any Projects runtime or ledger',not registry.exists())
        ah=Path(client['HERDR_APP_HOME']);(ah/'shared.json').write_text(json.dumps({'frame.welcomed':'skipped'}));(ah/'settings.json').write_text(json.dumps({'appearance':'dark'}))
        display_log=(scratch/'display.log').open('w')
        display=subprocess.Popen(['Xvfb','-displayfd','1','-screen','0','1600x1000x24','-nolisten','tcp'],stdout=subprocess.PIPE,stderr=display_log,text=True)
        display_id=display.stdout.readline().strip()
        if not display_id.isdigit():raise RuntimeError('Private display failed')
        client['DISPLAY']=':'+display_id
        window_log=(scratch/'window.log').open('w');window=subprocess.Popen([app],env=client,stdout=window_log,stderr=window_log)
        wait_for(lambda:call([app,'status'],ok=False).returncode==0,'window')
        address='gpu-fixture/'+terminal
        wait_for(lambda:address in call([app,'ls'],ok=False).stdout,'Agent adoption')
        os.environ['DISPLAY']=client['DISPLAY'];pointer=PrivateDisplay(client['DISPLAY']);pointer.resize(1600,1000)
        do('layout.switch',name='projects');do('pane.focus',terminal=address);time.sleep(.5)
        do('layout.select',stack='panel-body',child='project');do('layout.show',id='panel');time.sleep(1)
        pointer.click(1565,965)
        call([app,'shot',str(output/'empty.png')])
        check('Viewing an unprepared machine does not silently install anything',not registry.exists())
        # Native left Agent row context menu, with the same Space/Agent geometry
        # as Herdr's personal layout. The target is held by the menu, not focus.
        pointer.click(130,575,button=3);time.sleep(.3)
        call([app,'shot',str(output/'menu.png')])
        check('Left Agent right-click opens the Leader entry',bool(jcall([app,'status']).get('overlays')))
        pointer.click(220,592)
        wait_for(lambda:registry.exists(),'automatic remote runtime preparation')
        time.sleep(1)
        check('Setup automatically installs only on the selected machine',registry.exists() and not Path(client['XDG_DATA_HOME'],'herdr-projects').exists())
        call([app,'shot',str(output/'form.png')])
        pointer.type_ascii('deliver fixture');pointer.key('Return');pointer.key('Return')
        wait_for(lambda:(scratch/'server/attached-ready').exists(),'existing Agent receives introduction and writes a task')
        registered=json.loads(registry.read_text());cli=registered['command']
        record=json.loads((scratch/'server/attached-ready').read_text());project=record['project']
        wait_for(lambda:jcall(cli+['show','--project',project],env=server)['main'].get('notice',{}).get('state') not in (None,'sending'),'send acknowledgement')
        p=jcall(cli+['show','--project',project],env=server)
        check('Binding reuses the original terminal and stable Main identity',p['main']['mode']=='attached' and p['main']['terminal']==terminal and p['main']['generation']==1)
        check('Existing Agent reads context and writes through terminal-bound identity',p['items'][0]['title']=='First task from existing Leader')
        check('Only one visible introduction is recorded',p['main']['notice']['state']=='sent')
        check('The left Agent has a persistent Leader label',jcall(['hc','get',terminal],env=server)['labels']['projects.role']=='main')
        check('No replacement Agent was launched',len(jcall(['hc','ls','--json'],env=server)['terminals'])==1)
        call([app,'shot',str(output/'bound.png')])
        pointer.key('Escape');do('pane.focus',terminal=address);do('project.refresh');time.sleep(.7)
        call([app,'shot',str(output/'leader.png')])
        status=jcall([app,'status'])
        check('Native setup closes without host errors or a docked settings copy',not status.get('errors') and not status.get('overlays'))
        def docked(node):
            return node.get('content',{}).get('mod')=='project-setup' or any(docked(child) for child in node.get('children',[]))
        check('Setup is only a dialog and never inserts itself into the workspace',not docked(json.loads(Path(installed['layout']).read_text())))
        pointer.click(130,575,button=3);pointer.click(220,592);time.sleep(.7)
        pointer.resize(1024,800);call([app,'shot',str(output/'narrow.png')]);pointer.key('Escape')
        check('Leader setup fits a narrow window and closes by keyboard',not jcall([app,'status']).get('errors') and not jcall([app,'status']).get('overlays'))
        for key in ('panel','tabs','agents','setup'):call([app,'check',installed[key]])
        check('All four installed native mods pass check',True)
        (output/'result.json').write_text(json.dumps(dict(passed=len(checks),checks=checks,app=call([app,'--version']).stdout.strip(),
            core=call(['hc','--version']).stdout.strip(),synthetic=True,transport='isolated cores with real machine --via, existing deterministic Agent, no LLM'),indent=2)+'\n')
    finally:
        if pointer:pointer.close()
        if window:
            window.terminate()
            try:window.wait(timeout=10)
            except subprocess.TimeoutExpired:window.kill();window.wait(timeout=5)
        for env in (client,server):call(['hc','server','stop'],env=env,ok=False)
        if display:
            display.terminate()
            try:display.wait(timeout=5)
            except subprocess.TimeoutExpired:display.kill();display.wait(timeout=5)
        for name in ('window.log','display.log'):
            if (scratch/name).exists():shutil.copy2(scratch/name,output/name)
        print('Isolated verification files: '+str(scratch),flush=True)


if __name__=='__main__':main()
