import { View, div, svg } from 'gpui-kit';
import { h_flex, v_flex, TextView } from 'gpui-base';
import { props, exec, spaces, panes, focused, terminals, theme, run, layout, nextCommand } from 'herdr';
import { groups, labels, findNode, location, sessionStatus } from './model.js';

const caption = (s,t) => div().text_size(11).text_color(t.muted).child(s);
const paragraph = (s,t) => div().text_size(12).text_color(t.foreground).child(s);
const button = (id,label,action,t,selected=false) => h_flex().id(id).px(7).py(5).gap(6).rounded(5).cursor_pointer()
  .text_size(12).text_color(selected?t.foreground:t.muted).bg(selected?t.selected:t.background)
  .hover(s=>s.bg(t.hover).text_color(t.foreground)).on_click(action).child(label);

export default class Project extends View {
  init(initial,cx) {
    const p=initial??props()??{};
    this.python=p.python||'python3'; this.entry=p.entry; this.dataHome=p.dataHome;
    this.closed=false; this.key=null; this.epoch=0; this.ticket=0; this.busy=false;
    this.project=null; this.error=null; this.tab='tasks'; this.detail=null; this.file=null; this.preview=null;
    this.folded=new Set(['done','cancelled']); this.selected=null; this.focus=cx.focus_handle();
    this.refresh(cx);
    // Only the external ledger is polled. Native terminal/focus/theme data is reactive.
    cx.timer.every(5000,cx=>{ if(this.visible()&&!this.closed)this.refresh(cx); });
    cx.spawn(async cx=>{
      while(!this.closed) {
        const cmd=await nextCommand(); if(this.closed)return;
        if(cmd==='focus')this.focus.focus();
        else if(cmd==='refresh')this.refresh(cx);
        else if(['tasks','sessions','files'].includes(cmd)){this.tab=cmd;this.detail=null;this.file=null;}
        cx.notify();
      }
    });
  }
  close(){this.closed=true;this.epoch++;this.ticket++;}
  visible(){const root=layout(),panel=findNode(root,'panel'),body=findNode(root,'panel-body');return !panel||(!panel.hidden&&body?.active==='project');}
  currentLocation(){return location(focused(),panes(),spaces());}
  currentKey(){return JSON.stringify(this.currentLocation());}
  async call(args) {
    if(!this.entry)throw new Error('尚未安装运行入口。请运行项目安装器。');
    const r=await exec(this.python,[this.entry,...(this.dataHome?['--home',this.dataHome]:[]),...args],{timeout:10000});
    if(r.code!==0)throw new Error((r.stderr||r.stdout||'无法读取账本').slice(0,1500));
    return JSON.parse(r.stdout);
  }
  refresh(cx) {
    if(this.closed)return;
    const key=this.currentKey(), loc=this.currentLocation();
    if(key!==this.key){this.key=key;this.epoch++;this.project=null;this.detail=null;this.file=null;this.preview=null;this.error=null;this.busy=false;this.tab='tasks';}
    if(this.busy||loc.machine||!loc.terminal)return;
    const epoch=this.epoch, ticket=++this.ticket;
    this.busy=true;
    cx.spawn(async cx=>{
      try {
        const snapshot=await this.call(['snapshot','--terminal',loc.terminal]);
        if(this.closed||epoch!==this.epoch||key!==this.currentKey()||ticket!==this.ticket)return;
        this.project=snapshot.project;this.error=null;
      } catch(e) {if(!this.closed&&epoch===this.epoch&&ticket===this.ticket)this.error=String(e);}
      finally {if(!this.closed&&epoch===this.epoch&&ticket===this.ticket){this.busy=false;cx.notify();}}
    });
  }
  navigate(record,cx) {
    const live=terminals().find(t=>t.address===record?.terminal);
    if(!live){this.error='此执行终端已退出或不可访问。项目记录仍保留；请从终端使用 herdr-project start / reconcile 恢复。';cx.notify();return;}
    if(panes().some(p=>p.terminal===record.terminal))run('pane.focus',{terminal:record.terminal});
    else run('terminal.peek',{terminal:record.terminal});
  }
  openFile(id,cx) {
    this.file=id;this.detail=null;this.preview=null;
    const epoch=this.epoch,projectId=this.project.id;
    cx.spawn(async cx=>{
      try {const data=await this.call(['read','--project',projectId,'--artifact',id]);
        if(!this.closed&&this.epoch===epoch&&this.file===id)this.preview=data;
      } catch(e){if(!this.closed&&this.epoch===epoch&&this.file===id)this.preview={error:String(e)};}
      if(!this.closed)cx.notify();
    });cx.notify();
  }
  keyboardRows() {
    const p=this.project;if(!p||this.detail||this.file)return [];
    if(this.tab==='tasks')return groups(p.items).filter(g=>!this.folded.has(g.id)).flatMap(g=>g.items.map(i=>({key:'item:'+i.id,open:cx=>{this.detail=i.id;cx.notify();}})));
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
    const sub=i.status==='blocked'?i.resolution:i.nextAction||i.brief;
    return v_flex().id('work-'+i.id).py(8).px(6).gap(4).rounded(6).bg(this.selected==='item:'+i.id?t.selected:t.background).cursor_pointer().hover(s=>s.bg(t.hover))
      .on_click((_e,cx)=>{this.detail=i.id;this.file=null;cx.notify();})
      .child(h_flex().gap(8).items_center().child(div().flex_1().min_w(0).truncate().text_size(12).child(i.title))
        .child(div().flex_none().text_size(11).text_color(i.status==='blocked'?t.blocked:t.muted).child(labels[i.status]||i.status)))
      .when(Boolean(sub),el=>el.child(div().truncate().text_size(11).text_color(t.muted).child(sub)));
  }
  tasks(p,t) {
    const list=groups(p.items);
    if(!list.length)return paragraph('还没有工作记录。在 Main 终端中交代第一步。',t);
    return v_flex().gap(14).children(list.map(g=>v_flex().gap(2)
      .child(h_flex().id('group-'+g.id).py(5).px(6).gap(6).items_center().cursor_pointer().text_color(t.muted).text_size(11)
        .on_click((_e,cx)=>{this.folded.has(g.id)?this.folded.delete(g.id):this.folded.add(g.id);cx.notify();})
        .child(svg('mods/files/chevron-'+(this.folded.has(g.id)?'right':'down')+'.svg').size(11))
        .child(div().flex_1().child(g.title)).child(String(g.items.length)))
      .when(!this.folded.has(g.id),el=>el.children(g.items.map(i=>this.itemRow(i,t))))));
  }
  sessionRow(p,record,isMain,t) {
    const live=terminals().find(t=>t.address===record.terminal),item=p.items.find(i=>i.id===record.workItemId);
    return v_flex().id('session-'+record.id).px(6).py(8).gap(4).rounded(6).bg(this.selected==='session:'+record.id?t.selected:t.background).cursor_pointer().hover(s=>s.bg(t.hover))
      .on_click((_e,cx)=>this.navigate(record,cx))
      .child(h_flex().gap(8).child(div().flex_1().min_w(0).truncate().child(isMain?'Main':item?.title||record.id))
        .child(caption(sessionStatus(record,live),t)))
      .child(caption(isMain?'本项目唯一的 SuperAgent':record.id,t));
  }
  sessions(p,t) {
    const workers=p.runs.slice().reverse();
    const groupsByStatus=new Map();
    for(const r of workers){const label=sessionStatus(r,terminals().find(t=>t.address===r.terminal));if(!groupsByStatus.has(label))groupsByStatus.set(label,[]);groupsByStatus.get(label).push(r);}
    return v_flex().child(this.section('Main',[this.sessionRow(p,p.main,true,t)],t))
      .children([...groupsByStatus].map(([label,list])=>this.section(label+' · '+list.length,list.map(r=>this.sessionRow(p,r,false,t)),t)))
      .child(caption('会话状态来自执行端；是否完成以任务账本为准。',t));
  }
  fileRow(a,t) {return h_flex().id('artifact-'+a.id).py(8).px(6).gap(8).rounded(6).bg(this.selected==='file:'+a.id?t.selected:t.background).cursor_pointer().hover(s=>s.bg(t.hover))
    .on_click((_e,cx)=>this.openFile(a.id,cx)).child(svg('mods/files/file.svg').size(14).text_color(t.muted))
    .child(div().flex_1().min_w(0).truncate().child(a.title)).child(caption(a.version?'v'+a.version:'',t));}
  files(p,t) {return v_flex().gap(4).child(this.section('项目目标',[paragraph(p.goal,t)],t)).child(this.fileRow({id:'pm',title:'pm.md'},t))
    .children(p.artifacts.map(a=>this.fileRow(a,t)))
    .when(p.decisions.length>0,el=>el.child(this.section('决策',p.decisions.map(d=>v_flex().gap(4).child(paragraph(d.text,t)).child(caption(d.sourceRef,t))),t)));}
  taskDetail(p,i,t) {
    const active=p.runs.find(r=>r.id===i.activeRunId);
    return v_flex().gap(4)
      .child(h_flex().justify_between().mb(8).child(caption(labels[i.status],t)).child(caption(i.kind==='task'?'任务':'待办',t)))
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
        .child(caption('记录 · '+i.id+' · 修订 '+i.revision,t)).child(caption('维护者 · 本项目 Main',t)))
      .child(h_flex().mt(12).gap(6).child(button('detail-main',i.kind==='todo'?'到 Main 细化':'到 Main 核验',(_e,cx)=>this.navigate(p.main,cx),t))
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
        .child(div().flex_1().font_semibold().child('Project'))
        .child(button('project-refresh','↻',(_e,cx)=>this.refresh(cx),t)).child(row));
    if(this.error)root.child(div().flex_none().p(12).text_color(t.blocked).child((p?'刷新失败，以下是上次记录。\n':'')+this.error));
    if(!p)return root.child(v_flex().p(14).gap(12).child(paragraph(loc.machine?'此版本只连接本机账本，请在项目所在机器安装 Projects。':this.busy?'读取项目记录…':'此终端尚未关联项目。',t))
      .child(caption('在原生终端创建项目并启动其 Main：',t)).child(paragraph('herdr-project create my-project --name "项目名" --goal "项目目标" --cwd /path/to/repo',t))
      .child(paragraph('herdr-project start --project my-project --backend pi',t)));
    const summary=groups(p.items).filter(g=>g.id!=='cancelled').map(g=>g.items.length+' '+g.title).join(' · ');
    root.child(v_flex().flex_none().px(14).py(12).gap(7).child(div().font_semibold().text_size(13).child(p.name))
      .child(div().text_size(12).text_color(t.muted).child(p.goal.length>160?p.goal.slice(0,160)+'…':p.goal))
      .child(h_flex().gap(6).items_center().child(svg('mods/files/folder.svg').size(13).text_color(t.muted))
        .child(div().flex_1().min_w(0).truncate().text_size(11).text_color(t.muted).child(p.cwd.split('/').pop()))
        .child(button('project-main','Main',(_e,cx)=>this.navigate(p.main,cx),t)))
      .child(caption(summary||'尚无工作项',t)));
    if(!this.detail&&!this.file)root.child(h_flex().flex_none().px(10).pb(6).gap(5).border_b(1).border_color(t.border)
      .children([['tasks','任务'],['sessions','会话'],['files','资料']].map(([id,label])=>button('tab-'+id,label,(_e,cx)=>{this.tab=id;cx.notify();},t,this.tab===id))));
    const item=p.items.find(i=>i.id===this.detail);
    root.child(v_flex().id('project-content').flex_1().min_h(0).overflow_y_scrollbar().p(10)
      .child(this.file?this.artifactDetail(p,t):item?this.taskDetail(p,item,t):this.tab==='sessions'?this.sessions(p,t):this.tab==='files'?this.files(p,t):this.tasks(p,t)))
      .child(div().flex_none().px(14).py(9).border_t(1).border_color(t.border).text_size(11).text_color(t.muted).child('本项目 Main · 账本修订 '+p.revision));
    return root;
  }
}
