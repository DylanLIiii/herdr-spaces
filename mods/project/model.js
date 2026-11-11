export const labels = {open:'待办', ready:'待执行', running:'进行中', blocked:'受阻', review:'待核验', accepted:'已完成', resolved:'已结案', cancelled:'已取消'};
export function groups(items) {
  return [['blocked','受阻',i=>i.status==='blocked'],['review','待核验',i=>i.status==='review'],
    ['active','进行中',i=>i.status==='running'],['ready','待执行',i=>i.status==='ready'],['todo','待办',i=>i.kind==='todo'&&i.status==='open'],
    ['done','已完成',i=>['accepted','resolved'].includes(i.status)],['cancelled','已取消',i=>i.status==='cancelled']]
    .map(([id,title,test])=>({id,title,items:items.filter(test)})).filter(g=>g.items.length);
}
export function summary(items) {
  const count=(states)=>items.filter(i=>states.includes(i.status)).length;
  return {pending:count(['open','ready']),running:count(['running']),done:count(['accepted','resolved']),blocked:count(['blocked']),review:count(['review'])};
}
export function needsAttention(item){return !['accepted','resolved','cancelled'].includes(item.status)&&(['blocked','review'].includes(item.status)||Boolean(item.waitingOn||item.question));}
export function needsPerson(item){return !['accepted','resolved','cancelled'].includes(item.status)&&item.question?.recipient==='user';}
export const setupLabels={pending:'等待 PM 询问',configuring:'配置中',deferred:'已暂缓',verifying:'配置已保存 · 待验证',ready:'配置就绪'};
export const roleLabels={pm:'PM',worker:'开发',explore:'代码探索',librarian:'资料查询',reviewer:'核验',research:'研究',oracle:'疑难分析'};
export const waitingLabels={pm:'等待 PM',user:'等待你',dependency:'等待依赖',environment:'等待环境'};
export const reviewLabels={accepted:'已核验',rejected:'需修订',review:'待核验'};
export const dispositionLabels={undecided:'尚未决定',adopted:'已采用',deferred:'暂缓采用',declined:'不采用'};
export const validityLabels={current:'当前版本',stale:'需要复核',superseded:'已被替代'};
export function artifactMatches(artifact,query){return !query||[artifact.title,artifact.kind,artifact.sourceRef,...(artifact.claims||[]).map(c=>c.text)].join(' ').toLowerCase().includes(query.toLowerCase());}
export function statusColor(status,t) {
  if(['blocked','review'].includes(status))return t.blocked;
  if(status==='running')return t.working;
  if(['accepted','resolved'].includes(status))return t.done;
  return t.muted;
}
export function findNode(node,id) {
  if (node?.id===id) return node;
  for (const child of node?.children??[]) { const found=findNode(child,id); if(found)return found; }
  return null;
}
export function location(focus, allPanes, allSpaces) {
  const space=allSpaces.find(s=>s.active);
  const terminal=focus ? focus.terminal : allPanes.find(p=>p.focused)?.terminal;
  // A peek/layout terminal can belong to another machine than the active Space.
  const parts=terminal?.split('/')||[];
  const machine=terminal?(parts.length>1?parts[0]:null):space?.machine||null;
  return {terminal:terminal||null, localTerminal:terminal?(parts.length>1?parts.slice(1).join('/'):terminal):null,
    machine, space:space?.id||null};
}
export function terminalAddress(record, machine, scopes) {
  if(!record?.terminal||record.terminal.includes('/')||(record.scope&&!scopes.includes(record.scope)))return null;
  return machine?machine+'/'+record.terminal:record.terminal;
}
export function sessionStatus(record,live) {
  if (record.state==='exited') return '执行已退出';
  if (!live) return record.state==='inactive'?'尚未启动':record.state==='starting'?'正在启动':'无法观测';
  return ({working:'运行中',blocked:'等待输入',idle:'空闲',done:'本轮结束'})[live.status] || '状态未知';
}
