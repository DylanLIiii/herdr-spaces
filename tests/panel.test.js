import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { groups, sessionStatus, location } from '../mods/project/model.js';

const fixture = id => ({id,name:id,goal:'A goal',cwd:'/repo',revision:3,
  main:{id:'main-'+id,state:'running',terminal:id+'-main'},
  items:[{id:'todo',title:'Todo',kind:'todo',status:'open',sourceRef:'user',brief:'Next work',nextAction:'Refine',revision:1,acceptanceCriteria:[],checklist:[],artifactIds:[]},
    {id:'task',title:'Task',kind:'task',status:'review',sourceRef:'user',brief:'Scope',revision:2,acceptanceCriteria:['Check result'],checklist:[{title:'step',done:true}],artifactIds:[],activeRunId:'run'}],
  runs:[{id:'run',terminal:id+'-worker',state:'running',workItemId:'task',reports:[]}],artifacts:[],decisions:[]});

class Element {
  constructor(){this.nodes=[];this.events={};this.attrs={};return new Proxy(this,{get:(target,key)=>{
    if(key in target)return typeof target[key]==='function'?target[key].bind(target):target[key];
    return (...args)=>{target.attrs[key]=args;return target.proxy;};
  }});}
  child(value){this.nodes.push(value);return this.proxy;}
  children(values){this.nodes.push(...values);return this.proxy;}
  when(condition,fn){if(condition)fn(this.proxy);return this.proxy;}
  id(value){this.key=value;return this.proxy;}
  on_click(fn){this.events.click=fn;return this.proxy;}
  on_key_down(fn){this.events.key=fn;return this.proxy;}
}
function element(){const e=new Element();e.proxy=e;return e;}
function find(root,key){if(root?.key===key)return root;for(const node of root?.nodes||[]){const result=find(node,key);if(result)return result;}return null;}
function allText(root){return typeof root==='string'?root:(root?.nodes||[]).map(allText).join(' ');}
const turn=()=>new Promise(resolve=>setImmediate(resolve));

async function host(options={}){
  const state={focus:{terminal:'a-main'},space:{id:'s1',active:true,machine:null},pending:[],calls:[],notify:0,live:[],closed:false,...options};
  const cx={notify:()=>state.notify++,stop_propagation(){},focus_handle:()=>({focus(){}}),timer:{every(){}},spawn(fn){fn(cx).catch(e=>{state.error=e;});}};
  const context=vm.createContext({console,Set,Map,JSON,Date});
  const exports={
    'gpui-kit':{View:class{},div:element,svg:element},
    'gpui-base':{h_flex:element,v_flex:element,TextView:{markdown:(_id,text)=>element().child(text)}},
    herdr:{props:()=>({entry:'/app/project.py',dataHome:'/local/ledger',...options.config}),exec:(command,args,opts)=>new Promise((resolve,reject)=>state.pending.push({command,args,options:opts,resolve,reject})),
      spaces:()=>[state.space],panes:()=>state.live.map(t=>({terminal:t.address})),focused:()=>state.focus,terminals:()=>state.live,
      theme:()=>({}),layout:()=>null,nextCommand:()=>new Promise(()=>{}),run:(name,args)=>state.calls.push({name,args}),openOverlay:spec=>state.calls.push({name:'overlay',args:spec})},
  };
  const modules=new Map();
  const load=async path=>{
    if(modules.has(path))return modules.get(path);
    const m=new vm.SourceTextModule(await readFile(new URL(path,import.meta.url),'utf8'),{context,identifier:path});modules.set(path,m);
    await m.link(async spec=>{
      if(exports[spec]){const values=exports[spec];const module=new vm.SyntheticModule(Object.keys(values),function(){for(const [key,value]of Object.entries(values))this.setExport(key,value);},{context});return module;}
      return load('../mods/project/'+spec.slice(2));
    });return m;
  };
  const m=await load('../mods/project/main.js');await m.evaluate();const view=new m.namespace.default();view.init(null,cx);
  const respond=async(p,which=0,extra={})=>{const req=state.pending.splice(which,1)[0];req.resolve({code:0,stdout:JSON.stringify({project:p,protocolVersion:1,schemaVersion:1,coreScopes:['core:'+ (req.options.on||'local')],ledgerHome:req.options.on?'/remote/ledger':'/local/ledger',...extra})});await turn();};
  return {state,cx,view,respond};
}

