import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const turn=()=>new Promise(resolve=>setImmediate(resolve));
function element(){const target={nodes:[],events:{},child(x){this.nodes.push(x);return proxy;},children(xs){this.nodes.push(...xs);return proxy;},when(on,f){if(on)f(proxy);return proxy;},id(x){this.key=x;return proxy;}};
 const proxy=new Proxy(target,{get:(t,k)=>k in t?typeof t[k]==='function'?t[k].bind(t):t[k]:(...args)=>{if(k==='on_click')t.events.click=args[0];return proxy;}});return proxy;}
function find(root,key){if(root?.key===key)return root;for(const n of root?.nodes||[]){const r=find(n,key);if(r)return r;}return null;}
const catalog={coreScope:'core:server',terminal:'t1',cwd:'/srv/repo',suggestedName:'repo',newProjectId:'new-project',projects:[]};
async function host(){
 const state={pending:[],actions:[]};const cx={notify(){},stop_propagation(){},focus_handle:()=>({focus(){}}),spawn(fn){fn(cx).catch(e=>{state.error=e;});}};
 const config={terminal:'server/t1',entry:'/local/project.py',bootstrap:'/local/bootstrap.py',bundle:'/local/bundle.json',overlay:'overlay'};
 const exports={
  'gpui-kit':{View:class{},div:element},
  'gpui-base':{v_flex:element,h_flex:element,Input:{new:element},InputState:{new:({value})=>{const f={text:value,callbacks:{},value(){return this.text;},on(k,cb){this.callbacks[k]=cb;},focus(){this.callbacks.focus?.({},cx);}};return f;}}},
  herdr:{props:()=>config,exec:(command,args,options)=>new Promise((resolve,reject)=>state.pending.push({command,args,options,resolve,reject})),readTextFile:async path=>path.endsWith('.py')?'bootstrap source':'{}',theme:()=>({}),openOverlay:spec=>state.actions.push(['open',spec]),closeOverlay:id=>state.actions.push(['close',id]),run:(name,args)=>state.actions.push([name,args])}
 };
 const context=vm.createContext({console,Set,Map,JSON,Date});
 const transport=new vm.SourceTextModule(await readFile(new URL('../mods/project/transport.js',import.meta.url),'utf8'),{context});await transport.link(()=>{});
 const main=new vm.SourceTextModule(await readFile(new URL('../mods/project-setup/main.js',import.meta.url),'utf8'),{context});
 await main.link(spec=>{if(spec==='./transport.js')return transport;const values=exports[spec];return new vm.SyntheticModule(Object.keys(values),function(){for(const [key,value]of Object.entries(values))this.setExport(key,value);},{context});});
 await main.evaluate();const view=new main.namespace.default();view.init(config,cx);
 const respond=async(data,code=0)=>{const req=state.pending.shift();assert.ok(req);req.resolve({code,stdout:code?'':JSON.stringify(data),stderr:code?JSON.stringify(data):''});await turn();};
 return {state,cx,view,respond};
}

test('explicit Leader setup automatically prepares missing runtime then binds the selected remote terminal',async()=>{
 const h=await host();assert.equal(h.state.pending[0].args.at(-1),'probe');
 await h.respond({code:'runtime_missing'},2);
 assert.deepEqual([...h.state.pending[0].args],['-c','bootstrap source','projects','{}']);assert.equal(h.state.pending[0].options.on,'server');
 await h.respond({prepared:true});assert.deepEqual([...h.state.pending[0].args.slice(-3)],['setup','--terminal','t1']);
 await h.respond(catalog);h.view.fields.goal.text='Deliver a useful result';h.view.save(h.cx);
 assert.ok(h.state.pending[0].args.includes('bind'));assert.ok(h.state.pending[0].args.includes('/srv/repo'));assert.equal(h.state.pending[0].options.on,'server');
 await h.respond({project:{id:'new-project',name:'repo',main:{terminal:'t1',generation:1,scope:'core:server'}}});
 assert.ok(h.state.pending[0].args.includes('introduce'));
 await h.respond({state:'waiting',message:'context command'});assert.equal(h.view.notice.state,'waiting');assert.ok(find(h.view.render(h.cx),'setup-introduce'));assert.equal(h.state.error,undefined);
});

test('closing while preparing cannot bind a project or type into a terminal',async()=>{
 const h=await host();await h.respond({code:'runtime_missing'},2);h.view.close();await h.respond({prepared:true});assert.equal(h.state.pending.length,0);assert.equal(h.view.bound,null);
});

test('an existing Leader is opened instead of silently reassigned',async()=>{
 const h=await host();await h.respond({capabilities:['leader-bind']});
 await h.respond({...catalog,projects:[{id:'existing',name:'Existing',goal:'Goal',cwd:'/srv/repo',main:{state:'running',terminal:'t2',scope:'core:server'}}]});
 h.view.selected='existing';h.view.save(h.cx);assert.equal(h.state.pending.length,0);
 const open=find(h.view.render(h.cx),'setup-existing');assert.ok(open);open.events.click();assert.equal(h.state.actions[0][0],'agent.focus');assert.equal(h.state.actions[0][1].terminal,'server/t2');
});

test('GPUI isolated mods ship identical copies of the shared transport',async()=>{
 const a=await readFile(new URL('../mods/project/transport.js',import.meta.url),'utf8');
 const b=await readFile(new URL('../mods/project-setup/transport.js',import.meta.url),'utf8');assert.equal(a,b);
});
