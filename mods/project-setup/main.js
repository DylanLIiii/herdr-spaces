import { View, div } from 'gpui-kit';
import { v_flex, h_flex, InputState, Input } from 'gpui-base';
import { props, exec, readTextFile, theme, openOverlay, closeOverlay, run } from 'herdr';
import { callRuntime, prepareRuntime } from './transport.js';

const text=(value,t)=>div().text_size(12).text_color(t.muted).child(value);
const button=(id,label,action,t,primary=false,disabled=false)=>div().id(id).px(10).py(7).rounded(6)
  .bg(primary?t.selected:t.background).text_color(disabled?t.dim:t.foreground).text_size(12)
  .when(!disabled,e=>e.cursor_pointer().hover(s=>s.bg(t.hover)).on_click(action)).child(label);

export default class Setup extends View {
  init(initial,cx) {
    this.config=initial??props()??{};
    const address=this.config.terminal||'';
    const parts=address.split('/');
    this.loc={machine:parts.length>1?parts[0]:null,terminal:address,localTerminal:parts.at(-1)};
    this.closed=false;this.busy=false;this.error=null;this.catalog=null;this.bound=null;this.notice=null;this.selected='new';this.fields={};
    this.focus=cx.focus_handle();
    if(!this.config.menu)this.load(cx);
  }
  close(){this.closed=true;}
  dismiss(){closeOverlay(this.config.overlay);}
  call(args){return callRuntime(this.config,args,this.loc,exec);}
  load(cx) {
    if(this.busy)return;this.busy=true;this.error=null;this.stage='正在准备 '+(this.loc.machine||'本机')+' 的项目功能…';
    cx.spawn(async cx=>{
      try {
        if(!this.loc.localTerminal)throw new Error('请先选择一个 Agent 终端。');
        let probe;
        try {probe=await this.call(['probe']);}catch(e){if(e.code!=='runtime_missing')throw e;}
        if(this.closed)return;
        if(!probe?.capabilities?.includes('leader-bind'))await prepareRuntime(this.config,this.loc,exec,readTextFile);
        if(this.closed)return;
        const data=await this.call(['setup','--terminal',this.loc.localTerminal]);
        if(this.closed)return;
        this.catalog=data;
        for(const [key,value,hint] of [['name',data.suggestedName,'项目名称'],['goal','','希望完成什么'],['cwd',data.cwd,'项目目录']]) {
          const field=InputState.new({value:value||'',placeholder:hint});this.fields[key]=field;
          field.on('change',(_e,cx)=>{this.error=null;cx.notify();});
          field.on('focus',(_e,cx)=>{this.active=key;cx.notify();});
          field.on('blur',(_e,cx)=>{if(this.active===key)this.active=null;cx.notify();});
          field.on('submit',(_e,cx)=>{if(key==='name')this.fields.goal.focus();else if(key==='goal')this.fields.cwd.focus();else this.save(cx);});
        }
        if(data.binding)this.selected=data.binding.project_id;
        else this.fields.goal.focus();
      }catch(e){if(!this.closed)this.error=e.message||String(e);}
      finally{if(!this.closed){this.busy=false;cx.notify();}}
    });
  }
  chosen(){return this.catalog?.projects.find(p=>p.id===this.selected);}
  otherLeader(){const p=this.chosen();return p&&p.main.state!=='inactive'&&p.main.state!=='exited'&&!(p.main.terminal===this.loc.localTerminal&&p.main.scope===this.catalog.coreScope);}
  goTo(record) {
    const address=record?.terminal;
    if(address&&record.scope===this.catalog.coreScope){run('agent.focus',{terminal:this.loc.machine?this.loc.machine+'/'+address:address});this.dismiss();}
  }
  ready(){return this.catalog&&(this.selected!=='new'||['name','goal','cwd'].every(k=>this.fields[k]?.value().trim()));}
  async introduce() {
    this.notice=await this.call(['introduce','--project',this.bound.id,'--core-scope',this.catalog.coreScope,'--generation',String(this.bound.main.generation)]);
  }
  save(cx) {
    if(this.busy||!this.ready()||this.otherLeader())return;
    this.busy=true;this.error=null;this.stage='正在绑定项目…';
    cx.spawn(async cx=>{
      try {
        const args=['bind','--terminal',this.loc.localTerminal,'--core-scope',this.catalog.coreScope,'--project',this.selected==='new'?this.catalog.newProjectId:this.selected];
        if(this.selected==='new')for(const key of ['name','goal','cwd'])args.push('--'+key,this.fields[key].value().trim());
        const result=await this.call(args);if(this.closed)return;
        this.bound=result.project;this.warning=result.warning;
        this.stage='正在交代项目…';cx.notify();
        await this.introduce();
      }catch(e){if(!this.closed)this.error=e.message||String(e);}
      finally{if(!this.closed){this.busy=false;cx.notify();}}
    });
  }
  retryIntroduction(cx) {
    if(this.busy||!this.bound)return;
    this.busy=true;this.error=null;
    cx.spawn(async cx=>{try{await this.introduce();}catch(e){if(!this.closed)this.error=e.message||String(e);}finally{if(!this.closed){this.busy=false;cx.notify();}}});
  }
  field(key,label,t) {
    return v_flex().gap(6).child(text(label,t)).child(Input.new(this.fields[key]).h(34).px(10).items_center().rounded(6).border(1)
      .border_color(this.active===key?t.accent:t.input).bg(t.background).text_color(t.foreground));
  }
  render(cx) {
    const t=theme();
    if(this.config.menu)return v_flex().p(5).gap(3).bg(t.popover)
      .child(button('leader-menu','设为 Project Leader…',()=>{this.dismiss();openOverlay({mod:this.config.setupMod||'project-setup',kind:'dialog',width:460,height:560,props:{...this.config,overlay:undefined,menu:false}});},t))
      .child(button('leader-open','进入终端',()=>{run('agent.focus',{terminal:this.loc.terminal});this.dismiss();},t));
    const root=v_flex().id('leader-setup').size_full().min_h(0).bg(t.popover).text_color(t.foreground).text_size(13).track_focus(this.focus)
      .on_key_down((e,cx)=>{if(e.key==='escape'){cx.stop_propagation();this.dismiss();}else if(e.key==='tab'&&this.selected==='new'&&this.catalog&&!this.bound){cx.stop_propagation();const keys=['name','goal','cwd'];this.fields[keys[(keys.indexOf(this.active)+1)%keys.length]].focus();}})
      .child(h_flex().px(18).py(14).gap(10).border_b(1).border_color(t.border)
        .child(div().flex_1().font_semibold().child(this.bound?'Project Leader 已绑定':'指定 Project Leader'))
        .child(button('setup-close','关闭',()=>this.dismiss(),t)));
    const body=v_flex().id('setup-body').flex_1().min_h(0).overflow_y_scrollbar().p(18).gap(14)
      .child(text((this.loc.machine||'本机')+' · '+this.loc.localTerminal,t));
    if(this.bound) {
      const state=this.notice?.state;
      body.child(div().font_semibold().child(this.bound.name))
        .child(text(state==='sent'?'已向当前 Agent 交代项目，接下来继续在原生终端工作。':state==='waiting'?'当前 Agent 正在工作、等待确认，或尚未报告空闲状态。绑定已保存，暂未发送项目说明。':state==='uncertain'||state==='sending'?'发送结果尚未确认。请查看原生终端，避免重复发送。':this.stage,t));
      if(this.warning)body.child(text(this.warning,t));
      if(state==='waiting')body.child(button('setup-introduce','空闲后交代项目',(_e,cx)=>this.retryIntroduction(cx),t,false,this.busy));
      if(state&&state!=='sent')body.child(text(this.notice.message,t));
    }else if(this.catalog) {
      if(this.catalog.projects.length)body.child(v_flex().gap(5).child(text('选择项目',t))
        .children(this.catalog.projects.map(p=>button('choose-'+p.id,p.name+(p.main.state==='running'?' · 已有 Leader':''),(_e,cx)=>{this.selected=p.id;cx.notify();},t,this.selected===p.id)))
        .child(button('choose-new','新建项目',(_e,cx)=>{this.selected='new';this.fields.goal.focus();cx.notify();},t,this.selected==='new')));
      if(this.selected==='new')body.child(this.field('name','项目名称',t)).child(this.field('goal','项目目标',t)).child(this.field('cwd','项目目录',t));
      else {const p=this.chosen();if(p)body.child(text(p.goal,t)).child(text(p.cwd,t));}
      body.child(text(this.otherLeader()?'此项目已有 Leader，可以直接进入它的终端。':'当前终端将负责此项目。空闲时，Agent 会收到一次项目说明。',t));
    }else body.child(text(this.busy?this.stage:'项目设置未完成。',t));
    if(this.error)body.child(text(this.error,t)).child(button('setup-retry','重试',(_e,cx)=>this.catalog?this.save(cx):this.load(cx),t,false,this.busy));
    root.child(body);
    const foot=h_flex().px(18).py(12).gap(8).justify_end().border_t(1).border_color(t.border);
    if(this.busy)foot.child(text(this.stage,t));
    else if(this.bound)foot.child(button('setup-done','进入 Leader',()=>this.goTo(this.bound.main),t,true));
    else if(this.otherLeader())foot.child(button('setup-existing','进入现有 Leader',()=>this.goTo(this.chosen().main),t,true,this.chosen().main.scope!==this.catalog.coreScope));
    else foot.child(button('setup-bind','绑定并交代项目',(_e,cx)=>this.save(cx),t,true,!this.ready()));
    return root.child(foot);
  }
}
