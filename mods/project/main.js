import { View, div, svg } from 'gpui-kit';
import { h_flex, v_flex, TextView } from 'gpui-base';
import { props, exec, spaces, panes, focused, terminals, theme, run, layout, nextCommand, openOverlay } from 'herdr';
import { groups, labels, summary, needsAttention, statusColor, findNode, location, sessionStatus, terminalAddress } from './model.js';
import { callRuntime, validateSnapshot } from './transport.js';

const caption = (s,t) => div().text_size(11).text_color(t.muted).child(s);
const paragraph = (s,t) => div().text_size(12).text_color(t.foreground).child(s);
const badge = (label,color,t) => h_flex().flex_none().px(6).py(3).gap(5).items_center().rounded(5).bg(t.raised)
  .child(div().size(5).rounded(3).bg(color)).child(div().text_size(11).text_color(color).child(label));
const button = (id,label,action,t,selected=false) => h_flex().id(id).px(8).py(6).gap(6).rounded(6).cursor_pointer()
  .text_size(12).text_color(selected?t.foreground:t.muted).bg(selected?t.selected:t.background)
  .hover(s=>s.bg(t.hover).text_color(t.foreground)).on_click(action).child(label);

export default class Project extends View {
  init(initial,cx) {
    const p=initial??props()??{};
    this.config=p; this.origin=null;
    this.closed=false; this.key=null; this.epoch=0; this.ticket=0; this.busy=false;
    this.project=null; this.error=null; this.tab='tasks'; this.detail=null; this.file=null; this.preview=null;
    this.folded=new Set(['done','cancelled']); this.attentionOnly=false; this.selected=null; this.focus=cx.focus_handle();
    this.refresh(cx);
    // Only the external ledger is polled. Native terminal/focus/theme data is reactive.
    cx.timer.every(5000,cx=>{ if(this.visible()&&!this.closed)this.refresh(cx); });
    cx.spawn(async cx=>{
      while(!this.closed) {
        const cmd=await nextCommand(); if(this.closed)return;
        if(cmd==='focus')this.focus.focus();
        else if(cmd==='refresh')this.refresh(cx);
        else if(cmd==='setup')this.setup();
        else if(['tasks','sessions','files'].includes(cmd)){this.tab=cmd;this.detail=null;this.file=null;}
        cx.notify();
      }
    });
  }
  close(){this.closed=true;this.epoch++;this.ticket++;}
  visible(){const root=layout(),panel=findNode(root,'panel'),body=findNode(root,'panel-body');return !panel||(!panel.hidden&&body?.active==='project');}
  currentLocation(){return location(focused(),panes(),spaces());}
  currentKey(){return JSON.stringify(this.currentLocation());}
  call(args,loc) {return callRuntime(this.config,args,loc,exec);}
  setup(terminal=this.currentLocation().terminal) {
    if(terminal)openOverlay({mod:this.config.setupMod||'project-setup',kind:'dialog',width:600,height:720,
      props:{...this.config,terminal}});
  }
  address(record){return this.origin?terminalAddress(record,this.origin.machine,this.origin.coreScopes):null;}
  live(record){const address=this.address(record);return address?terminals().find(t=>t.address===address):null;}
  refresh(cx) {
    if(this.closed)return;
    const key=this.currentKey(), loc=this.currentLocation();
    if(key!==this.key){this.key=key;this.epoch++;this.project=null;this.origin=null;this.detail=null;this.file=null;this.preview=null;this.error=null;this.busy=false;this.tab='tasks';this.attentionOnly=false;this.selected=null;}
    if(this.busy||!loc.terminal)return;
    const epoch=this.epoch, ticket=++this.ticket;
    this.busy=true;
    cx.spawn(async cx=>{
      try {
        const snapshot=validateSnapshot(await this.call(['snapshot','--terminal',loc.localTerminal],loc));
        if(this.closed||epoch!==this.epoch||key!==this.currentKey()||ticket!==this.ticket)return;
        const changed=this.origin&&(this.origin.coreScopes[0]!==snapshot.coreScopes[0]||this.origin.ledgerHome!==snapshot.ledgerHome||this.project?.id!==snapshot.project?.id);
        if(changed){this.epoch++;this.detail=null;this.file=null;this.preview=null;this.busy=false;}
        this.project=snapshot.project;this.origin={...loc,coreScopes:snapshot.coreScopes,ledgerHome:snapshot.ledgerHome};this.error=null;cx.notify();
      } catch(e) {if(!this.closed&&epoch===this.epoch&&key===this.currentKey()&&ticket===this.ticket)this.error=e;}
      finally {if(!this.closed&&epoch===this.epoch&&ticket===this.ticket){this.busy=false;cx.notify();}}
    });
  }
  navigate(record,cx) {
    if(this.key!==this.currentKey()){this.refresh(cx);return;}
    const address=this.address(record),live=this.live(record);
    if(!live){this.error='此执行终端已退出或不可访问。项目记录仍保留；请在项目所在机器使用 herdr-project start / reconcile 恢复。';cx.notify();return;}
    if(panes().some(p=>p.terminal===address))run('pane.focus',{terminal:address});
    else run('terminal.peek',{terminal:address});
  }
  openFile(id,cx) {
    if(!this.origin||this.key!==this.currentKey()){this.refresh(cx);return;}
    this.file=id;this.detail=null;this.preview=null;
    const epoch=this.epoch,projectId=this.project.id,key=this.key,origin=this.origin;
    const current=()=>!this.closed&&this.epoch===epoch&&key===this.currentKey()&&this.file===id;
    cx.spawn(async cx=>{
      try {const data=await this.call(['read','--project',projectId,'--artifact',id,'--core-scope',origin.coreScopes[0],'--ledger-home',origin.ledgerHome],origin);
        if(data.protocolVersion!==1||data.coreScope!==origin.coreScopes[0]||data.ledgerHome!==origin.ledgerHome)throw new Error('资料来源已改变，请刷新项目记录。');
        if(current())this.preview=data;
      } catch(e){if(current())this.preview={error:String(e)};}
      if(!this.closed)cx.notify();
    });cx.notify();
  }
  keyboardRows() {
    const p=this.project;if(!p||this.detail||this.file)return [];
    if(this.tab==='tasks')return groups(p.items.filter(i=>!this.attentionOnly||needsAttention(i))).filter(g=>!this.folded.has(g.id)).flatMap(g=>g.items.map(i=>({key:'item:'+i.id,open:cx=>{this.detail=i.id;cx.notify();}})));
    if(this.tab==='sessions')return [p.main,...p.runs.slice().reverse()].map(r=>({key:'session:'+r.id,open:cx=>this.navigate(r,cx)}));
    return [{id:'pm'},...p.artifacts].map(a=>({key:'file:'+a.id,open:cx=>this.openFile(a.id,cx)}));
  }
  handleKey(e,cx) {
    if(['1','2','3'].includes(e.key)){this.tab=['tasks','sessions','files'][Number(e.key)-1];this.detail=null;this.file=null;this.selected=null;}
    else if(e.key==='r')this.refresh(cx);
    else if(e.key==='escape'||e.key==='left'){this.detail=null;this.file=null;}
    else if(['down','up','enter'].includes(e.key)){
      const rows=this.keyboardRows();if(!rows.length)return;
      const at=rows.findIndex(r=>r.key===this.selected);
      if(e.key==='enter'){if(at>=0)rows[at].open(cx);}
      else this.selected=rows[e.key==='down'?(at+1)%rows.length:(at<0?rows.length-1:(at+rows.length-1)%rows.length)].key;
    }else return;
    cx.stop_propagation();cx.notify();
  }
  section(title,children,t) {return v_flex().gap(8).mb(18).child(caption(title,t)).children(children);}
  itemRow(i,t) {
    const sub=i.status==='blocked'?(i.resolution||i.nextAction||i.brief):i.nextAction||i.brief;
    const worker=this.project.runs.find(r=>r.id===i.activeRunId),steps=i.checklist||[];
    return v_flex().id('work-'+i.id).py(10).px(10).gap(6).rounded(8).bg(this.selected==='item:'+i.id?t.selected:t.chrome).cursor_pointer().hover(s=>s.bg(t.hover))
      .on_click((_e,cx)=>{this.detail=i.id;this.file=null;cx.notify();})
      .child(h_flex().gap(8).items_center().child(div().flex_1().min_w(0).truncate().tooltip(i.title).font_medium().text_size(13).child(i.title))
        .child(badge(labels[i.status]||i.status,statusColor(i.status,t),t)))
      .when(Boolean(sub),el=>el.child(div().truncate().tooltip(sub).text_size(12).text_color(t.muted).child(sub)))
      .when(Boolean(worker||steps.length),el=>el.child(h_flex().gap(8).items_center()
        .child(caption(worker?'Worker · '+(worker.terminal||(worker.state==='exited'?'已退出':worker.state==='starting'?'启动中':'尚无终端')):'PM 维护',t))
        .child(div().flex_1()).when(steps.length>0,el=>el.child(caption('步骤 '+steps.filter(s=>s.done).length+'/'+steps.length,t)))));
  }
  tasks(p,t) {
    const list=groups(p.items.filter(i=>!this.attentionOnly||needsAttention(i)));
    if(!list.length)return v_flex().p(16).gap(10).rounded(8).bg(t.surface)
      .child(div().font_semibold().child(this.attentionOnly?'当前没有待处理事项':'从第一项任务开始'))
      .child(paragraph(this.attentionOnly?'受阻和待核验的任务会显示在这里。':'在 PM 终端交代目标，任务与执行结果会汇总到这里。',t))
      .child(button('tasks-empty-action',this.attentionOnly?'查看全部任务':'进入 PM 终端',(_e,cx)=>{if(this.attentionOnly){this.attentionOnly=false;cx.notify();}else this.navigate(p.main,cx);},t,true));
    return v_flex().gap(16).children(list.map(g=>v_flex().gap(6)
      .child(h_flex().id('group-'+g.id).py(5).px(6).gap(6).items_center().cursor_pointer().text_color(t.muted).text_size(11)
        .on_click((_e,cx)=>{this.folded.has(g.id)?this.folded.delete(g.id):this.folded.add(g.id);cx.notify();})
        .child(svg('mods/files/chevron-'+(this.folded.has(g.id)?'right':'down')+'.svg').size(11))
        .child(div().flex_1().child(g.title)).child(String(g.items.length)))
      .when(!this.folded.has(g.id),el=>el.children(g.items.map(i=>this.itemRow(i,t))))));
  }
  sessionRow(p,record,isMain,t) {
    const live=this.live(record),item=p.items.find(i=>i.id===record.workItemId);
    return v_flex().id('session-'+record.id).px(6).py(8).gap(4).rounded(6).bg(this.selected==='session:'+record.id?t.selected:t.background).cursor_pointer().hover(s=>s.bg(t.hover))
      .on_click((_e,cx)=>this.navigate(record,cx))
      .child(h_flex().gap(8).items_center().child(div().flex_1().min_w(0).truncate().tooltip(isMain?p.name:item?.title||record.id).font_medium().child(isMain?'项目负责人':item?.title||record.id))
        .child(badge(sessionStatus(record,live),record.state==='exited'?t.muted:(t[live?.status]||t.muted),t)))
      .child(caption((isMain?'PM':'Worker')+' · '+(record.terminal||'尚无终端')+(record.backend?' · '+record.backend:''),t))
      .when(Boolean(item),el=>el.child(caption('任务账本 · '+(labels[item.status]||item.status),t)));
  }
  sessions(p,t) {
    const workers=p.runs.slice().reverse();
    const groupsByStatus=new Map();
    for(const r of workers){const label=sessionStatus(r,this.live(r));if(!groupsByStatus.has(label))groupsByStatus.set(label,[]);groupsByStatus.get(label).push(r);}
    return v_flex().child(this.section('项目负责人',[this.sessionRow(p,p.main,true,t)],t))
      .when(!workers.length,el=>el.child(v_flex().p(12).mb(16).rounded(8).bg(t.surface).gap(6)
        .child(paragraph('尚未派发 Worker',t)).child(caption('PM 派发后，可在这里查看执行状态并进入原终端。',t))))
      .children([...groupsByStatus].map(([label,list])=>this.section(label+' · '+list.length,list.map(r=>this.sessionRow(p,r,false,t)),t)))
      .child(caption('会话状态来自执行端；是否完成以任务账本为准。',t));
  }
  fileRow(a,t) {return h_flex().id('artifact-'+a.id).py(8).px(6).gap(8).rounded(6).bg(this.selected==='file:'+a.id?t.selected:t.background).cursor_pointer().hover(s=>s.bg(t.hover))
    .on_click((_e,cx)=>this.openFile(a.id,cx)).child(svg('mods/files/file.svg').size(14).text_color(t.muted))
    .child(v_flex().flex_1().min_w(0).gap(4).child(div().truncate().tooltip(a.title).child(a.title))
      .when(Boolean(a.path),el=>el.child(div().truncate().tooltip(a.path).text_size(11).text_color(t.muted).child(a.path))))
    .child(caption(a.version?'v'+a.version+' · '+({accepted:'已采纳',rejected:'未采纳'}[a.status]||'待核验'):'项目指南',t));}
  files(p,t) {return v_flex().gap(4).child(this.section('项目目标',[paragraph(p.goal,t)],t)).child(this.fileRow({id:'pm',title:'项目说明 · pm.md'},t))
    .children(p.artifacts.map(a=>this.fileRow(a,t)))
    .when(p.decisions.length>0,el=>el.child(this.section('决策',p.decisions.map(d=>v_flex().gap(4).child(paragraph(d.text,t)).child(caption(d.sourceRef,t))),t)));}
  taskDetail(p,i,t) {
    const active=p.runs.find(r=>r.id===i.activeRunId);
    return v_flex().gap(4)
      .child(h_flex().justify_between().mb(8).child(badge(labels[i.status],statusColor(i.status,t),t)).child(caption(i.kind==='task'?'任务':'待办',t)))
      .child(div().font_semibold().mb(14).child(i.title))
      .when(Boolean(i.brief),el=>el.child(this.section('范围',[paragraph(i.brief,t)],t)))
      .when(Boolean(i.nextAction),el=>el.child(this.section('下一步',[paragraph(i.nextAction,t)],t)))
      .when(i.acceptanceCriteria.length>0,el=>el.child(this.section('完成条件',i.acceptanceCriteria.map(c=>paragraph('· '+c,t)),t)))
      .when(i.checklist.length>0,el=>el.child(this.section('步骤 · '+i.checklist.filter(c=>c.done).length+'/'+i.checklist.length,
        i.checklist.map(c=>h_flex().gap(8).child(svg('mods/workspace-chrome/'+(c.done?'check':'square')+'.svg').size(13).text_color(t.muted)).child(paragraph(c.title,t))),t)))
      .when(i.artifactIds.length>0,el=>el.child(this.section('资料',p.artifacts.filter(a=>i.artifactIds.includes(a.id)).map(a=>this.fileRow(a,t)),t)))
      .when(Boolean(i.resolution),el=>el.child(this.section('最新说明',[paragraph(i.resolution,t)],t)))
      .when(Boolean(active?.reports?.length),el=>el.child(this.section('执行回报',active.reports.slice(-5).map(r=>paragraph(r.text,t)),t)))
      .child(v_flex().pt(10).gap(6).border_t(1).border_color(t.border).child(caption('来源 · '+i.sourceRef,t))
        .child(caption('记录 · '+i.id+' · 修订 '+i.revision,t)).child(caption('维护者 · 本项目 PM',t)))
      .child(h_flex().mt(12).gap(6).child(button('detail-main',i.kind==='todo'?'到 PM 细化':'到 PM 核验',(_e,cx)=>this.navigate(p.main,cx),t))
        .when(Boolean(active),el=>el.child(button('detail-worker','执行终端',(_e,cx)=>this.navigate(active,cx),t))));
  }
  artifactDetail(p,t) {
    const a=p.artifacts.find(a=>a.id===this.file),preview=this.preview;
    return v_flex().gap(10).child(div().font_semibold().child(a?.title||'pm.md'))
      .when(Boolean(a),el=>el.child(caption((a.status==='accepted'?'已采纳':a.status==='rejected'?'未采纳':'待核验')+' · v'+a.version,t))
        .child(caption(a.path,t)).child(caption('来源 · '+a.sourceRef,t))
        .child(button('artifact-source','来源任务',(_e,cx)=>{this.detail=a.workItemId;this.file=null;cx.notify();},t)))
      .when(Boolean(preview?.changed),el=>el.child(div().text_color(t.blocked).child('文件已变更，与登记证据的校验值不同。请重新登记版本。')))
      .when(Boolean(preview?.truncated),el=>el.child(caption('仅显示前 64 KB',t)))
      .child(preview?.text?TextView.markdown('artifact-preview-'+this.file,preview.text):paragraph(preview?.error||'读取中…',t));
  }
  render(cx) {
    if(this.currentKey()!==this.key)this.refresh(cx);
    const t=theme(),p=this.project,loc=this.currentLocation();
    const row=button('project-close','×',()=>{run('layout.hide',{id:'panel'});if(loc.terminal)run('pane.focus',{terminal:loc.terminal});},t);
    const root=v_flex().id('project-root').size_full().min_h(0).rounded(10).overflow_hidden().border(1).border_color(t.border)
      .bg(t.background).text_color(t.foreground).text_size(12).track_focus(this.focus)
      .on_mouse_down('left',()=>this.focus.focus()).on_key_down((e,cx)=>this.handleKey(e,cx))
      .child(h_flex().h(42).flex_none().px(10).gap(6).items_center().border_b(1).border_color(t.border)
        .when(Boolean(this.detail||this.file),el=>el.child(button('project-back','←',(_e,cx)=>{this.detail=null;this.file=null;cx.notify();},t)))
        .child(div().flex_1().font_semibold().child(this.detail?'任务详情':this.file?'项目资料':'Project'))
        .when(Boolean(p&&loc.terminal),el=>el.child(button('project-configure','PM 配置',()=>this.setup(),t)))
        .child(button('project-refresh','↻',(_e,cx)=>this.refresh(cx),t)).child(row));
    const missing=this.error?.code==='runtime_missing';
    if(this.error&&!missing)root.child(v_flex().flex_none().p(12).gap(6)
      .child(paragraph(p?'连接暂不可用，以下是上次记录。':'暂时无法读取项目记录。',t))
      .child(button('project-error-detail',this.showError?'收起详情':'查看详情',(_e,cx)=>{this.showError=!this.showError;cx.notify();},t))
      .when(Boolean(this.showError),el=>el.child(caption(this.error?.detail||this.error?.message||String(this.error),t))));
    if(!p)return root.child(v_flex().p(16).gap(12)
      .child(div().font_semibold().child(this.busy?'正在读取项目…':loc.terminal?'让这个终端负责一个项目':'先选择一个 Agent 终端'))
      .child(paragraph(loc.terminal?'把当前 Agent 设为 PM，任务与资料会留在 '+(loc.machine||'本机')+'。':'在左侧选择 Agent，或进入一个原生终端。',t))
      .when(Boolean(loc.terminal&&!this.busy),el=>el.child(button('project-setup','设置项目 PM…',()=>this.setup(),t,true)))
      .when(Boolean(missing),el=>el.child(caption('设置时会自动准备这台机器所需的项目功能。',t)))
      .child(caption('也可以右键左侧 Agent，选择“设置 / 重新绑定 PM”。',t)));
    if(p.main.mode==='attached'&&p.main.notice?.state!=='sent')root.child(v_flex().px(14).py(10).gap(5)
      .child(caption('PM 已绑定，尚未确认收到项目说明。',t))
      .child(button('project-introduce','交代项目…',()=>this.setup(this.address(p.main)),t)));
    const counts=summary(p.items),pm=this.live(p.main);
    if(this.detail||this.file)root.child(div().px(14).py(10).truncate().text_size(11).text_color(t.muted).child(p.name));
    else root.child(v_flex().flex_none().px(14).py(14).gap(12)
      .child(div().font_semibold().text_size(16).truncate().tooltip(p.name).child(p.name))
      .child(div().text_size(12).text_color(t.muted).tooltip(p.goal).child(p.goal.length>100?p.goal.slice(0,100)+'…':p.goal))
      .child(h_flex().gap(8).items_center()
        .child(badge('PM · '+sessionStatus(p.main,pm),p.main.state==='exited'?t.muted:(t[pm?.status]||t.muted),t))
        .child(div().flex_1()).child(button('project-main','进入 PM ↗',(_e,cx)=>this.navigate(p.main,cx),t,true)))
      .child(h_flex().gap(6).children([['待安排',counts.pending,t.muted],['执行中',counts.running,t.working],['已完成',counts.done,t.done]].map(([label,n,color])=>v_flex().flex_1().p(10).gap(4).rounded(7).bg(t.raised)
        .child(div().text_size(18).font_semibold().text_color(color).child(String(n))).child(caption(label,t)))))
      .when(Boolean(counts.blocked+counts.review||this.attentionOnly),el=>el.child(button('project-attention',
        this.attentionOnly?'← 全部任务':'待处理 '+(counts.blocked+counts.review)+' · 受阻 '+counts.blocked+' / 待核验 '+counts.review,
        (_e,cx)=>{this.attentionOnly=!this.attentionOnly;this.tab='tasks';this.selected=null;cx.notify();},t,this.attentionOnly))));
    if(!this.detail&&!this.file)root.child(h_flex().flex_none().px(10).pb(6).gap(5).border_b(1).border_color(t.border)
      .children([['tasks','任务'],['sessions','会话'],['files','资料']].map(([id,label])=>button('tab-'+id,label+' '+(id==='tasks'?p.items.length:id==='sessions'?p.runs.length+1:p.artifacts.length+1),(_e,cx)=>{this.tab=id;this.selected=null;cx.notify();},t,this.tab===id))));
    const item=p.items.find(i=>i.id===this.detail);
    root.child(v_flex().id('project-content').flex_1().min_h(0).overflow_y_scrollbar().p(10)
      .child(this.file?this.artifactDetail(p,t):item?this.taskDetail(p,item,t):this.tab==='sessions'?this.sessions(p,t):this.tab==='files'?this.files(p,t):this.tasks(p,t)))
      .child(div().flex_none().px(14).py(9).border_t(1).border_color(t.border).text_size(11).text_color(t.muted).child((this.origin?.machine||'本机')+' · '+(this.error?'离线记录':'账本 r'+p.revision)+' · '+p.cwd.split('/').pop()));
    return root;
  }
}
