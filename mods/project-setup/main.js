import { View, div } from 'gpui-kit';
import { v_flex, h_flex, InputState, Input } from 'gpui-base';
import { props, exec, readTextFile, theme, openOverlay, closeOverlay, run } from 'herdr';
import { callRuntime, prepareRuntime, supportsLeaderSetup } from './transport.js';

const tools=[['pi','Pi'],['claude','Claude Code'],['codex','Codex']];
const text=(value,t)=>div().text_size(12).text_color(t.muted).child(value);
const button=(id,label,action,t,primary=false,disabled=false)=>div().id(id).px(12).py(8).rounded(6)
  .bg(disabled?t.raised:primary?t.solid:t.background).text_color(disabled?t.dim:primary?t.solid_foreground:t.foreground).text_size(12)
  .when(!disabled,e=>e.cursor_pointer().hover(s=>s.bg(primary?t.accent:t.hover)).on_click(action)).child(label);
const section=(number,title,t)=>h_flex().gap(8).items_center()
  .child(div().w(20).h(20).rounded(5).bg(t.selected).text_size(11).text_color(t.accent).flex().items_center().justify_center().child(number))
  .child(div().font_semibold().child(title));

export default class Setup extends View {
  init(initial,cx) {
    this.config=initial??props()??{};
    const address=this.config.terminal||'',parts=address.split('/');
    this.loc={machine:parts.length>1?parts[0]:null,terminal:address,localTerminal:parts.at(-1)};
    this.closed=false;this.busy=false;this.error=null;this.catalog=null;this.bound=null;this.notice=null;
    this.selected='new';this.fields={};this.backend='pi';this.replacing=false;this.customSkill=false;this.showMessage=false;this.editing=new Set();this.showProjects=true;
    this.focus=cx.focus_handle();
    if(!this.config.menu)this.load(cx);
  }
  close(){this.closed=true;}
  dismiss(){closeOverlay(this.config.overlay);}
  call(args){return callRuntime(this.config,args,this.loc,exec);}
  load(cx) {
    if(this.busy)return;
    this.busy=true;this.error=null;this.stage='正在准备项目功能…';
    cx.spawn(async cx=>{
      try {
        if(!this.loc.localTerminal)throw new Error('请先选择一个 Agent 终端。');
        let probe;
        try {probe=await this.call(['probe']);}catch(e){if(e.code!=='runtime_missing')throw e;}
        if(this.closed)return;
        if(!supportsLeaderSetup(probe))await prepareRuntime(this.config,this.loc,exec,readTextFile);
        if(this.closed)return;
        const data=await this.call(['setup','--terminal',this.loc.localTerminal]);
        if(this.closed)return;
        this.catalog=data;
        for(const [key,value,hint] of [['name',data.suggestedName,'例如：网站改版'],['goal','','这次希望达成什么结果？'],['cwd',data.cwd,'项目目录的绝对路径'],['pmSkill','','项目机器上的 Skill 目录或 SKILL.md'],['model','','使用工具默认模型']]) {
          const field=InputState.new({value:value||'',placeholder:hint});this.fields[key]=field;
          field.on('change',(_e,cx)=>{this.error=null;cx.notify();});
          field.on('focus',(_e,cx)=>{this.active=key;cx.notify();});
          field.on('blur',(_e,cx)=>{if(this.active===key)this.active=null;cx.notify();});
          field.on('submit',(_e,cx)=>{const keys=this.fieldKeys(),next=keys[keys.indexOf(key)+1];if(next)this.fields[next].focus();else if(!this.otherLeader())this.save(cx);});
        }
        this.select(data.binding?.project_id||'new');
        if(!data.binding)this.fields.goal.focus();
      }catch(e){if(!this.closed)this.error=e.message||String(e);}
      finally{if(!this.closed){this.busy=false;cx.notify();}}
    });
  }
  fieldKeys(){return [...(this.selected==='new'?['name','goal','cwd']:[]),...(this.customSkill&&this.editing.has('skill')?['pmSkill']:[]),...(this.editing.has('worker')?['model']:[])];}
  select(id) {
    this.selected=id;this.replacing=false;this.error=null;this.active=null;
    this.showProjects=id==='new';this.editing=new Set(id==='new'?['skill','worker']:[]);
    const p=this.chosen()||this.catalog?.defaults||{};
    this.backend=p.subAgent?.backend||'pi';
    const skill=p.pmSkill===this.catalog?.defaults?.pmSkill?'':p.pmSkill||'';
    this.customSkill=Boolean(skill);this.fields.pmSkill.set_value(skill);
    this.fields.model.set_value(p.subAgent?.model||'');
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
    if(this.customSkill&&!this.fields.pmSkill.value().trim()){this.error='请填写自定义 Skill 的绝对路径，或选择内置 Skill。';this.replacing=false;this.editing.add('skill');this.fields.pmSkill.focus();cx.notify();return;}
    this.busy=true;this.error=null;this.stage=this.replacing?'正在交接 PM…':'正在保存项目配置…';
    cx.spawn(async cx=>{
      try {
        const args=['bind','--terminal',this.loc.localTerminal,'--core-scope',this.catalog.coreScope,'--project',this.selected==='new'?this.catalog.newProjectId:this.selected];
        if(this.selected==='new')for(const key of ['name','goal','cwd'])args.push('--'+key,this.fields[key].value().trim());
        else args.push('--replace-generation',String(this.chosen().main.generation));
        args.push('--pm-skill',this.customSkill?this.fields.pmSkill.value().trim():'','--worker-backend',this.backend,'--worker-model',this.fields.model.value().trim());
        const result=await this.call(args);if(this.closed)return;
        this.bound=result.project;this.warning=result.warning;
        this.stage='配置已保存，正在发送项目说明…';cx.notify();await this.introduce();
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
    return v_flex().gap(5).child(text(label,t)).child(Input.new(this.fields[key]).h(34).px(10).items_center().rounded(6).border(1)
      .border_color(this.active===key?t.accent:t.input).bg(t.background).text_color(t.foreground));
  }
  result(t,cx) {
    const state=this.notice?.state,agent=this.bound.subAgent||{backend:this.backend,model:this.fields.model.value()},tool=tools.find(([id])=>id===agent.backend)?.[1]||agent.backend;
    const heading=state==='sent'?'PM 已就位':state==='waiting'?'配置已保存，等待 Agent 空闲':state==='uncertain'||state==='sending'?'配置已保存，请确认消息是否送达':'项目配置已保存';
    const message=state==='sent'?'项目说明已发送。继续在原终端工作，PM 将读取完整 Skill 和项目记录。':state==='waiting'?'当前 Agent 正在工作、等待确认，或尚未报告空闲。你可以先关闭窗口，稍后从「PM 配置」再次发送说明。':state==='uncertain'||state==='sending'?'请先查看原终端。为避免重复输入，这条说明不会自动重发。':'绑定已经生效。项目说明尚未确认发送，可重新发送。';
    const card=v_flex().p(18).gap(10).rounded(10).border(1).border_color(t.border).bg(t.background)
      .child(div().text_size(18).font_semibold().child(heading)).child(text(message,t));
    const details=v_flex().p(16).gap(12).rounded(10).bg(t.background)
      .child(div().font_semibold().child(this.bound.name))
      .child(text('PM 终端　'+this.loc.localTerminal+' · 第 '+this.bound.main.generation+' 代',t))
      .child(text('SubAgent　'+tool+' · '+(agent.model||'工具默认模型'),t))
      .child(text('PM Skill　'+(this.customSkill?'自定义 Skill · 完整读取':'内置 Project Manager · 完整读取'),t));
    const result=v_flex().gap(16).child(card).child(details)
      .child(div().font_semibold().child('接下来'))
      .child(text('1. PM 读取 Skill、引用资料与已有任务。',t))
      .child(text('2. 核对 SubAgent 模型与工具登录，按你的要求开展工作。',t))
      .child(text('3. 随时从项目侧栏「PM 配置」调整设置或交接。',t));
    if(this.replacing)result.child(text('旧 PM 的账本凭据已失效；原终端和已有 Worker 继续运行。',t));
    if(this.warning)result.child(text(this.warning,t));
    if(state==='waiting')result.child(button('setup-introduce','Agent 空闲后，发送项目说明',(_e,cx)=>this.retryIntroduction(cx),t,true,this.busy));
    if(state&&state!=='sent')result.child(button('setup-message',this.showMessage?'收起项目说明':'查看待发送的项目说明',(_e,cx)=>{this.showMessage=!this.showMessage;cx.notify();},t))
      .when(this.showMessage,el=>el.child(text(this.notice.message,t)));
    return result;
  }
  confirmation(t) {
    const p=this.chosen(),tool=tools.find(([id])=>id===this.backend)?.[1]||this.backend;
    return v_flex().gap(18)
      .child(div().text_size(18).font_semibold().child('将 '+p.name+' 交接给当前终端？'))
      .child(h_flex().gap(12).items_center()
        .child(v_flex().flex_1().p(16).gap(8).rounded(8).bg(t.background).child(text('当前 PM',t)).child(div().text_size(20).font_semibold().child(p.main.terminal||'启动中')))
        .child(text('→',t))
        .child(v_flex().flex_1().p(16).gap(8).rounded(8).bg(t.selected).child(text('接任 PM',t)).child(div().text_size(20).font_semibold().child(this.loc.localTerminal))))
      .child(text('项目记录、任务和稳定的 Main 身份将保留。接任 PM 会收到读取 Skill 和现有任务的指引。',t))
      .child(v_flex().p(16).gap(10).rounded(8).border(1).border_color(t.blocked)
        .child(div().font_semibold().child('交接后'))
        .child(text('旧 PM 的账本写入凭据立即失效。',t))
        .child(text('原终端和已有 Worker 继续运行，请协调仍在进行的文件修改。',t)))
      .child(text('SubAgent　'+tool+' · '+(this.fields.model.value().trim()||'工具默认模型'),t))
      .child(text('PM Skill　'+(this.customSkill?this.fields.pmSkill.value().trim():'内置 Project Manager'),t));
  }
  settingHeader(key,number,title,t) {
    return h_flex().gap(8).items_center().child(div().flex_1().child(section(number,title,t)))
      .when(this.selected!=='new',el=>el.child(button('edit-'+key,this.editing.has(key)?'收起':'编辑',(_e,cx)=>{
        this.editing.has(key)?this.editing.delete(key):this.editing.add(key);this.active=null;cx.notify();
      },t,false,this.busy)));
  }
  form(t,cx) {
    const p=this.chosen(),body=v_flex().gap(16);
    const project=v_flex().p(16).gap(10).rounded(10).bg(t.background)
      .child(h_flex().items_center().gap(8).child(div().flex_1().child(section('1','项目',t)))
        .when(Boolean(p),el=>el.child(button('setup-project-picker',this.showProjects?'收起':'切换项目',(_e,cx)=>{this.showProjects=!this.showProjects;cx.notify();},t,false,this.busy))));
    if(this.catalog.projects.length&&this.showProjects)project.child(v_flex().id('setup-project-list').max_h(132).overflow_y_scrollbar().gap(4)
      .children(this.catalog.projects.map(p=>button('choose-'+p.id,(this.selected===p.id?'✓  ':'')+p.name+(p.main.state==='running'?' · PM '+p.main.terminal:''),(_e,cx)=>{this.select(p.id);cx.notify();},t,false,this.busy)))
      .child(button('choose-new',this.selected==='new'?'✓  创建新项目':'+ 创建新项目',(_e,cx)=>{this.select('new');this.fields.goal.focus();cx.notify();},t,false,this.busy)));
    if(this.selected==='new')project.child(this.field('name','项目名称',t)).child(this.field('goal','项目目标',t)).child(this.field('cwd','工作目录',t));
    else if(p)project.child(v_flex().gap(8).child(div().font_semibold().text_size(15).child(p.name))
      .child(text(p.goal,t)).child(div().truncate().tooltip(p.cwd).text_size(11).text_color(t.muted).child(p.cwd))
      .child(text('当前 PM · '+(p.main.terminal||'尚未启动')+(this.otherLeader()?' · 可在下方发起交接':' · 当前终端'),t)));
    const skill=v_flex().p(16).gap(10).rounded(10).bg(t.background).child(this.settingHeader('skill','2','PM 工作指南',t));
    if(this.editing.has('skill'))skill
      .child(h_flex().gap(6).children([[false,'内置 Skill'],[true,'自定义 Skill']].map(([custom,label])=>button('skill-'+(custom?'custom':'builtin'),(this.customSkill===custom?'✓  ':'')+label,(_e,cx)=>{this.customSkill=custom;this.error=null;cx.notify();},t,false,this.busy))))
      .child(text('授权 PM 完整读取 Skill 与引用文件，指导项目维护、派发和验收。',t));
    else skill.child(div().font_medium().child(this.customSkill?'自定义 Project Manager Skill':'内置 Project Manager Skill'))
      .child(div().truncate().tooltip(this.fields.pmSkill.value()||this.catalog.defaults?.pmSkill||'随项目功能安装').text_size(11).text_color(t.muted).child(this.customSkill?this.fields.pmSkill.value():'完整读取正文与引用资料'));
    if(this.customSkill&&this.editing.has('skill'))skill.child(this.field('pmSkill','Skill 绝对路径 · 位于'+(this.loc.machine||'本机'),t));
    const available=this.catalog.tools?.find(tool=>tool.id===this.backend);
    const worker=v_flex().p(16).gap(10).rounded(10).bg(t.background).child(this.settingHeader('worker','3','SubAgent 默认配置',t));
    if(this.editing.has('worker'))worker
      .child(h_flex().gap(6).children(tools.map(([id,label])=>button('tool-'+id,(this.backend===id?'✓  ':'')+label,(_e,cx)=>{if(this.backend!==id){this.backend=id;this.fields.model.set_value('');}cx.notify();},t,false,this.busy))))
      .child(this.field('model',this.backend==='pi'?'模型 · 可填写 provider/model':'模型 · 填写该工具支持的模型标识',t))
      .child(text(available?(available.available?'已找到所选工具。请确认已登录；模型留空使用工具默认值。':'目标机器暂未找到此工具。可先保存，安装并登录后再派发。'):'模型留空使用工具默认值。请先在项目机器安装并登录所选工具。',t));
    else worker.child(h_flex().gap(8).items_center()
      .child(div().font_medium().child(tools.find(([id])=>id===this.backend)?.[1]||this.backend))
      .child(div().flex_1().min_w(0).truncate().tooltip(this.fields.model.value()||'使用工具默认模型').text_size(12).text_color(t.muted).child(this.fields.model.value()||'工具默认模型')))
      .child(text(available?(available.available?'已找到工具 · 登录与模型可用性由工具确认':'尚未找到工具 · 安装并登录后可派发'):'请确认工具已安装并登录',t));
    body.child(project).child(skill).child(worker);
    if(this.foreign())body.child(text('此项目属于另一个 Core，请在原来的机器连接中管理 PM。',t));
    else if(this.otherLeader())body.child(v_flex().p(14).gap(8).rounded(8).bg(t.background).border(1).border_color(this.replacing?t.accent:t.border)
      .child(div().font_semibold().child(this.replacing?'确认交接 PM':'项目已有 PM'))
      .child(text('当前 '+p.main.terminal+' → 新 PM '+this.loc.localTerminal,t))
      .child(text(this.replacing?'旧 PM 的账本写入凭据将失效。保留项目记录、原终端和已有 Worker；请协调仍在进行的文件修改。':'可进入原终端，或将 PM 职责交给当前终端。',t)));
    return body;
  }
  render(cx) {
    const t=theme();
    if(this.config.menu)return v_flex().p(5).gap(3).bg(t.popover)
      .child(button('leader-menu','设置 / 重新绑定 PM…',()=>{this.dismiss();openOverlay({mod:this.config.setupMod||'project-setup',kind:'dialog',width:600,height:720,props:{...this.config,overlay:undefined,menu:false}});},t))
      .child(button('leader-open','进入终端',()=>{run('agent.focus',{terminal:this.loc.terminal});this.dismiss();},t));
    const root=v_flex().id('leader-setup').size_full().min_h(0).bg(t.popover).text_color(t.foreground).text_size(13).track_focus(this.focus)
      .on_key_down((e,cx)=>{if(e.key==='escape'){cx.stop_propagation();this.dismiss();}else if(e.key==='tab'&&this.catalog&&!this.bound){cx.stop_propagation();const keys=this.fieldKeys(),at=keys.indexOf(this.active),step=e.modifiers?.shift?-1:1;if(keys.length)this.fields[keys[(at+step+keys.length)%keys.length]].focus();}})
      .child(h_flex().px(22).py(16).gap(12).items_center().border_b(1).border_color(t.border)
        .child(v_flex().flex_1().gap(5).child(div().text_size(17).font_semibold().child(this.bound?'PM 配置已保存':this.replacing?'交接项目负责人':this.chosen()?'PM 设置':'设置项目 PM'))
          .child(text((this.loc.machine||'本机')+' / '+this.loc.localTerminal+' · 继续使用当前原生会话',t)))
        .child(button('setup-close','关闭',()=>this.dismiss(),t)));
    const body=v_flex().id('setup-body').flex_1().min_h(0).overflow_y_scrollbar().p(22).gap(16);
    if(this.bound)body.child(this.result(t,cx));
    else if(this.catalog)body.child(this.replacing&&this.otherLeader()?this.confirmation(t):this.form(t,cx));
    else body.child(text(this.busy?this.stage:'项目设置未完成。',t));
    if(this.error)root.child(v_flex().flex_none().mx(22).mt(12).p(12).gap(8).rounded(8).border(1).border_color(t.blocked)
      .child(text(this.error,t)).child(h_flex().gap(6)
        .child(button('setup-retry',this.bound?'重新发送说明':'重试',(_e,cx)=>this.bound?this.retryIntroduction(cx):this.catalog?this.save(cx):this.load(cx),t,false,this.busy))
        .when(Boolean(this.catalog&&!this.bound),el=>el.child(button('setup-reload','重新读取项目',(_e,cx)=>this.load(cx),t,false,this.busy)))));
    root.child(body);
    const foot=h_flex().flex_none().px(22).py(14).gap(8).items_center().justify_end().border_t(1).border_color(t.border);
    if(this.busy)foot.child(text(this.stage,t));
    else if(this.bound)foot.child(button('setup-done','返回 PM 终端',()=>this.goTo(this.bound.main),t,true));
    else if(this.otherLeader()) {
      foot.child(button('setup-existing','进入现有 PM',()=>this.goTo(this.chosen().main),t,false,this.foreign()));
      if(this.replacing)foot.child(button('setup-cancel-rebind','取消交接',(_e,cx)=>{this.replacing=false;cx.notify();},t));
      foot.child(this.replacing?button('setup-rebind-confirm','确认交接给 '+this.loc.localTerminal,(_e,cx)=>this.save(cx),t,true,!this.ready()):button('setup-rebind','重新绑定到此终端…',(_e,cx)=>{this.replacing=true;cx.notify();},t,true,!this.ready()));
    }else {
      if(this.missing().length)foot.child(div().flex_1().child(text('请填写'+this.missing().map(k=>({name:'项目名称',goal:'目标',cwd:'目录'}[k])).join('、'),t)));
      foot.child(button('setup-bind',this.chosen()?.main.terminal===this.loc.localTerminal?'保存并同步给 PM':'绑定 PM 并发送说明',(_e,cx)=>this.save(cx),t,true,!this.ready()));
    }
    return root.child(foot);
  }
}
