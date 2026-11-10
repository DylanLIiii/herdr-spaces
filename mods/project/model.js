export const labels = {open:'待办', ready:'待执行', running:'进行中', blocked:'受阻', review:'待核验', accepted:'已完成', resolved:'已结案', cancelled:'已取消'};
export function groups(items) {
  return [['todo','待办',i=>i.kind==='todo'&&i.status==='open'],['ready','待执行',i=>i.status==='ready'],
    ['active','进行中',i=>['running','blocked'].includes(i.status)],['review','待核验',i=>i.status==='review'],
    ['done','已完成',i=>['accepted','resolved'].includes(i.status)],['cancelled','已取消',i=>i.status==='cancelled']]
    .map(([id,title,test])=>({id,title,items:items.filter(test)})).filter(g=>g.items.length);
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
