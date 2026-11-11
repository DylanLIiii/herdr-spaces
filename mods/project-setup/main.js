import { View, div } from 'gpui-kit';
import { v_flex, h_flex, InputState, Input } from 'gpui-base';
import { props, exec, readTextFile, theme, openOverlay, closeOverlay, run } from 'herdr';
import { callRuntime, prepareRuntime, supportsLeaderSetup } from './transport.js';

const text=(value,t)=>div().text_size(12).text_color(t.muted).child(value);
const states={pending:'等待 PM 询问',configuring:'配置中',deferred:'已暂缓',verifying:'配置已保存 · 待验证',ready:'配置就绪'};
const roleNames={pm:'PM',worker:'开发',explore:'代码探索',librarian:'资料查询',reviewer:'独立核验',research:'研究',oracle:'疑难分析'};
const button=(id,label,action,t,primary=false,disabled=false)=>div().id(id).accessibility_label(label).tab_index(0)
  .px(12).py(8).rounded(6).bg(disabled?t.raised:primary?t.solid:t.background)
  .text_color(disabled?t.dim:primary?t.solid_foreground:t.foreground).text_size(12)
  .when(!disabled,e=>e.cursor_pointer().hover(s=>s.bg(primary?t.accent:t.hover)).on_click(action)
    .on_key_down((event,cx)=>{if(event.key==='enter'||event.key==='space'){cx.stop_propagation();action(event,cx);}})).child(label);

