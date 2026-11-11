#!/usr/bin/env python3
"""Exercise new ledger/bundle protocol through real isolated Core machine links."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.install import install
from scripts.remote_smoke import BRIDGE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT/'docs/coordination/remote-result.json'))
    args = parser.parse_args()
    scratch = Path(tempfile.mkdtemp(prefix='hps-remote-', dir='/tmp')).resolve()
    base = {k:v for k,v in os.environ.items() if not k.startswith(('HC_', 'HERDR_', 'XDG_'))}
    def environment(name):
        settings = dict(HC_SOCKET=str(scratch/(name+'.sock')), HC_SESSION=name, HERDR_APP_HOME=str(scratch/name/'app'))
        for key, directory in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_STATE_HOME','state'),('XDG_CACHE_HOME','cache')]:
            settings[key]=str(scratch/name/directory);Path(settings[key]).mkdir(parents=True)
        return base|settings,settings
    server, settings = environment('server'); first,_ = environment('first'); second,_ = environment('second')
    settings_path=scratch/'server.json';settings_path.write_text(json.dumps(settings))
    bridge=scratch/'bridge.py';bridge.write_text(BRIDGE);gate=scratch/'offline'
    via=shlex.join([sys.executable,str(bridge),str(settings_path),str(gate)])
    checks=[]
    def call(argv,env=first,ok=True):
        result=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=30)
        if ok and result.returncode:raise RuntimeError(str(argv[:3])+': '+(result.stderr or result.stdout))
        return result
    def remote(argv,env=first,alias='fixture',ok=True):
        return call(['hc','exec','--on',alias,'--timeout','10','--',*argv],env,ok)
    def wait_for(fn,label):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            value=fn()
            if value:return value
            time.sleep(.15)
        raise RuntimeError('Timed out: '+label)
    def check(label,value):
        if not value:raise AssertionError(label)
        checks.append(label);print('PASS '+label,flush=True)
    try:
        target=install(server['HERDR_APP_HOME'],scratch/'server/bin',scratch/'server/ledger',runtime_only=True,
                       registry_dir=Path(server['XDG_CONFIG_HOME'])/'herdr-spaces/runtimes')
        for env in (server,first,second):call(['hc','server','start'],env)
        for env,alias in ((first,'fixture'),(second,'alternate')):call(['hc','machine','add','--name',alias,'--session','server','--via',via],env)
        discovery=call(['node','--input-type=module','-e',"import {discoverRuntime} from './mods/project/transport.js';process.stdout.write(discoverRuntime)"],base).stdout
        cli=['python3','-c',discovery,'projects']
        probe=json.loads(remote(cli+['probe']).stdout)
        check('Remote discovery reports schema 2 and guided setup/bundle capabilities',probe['schemaVersion']==2 and {'guided-setup','artifact-bundles'}.issubset(probe['capabilities']))
        seed='''import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from herdr_projects.store import Store
s=Store(sys.argv[2]);p=s.create('remote','Remote study','Durable research',sys.argv[3])
with s.transaction():
 p=s.get('remote');p['main'].update(state='running',generation=1,token='fixture-token',scope='fixture');s.save(p)
i=dict(role='main',project='remote',main=p['main']['id'],generation=1,token='fixture-token')
def apply(op,**fields):
 p=s.get('remote');s.apply('remote',p['revision'],dict(requestId='seed-'+str(p['revision']),op=op,**fields),i)
apply('todo.add',id='study',title='Source study',sourceRef='fixture')
r=Path(sys.argv[3])/'source';r.mkdir();(r/'brief.md').write_text('# Remote durable brief\\n\\nEvidence on the project machine.')
apply('artifact.add',id='brief-v1',workItemId='study',sourceRef='fixture',title='Remote study',bundle=dict(root=str(r),entrypoint='brief.md',files=[dict(path='brief.md',role='brief')]))
print(json.dumps(s.public(s.get('remote'))));s.close()
'''
        p=json.loads(remote([sys.executable,'-c',seed,target['runtime'],target['dataHome'],str(scratch/'server')]).stdout)
        scope='core:'+json.loads(call(['hc','server','status','--json'],server).stdout)['core']['id']
        read=['read','--project','remote','--artifact','brief-v1','--core-scope',scope,'--ledger-home',target['dataHome']]
        one=json.loads(remote(cli+read).stdout);two=json.loads(remote(cli+read,second,'alternate').stdout)
        check('Two clients read one published remote artifact version',one['text']==two['text'] and one['ledgerHome']==two['ledgerHome']==target['dataHome'])
        check('Remote bundle integrity and members are preserved',not one['changed'] and one['files'][0]['path']=='brief.md')
        check('No second ledger is created on either client',not (Path(first['XDG_DATA_HOME'])/'herdr-projects').exists() and not (Path(second['XDG_DATA_HOME'])/'herdr-projects').exists())
        wrong=remote(cli+read[:-1]+[str(scratch/'wrong-ledger')],ok=False)
        check('Remote read refuses changed ledger identity',wrong.returncode!=0)
        gate.write_text('disconnect')
        wait_for(lambda:remote(cli+['probe'],ok=False).returncode!=0,'transport disconnection')
        check('Disconnection fails without local fallback',True)
        gate.unlink()
        wait_for(lambda:remote(cli+['probe'],ok=False).returncode==0,'transport recovery')
        recovered=json.loads(remote(cli+['show','--project','remote']).stdout)
        check('Reconnect preserves Main identity and artifact hash',recovered['main']['id']==p['main']['id'] and recovered['artifacts'][0]['sha256']==p['artifacts'][0]['sha256'])
        check('Remote full-text search returns the same version',json.loads(remote(cli+['search','--project','remote','--query','project machine']).stdout)['artifacts'][0]['id']=='brief-v1')
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(dict(passed=len(checks),checks=checks,synthetic=True,transport='real hc machine --via; isolated loopback cores, not physical SSH',scratch=str(scratch)),indent=2)+'\n')
    finally:
        gate.unlink(missing_ok=True)
        for env in (first,second,server):call(['hc','server','stop'],env,ok=False)


if __name__=='__main__':main()
