"""No-model smoke: real OpenCode plugin loads, handles native session creation and Core reports it."""
import os,json,subprocess,tempfile,sys,time,select,base64,secrets,urllib.request
from pathlib import Path
repo=Path(__file__).resolve().parent.parent
import argparse,shutil
parser=argparse.ArgumentParser();parser.add_argument('--opencode',default=shutil.which('opencode'));parser.add_argument('--output',default=str(repo/'docs/native-core/mini-result.json'));options=parser.parse_args()
if not options.opencode:raise SystemExit('OpenCode binary is required')
root=Path(tempfile.mkdtemp(prefix='hp-mini-',dir='/tmp'))
env={k:v for k,v in os.environ.items() if not k.startswith(('HC_','HERDR_PROJECT','OPENCODE_'))}
env.update(HC_SOCKET=str(root/'core.sock'),HC_SESSION='mini-status-test')
child=root/'child.py'
child.write_text('''import os,sys,json,subprocess,secrets,base64,urllib.request,select,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from herdr_projects.native_agents import environment
root=Path(sys.argv[2]);binary=sys.argv[3]
run=dict(id='run-native-status',execution=dict(backend='opencode'))
env,argv=environment(run,dict(os.environ,HERDR_RUN_ID=run['id']),[binary,'--standalone','mini'])
password=secrets.token_urlsafe(32);env['OPENCODE_PASSWORD']=password
log=(root/'server.log').open('w')
server=subprocess.Popen([binary,'serve','--stdio','--port','0'],env=env,cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
mini=None
try:
 if not select.select([server.stdout],[],[],25)[0]: raise RuntimeError('Server did not become ready')
 url=json.loads(server.stdout.readline())['url']
 headers={'Authorization':'Basic '+base64.b64encode(('opencode:'+password).encode()).decode(),'Content-Type':'application/json'}
 payload=json.dumps({'id':env['HERDR_SPACES_SESSION_ID'],'title':'No model native status test','location':{'type':'local','directory':str(root)}}).encode()
 request=urllib.request.Request(url+'/api/session',data=payload,headers=headers)
 data=json.load(urllib.request.urlopen(request,timeout=20))
 (root/'created.json').write_text(json.dumps({'id':data['data']['id']}))
 mini=subprocess.Popen([binary,'mini','--server',url,'--session',env['HERDR_SPACES_SESSION_ID']],env=env,cwd=root)
 (root/'ready').write_text('ready')
 while not (root/'stop').exists():time.sleep(.1)
finally:
 if mini:
  mini.terminate()
  try:mini.wait(timeout=5)
  except subprocess.TimeoutExpired:mini.kill();mini.wait()
 server.stdin.close()
 try:server.wait(timeout=5)
 except subprocess.TimeoutExpired:server.kill();server.wait()
''')
def call(args):return json.loads(subprocess.check_output(['hc',*args,'--json'],env=env,text=True))
try:
 call(['server','start'])
 parent=call(['run','--bg','--no-parent','--no-notify','--',sys.executable,'-c','import time; time.sleep(80)'])['address']
 worker=call(['run','--bg','--parent',parent,'--outlive-parent','--no-notify','--',sys.executable,str(child),str(repo),str(root),options.opencode])['address']
 deadline=time.monotonic()+55
 while time.monotonic()<deadline:
  value=call(['get',worker])
  if value.get('status',{}):break
  if value['state']!='live':raise RuntimeError('Fixture exited before status; '+subprocess.check_output(['hc','read',worker,'--lines','20'],env=env,text=True))
  time.sleep(.2)
 assert value['parent']==parent,value.get('parent')
 assert value.get('status',{}).get('app')=='opencode', 'No OpenCode status: '+str(root)
 assert value['status']['state']=='idle',value['status']
 result={'passed':True,'parent':parent,'worker':worker,'status':value['status'],'root':str(root),'modelCalls':False,'backend':'OpenCode V2 plugin and mini, real Core'}
 output=Path(options.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:
 (root/'stop').write_text('stop')
 subprocess.run(['hc','server','stop'],env=env,stdout=subprocess.DEVNULL)
 print('Artifacts',root)
