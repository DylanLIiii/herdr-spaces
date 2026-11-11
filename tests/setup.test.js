import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const turn=()=>new Promise(resolve=>setImmediate(resolve));
const probe={capabilities:['leader-bind','core-command-discovery','pm-configuration','guided-setup','artifact-bundles']};
function element(){const target={nodes:[],events:{},child(x){this.nodes.push(x);return proxy;},children(xs){this.nodes.push(...xs);return proxy;},when(on,f){if(on)f(proxy);return proxy;},id(x){this.key=x;return proxy;}};
 const proxy=new Proxy(target,{get:(t,k)=>k in t?typeof t[k]==='function'?t[k].bind(t):t[k]:(...args)=>{if(k==='on_click')t.events.click=args[0];return proxy;}});return proxy;}
function find(root,key){if(root?.key===key)return root;for(const n of root?.nodes||[]){const r=find(n,key);if(r)return r;}return null;}
function allText(root){return typeof root==='string'?root:(root?.nodes||[]).map(allText).join(' ');}
const catalog={coreScope:'core:server',terminal:'t1',cwd:'/srv/repo',suggestedName:'repo',newProjectId:'new-project',projects:[]};
async function host(){
 const state={pending:[],actions:[]};const cx={notify(){},stop_propagation(){},focus_handle:()=>({focus(){}}),spawn(fn){fn(cx).catch(e=>{state.error=e;});}};
 const config={terminal:'server/t1',entry:'/local/project.py',bootstrap:'/local/bootstrap.py',bundle:'/local/bundle.json',overlay:'overlay'};
 const exports={
  'gpui-kit':{View:class{},div:element},
  'gpui-base':{v_flex:element,h_flex:element,Input:{new:element},InputState:{new:({value})=>{const f={text:value,callbacks:{},value(){return this.text;},set_value(value){this.text=value;},on(k,cb){this.callbacks[k]=cb;},focus(){this.callbacks.focus?.({},cx);}};return f;}}},
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
const existing=(terminal='t2')=>({id:'existing',name:'Existing',goal:'Goal',cwd:'/srv/repo',pmSkill:'/srv/skills/pm/SKILL.md',subAgent:{backend:'codex',model:'saved-model'},setup:{state:'deferred',answers:{work:'research'},nextAction:'稍后继续'},main:{state:'running',terminal,scope:'core:server',generation:3}});

test('first use binds the PM without asking for models and sends the setup Skill introduction',async()=>{
 const h=await host();await h.respond({code:'runtime_missing'},2);
 assert.deepEqual([...h.state.pending[0].args],['-c','bootstrap source','projects','{}']);assert.equal(h.state.pending[0].options.on,'server');
 await h.respond({prepared:true});await h.respond(catalog);
 let root=h.view.render(h.cx);assert.equal(find(root,'tool-pi'),null);assert.equal(find(root,'skill-custom'),null);assert.match(allText(root),/PM 会先询问/);
 h.view.fields.goal.text='Deliver a useful result';h.view.save(h.cx);
 const args=h.state.pending[0].args;assert.ok(args.includes('bind'));assert.ok(!args.includes('--worker-backend'));assert.ok(!args.includes('--worker-model'));
 await h.respond({project:{id:'new-project',name:'repo',setup:{state:'pending'},main:{terminal:'t1',generation:1,scope:'core:server'}}});
 assert.ok(h.state.pending[0].args.includes('introduce'));await h.respond({state:'sent'});
 root=h.view.render(h.cx);assert.match(allText(root),/PM 已绑定/);assert.match(allText(root),/不代表配置已完成/);assert.equal(h.state.error,undefined);
});

test('closing while preparing cannot bind or type into the terminal',async()=>{
 const h=await host();await h.respond({code:'runtime_missing'},2);h.view.close();await h.respond({prepared:true});assert.equal(h.state.pending.length,0);assert.equal(h.view.bound,null);
});

test('old runtime with PM configuration but no guided setup gets upgraded',async()=>{
 const h=await host();await h.respond({capabilities:['leader-bind','core-command-discovery','pm-configuration']});
 assert.equal(h.state.pending[0].args[1],'bootstrap source');await h.respond({prepared:true});await h.respond(catalog);assert.ok(h.view.catalog);
});

test('existing PM is opened without silently reassigning it',async()=>{
 const h=await host();await h.respond(probe);await h.respond({...catalog,projects:[existing()]});h.view.select('existing');h.view.save(h.cx);assert.equal(h.state.pending.length,0);
 find(h.view.render(h.cx),'setup-existing').events.click();assert.equal(h.state.actions[0][1].terminal,'server/t2');
});

test('handoff requires separate confirmation and preserves team configuration',async()=>{
 const h=await host();await h.respond(probe);await h.respond({...catalog,projects:[existing()]});find(h.view.render(h.cx),'choose-existing').events.click({},h.cx);
 find(h.view.render(h.cx),'setup-rebind').events.click({},h.cx);assert.equal(h.state.pending.length,0);
 find(h.view.render(h.cx),'setup-rebind-confirm').events.click({},h.cx);
 const argv=h.state.pending[0].args;assert.equal(argv[argv.indexOf('--replace-generation')+1],'3');assert.ok(!argv.includes('--worker-backend'));assert.ok(!argv.includes('--worker-model'));
 await h.respond({project:{...existing('t1'),main:{terminal:'t1',generation:4,scope:'core:server'}}});await h.respond({state:'sent'});assert.equal(h.state.error,undefined);
});

test('deferred setup resumes in the same PM without changing configuration from the UI',async()=>{
 const h=await host();await h.respond(probe);await h.respond({...catalog,binding:{project_id:'existing'},projects:[existing('t1')]});
 const root=h.view.render(h.cx);assert.match(allText(root),/已暂缓/);find(root,'setup-continue').events.click();
 assert.equal(h.state.actions[0][0],'agent.focus');assert.equal(h.state.actions[0][1].terminal,'server/t1');assert.equal(h.state.pending.length,0);
});

test('uncertain introduction is displayed honestly without automatic resend',async()=>{
 const h=await host();await h.respond(probe);await h.respond(catalog);h.view.fields.goal.text='Goal';h.view.save(h.cx);
 await h.respond({project:{id:'new-project',name:'repo',main:{terminal:'t1',generation:1,scope:'core:server'}}});await h.respond({state:'uncertain',message:'read Skill'});
 assert.match(allText(h.view.render(h.cx)),/送达待确认/);assert.equal(h.state.pending.length,0);assert.equal(find(h.view.render(h.cx),'setup-introduce'),null);
});

test('retry after introduction failure never repeats successful binding',async()=>{
 const h=await host();await h.respond(probe);await h.respond(catalog);h.view.fields.goal.text='Goal';h.view.save(h.cx);
 await h.respond({project:{id:'new-project',name:'repo',main:{terminal:'t1',generation:1,scope:'core:server'}}});await h.respond({error:'connection lost'},1);
 find(h.view.render(h.cx),'setup-retry').events.click({},h.cx);assert.ok(h.state.pending[0].args.includes('introduce'));assert.ok(!h.state.pending[0].args.includes('bind'));
 await h.respond({state:'waiting',message:'context'});assert.ok(find(h.view.render(h.cx),'setup-introduce'));assert.equal(h.state.error,undefined);
});

test('advanced custom PM Skill stays available without becoming a first-use form requirement',async()=>{
 const h=await host();await h.respond(probe);await h.respond(catalog);h.view.fields.goal.text='Goal';
 find(h.view.render(h.cx),'edit-skill').events.click({},h.cx);find(h.view.render(h.cx),'skill-custom').events.click({},h.cx);h.view.save(h.cx);
 assert.equal(h.state.pending.length,0);assert.match(h.view.error,/Skill/);h.view.fields.pmSkill.text='/old/skill';find(h.view.render(h.cx),'skill-builtin').events.click({},h.cx);h.view.save(h.cx);
 const args=h.state.pending[0].args;assert.equal(args[args.indexOf('--pm-skill')+1],'');h.view.close();
});

test('foreign Core projects cannot be rebound even when exited',async()=>{
 const h=await host();await h.respond(probe);await h.respond({...catalog,projects:[{...existing(),main:{state:'exited',terminal:'t2',scope:'core:other',generation:2}}]});
 h.view.select('existing');assert.equal(h.view.ready(),false);h.view.save(h.cx);assert.equal(h.state.pending.length,0);
});

test('configuration summary distinguishes fixture checks from observed verification',async()=>{
 const h=await host();await h.respond(probe);const p=existing('t1');p.setup={state:'verifying',checks:[{key:'reporting',status:'passed',mode:'fixture'}]};p.configuration={revision:1,roles:{research:{enabled:true,backend:'feynman'}}};
 await h.respond({...catalog,binding:{project_id:'existing'},projects:[p]});const root=h.view.render(h.cx);assert.match(allText(root),/待验证/);assert.match(allText(root),/协议模拟通过/);assert.match(allText(root),/feynman/);assert.equal(find(root,'tool-pi'),null);
});

test('GPUI isolated mods ship identical transport copies',async()=>{
 const a=await readFile(new URL('../mods/project/transport.js',import.meta.url),'utf8');const b=await readFile(new URL('../mods/project-setup/transport.js',import.meta.url),'utf8');assert.equal(a,b);
});