export default class Setup extends View {
  init(initial,cx) {
    this.config=initial??props()??{};
    const address=this.config.terminal||'',parts=address.split('/');
    this.loc={machine:parts.length>1?parts[0]:null,terminal:address,localTerminal:parts.at(-1)};
    this.closed=false;this.busy=false;this.error=null;this.catalog=null;this.bound=null;this.notice=null;
    this.selected='new';this.fields={};this.replacing=false;this.customSkill=false;this.showMessage=false;this.editing=new Set();this.showProjects=true;
    this.focus=cx.focus_handle();
    if(!this.config.menu)this.load(cx);
  }
  close(){this.closed=true;}
  dismiss(){closeOverlay(this.config.overlay);}
  call(args){return callRuntime(this.config,args,this.loc,exec);}
  load(cx) {
    if(this.busy)return;
    this.busy=true;this.error=null;this.stage='正在读取项目…';
    cx.spawn(async cx=>{
      try {
        if(!this.loc.localTerminal)throw new Error('请先选择一个 Agent 终端。');
        let probe;
        try {probe=await this.call(['probe']);}catch(e){if(e.code!=='runtime_missing')throw e;}
        if(this.closed)return;
        if(!supportsLeaderSetup(probe)){this.stage='正在准备项目功能…';cx.notify();await prepareRuntime(this.config,this.loc,exec,readTextFile);}
        if(this.closed)return;
        const data=await this.call(['setup','--terminal',this.loc.localTerminal]);
        if(this.closed)return;
        this.catalog=data;
        for(const [key,value,hint] of [['name',data.suggestedName,'例如：研究助手'],['goal','','这个项目希望达成什么结果？'],['cwd',data.cwd,'项目机器上的工作目录'],['pmSkill','','项目机器上的 Skill 路径']]) {
          const field=InputState.new({value:value||'',placeholder:hint});this.fields[key]=field;
          field.on('change',(_e,cx)=>{this.error=null;cx.notify();});
          field.on('focus',(_e,cx)=>{this.active=key;cx.notify();});
          field.on('blur',(_e,cx)=>{if(this.active===key)this.active=null;cx.notify();});
          field.on('submit',(_e,cx)=>{const keys=this.fieldKeys(),next=keys[keys.indexOf(key)+1];if(next)this.fields[next].focus();});
        }
        this.select(data.binding?.project_id||'new');
        if(!data.binding)this.fields.goal.focus();
      }catch(e){if(!this.closed)this.error=e.message||String(e);}
      finally{if(!this.closed){this.busy=false;cx.notify();}}
    });
  }
  fieldKeys(){return [...(this.selected==='new'?['name','goal','cwd']:[]),...(this.customSkill&&this.editing.has('skill')?['pmSkill']:[])];}
  select(id) {
    this.selected=id;this.replacing=false;this.error=null;this.active=null;
    this.showProjects=id==='new';this.editing=new Set();
    const p=this.chosen()||this.catalog?.defaults||{};
    const skill=p.pmSkill===this.catalog?.defaults?.pmSkill?'':p.pmSkill||'';
    this.customSkill=Boolean(skill);this.fields.pmSkill.set_value(skill);
  }
  chosen(){return this.catalog?.projects.find(p=>p.id===this.selected);}
  otherLeader(){const p=this.chosen();return p&&p.main.state!=='inactive'&&p.main.state!=='exited'&&!(p.main.terminal===this.loc.localTerminal&&p.main.scope===this.catalog.coreScope);}
  foreign(){return Boolean(this.chosen()?.main.scope&&this.chosen().main.scope!==this.catalog.coreScope);}
  missing(){return this.selected==='new'?['name','goal','cwd'].filter(k=>!this.fields[k]?.value().trim()):[];}
  ready(){return Boolean(this.catalog&&(this.selected==='new'||this.chosen())&&!this.missing().length&&!this.foreign());}
  goTo(record) {
    const address=record?.terminal;
    if(address&&record.scope===this.catalog.coreScope){run('agent.focus',{terminal:this.loc.machine?this.loc.machine+'/'+address:address});this.dismiss();}
  }
  async introduce(){this.notice=await this.call(['introduce','--project',this.bound.id,'--core-scope',this.catalog.coreScope,'--generation',String(this.bound.main.generation)]);}
  save(cx) {
    if(this.busy||this.bound||!this.ready()||(this.otherLeader()&&!this.replacing))return;
    if(this.customSkill&&!this.fields.pmSkill.value().trim()){this.error='请填写自定义 Skill 路径，或选择内置指南。';this.replacing=false;this.editing.add('skill');this.fields.pmSkill.focus();cx.notify();return;}
    this.busy=true;this.error=null;this.stage=this.replacing?'正在交接 PM…':'正在绑定 PM…';
    cx.spawn(async cx=>{
      try {
        const args=['bind','--terminal',this.loc.localTerminal,'--core-scope',this.catalog.coreScope,'--project',this.selected==='new'?this.catalog.newProjectId:this.selected];
        if(this.selected==='new')for(const key of ['name','goal','cwd'])args.push('--'+key,this.fields[key].value().trim());
        else args.push('--replace-generation',String(this.chosen().main.generation));
        args.push('--pm-skill',this.customSkill?this.fields.pmSkill.value().trim():'');
        const result=await this.call(args);if(this.closed)return;
        this.bound=result.project;this.warning=result.warning;
        this.stage='PM 已绑定，正在发送 Skill 读取指引…';cx.notify();await this.introduce();
      }catch(e){if(!this.closed)this.error=e.message||String(e);}
      finally{if(!this.closed){this.busy=false;cx.notify();}}
    });
  }
  retryIntroduction(cx) {
    if(this.busy||!this.bound)return;
    this.busy=true;this.error=null;this.stage='正在发送项目说明…';
    cx.spawn(async cx=>{try{await this.introduce();}catch(e){if(!this.closed)this.error=e.message||String(e);}finally{if(!this.closed){this.busy=false;cx.notify();}}});
  }
  field(key,label,t) {
    return v_flex().gap(6).child(text(label,t)).child(Input.new(this.fields[key]).accessibility_label(label).h(36).px(10).items_center().rounded(6).border(1)
      .border_color(this.active===key?t.accent:t.input).bg(t.background).text_color(t.foreground));
  }
  result(t) {
    const state=this.notice?.state;
    const heading=state==='sent'?'PM 已绑定，指引已发送':state==='waiting'?'PM 已绑定，等待空闲':state==='uncertain'||state==='sending'?'PM 已绑定，送达待确认':'PM 已绑定';
    const message=state==='sent'?'PM 将读取配置 Skill，并询问是否现在开始。你也可以选择稍后继续。':state==='waiting'?'当前 Agent 正在工作或等待输入。空闲后再交代项目，不会打断当前会话。':state==='uncertain'||state==='sending'?'请先查看 PM 终端，确认是否已收到指引；系统不会自动重复发送。':'项目说明尚未确认送达。';
    const result=v_flex().gap(16)
      .child(div().text_size(18).font_semibold().child(heading)).child(text(message,t))
      .child(v_flex().py(14).gap(8).border_t(1).border_b(1).border_color(t.border)
        .child(div().font_medium().child(this.bound.name))
        .child(text('配置状态 · '+(states[this.bound.setup?.state||'pending']||'尚未配置'),t)))
      .child(text('PM 会与你确定 SubAgent 分工、模型和成果保存位置。绑定完成不代表配置已完成。',t));
    if(this.replacing)result.child(text('已有任务与配置进度已保留，接任 PM 将继续跟进。',t));
    if(this.warning)result.child(text(this.warning,t));
    if(state==='waiting')result.child(button('setup-introduce','空闲后发送指引',(_e,cx)=>this.retryIntroduction(cx),t,true,this.busy));
    if(state&&state!=='sent')result.child(button('setup-message',this.showMessage?'收起项目说明':'查看待发送说明',(_e,cx)=>{this.showMessage=!this.showMessage;cx.notify();},t))
      .when(this.showMessage,el=>el.child(text(this.notice.message,t)));
    return result;
  }
  confirmation(t) {
    const p=this.chosen();
    return v_flex().gap(18).child(div().text_size(18).font_semibold().child('将 '+p.name+' 交接给当前终端？'))
      .child(text('当前 PM：'+(p.main.terminal||'启动中')+'　接任 PM：'+this.loc.localTerminal,t))
      .child(text('稳定的 PM 身份、任务、成果和配置进度都会保留。接任 PM 读取已有记录继续工作。',t))
      .child(v_flex().p(14).gap(8).rounded(8).bg(t.background)
        .child(div().font_medium().child('旧 PM 的账本写入凭据将失效'))
        .child(text('原终端和已有 Worker 继续运行，请协调正在进行的文件修改。',t)));
  }
  form(t) {
    const p=this.chosen(),body=v_flex().gap(20);
    const project=v_flex().gap(12).child(h_flex().items_center().gap(8)
      .child(div().flex_1().font_semibold().child('项目'))
      .when(Boolean(p),el=>el.child(button('setup-project-picker',this.showProjects?'收起':'切换项目',(_e,cx)=>{this.showProjects=!this.showProjects;cx.notify();},t,false,this.busy))));
    if(this.catalog.projects.length&&this.showProjects)project.child(v_flex().id('setup-project-list').max_h(132).overflow_y_scrollbar().gap(4)
      .children(this.catalog.projects.map(project=>button('choose-'+project.id,project.name+(this.selected===project.id?' · 当前选择':''),(_e,cx)=>{this.select(project.id);cx.notify();},t,false,this.busy)))
      .child(button('choose-new','创建新项目',(_e,cx)=>{this.select('new');this.fields.goal.focus();cx.notify();},t,false,this.busy)));
    if(this.selected==='new')project.child(this.field('name','项目名称',t)).child(this.field('goal','项目目标',t)).child(this.field('cwd','工作目录',t));
    else if(p)project.child(div().font_medium().text_size(15).child(p.name)).child(text(p.goal,t))
      .child(div().truncate().tooltip(p.cwd).text_size(11).text_color(t.muted).child(p.cwd));
    body.child(project);
    const setup=p?.setup,config=p?.configuration;
    body.child(v_flex().pt(16).gap(10).border_t(1).border_color(t.border)
      .child(div().font_semibold().child(setup?states[setup.state]||'配置进度':'由 PM 带你完成配置'))
      .child(text(setup?.nextAction||'绑定后，PM 会先询问是否开始，再逐步推荐和配置你的 SubAgent 团队。',t))
      .when(Boolean(p&&!this.otherLeader()),el=>el.child(button('setup-continue','进入 PM 继续配置',()=>this.goTo(p.main),t,true,this.busy))));
    if(config?.revision)body.child(v_flex().gap(8).child(div().font_medium().child('当前团队'))
      .children(Object.entries(config.roles||{}).filter(([,value])=>value.enabled).map(([role,value])=>h_flex().gap(10)
        .child(div().w(72).child(roleNames[role]||role)).child(text(value.backend+' · '+(value.model||value.tier||'工具默认'),t))))
      .child(text('成果位置 · '+(config.artifactRoot||'项目机器的持久数据目录'),t))
      .child(text('配置变更在 PM 中确认；运行中的任务保留原配置。',t)));
    if(setup?.checks?.length)body.child(v_flex().gap(6).children(setup.checks.map(check=>text(check.key+' · '+({passed:check.mode==='fixture'?'协议模拟通过':'已验证',failed:'需处理',unverified:'未验证'}[check.status]||check.status),t))));
    const skill=v_flex().pt(14).gap(10).border_t(1).border_color(t.border)
      .child(h_flex().items_center().child(div().flex_1().child(text('PM 工作指南 · '+(this.customSkill?'自定义':'内置'),t)))
        .child(button('edit-skill',this.editing.has('skill')?'收起':'高级设置',(_e,cx)=>{this.editing.has('skill')?this.editing.delete('skill'):this.editing.add('skill');cx.notify();},t,false,this.busy)));
    if(this.editing.has('skill'))skill.child(h_flex().gap(6).children([[false,'内置指南'],[true,'自定义 Skill']].map(([custom,label])=>button('skill-'+(custom?'custom':'builtin'),label,(_e,cx)=>{this.customSkill=custom;this.error=null;cx.notify();},t,this.customSkill===custom,this.busy))))
      .when(this.customSkill,el=>el.child(this.field('pmSkill','Skill 绝对路径 · '+(this.loc.machine||'本机'),t)))
      .child(text('配置 Skill 始终随项目提供；自定义指南不会改变首次配置流程。',t));
    body.child(skill);
    if(this.foreign())body.child(text('此项目属于另一个 Core，请在原来的机器连接中管理 PM。',t));
    else if(this.otherLeader())body.child(text('项目已有 PM：'+p.main.terminal+'。可以进入原终端，或明确交接给当前终端。',t));
    return body;
  }
  render(cx) {
    const t=theme();
    if(this.config.menu)return v_flex().p(5).gap(3).bg(t.popover)
      .child(button('leader-menu','指定 / 交接项目 PM…',()=>{this.dismiss();openOverlay({mod:this.config.setupMod||'project-setup',kind:'dialog',width:600,height:720,props:{...this.config,overlay:undefined,menu:false}});},t))
      .child(button('leader-open','进入终端',()=>{run('agent.focus',{terminal:this.loc.terminal});this.dismiss();},t));
    const root=v_flex().id('leader-setup').size_full().min_h(0).bg(t.popover).text_color(t.foreground).text_size(13).track_focus(this.focus)
      .on_key_down((e,cx)=>{if(e.key==='escape'){cx.stop_propagation();this.dismiss();}})
      .child(h_flex().px(22).py(16).gap(12).items_center().border_b(1).border_color(t.border)
        .child(v_flex().flex_1().gap(5).child(div().text_size(17).font_semibold().child(this.bound?'PM 已绑定':this.replacing?'交接项目负责人':this.chosen()?'项目配置':'指定项目 PM'))
          .child(text((this.loc.machine||'本机')+' / '+this.loc.localTerminal+' · 继续使用当前原生会话',t)))
        .child(button('setup-close','关闭',()=>this.dismiss(),t)));
    const body=v_flex().id('setup-body').flex_1().min_h(0).overflow_y_scrollbar().p(22).gap(16);
    if(this.bound)body.child(this.result(t));
    else if(this.catalog)body.child(this.replacing&&this.otherLeader()?this.confirmation(t):this.form(t));
    else body.child(text(this.busy?this.stage:'项目设置未完成。',t));
    if(this.error)root.child(v_flex().flex_none().mx(22).mt(12).p(12).gap(8).rounded(8).border(1).border_color(t.blocked).child(text(this.error,t))
      .child(button('setup-retry',this.bound?'重新检查说明送达':'重试',(_e,cx)=>this.bound?this.retryIntroduction(cx):this.catalog?this.save(cx):this.load(cx),t,false,this.busy)));
    root.child(body);
    const foot=h_flex().flex_none().px(22).py(14).gap(8).items_center().justify_end().border_t(1).border_color(t.border);
    if(this.busy)foot.child(text(this.stage,t));
    else if(this.bound)foot.child(button('setup-done','进入 PM 终端',()=>this.goTo(this.bound.main),t,true));
    else if(this.otherLeader()) {
      foot.child(button('setup-existing','进入现有 PM',()=>this.goTo(this.chosen().main),t,false,this.foreign()));
      if(this.replacing)foot.child(button('setup-cancel-rebind','取消交接',(_e,cx)=>{this.replacing=false;cx.notify();},t));
      foot.child(this.replacing?button('setup-rebind-confirm','确认交接给 '+this.loc.localTerminal,(_e,cx)=>this.save(cx),t,true,!this.ready()):button('setup-rebind','交接给当前终端…',(_e,cx)=>{this.replacing=true;cx.notify();},t,true,!this.ready()));
    }else {
      if(this.missing().length)foot.child(div().flex_1().child(text('请填写'+this.missing().map(k=>({name:'项目名称',goal:'目标',cwd:'目录'}[k])).join('、'),t)));
      foot.child(button('setup-bind',this.chosen()?.main.terminal===this.loc.localTerminal?'保存 PM 指南并交代':'绑定 PM 并交代配置',(_e,cx)=>this.save(cx),t,true,!this.ready()));
    }
    return root.child(foot);
  }
}