test('ledger groups preserve ready/review/cancelled distinctions and exact counts',()=>{
  const p=fixture('a');p.items.push({id:'ready',kind:'task',status:'ready'},{id:'cancel',kind:'todo',status:'cancelled'});
  assert.deepEqual(groups(p.items).map(g=>[g.id,g.items.length]),[['todo',1],['ready',1],['review',1],['cancelled',1]]);
  assert.equal(sessionStatus(p.runs[0],{status:'idle'}),'空闲');assert.equal(p.items[1].status,'review');
});

test('actual View renders ledger, detail, scoped sessions and native navigation',async()=>{
  const h=await host();await h.respond(fixture('a'));let root=h.view.render(h.cx);
  assert.ok(find(root,'group-todo'));assert.ok(find(root,'group-review'));
  find(root,'work-task').events.click({},h.cx);root=h.view.render(h.cx);
  assert.match(allText(root),/完成条件/);assert.match(allText(root),/步骤/);assert.match(allText(root),/来源/);
  h.state.live=[{address:'a-main',status:'idle'},{address:'a-worker',status:'idle'},{address:'b-worker',status:'working'}];
  find(root,'detail-worker').events.click({},h.cx);assert.equal(h.state.calls.at(-1).args.terminal,'a-worker');
  find(root,'project-back').events.click({},h.cx);root=h.view.render(h.cx);find(root,'tab-sessions').events.click({},h.cx);
  root=h.view.render(h.cx);assert.ok(find(root,'session-main-a'));assert.ok(find(root,'session-run'));assert.doesNotMatch(allText(root),/b-worker/);
  find(root,'project-close').events.click({},h.cx);assert.equal(h.state.calls.at(-1).args.terminal,'a-main');
  assert.equal(h.view.project.items[1].status,'review');assert.equal(h.state.error,undefined);h.view.close();
});

test('keyboard navigation opens work records and returns through native sessions',async()=>{
  const h=await host();await h.respond(fixture('a'));
  h.view.handleKey({key:'1'},h.cx);h.view.handleKey({key:'down'},h.cx);h.view.handleKey({key:'down'},h.cx);h.view.handleKey({key:'enter'},h.cx);
  assert.equal(h.view.detail,'task');h.view.handleKey({key:'escape'},h.cx);assert.equal(h.view.detail,null);
  h.state.live=[{address:'a-main',status:'idle'}];h.view.handleKey({key:'2'},h.cx);h.view.handleKey({key:'down'},h.cx);h.view.handleKey({key:'enter'},h.cx);
  assert.equal(h.state.calls.at(-1).args.terminal,'a-main');h.view.close();
});

test('late result from another project cannot replace current terminal context',async()=>{
  const h=await host();h.state.focus={terminal:'b-main'};h.view.render(h.cx);
  assert.equal(h.state.pending.length,2);await h.respond(fixture('b'),1);await h.respond(fixture('a'),0);
  assert.equal(h.view.project.id,'b');assert.equal(h.view.busy,false);h.view.close();
});

test('read errors show last known records without changing their truth',async()=>{
  const h=await host();await h.respond(fixture('a'));h.view.refresh(h.cx);h.state.pending.shift().reject(new Error('offline'));await turn();
  const root=h.view.render(h.cx);assert.match(allText(root),/上次记录/);assert.equal(h.view.project.items[1].status,'review');h.view.close();
});

test('remote terminal reads and navigation stay on the owning machine',async()=>{
  const h=await host({focus:{pane:null,terminal:'server/t1'}});
  const req=h.state.pending[0];assert.equal(req.options.on,'server');
  assert.equal(req.args.at(-1),'t1');assert.ok(!req.args.includes('/local/ledger'));assert.ok(!req.args.includes('/app/project.py'));
  const p=fixture('remote');p.main.terminal='t1';p.main.scope='core:server';p.runs[0].terminal='t2';p.runs[0].scope='core:server';
  await h.respond(p);
  h.state.live=[{address:'t2',status:'working'},{address:'other/t2',status:'working'},{address:'server/t2',status:'idle'}];
  h.view.navigate(p.runs[0],h.cx);assert.equal(h.state.calls.at(-1).args.terminal,'server/t2');
  h.view.tab='sessions';assert.match(allText(h.view.render(h.cx)),/空闲/);
  const count=h.state.calls.length;h.view.navigate({...p.main,scope:'core:other'},h.cx);assert.equal(h.state.calls.length,count);
  h.view.openFile('pm',h.cx);const read=h.state.pending[0];
  assert.equal(read.options.on,'server');assert.ok(read.args.includes('core:server'));assert.ok(read.args.includes('/remote/ledger'));
  await h.respond(null,0,{coreScope:'core:server',text:'remote evidence'});assert.equal(h.view.preview.text,'remote evidence');h.view.close();
});

