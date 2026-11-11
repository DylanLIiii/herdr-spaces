#!/usr/bin/env python3
"""Production manager -> Core -> _run -> standalone mini, local deterministic model only."""
import argparse,json,os,shutil,subprocess,sys,tempfile,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from herdr_projects import runtime,manager,teams
from herdr_projects.store import Store


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'docs/native-core-audit/blocking-mini.json'));args=parser.parse_args()
    scratch=Path(tempfile.mkdtemp(prefix='hps-production-',dir='/tmp')).resolve()
    requests=[];mode={'error':False,'blocker':None};release=threading.Event();release.set()
    class Model(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
            requests.append({'path':self.path,'model':body.get('model'),'stream':body.get('stream'),'error':mode['error']})
            if mode['blocker'] and body.get('model')=='spaces-fixture':
                name='shell' if mode['blocker']=='permission' else 'question'
                tools=[t.get('name',t.get('function',{}).get('name')) for t in body.get('tools',[])]
                requests[-1]['availableTools']=tools
                args={'command':'printf native-permission-fixture'} if name=='shell' else {'questions':[{'header':'Fixture','question':'Choose fixture option','options':[{'label':'A','description':'Fixture answer'}]}]}
                item={'id':'fc_fixture','type':'function_call','call_id':'call_fixture','name':name,'arguments':json.dumps(args),'status':'completed'}
                response={'id':'resp_fixture','object':'response','status':'completed','model':body.get('model'),'output':[item],'usage':{'input_tokens':20,'output_tokens':20,'total_tokens':40}}
                if body.get('stream'):
                    events=[{'type':'response.created','response':dict(response,status='in_progress',output=[])},
                            {'type':'response.output_item.added','output_index':0,'item':dict(item,arguments='',status='in_progress')},
                            {'type':'response.function_call_arguments.delta','output_index':0,'item_id':'fc_fixture','delta':item['arguments']},
                            {'type':'response.function_call_arguments.done','output_index':0,'item_id':'fc_fixture','arguments':item['arguments']},
                            {'type':'response.output_item.done','output_index':0,'item':item},
                            {'type':'response.completed','response':response}]
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                    for n,e in enumerate(events):self.wfile.write(('event: '+e['type']+'\ndata: '+json.dumps(dict(e,sequence_number=n))+'\n\n').encode());self.wfile.flush()
                else:self.json(response)
                return
            # Let Core's actual working status be observed before ending a turn.
            release.wait(15)
            if mode['error']:
                raw=json.dumps({'error':{'message':'Deterministic fixture failure','type':'invalid_request_error','code':'fixture'}}).encode()
                self.send_response(400);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw);return
            if '/responses' in self.path:
                response={'id':'resp_fixture','object':'response','status':'completed','model':body.get('model'),
                          'output':[{'id':'msg_fixture','type':'message','status':'completed','role':'assistant','content':[{'type':'output_text','text':'Local fixture completed.','annotations':[]}]}],
                          'usage':{'input_tokens':20,'output_tokens':5,'total_tokens':25}}
                if body.get('stream'):
                    chunks=[{'type':'response.created','response':dict(response,status='in_progress',output=[])},
                            {'type':'response.output_item.added','output_index':0,'item':dict(response['output'][0],content=[])},
                            {'type':'response.content_part.added','output_index':0,'content_index':0,'item_id':'msg_fixture','part':{'type':'output_text','text':'','annotations':[]}},
                            {'type':'response.output_text.delta','output_index':0,'content_index':0,'item_id':'msg_fixture','delta':'Local fixture completed.'},
                            {'type':'response.output_text.done','output_index':0,'content_index':0,'item_id':'msg_fixture','text':'Local fixture completed.'},
                            {'type':'response.output_item.done','output_index':0,'item':response['output'][0]},
                            {'type':'response.completed','response':response}]
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                    for i,event in enumerate(chunks):self.wfile.write(('event: '+event['type']+'\ndata: '+json.dumps(dict(event,sequence_number=i))+'\n\n').encode());self.wfile.flush()
                else:self.json(response)
            else:
                answer={'id':'chatcmpl-fixture','object':'chat.completion','created':1,'model':body.get('model'),'choices':[{'index':0,'message':{'role':'assistant','content':'Local fixture completed.'},'finish_reason':'stop'}],'usage':{'prompt_tokens':20,'completion_tokens':5,'total_tokens':25}}
                if body.get('stream'):
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                    for delta,finish in [({'role':'assistant','content':'Local fixture completed.'},None),({},'stop')]:
                        self.wfile.write(('data: '+json.dumps({'id':'chatcmpl-fixture','object':'chat.completion.chunk','created':1,'model':body.get('model'),'choices':[{'index':0,'delta':delta,'finish_reason':finish}]})+'\n\n').encode());self.wfile.flush()
                    self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
                else:self.json(answer)
        def json(self,value):
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(value).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Model);threading.Thread(target=server.serve_forever,daemon=True).start()
    config={'providers':{'openai':{'settings':{'baseURL':f'http://127.0.0.1:{server.server_port}/v1','apiKey':'fixture-only'},'models':{'spaces-fixture':{'limit':{'context':32000,'output':1000}}}}},'model':'openai/spaces-fixture','permissions':[{'action':'shell','resource':'*','effect':'ask'},{'action':'question','resource':'*','effect':'allow'}]}
    for key in list(os.environ):
        if key.startswith(('HC_','HERDR_PROJECT','OPENCODE_','OPENAI_')):os.environ.pop(key)
    os.environ.update(HC_SOCKET=str(scratch/'core.sock'),HC_SESSION='production-mini',OPENAI_API_KEY='fixture-only',
                      OPENCODE_CONFIG_CONTENT=json.dumps(config),XDG_CONFIG_HOME=str(scratch/'config'),XDG_DATA_HOME=str(scratch/'data'),XDG_STATE_HOME=str(scratch/'state'),XDG_CACHE_HOME=str(scratch/'cache'))
    observations=[]
    def hc(*cmd):return json.loads(subprocess.check_output([runtime.core_command(),*cmd,'--json'],text=True))
    def wait(fn,label,seconds=45):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            result=fn()
            if result:return result
            time.sleep(.1)
        raise RuntimeError('Timeout: '+label+'; scratch='+str(scratch))
    store=Store(scratch/'ledger')
    try:
        p=store.create('fixture','Production native smoke','Deterministic local model only',scratch)
        parent=runtime.start(store,'fixture',[sys.executable,'-c',"import time;print('\\033]7501;state=idle:app=pi\\033\\\\',end='',flush=True);time.sleep(120)",'{context}'])['terminal']
        wait(lambda:store.get('fixture')['main']['state']=='running','managed PM')
        p=store.get('fixture');m=p['main'];identity=dict(project=p['id'],main=m['id'],role='main',generation=m['generation'],token=m['token'])
        evidence=[]
        for blocker in ['permission','question']:
            mode['blocker']=blocker
            for op,fields in [('todo.add',dict(title='Native '+blocker,sourceRef='fixture')),('todo.promote',dict(brief='Deterministic '+blocker+' test only',acceptanceCriteria=['Native blocker state']))]:
                store.apply('fixture',store.get('fixture')['revision'],dict(requestId=blocker+'-'+op.replace('.','-'),op=op,id=blocker,**fields),identity)
            profile=teams.resolve(store.get('fixture'),role='explore',backend='opencode',model='openai/spaces-fixture')
            argv=manager.worker_command(store.get('fixture'),profile=profile)
            launched=runtime.start(store,'fixture',argv,item_id=blocker,revision=store.get('fixture')['revision'],identity=identity,profile=profile)
            child=launched['terminal']
            def blocked():
                d=hc('get',child);st=d.get('status') or {}
                if d['state']=='finished':raise RuntimeError('Fixture exited before native blocker: '+str(scratch))
                return d if st.get('state')=='blocked' and st.get('kind')==blocker else None
            native=wait(blocked,'native '+blocker,40)
            assert native['parent']==parent
            evidence.append(dict(scenario=blocker,terminal=child,parent=native['parent'],status=native['status'],productionCommand=argv,tool='shell' if blocker=='permission' else 'question'))
        result=dict(passed=True,through='manager.worker_command -> runtime.start -> _run -> production standalone mini -> actual OpenCode tools -> native permission/form events -> Core',
                    evidence=evidence,modelRequests=requests,paidModelCalls=0,localDeterministicHTTP=True,scratch=str(scratch),userInputInjected=False)
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    finally:
        release.set();store.close();subprocess.run([runtime.core_command(),'server','stop'],stdout=subprocess.DEVNULL);server.shutdown();print('Smoke artifacts:',scratch,flush=True)

if __name__=='__main__':main()
