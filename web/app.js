'use strict';
let csrf = '', enableReadonly = false, projects = [], tasks = [], approvals = [], jobs = [];
const $ = id => document.getElementById(id);
const agentName = {claude:'Claude Code',codex:'Codex CLI',dual:'Claude + Codex',manual:'手动选择'};
const statusName = {pending:'待处理',prepared:'已准备',running:'执行中',done:'已完成',failed:'失败'};
function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function toast(text){const e=$('toast');e.textContent=String(text);e.classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>e.classList.remove('show'),4000);}
async function api(url, data){const opts={headers:{'Accept':'application/json'}};if(data!==undefined){opts.method='POST';opts.headers['Content-Type']='application/json';opts.headers['X-AIWS-Token']=csrf;opts.body=JSON.stringify(data)}let r=await fetch(url,opts);let j=await r.json();if(!r.ok)throw new Error(j.error||'请求失败');return j;}
async function refresh(){const [t,p,h,a,j]=await Promise.all([api('/api/tasks'),api('/api/projects'),api('/api/health'),api('/api/approvals'),api('/api/jobs')]);tasks=t.tasks;projects=p.projects;approvals=a.approvals;jobs=j.jobs;let ps=$('project-select');let selected=ps.value;ps.replaceChildren(node('option','', '选择项目'));ps.firstChild.value='';for(const project of projects){let opt=node('option','',project);opt.value=project;ps.append(opt)}if(projects.includes(selected))ps.value=selected;else if(projects.length)ps.value=projects[0];$('stat-all').textContent=tasks.length;$('stat-pending').textContent=tasks.filter(x=>['pending','prepared','running'].includes(x.status)).length;$('stat-done').textContent=tasks.filter(x=>x.status==='done').length;$('stat-agents').textContent=Object.values(h.tools).filter(x=>x.available).length+'/4';$('workspace-path').textContent='工作区：'+h.workspace;renderTools(h.tools);renderTasks();renderApprovals();}
function renderTools(tools){const c=$('agent-list');c.replaceChildren();for(const [key,title] of [['claude','Claude Code'],['codex','Codex CLI'],['t3','T3 Code'],['openclaw','OpenClaw']]){let row=node('div','agent');let info=node('div');info.append(node('strong','',title),node('small','',tools[key]?.available?'检测到本地程序':'未安装或未加入 PATH'));row.append(info,node('span','indicator'+(tools[key]?.available?'':' off'),tools[key]?.available?'● 已检测':'○ 未检测'));c.append(row);}}
function btn(title,action,cls='tiny'){const b=node('button','btn '+cls,title);b.type='button';b.addEventListener('click',action);return b;}
async function doTask(id,action,body={}){try{let j=await api(`/api/tasks/${id}/${action}`,body);if(j.brief)toast('已生成交接文档：'+j.brief);else toast('操作已接受');await refresh();}catch(e){toast(e.message);}}
function renderStages(t,row){
  const stages=t.steps||[];
  if(!stages.length)return;
  const container=node('div','stage-list');
  for(const s of stages){
    const line=node('div','stage-row'+(s.status==='done'?' stage-done':''));
    line.append(node('span','stage-index',String(s.step_index+1)),
                node('span','stage-info',`${s.name} · ${agentName[s.agent]||s.agent}`),
                node('span','stage-status',statusName[s.status]||s.status));
    container.append(line);
    if(s.result){const d=node('details','stage-result');d.append(node('summary','','阶段记录'),node('pre','result',s.result));container.append(d);}
  }
  row.append(container);
}
function renderTasks(){
  const c=$('tasks-container');c.replaceChildren();
  if(!tasks.length){c.append(node('p','muted','暂无任务。请先创建项目目录和第一个任务。'));return;}
  for(const t of tasks){
    const row=node('article','task-row'),top=node('div','task-top'),left=node('div');
    left.append(node('div','task-name',t.title),
      node('div','task-sub',`${t.id} · ${t.project} · ${agentName[t.agent]||t.agent} · ${t.created_at.replace('T',' ')}`));
    top.append(left,node('span','status '+t.status,statusName[t.status]||t.status));row.append(top);
    if(t.description)row.append(node('div','task-desc',t.description.slice(0,450)));
    if(t.reason)row.append(node('div','task-sub','路由建议：'+t.reason));
    if(t.worktree)row.append(node('div','task-sub','✓ 已启用独立 Git Worktree 工作区'));
    renderStages(t,row);
    const step=(t.steps||[]).find(x=>x.status!=='done');
    const acts=node('div','task-actions');
    if(t.status==='pending'&&!t.worktree){
      acts.append(btn('新建隔离 Git 工作区',()=>{
        if(confirm('此操作会在项目 Git 仓库中建立新分支和独立工作区，仅用于可信项目。请确认项目无未提交修改。'))
          doTask(t.id,'worktree',{confirmed:true});
      },'tiny warn'));
    }
    if(step&&['pending','failed'].includes(step.status))
      acts.append(btn('生成当前阶段交接文档',()=>doTask(t.id,'prepare')));
    if(step&&step.status==='prepared'){
      const agents=step.agent==='manual'?['claude','codex']:[step.agent];
      for(const a of agents)acts.append(btn(`启动 ${agentName[a]}`,()=>doTask(t.id,'launch',{agent:a})));
      const form=node('form','step-form');
      const label=node('label','','填写本阶段执行结果，再进入下一个阶段');
      const area=node('textarea');area.rows=3;area.maxLength=12000;area.required=true;
      area.placeholder='概述实际结果、测试情况、遗留问题；请勿包含账号密码或 Token';
      label.append(area);form.append(label);
      form.append(btn('确认完成当前阶段',async()=>{
        if(!area.value.trim()){toast('请先填写本阶段的真实执行结果');return;}
        await doTask(t.id,'step-finish',{state:'done',result:area.value});
      },'tiny'));
      form.append(btn('标记当前阶段失败',async()=>{
        if(!area.value.trim()){toast('请写明失败原因');return;}
        await doTask(t.id,'step-finish',{state:'failed',result:area.value});
      },'tiny warn'));
      row.append(form);
    }
    if(enableReadonly&&t.agent==='codex'&&step&&step.status==='prepared'&&t.status==='prepared'){
      const openApproval=approvals.some(x=>x.task_id===t.id && x.step_index===step.step_index && x.status==='pending');
      const openJob=jobs.some(x=>x.task_id===t.id && x.step_index===step.step_index && ['queued','running'].includes(x.status));
      if(!openApproval&&!openJob){
        acts.append(btn('申请 Codex 只读后台执行',()=>doTask(t.id,'request-readonly'), 'tiny warn'));
      }
    }
    if(t.status==='running')acts.append(node('span','task-sub','后台分析进行中；会自动更新执行状态。'));
    row.append(acts);
    if(t.result){const details=node('details');const summary=node('summary','task-sub','查看最新结果');
      details.append(summary,node('pre','result',t.result));row.append(details);}
    c.append(row);
  }
}
async function decideApproval(id,decision){
  if(decision==='approve'&&!confirm('此批准仅限当前任务的 Codex 只读分析；执行器/MCP 仍可能有额外权限。确定批准并加入本地队列？'))return;
  try{await api(`/api/approvals/${id}/decide`,{decision});toast('审批已处理');await refresh();}catch(e){toast(e.message);}
}
async function cancelJob(id){
  try{await api(`/api/jobs/${id}/cancel`,{});toast('已取消尚未开始的任务');await refresh();}catch(e){toast(e.message);}
}
function renderApprovals(){
  const a=$('approval-list'),j=$('job-list');a.replaceChildren();j.replaceChildren();
  if(!approvals.length)a.append(node('p','muted','暂时没有审批申请。'));
  const decisionName={pending:'待审批',approved:'已批准',denied:'已拒绝'};
  for(const x of approvals){
    const row=node('div','approval-row');
    row.append(node('strong','',`${x.id} · ${decisionName[x.status]||x.status}`),
      node('small','',`任务 ${x.task_id} · 阶段 ${x.step_index+1} · Codex 只读分析`));
    if(x.status==='pending'){
      const acts=node('div','task-actions');
      acts.append(btn('批准一次',()=>decideApproval(x.id,'approve'),'tiny warn'),
                  btn('拒绝',()=>decideApproval(x.id,'deny'),'tiny'));
      row.append(acts);
    }
    a.append(row);
  }
  if(!jobs.length)j.append(node('p','muted','尚无后台执行记录。'));
  const statuses={queued:'排队中',running:'执行中',succeeded:'完成',failed:'失败',cancelled:'已取消',interrupted:'中断，需重新审批'};
  for(const x of jobs){
    const row=node('div','approval-row');
    row.append(node('strong','',`${x.id} · ${statuses[x.status]||x.status}`),
               node('small','',`${x.task_id} · ${x.operation} · ${x.updated_at}`));
    if(x.status==='queued')row.append(btn('取消队列任务',()=>cancelJob(x.id),'tiny warn'));
    if(x.result){const d=node('details');d.append(node('summary','task-sub','执行结果'),node('pre','result',x.result));row.append(d);}
    j.append(row);
  }
}
$('task-form').addEventListener('submit',async e=>{e.preventDefault();const f=new FormData(e.target);try{const result=await api('/api/tasks',{title:f.get('title'),description:f.get('description'),project:f.get('project'),agent:f.get('agent')});e.target.reset();toast('任务创建成功：'+result.task.id);await refresh();}catch(err){toast(err.message);}});
$('project-form').addEventListener('submit',async e=>{e.preventDefault();const f=new FormData(e.target);try{await api('/api/projects',{name:f.get('name')});e.target.reset();toast('项目目录已创建；可在其中初始化或克隆 Git 仓库。');await refresh();}catch(err){toast(err.message);}});
$('refresh').addEventListener('click',()=>refresh().catch(e=>toast(e.message)));
(async()=>{try{const s=await api('/api/session');csrf=s.csrf;enableReadonly=s.read_only_enabled;await refresh();setInterval(()=>refresh().catch(()=>{}),7000);}catch(e){toast('无法连接本地服务：'+e.message)}})();