test('peek machine follows focused terminal, including a local peek over a remote Space',()=>{
  const spaces=[{id:'remote',active:true,machine:'server'}];
  assert.equal(location({pane:null,terminal:'other/t1'},[],spaces).machine,'other');
  assert.equal(location({pane:null,terminal:'t1'},[],spaces).machine,null);
  assert.equal(location({pane:'mod',terminal:null},[{terminal:'server/t2',focused:true}],spaces).terminal,null);
});

test('same terminal and project ids on different machines cannot share a late response',async()=>{
  const h=await host({focus:{terminal:'one/t1'}});
  h.state.focus={terminal:'two/t1'};h.view.render(h.cx);
  const p=fixture('same');p.goal='Machine two';await h.respond(p,1);
  const old=fixture('same');old.goal='Machine one';await h.respond(old);
  assert.equal(h.view.project.goal,'Machine two');assert.equal(h.view.origin.machine,'two');
  h.view.openFile('pm',h.cx);h.state.focus={terminal:'one/t1'};
  await h.respond(null,0,{coreScope:'core:two',text:'must not appear'});
  assert.equal(h.view.preview,null);h.view.render(h.cx);assert.equal(h.view.project,null);h.view.close();
});

test('remote disconnect keeps marked stale data and never falls back to a local ledger',async()=>{
  const h=await host({focus:{terminal:'server/t1'}});await h.respond(fixture('same'));
  h.view.refresh(h.cx);const req=h.state.pending.shift();assert.equal(req.options.on,'server');req.reject(new Error('offline'));await turn();
  assert.match(allText(h.view.render(h.cx)),/上次记录/);assert.equal(h.state.pending.length,0);
  h.view.refresh(h.cx);assert.equal(h.state.pending[0].options.on,'server');
  const fresh=fixture('same');fresh.revision=9;await h.respond(fresh);assert.equal(h.view.project.revision,9);assert.equal(h.view.error,null);h.view.close();
});

test('incompatible runtime fails explicitly and a changed core clears old evidence',async()=>{
  const h=await host({focus:{terminal:'server/t1'}});await h.respond(fixture('a'),0,{protocolVersion:99});
  assert.equal(h.view.project,null);assert.match(h.view.error.message,/版本不兼容/);
  h.view.refresh(h.cx);await h.respond(fixture('a'));h.view.openFile('pm',h.cx);
  h.view.refresh(h.cx);await h.respond(fixture('b'),1,{coreScopes:['core:replacement']});
  await h.respond(null,0,{coreScope:'core:server',text:'stale evidence'});
  assert.equal(h.view.project.id,'b');assert.equal(h.view.file,null);assert.equal(h.view.preview,null);assert.equal(h.view.busy,false);h.view.close();
});

test('custom remote command stays an argv array with spaces intact',async()=>{
  const h=await host({focus:{terminal:'server/t1'},config:{remotes:{server:{command:['/opt/my runtime/herdr-project','--home','/srv/project data']}}}});
  const req=h.state.pending[0];assert.equal(req.command,'/opt/my runtime/herdr-project');
  assert.deepEqual([...req.args],['--home','/srv/project data','snapshot','--terminal','t1']);assert.equal(req.options.on,'server');h.view.close();
});

test('missing runtime offers Leader setup instead of raw installation commands',async()=>{
  const h=await host({focus:{terminal:'gpu-dev/t1'}});
  h.state.pending.shift().resolve({code:2,stderr:JSON.stringify({code:'runtime_missing',message:'runtime absent'})});await turn();
  const root=h.view.render(h.cx);assert.ok(find(root,'project-setup'));
  assert.doesNotMatch(allText(root),/scripts\/install.py|herdr-project create|Error:/);h.view.close();
});

test('closing during a read prevents updates and renders no new composer',async()=>{
  const h=await host();h.view.close();const count=h.state.notify;await h.respond(fixture('a'));
  assert.equal(h.view.project,null);assert.equal(h.state.notify,count);
  const source=await readFile(new URL('../mods/project/main.js',import.meta.url),'utf8');
  assert.doesNotMatch(source,/TextareaState|InputState|hc\(['"]send|terminal\.run/);
});
