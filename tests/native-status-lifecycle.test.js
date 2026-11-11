import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import plugin from '../herdr_projects/integrations/opencode-status/index.js';

function deferred(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
const turn=()=>new Promise(r=>setImmediate(r));
async function harness(run){
 const dir=mkdtempSync(join(tmpdir(),'spaces-status-')),file=join(dir,'tty');
 const previous={};for(const key of ['HERDR_RUN_ID','HERDR_SPACES_SESSION_ID','HERDR_SPACES_STATUS_TTY'])previous[key]=process.env[key];
 Object.assign(process.env,{HERDR_RUN_ID:'fixture',HERDR_SPACES_SESSION_ID:'ses_test',HERDR_SPACES_STATUS_TTY:file});
 try{await run(()=>readFileSync(file,'utf8'));}finally{for(const [key,value]of Object.entries(previous)){if(value===undefined)delete process.env[key];else process.env[key]=value;}rmSync(dir,{recursive:true});}
}

test('normal stream exhaustion clears a previously emitted working status',async()=>harness(async output=>{
 const end=deferred();
 const cleanup=await plugin.setup({event:{subscribe:async function*(){yield {type:'session.status',data:{sessionID:'ses_test',status:{type:'busy'}}};await end.promise;}},session:{get:async()=>({id:'ses_test',time:{}})},permission:{list:async()=>[]}});
 await turn();assert.match(output(),/state=working/);end.resolve();await turn();
 assert.ok(output().endsWith('state=clear\x1b\\'));cleanup();
}));

for(const fails of [false,true])test('late snapshot cannot revive '+(fails?'failed':'closed')+' subscription',async()=>harness(async output=>{
 const snapshot=deferred();
 const pending=plugin.setup({event:{subscribe:async function*(){if(fails)throw new Error('disconnected');}},session:{get:()=>snapshot.promise},permission:{list:async()=>[]}});
 await turn();snapshot.resolve({id:'ses_test',time:{busy:2000,idle:1000}});const cleanup=await pending;await turn();
 assert.doesNotMatch(output(),/state=working|state=idle/);assert.ok(output().endsWith('state=clear\x1b\\'));cleanup();
}));

test('synchronous subscribe failure clears and releases the adapter',async()=>harness(async output=>{
 const cleanup=await plugin.setup({event:{subscribe(){throw new Error('offline');}},session:{get:async()=>({id:'ses_test',time:{}})},permission:{list:async()=>[]}});
 assert.ok(output().endsWith('state=clear\x1b\\'));cleanup();
}));
