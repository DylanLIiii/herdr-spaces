import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import plugin,{tracker} from '../herdr_projects/integrations/opencode-status/index.js';
const defer=()=>{let resolve,reject;const promise=new Promise((r,j)=>{resolve=r;reject=j;});return {promise,resolve,reject};};
const turn=()=>new Promise(r=>setImmediate(r));
async function fixture(body){
 const dir=mkdtempSync(join(tmpdir(),'status-recovery-')),path=join(dir,'tty'),old={};
 for(const key of ['HERDR_RUN_ID','HERDR_SPACES_SESSION_ID','HERDR_SPACES_STATUS_TTY'])old[key]=process.env[key];
 Object.assign(process.env,{HERDR_RUN_ID:'test',HERDR_SPACES_SESSION_ID:'ses_root',HERDR_SPACES_STATUS_TTY:path});
 const queue=[],waiting=[];let ended=false;
 const stream={ [Symbol.asyncIterator](){return this;}, next(){if(queue.length)return Promise.resolve(queue.shift());if(ended)return Promise.resolve({done:true});return new Promise(r=>waiting.push(r));} };
 const push=e=>{const result={done:false,value:e};waiting.length?waiting.shift()(result):queue.push(result);};
 const close=()=>{ended=true;while(waiting.length)waiting.shift()({done:true});};
 let cleanup;
 try{await body({push,close,stream,output:()=>readFileSync(path,'utf8'),setCleanup:c=>cleanup=c});}
 finally{cleanup?.();close();for(const [key,value]of Object.entries(old)){if(value===undefined)delete process.env[key];else process.env[key]=value;}rmSync(dir,{recursive:true});}
}

test('missing or invalid snapshot timestamps do not imply idle',()=>{
 for(const time of [{},{busy:null,idle:null},{busy:'invalid',idle:'invalid'},{busy:NaN,idle:0}]){
  const s=tracker('ses_root');assert.equal(s.seed({id:'ses_root',time}),null);
 }
 const s=tracker('ses_root');assert.deepEqual(s.seed({id:'ses_root',time:{idle:2000}}),{state:'idle'});
 assert.deepEqual(s.seed({id:'ses_root',time:{busy:3000,idle:2000}}),{state:'working'});
});

test('busy event cannot skip an existing permission snapshot or expose premature working',async()=>fixture(async f=>{
 const permissions=defer();
 const setup=plugin.setup({event:{subscribe:()=>f.stream},session:{get:async()=>({id:'ses_root',time:{busy:2000,idle:1000}})},permission:{list:()=>permissions.promise}});
 f.push({type:'session.status',data:{sessionID:'ses_root',status:{type:'busy'}}});await turn();
 assert.doesNotMatch(f.output(),/state=working/);
 permissions.resolve([{id:'p1',sessionID:'ses_root'}]);f.setCleanup(await setup);
 assert.ok(f.output().endsWith('state=blocked:kind=permission\x1b\\'));
 f.push({type:'permission.replied',data:{sessionID:'ses_root',requestID:'p1'}});await turn();
 assert.ok(f.output().endsWith('state=working\x1b\\'));
}));

test('reply during snapshot removes the stale permission rather than resurrecting it',async()=>fixture(async f=>{
 const permissions=defer();
 const setup=plugin.setup({event:{subscribe:()=>f.stream},session:{get:async()=>({id:'ses_root',time:{busy:2000}})},permission:{list:()=>permissions.promise}});
 f.push({type:'permission.replied',data:{sessionID:'ses_root',requestID:'p1'}});await turn();
 permissions.resolve([{id:'p1',sessionID:'ses_root'}]);f.setCleanup(await setup);
 assert.ok(f.output().endsWith('state=working\x1b\\'));assert.doesNotMatch(f.output(),/state=blocked/);
}));

test('question arriving during snapshot is retained over an idle snapshot',async()=>fixture(async f=>{
 const snapshot=defer();
 const setup=plugin.setup({event:{subscribe:()=>f.stream},session:{get:()=>snapshot.promise},permission:{list:async()=>[]}});
 f.push({type:'form.created',data:{form:{id:'q',sessionID:'ses_root'}}});await turn();
 snapshot.resolve({id:'ses_root',time:{idle:2000}});f.setCleanup(await setup);
 assert.ok(f.output().endsWith('state=blocked:kind=question\x1b\\'));
}));

test('failed permission inspection cannot publish an apparently safe existing-session state',async()=>fixture(async f=>{
 const setup=plugin.setup({event:{subscribe:()=>f.stream},session:{get:async()=>({id:'ses_root',time:{idle:2000}})},permission:{list:async()=>{throw new Error('offline');}}});
 f.setCleanup(await setup);f.push({type:'session.status',data:{sessionID:'ses_root',status:{type:'busy'}}});await turn();
 assert.doesNotMatch(f.output(),/state=working|state=idle/);
}));

test('new session creation after a missing snapshot resumes event reporting without guessed idle',async()=>fixture(async f=>{
 f.setCleanup(await plugin.setup({event:{subscribe:()=>f.stream},session:{get:async()=>{throw new Error('not found');}},permission:{list:async()=>[]}}));
 assert.doesNotMatch(f.output(),/state=idle/);
 f.push({type:'session.created',data:{sessionID:'ses_root'}});await turn();assert.ok(f.output().endsWith('state=idle\x1b\\'));
 f.push({type:'session.execution.started',data:{sessionID:'ses_root'}});await turn();assert.ok(f.output().endsWith('state=working\x1b\\'));
}));

test('resolved blocker with unknown activity clears status and unrelated events do not overwrite it',async()=>fixture(async f=>{
 f.setCleanup(await plugin.setup({event:{subscribe:()=>f.stream},session:{get:async()=>({id:'ses_root',time:{}})},permission:{list:async()=>[{id:'p1',sessionID:'ses_root'}]}}));
 assert.ok(f.output().endsWith('state=blocked:kind=permission\x1b\\'));
 f.push({type:'session.status',data:{sessionID:'unrelated',status:{type:'busy'}}});await turn();
 assert.ok(f.output().endsWith('state=blocked:kind=permission\x1b\\'));
 f.push({type:'permission.replied',data:{sessionID:'ses_root',requestID:'p1'}});await turn();
 assert.ok(f.output().endsWith('state=clear\x1b\\'));
}));
