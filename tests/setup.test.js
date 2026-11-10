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
 const h=await host();await h.respond({capabilities:['leader-bind','core-command-discovery','pm-configuration']});
 await h.respond({...catalog,projects:[{id:'existing',name:'Existing',goal:'Goal',cwd:'/srv/repo',main:{state:'running',terminal:'t2',scope:'core:server',generation:3}}]});
 h.view.selected='existing';h.view.save(h.cx);assert.equal(h.state.pending.length,0);
 const open=find(h.view.render(h.cx),'setup-existing');assert.ok(open);open.events.click();assert.equal(h.state.actions[0][0],'agent.focus');assert.equal(h.state.actions[0][1].terminal,'server/t2');
});

test('setup upgrades an existing 0.3.0 runtime before asking it to call Core',async()=>{
 const h=await host();await h.respond({version:'0.3.0',capabilities:['leader-bind','guarded-introduction']});
 assert.equal(h.state.pending[0].args[1],'bootstrap source');assert.equal(h.state.pending[0].options.on,'server');
 await h.respond({prepared:true});assert.equal(h.state.pending[0].args.at(-3),'setup');
 await h.respond(catalog);assert.ok(h.view.catalog);assert.equal(h.state.pending.length,0);h.view.close();
});

test('rebind requires a separate confirmation and passes the observed generation and SubAgent preferences',async()=>{
 const h=await host();await h.respond({capabilities:['leader-bind','core-command-discovery','pm-configuration']});
 await h.respond({...catalog,projects:[{id:'existing',name:'Existing',goal:'Goal',cwd:'/srv/repo',pmSkill:'/srv/skills/pm/SKILL.md',subAgent:{backend:'codex',model:'saved-model'},main:{state:'running',terminal:'t2',scope:'core:server',generation:3}}]});
 find(h.view.render(h.cx),'choose-existing').events.click({},h.cx);
 assert.equal(h.view.backend,'codex');assert.equal(h.view.fields.model.value(),'saved-model');assert.equal(h.view.fields.pmSkill.value(),'/srv/skills/pm/SKILL.md');
 find(h.view.render(h.cx),'setup-rebind').events.click({},h.cx);assert.equal(h.state.pending.length,0);
 find(h.view.render(h.cx),'setup-rebind-confirm').events.click({},h.cx);
 const argv=h.state.pending[0].args;assert.equal(argv[argv.indexOf('--replace-generation')+1],'3');assert.equal(argv[argv.indexOf('--worker-backend')+1],'codex');assert.equal(argv[argv.indexOf('--worker-model')+1],'saved-model');
 await h.respond({project:{id:'existing',name:'Existing',main:{terminal:'t1',generation:4,scope:'core:server'}}});
 assert.equal(h.state.pending[0].args.at(-1),'4');await h.respond({state:'sent'});assert.equal(h.state.error,undefined);
});

test('choosing another project resets replacement consent and backend changes clear incompatible models',async()=>{
 const h=await host();await h.respond({capabilities:['leader-bind','core-command-discovery','pm-configuration']});await h.respond(catalog);
 h.view.replacing=true;h.view.fields.model.text='old-model';
 find(h.view.render(h.cx),'tool-claude').events.click({},h.cx);assert.equal(h.view.fields.model.value(),'');assert.equal(h.view.backend,'claude');
 h.view.select('new');assert.equal(h.view.replacing,false);assert.equal(h.view.backend,'pi');assert.equal(h.state.pending.length,0);
});

test('a runtime with binding support but no PM configuration is upgraded',async()=>{
 const h=await host();await h.respond({capabilities:['leader-bind','core-command-discovery']});
 assert.equal(h.state.pending[0].args[1],'bootstrap source');await h.respond({prepared:true});await h.respond(catalog);assert.ok(h.view.catalog);
});

