import test from 'node:test';
import assert from 'node:assert/strict';
import {tracker,frame} from '../herdr_projects/integrations/opencode-status/index.js';

test('only scoped native events change status; tokens and tool progress do not invent it',()=>{
 const s=tracker('ses_root');
 assert.equal(s.current(),null);
 assert.equal(s.apply({type:'session.execution.started',data:{sessionID:'other'}}),undefined);
 assert.equal(s.apply({type:'session.message.delta',data:{sessionID:'ses_root',text:'working'}}),undefined);
 assert.deepEqual(s.apply({type:'session.status',data:{sessionID:'ses_root',status:{type:'busy'}}}),{state:'working'});
 assert.deepEqual(s.apply({type:'permission.asked',data:{sessionID:'ses_root',id:'p1'}}),{state:'blocked',kind:'permission'});
 assert.deepEqual(s.apply({type:'session.status',data:{sessionID:'ses_root',status:{type:'busy'}}}),{state:'blocked',kind:'permission'});
 assert.deepEqual(s.apply({type:'permission.replied',data:{sessionID:'ses_root',requestID:'p1'}}),{state:'working'});
 assert.deepEqual(s.apply({type:'session.execution.succeeded',data:{sessionID:'ses_root'}}),{state:'done'});
 assert.equal(frame(s.current()),'\x1b]7501;app=opencode:state=done\x1b\\');
});

test('native descendant activity and questions are reflected without other-session leakage',()=>{
 const s=tracker('ses_root');
 s.apply({type:'session.created',data:{sessionID:'ses_root'}});
 s.apply({type:'session.created',data:{sessionID:'ses_child',parentID:'ses_root'}});
 assert.deepEqual(s.apply({type:'session.execution.started',data:{sessionID:'ses_child'}}),{state:'working'});
 assert.deepEqual(s.apply({type:'form.created',data:{form:{id:'q',sessionID:'ses_child'}}}),{state:'blocked',kind:'question'});
 assert.deepEqual(s.apply({type:'form.replied',data:{id:'q',sessionID:'ses_child'}}),{state:'working'});
 s.apply({type:'session.execution.succeeded',data:{sessionID:'ses_child'}});
 assert.deepEqual(s.current(),{state:'idle'});
});

test('recovery seeds from actual execution timestamps, not process existence',()=>{
 const s=tracker('ses_root');
 assert.deepEqual(s.seed({id:'ses_root',time:{busy:2000,idle:1000}}),{state:'working'});
 assert.deepEqual(s.seed({id:'ses_root',time:{busy:1000,idle:2000},outcome:'failed'}),{state:'error'});
 assert.equal(frame({state:'invented'}),'');
});
