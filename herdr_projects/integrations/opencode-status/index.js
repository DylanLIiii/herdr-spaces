import { openSync, writeSync, closeSync } from 'node:fs';

// OpenCode V2 native session events, never screen/log heuristics. The fixed
// session id and private server bind this adapter to one managed Herdr terminal.
export function tracker(root) {
  const sessions=new Map([[root,{state:null,permissions:new Set(),forms:new Set()}]]);
  function apply(event) {
    const data=event.data||{},id=data.sessionID||data.form?.sessionID;
    if(event.type==='session.created'&&sessions.has(data.parentID)&&!sessions.has(id))sessions.set(id,{state:'idle',permissions:new Set(),forms:new Set()});
    const session=sessions.get(id);
    if(!session)return undefined;
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
      default:return undefined;
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
    const timestamp=value=>{
      if(value===null||value===undefined||value==='')return null;
      const n=typeof value==='number'?value:typeof value==='string'?(Number(value)||Date.parse(value)):NaN;
      return Number.isFinite(n)&&n>0?n:null;
    };
    const busy=timestamp(info.time?.busy),idle=timestamp(info.time?.idle);
    sessions.get(info.id).state=busy!==null&&(idle===null||busy>idle)?'working':
      info.outcome==='failed'?'error':idle!==null?'idle':null;
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
    // Buffer until both snapshots finish: an activity event must not cause a
    // permission snapshot to be discarded, nor publish a briefly unsafe state.
    // Replay then wins over stale snapshot entries (e.g. a permission replied
    // while permission.list was running). No model tokens are retained here.
    let initializing=true,verified=false;
    const buffered=[];
    const accepted=/^(session\.(created|status|execution\.(started|succeeded|failed|interrupted)|step\.started|idle)|permission\.(asked|replied)|form\.(created|replied|cancelled))$/;
    const applyEvent=event=>{
      if(event.type==='session.created'&&event.data?.sessionID===root)verified=true;
      return state.apply(event);
    };
    const publish=status=>{if(verified)send(status||{state:'clear'});else if(status?.state==='blocked')send(status);else send({state:'clear'});};
    const running=(async()=>{
      try{
        const stream=ctx.event.subscribe({signal:abort.signal});
        for await(const event of stream){
          if(closed)break;
          if(!accepted.test(event.type))continue;
          if(initializing){
            if(buffered.length>=1000)break; // Fail closed on an unbounded bootstrap.
            buffered.push(event);
          }else{const status=applyEvent(event);if(status!==undefined)publish(status);}
        }
      }catch{/* Loss of observation clears status; it is not an Agent failure. */}
      finally{endStream();}
    })();
    if(streamEnded)return cleanup;
    const [snapshot,permissions]=await Promise.allSettled([
      Promise.resolve().then(()=>ctx.session.get({sessionID:root},{signal:abort.signal})),
      Promise.resolve().then(()=>ctx.permission.list({sessionID:root},{signal:abort.signal}))
    ]);
    if(!closed&&!streamEnded){
      verified=snapshot.status==='fulfilled'&&snapshot.value?.id===root&&permissions.status==='fulfilled'&&Array.isArray(permissions.value);
      if(snapshot.status==='fulfilled'&&snapshot.value?.id===root)state.seed(snapshot.value);
      if(permissions.status==='fulfilled'&&Array.isArray(permissions.value)){
        for(const permission of permissions.value){
          if(permission.id&&(!permission.sessionID||permission.sessionID===root))
            state.apply({type:'permission.asked',data:{...permission,sessionID:root}});
        }
      }
      for(const event of buffered)applyEvent(event);
      initializing=false;buffered.length=0;
      publish(state.current());
    }
    void running;
    return cleanup;
  }
};