test('retry after introduction failure never repeats the successful binding',async()=>{
 const h=await host();await h.respond({capabilities:['leader-bind','core-command-discovery','pm-configuration']});await h.respond(catalog);
 h.view.fields.goal.text='Goal';h.view.save(h.cx);
 await h.respond({project:{id:'new-project',name:'repo',main:{terminal:'t1',generation:1,scope:'core:server'},subAgent:{backend:'pi',model:null}}});
 await h.respond({error:'connection lost'},1);assert.ok(h.view.bound);assert.ok(h.view.error);
 find(h.view.render(h.cx),'setup-retry').events.click({},h.cx);
 assert.ok(h.state.pending[0].args.includes('introduce'));assert.ok(!h.state.pending[0].args.includes('bind'));
 await h.respond({state:'sent'});assert.equal(h.view.notice.state,'sent');assert.equal(h.state.error,undefined);
});

test('custom Skill must be filled while the built-in option clears a previous path',async()=>{
 const h=await host();await h.respond({capabilities:['leader-bind','core-command-discovery','pm-configuration']});await h.respond(catalog);
 h.view.fields.goal.text='Goal';find(h.view.render(h.cx),'skill-custom').events.click({},h.cx);h.view.save(h.cx);
 assert.equal(h.state.pending.length,0);assert.match(h.view.error,/Skill/);
 h.view.fields.pmSkill.text='/old/skill';find(h.view.render(h.cx),'skill-builtin').events.click({},h.cx);h.view.save(h.cx);
 const args=h.state.pending[0].args;assert.equal(args[args.indexOf('--pm-skill')+1],'');h.view.close();
});

test('foreign Core projects cannot be rebound even if the old PM exited',async()=>{
 const h=await host();await h.respond({capabilities:['leader-bind','core-command-discovery','pm-configuration']});
 await h.respond({...catalog,projects:[{id:'other',name:'Other',goal:'Goal',cwd:'/repo',main:{state:'exited',terminal:'t2',scope:'core:other',generation:2}}]});
 h.view.select('other');assert.equal(h.view.ready(),false);h.view.save(h.cx);assert.equal(h.state.pending.length,0);
});

test('existing PM opens a settings summary, edits only on demand, and preserves hidden preferences on save',async()=>{
 const h=await host();await h.respond({capabilities:['leader-bind','core-command-discovery','pm-configuration']});
 const project={id:'existing',name:'Existing',goal:'Goal',cwd:'/repo',pmSkill:'/custom/SKILL.md',subAgent:{backend:'codex',model:'saved'},main:{state:'running',terminal:'t1',scope:'core:server',generation:3}};
 await h.respond({...catalog,binding:{project_id:'existing'},projects:[project]});
 assert.equal(find(h.view.render(h.cx),'tool-pi'),null);assert.equal(h.view.fieldKeys().length,0);
 find(h.view.render(h.cx),'edit-worker').events.click({},h.cx);assert.ok(find(h.view.render(h.cx),'tool-pi'));assert.deepEqual([...h.view.fieldKeys()],['model']);
 find(h.view.render(h.cx),'tool-claude').events.click({},h.cx);assert.equal(h.view.fields.model.value(),'');
 find(h.view.render(h.cx),'edit-worker').events.click({},h.cx);h.view.save(h.cx);
 const argv=h.state.pending[0].args;assert.equal(argv[argv.indexOf('--pm-skill')+1],'/custom/SKILL.md');assert.equal(argv[argv.indexOf('--worker-backend')+1],'claude');assert.equal(argv[argv.indexOf('--replace-generation')+1],'3');h.view.close();
});

test('invalid custom Skill returns from handoff confirmation to its editor without a bind',async()=>{
 const h=await host();await h.respond({capabilities:['leader-bind','core-command-discovery','pm-configuration']});
 await h.respond({...catalog,projects:[{id:'existing',name:'Existing',goal:'Goal',cwd:'/repo',main:{state:'running',terminal:'t2',scope:'core:server',generation:3}}]});
 h.view.select('existing');h.view.customSkill=true;h.view.fields.pmSkill.text='';h.view.replacing=true;h.view.save(h.cx);
 assert.equal(h.state.pending.length,0);assert.equal(h.view.replacing,false);assert.equal(h.view.editing.has('skill'),true);assert.match(h.view.error,/Skill/);
});

test('GPUI isolated mods ship identical copies of the shared transport',async()=>{
 const a=await readFile(new URL('../mods/project/transport.js',import.meta.url),'utf8');
 const b=await readFile(new URL('../mods/project-setup/transport.js',import.meta.url),'utf8');assert.equal(a,b);
});
