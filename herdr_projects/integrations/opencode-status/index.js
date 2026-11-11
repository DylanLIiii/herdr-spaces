import { openSync, writeSync, closeSync } from 'node:fs';

// OpenCode V2 native session events, never screen/log heuristics. The fixed
// session id and private server bind this adapter to one managed Herdr terminal.
export function tracker(root) {
  const sessions=new Map([[root,{state:null,permissions:new Set(),forms:new Set()}]]);
  function apply(event) {
    const data=event.data||{},id=data.sessionID||data.form?.sessionID;
    if(event.type==='session.created'&&sessions.has(data.parentID)&&!sessions.has(id))sessions.set(id,{state:'idle',permissions:new Set(),forms:new Set()});
    const session=sessions.get(id);
    if(!session)return null;
    switch(event.type){
      case 'session.created': session.state='idle';break;
      case 'session.status':
        if(['busy','retry'].includes(data.status?.type))session.state='working';
        else if(data.status?.type==='idle')session.state='idle';
        break;
      case 'session.execution.started':case 'session.step.started':session.state='working';break;
      case 'session.execution.succeeded':session.state='done';break;
      case 'session.execution.interrupted':case 'session.idle':session.state='idle';break;
      case 'session.execution.failed':session.state='error';break;
      case 'permission.asked':session.permissions.add(data.id);break;
      case 'permission.replied':session.permissions.delete(data.requestID);break;
      case 'form.created':session.forms.add(data.form.id);break;
      case 'form.replied':case 'form.cancelled':session.forms.delete(data.id);break;
      default:return null;
    }
    return current();
  }
  function current(){
    const values=[...sessions.values()];
    if(values.some(s=>s.permissions.size))return {state:'blocked',kind:'permission'};
    if(values.some(s=>s.forms.size))return {state:'blocked',kind:'question'};
    if(values.some(s=>s.state==='working'))return {state:'working'};
    const state=sessions.get(root).state;
    return state?{state}:null;
  }
  function seed(info){
    if(!sessions.has(info.id))return;
    const busy=Date.parse(info.time?.busy)||Number(info.time?.busy)||0,idle=Date.parse(info.time?.idle)||Number(info.time?.idle)||0;
    sessions.get(info.id).state=busy>idle?'working':info.outcome==='failed'?'error':'idle';
    return current();
  }
  return {apply,seed,current};
}

export function frame(status){
  if(!status||!['idle','working','blocked','done','error','clear'].includes(status.state))return '';
  return '\x1b]7501;app=opencode:state='+status.state+(status.kind?':kind='+status.kind:'')+'\x1b\\';
}

export default {
  id:'herdr-spaces-native-status',
  async setup(ctx){
    const root=process.env.HERDR_SPACES_SESSION_ID,tty=process.env.HERDR_SPACES_STATUS_TTY;
    if(!root||!tty||!process.env.HERDR_RUN_ID)return;
    const fd=openSync(tty,'w'),state=tracker(root),abort=new AbortController();
    let closed=false,streamEnded=false,last='';
    const send=status=>{const output=frame(status);if(!closed&&output&&output!==last){writeSync(fd,output);last=output;}};
    const cleanup=()=>{if(closed)return;try{send({state:'clear'});}finally{closed=true;abort.abort();closeSync(fd);}};
    const endStream=()=>{streamEnded=true;cleanup();};
    // Subscribe before reading a snapshot; if an event wins, do not overwrite it
    // with older state from the snapshot request.
    let events=0;
    const running=(async()=>{
      try{
        const stream=ctx.event.subscribe({signal:abort.signal});
        for await(const event of stream){if(closed)break;const status=state.apply(event);if(status){events++;send(status);}}
      }catch{/* Loss of observation clears status; it is not an Agent failure. */}
      finally{endStream();}
    })();
    if(streamEnded)return cleanup;
    try{
      const info=await ctx.session.get({sessionID:root});
      const permissions=await ctx.permission.list({sessionID:root});
      if(!closed&&!streamEnded&&!events){
        state.seed(info);
        for(const permission of permissions)state.apply({type:'permission.asked',data:{...permission,sessionID:root}});
        send(state.current());
      }
    }catch{/* A fresh named session is created by the first prompt. Wait for its event. */}
    void running;
    return cleanup;
  }
};
