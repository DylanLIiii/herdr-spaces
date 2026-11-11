#!/usr/bin/env python3
"""Read-only, allowlisted comparison of the real target project before/after upgrade."""
import argparse,hashlib,json,sqlite3,subprocess
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--backup',required=True);args=parser.parse_args()
    command=json.loads((Path.home()/'.config/herdr-spaces/runtimes/projects.json').read_text())['command']
    probe=json.loads(subprocess.check_output(command+['probe'],text=True))
    def load(path, immutable=False):
        db=sqlite3.connect(path.as_uri()+'?mode=ro'+('&immutable=1' if immutable else ''),uri=True)
        try:
            schema=db.execute('PRAGMA user_version').fetchone()[0]
            p=json.loads(db.execute('SELECT body FROM projects WHERE id=?',(args.project,)).fetchone()[0]);return schema,p
        finally:db.close()
    before_schema,before=load(Path(args.backup)/'projects.sqlite3', immutable=True)
    after_schema,after=load(Path(probe['ledgerHome'])/'projects.sqlite3')
    def safe(p):
        return dict(project=p['id'],main={k:p['main'].get(k) for k in ('id','terminal','scope','generation','mode')},
                    revision=p['revision'],items=[{'id':i['id'],'status':i['status'],'activeRunId':i.get('activeRunId')} for i in p['items']],
                    runs=[{'id':r['id'],'terminal':r.get('terminal'),'state':r['state'],'parentTerminal':r.get('parentTerminal'),
                           'reportIds':[x['id'] for x in r.get('reports',[])]} for r in p['runs']],
                    artifactIds=[a['id'] for a in p['artifacts']],decisionIds=[d['id'] for d in p['decisions']])
    old,new=safe(before),safe(after)
    checks={'stableMain':old['main']['id']==new['main']['id'],'sameGeneration':old['main']['generation']==new['main']['generation'],
            'priorRunsRetained':{r['id'] for r in old['runs']} <= {r['id'] for r in new['runs']},
            'priorArtifactsRetained':set(old['artifactIds'])<=set(new['artifactIds']),
            'priorDecisionsRetained':set(old['decisionIds'])<=set(new['decisionIds'])}
    assert all(checks.values()),checks
    core=str(Path.home()/'.local/bin/herdr-core')
    executions=[]
    for run in after['runs']:
        if not run.get('terminal'):continue
        result=subprocess.run([core,'get',run['terminal'],'--json'],capture_output=True,text=True)
        if result.returncode:
            executions.append(dict(runId=run['id'],terminal=run['terminal'],observable=False));continue
        value=json.loads(result.stdout)
        executions.append(dict(runId=run['id'],**{k:value.get(k) for k in ('address','state','parent','pid','reported','created_ms','exit_code')}))
    root=Path(command[1]).parent
    hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['herdr_projects/teams.py','herdr_projects/workspaces.py','herdr_projects/integrations/opencode-status/index.js']}
    print(json.dumps(dict(project=args.project,beforeSchema=before_schema,afterSchema=after_schema,version=probe['version'],
        before=old,after=new,checks=checks,currentCore=executions,installedHashes=hashes,scope='Actual ts-mini project. No terminal restart or parent mutation requested.'),indent=2))

if __name__=='__main__':main()
