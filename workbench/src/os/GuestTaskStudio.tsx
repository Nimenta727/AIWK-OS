import {useCallback,useEffect,useState} from 'react';
import {api} from './api';
import {BrainCircuit,CheckCircle2,ChevronRight,Clock3,Play,Plus,RefreshCw,ShieldCheck} from 'lucide-react';

type Capability={name:string;description:string;inputSchema:{properties:Record<string,{type:string}>;required:string[]}};
type StageDraft={key:string;label:string;tool:string;path:string;query:string;dependsOn:string};
type TaskHeader={id:string;title:string;goal:string;created_at:number};
type Stage={id:string;stage_key:string;label:string;tool:string;arguments:Record<string,string>;state:string;approval:number;dependsOn:string[];error:string|null;result:unknown};
type TaskDetail={task:TaskHeader;stages:Stage[]};
type ModelStatus={configured:boolean;online:boolean;cloudFallback:boolean;model:string;automaticExecution:boolean;cpuOnly:boolean;weightsPresent:boolean};
type Step={tool:string;arguments:Record<string,string>;reason:string;grade?:string};
type Bilingual={zh:string;en:string};
type Decision={route:string;agent:string;rule:string;reason:Bilingual;forbidden:string[];externalAllowed:boolean;externalEnabled:boolean;
 providers:Record<string,{enabled:boolean;installed:boolean}>;requiresConsent:boolean};
type FollowUp={escalate:boolean;final:boolean;action:string;agent?:string;reason?:Bilingual};
type RouteInfo={decision:Decision;followUp?:FollowUp;error?:string;refused?:boolean};
type Proposal={tool:string;arguments:Record<string,string>;reason:string;requiresReview:boolean;executed:boolean;refused?:boolean;grade?:string;steps?:Step[]};
const READ_ONLY=new Set(['workspace.tree','file.read','file.stat','file.trashList','code.search','git.inspect','runtime.detect','browser.local_text','platform.inspect','code.symbols','code.references','code.dependencies','code.platformApis','system.info','network.status','download.list','download.progress']);

// shared client: localized errors and one automatic CSRF refresh, like every other page
const request=<T,>(url:string,opts?:RequestInit):Promise<T>=>api<T>(url,opts);
const newStage=(n:number):StageDraft=>({key:'step'+n,label:'Step '+n,tool:'workspace.tree',
 path:'.',query:'',dependsOn:n>1?'step'+(n-1):''});

export default function GuestTaskStudio({csrf,english,capabilities,focus='tasks'}:{
 csrf:string;english:boolean;capabilities:Capability[];focus?:'tasks'|'model'
}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const [taskList,setTaskList]=useState<TaskHeader[]>([]);
 const [detail,setDetail]=useState<TaskDetail|null>(null);
 const [audit,setAudit]=useState<Array<{seq:number;action:string;entry_hash:string}>>([]);
 const [title,setTitle]=useState('');
 const [goal,setGoal]=useState('');
 const [drafts,setDrafts]=useState<StageDraft[]>([newStage(1)]);
 const [instruction,setInstruction]=useState('');
 const [model,setModel]=useState<ModelStatus|null>(null);
 const [proposal,setProposal]=useState<Proposal|null>(null);
 const [routeInfo,setRouteInfo]=useState<RouteInfo|null>(null);
 const [routeCfg,setRouteCfg]=useState<{externalEnabled:boolean}|null>(null);
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const headers={'Content-Type':'application/json','X-AIWS-CSRF':csrf};
 const update=useCallback(async()=>{
  try{
   const rows=await request<{tasks:TaskHeader[]}>('/tasks');
   setTaskList(rows.tasks);
   if(focus==='model'){setModel(await request<ModelStatus>('/model/status'));
    setRouteCfg((await request<{config:{externalEnabled:boolean}}>('/route/config')).config);}
  }catch(e){setError(e instanceof Error?e.message:String(e));}
 },[focus]);
 useEffect(()=>{void update();},[update]);
 const open=useCallback(async(id:string)=>{
  try{
   setDetail(await request<TaskDetail>('/tasks/'+id));
   const records=await request<{events:typeof audit}>('/tasks/'+id+'/audit');
   setAudit(records.events);
  }catch(e){setError(e instanceof Error?e.message:String(e));}
 },[]);
 useEffect(()=>{
  if(!detail||!detail.stages.some(s=>s.state==='queued'||s.state==='running'))return;
  const interval=window.setInterval(()=>{void open(detail.task.id);},1400);
  return()=>window.clearInterval(interval);
 },[detail,open]);
 const create=async()=>{
  if(!csrf||busy)return;
  setBusy(true);setError('');
  try{
   const stages=drafts.map(d=>{
    const spec=capabilities.find(c=>c.name===d.tool);
    const args:Record<string,string>={};
    if(spec?.inputSchema.properties.path)args.path=d.path||'.';
    if(spec?.inputSchema.properties.query)args.query=d.query;
    if(spec?.inputSchema.properties.symbol)args.symbol=d.query;
    if(spec?.inputSchema.properties.view)args.view='status';
    return {key:d.key,label:d.label,tool:d.tool,arguments:args,
      dependsOn:d.dependsOn?[d.dependsOn]:[]};
   });
   const next=await request<TaskDetail>('/tasks',{method:'POST',headers,
    body:JSON.stringify({title,goal,stages})});
   setDetail(next);setDrafts([newStage(1)]);setTitle('');setGoal('');
   await update();await open(next.task.id);
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setBusy(false);}
 };
 const command=async(stage:Stage,action:'approve'|'dispatch')=>{
  if(!detail||busy||!csrf)return;
  setBusy(true);setError('');
  try{
   await request('/tasks/'+detail.task.id+'/stages/'+stage.stage_key+'/'+action,{
    method:'POST',headers,body:'{}'
   });
   await open(detail.task.id);
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setBusy(false);}
 };
 const approveAndRun=async(stage:Stage)=>{
  if(!detail||busy||!csrf)return;
  setBusy(true);setError('');
  try{
   const base='/tasks/'+detail.task.id+'/stages/'+stage.stage_key+'/';
   await request(base+'approve',{method:'POST',headers,body:'{}'});
   await request(base+'dispatch',{method:'POST',headers,body:'{}'});
   await open(detail.task.id);
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setBusy(false);}
 };
 const toggleModel=async(value:boolean)=>{
  if(busy||!csrf)return;
  setBusy(true);setError('');
  try{
   const plan=await request<TaskDetail>('/model/'+(value?'enable':'disable'),{
    method:'POST',headers,body:'{}'
   });
   await update();
   await open(plan.task.id);
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setBusy(false);}
 };
 const suggest=async()=>{
  if(!csrf||busy||!instruction.trim())return;
  setBusy(true);setError('');setProposal(null);
  try{
   const result=await request<Proposal>('/model/suggest',{method:'POST',headers,
    body:JSON.stringify({instruction})});
   setProposal(result);
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setBusy(false);}
 };
 const createOfflinePlan=async()=>{
  if(!csrf||busy||!model?.online||!instruction.trim())return;
  setBusy(true);setError('');
  try{
   // The model proposes one tool or an ordered plan. The server persists an audited DAG:
   // local read-only stages run automatically; file-changing stages wait for approval.
   setRouteInfo(null);
   const item=await request<TaskDetail|{refused:true;proposal:Proposal;decision:Decision;followUp:FollowUp}|
    {routed:string;decision:Decision;followUp?:FollowUp;error?:string}>('/model/plan',{
    method:'POST',headers,body:JSON.stringify({instruction})
   });
   if('refused' in item){setProposal(item.proposal);setRouteInfo({decision:item.decision,followUp:item.followUp,refused:true});return;}
   if('routed' in item){setRouteInfo({decision:item.decision,followUp:item.followUp,error:item.error});return;}
   await update();
   await open(item.task.id);
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setBusy(false);}
 };
 const createHandoff=async(agent:string)=>{
  if(!csrf||busy||!instruction.trim())return;
  setBusy(true);setError('');
  try{
   const out=await request<{task:{id:string}}>('/route/handoff',{method:'POST',headers,body:JSON.stringify({instruction,agent})});
   await update();await open(out.task.id);
  }catch(e){setError(e instanceof Error?e.message:String(e));}
  finally{setBusy(false);}
 };
 const addProposal=()=>{
  if(!proposal||proposal.tool==='refuse'||proposal.steps)return;
  setTitle(instruction.slice(0,100));
  setGoal(proposal.reason);
  setDrafts([{key:'step1',label:proposal.reason.slice(0,140),tool:proposal.tool,
    path:proposal.arguments.path||'.',
    query:proposal.arguments.query||proposal.arguments.symbol||'',
    dependsOn:''}]);
 };
 const needWhy=!model?.online?tr('本地模型没有在线：先导入权重并启用','The local model is not online: import weights and enable it first'):!instruction.trim()?tr('先写下希望完成什么','Describe what you want first'):undefined;
 const choices=capabilities.filter(t=>t.name!=='file.replace'||focus==='tasks');
 return <div className="aiws-os-stack aiws-os-studio">
  {error&&<div className="aiws-os-error" role="alert">{error}</div>}
  {focus==='model'&&<section className="aiws-os-card">
   <div className="aiws-os-studio-title"><h2><BrainCircuit size={18}/>{tr('本地模型（Qwen3.5-9B）','Local model (Qwen3.5-9B)')}</h2>
    <span className="aiws-os-muted">{model?.online?tr('在线','Online'):model?.configured?tr('已启用，服务未就绪','Enabled, service not ready'):tr('未启用','Off')}</span></div>
   <div className="aiws-os-studio-actions">
     <button type="button" disabled={!csrf||busy||!model?.weightsPresent||Boolean(model?.configured)}
      title={!model?.weightsPresent?tr('还没有导入模型权重：步骤见 docs/AIWS_MODEL_WEIGHTS.md','No model weights imported yet: see docs/AIWS_MODEL_WEIGHTS.md'):model?.configured?tr('模型已经启用','The model is already enabled'):undefined}
      onClick={()=>void toggleModel(true)}>{tr('申请启用模型（需审核）','Request model enable approval')}</button>
     <button type="button" disabled={!csrf||busy||!model?.configured} title={!model?.configured?tr('模型没有启用，无需关闭','The model is not enabled'):undefined}
      onClick={()=>void toggleModel(false)}>{tr('申请关闭模型（需审核）','Request model disable approval')}</button>
     <span className="aiws-os-muted">{model?.weightsPresent?tr('已发现客户机权重','Guest weights found'):tr('尚未安装客户机 GGUF 权重','Guest GGUF weights not provisioned')}</span>
    </div>
   <p>{tr('模型完全在本机离线运行，不联网、不下载、不调用云端。它可以读取系统与网络状态、查看下载进度，并提出文件整理计划：只读步骤自动执行，任何会改动文件的步骤都要你逐项批准，删除只会进回收站。',
    'The model runs fully offline on this machine: no network, no downloading, no cloud. It can read system and network state, check download progress and plan file organisation. Read-only steps run automatically; every file change needs your approval, and deleting only moves to trash.')}</p>
   <label>{tr('希望 AI 完成什么？','What should the local assistant plan?')}
    <textarea value={instruction} onChange={e=>setInstruction(e.target.value)} rows={3} maxLength={1000}
     placeholder={tr('例如：看看下载进度，把已完成的下载移到 isos 文件夹','e.g. Check download progress and move finished downloads into isos/')}/></label>
   <div className="aiws-os-studio-actions">
    <button type="button" className="aiws-os-primary" disabled={!model?.online||!csrf||busy||!instruction.trim()} title={needWhy}
     onClick={()=>void suggest()}><BrainCircuit size={16}/>{tr('生成本地工具建议','Suggest a local tool')}</button>
    <button type="button" disabled={!model?.online||!csrf||busy||!instruction.trim()} title={needWhy}
     onClick={()=>void createOfflinePlan()}>{tr('生成并保存待审核任务','Create a pending audited task')}</button></div>
   <p className="aiws-os-muted">{routeCfg?.externalEnabled?
    tr('外部官方 CLI 已在 routes.json 启用：仅在你确认后生成交接文件，AIWS 不会自动调用它们。','External official CLIs are enabled in routes.json: a handoff file is only prepared after your consent; AIWS never launches them.'):
    tr('外部模型默认关闭，所有请求只在本机离线处理（可在 ~/.config/aiws/routes.json 启用交接）。','External models are off by default: everything stays on this machine (enable handoff in ~/.config/aiws/routes.json).')}</p>
   {routeInfo&&<div className="aiws-os-proposal" role="status" data-aiws="route-card">
    <strong>{tr('路由决定','Routing decision')}: {routeInfo.decision.route}{routeInfo.decision.agent!=='local'?' → '+routeInfo.decision.agent:''}</strong>
    <p>{english?routeInfo.decision.reason.en:routeInfo.decision.reason.zh}</p>
    {routeInfo.decision.forbidden.length>0&&<p className="aiws-os-muted">{tr('命中受限类别：','Restricted categories: ')}{routeInfo.decision.forbidden.join(', ')}</p>}
    {routeInfo.error&&<p className="aiws-os-muted">{routeInfo.error}</p>}
    {routeInfo.followUp?.reason&&<p>{english?routeInfo.followUp.reason.en:routeInfo.followUp.reason.zh}</p>}
    {(routeInfo.decision.route==='external'||routeInfo.followUp?.action==='propose-handoff')&&routeInfo.decision.externalAllowed&&
     <><p className="aiws-os-muted">{tr('将写入工作区 handoff/ 的文件只含指令和文件名，不含文件内容或凭据；写入本身需要你批准。','The file written to handoff/ holds only your instruction and file names: no contents or credentials; writing it needs your approval.')}</p>
      <button type="button" disabled={busy||!csrf} onClick={()=>void createHandoff(routeInfo.followUp?.agent||routeInfo.decision.agent)}>
       {tr('生成交接文件（需批准）','Prepare handoff file (needs approval)')}</button></>}
    {Object.entries(routeInfo.decision.providers).map(([name,p])=><span key={name} className="aiws-os-muted"> {name}: {p.enabled?tr('已启用','enabled'):tr('未启用','disabled')} / {p.installed?tr('已安装','installed'):tr('本机未安装','not installed here')} </span>)}
   </div>}
   {proposal&&<div className="aiws-os-proposal">
    <strong>{proposal.steps?tr('多步计划','Multi-step plan')+' ('+proposal.steps.length+')':proposal.tool}</strong><p>{proposal.reason}</p>
    {proposal.steps?<ol>{proposal.steps.map((s,i)=><li key={i}><code>{s.tool}</code> {JSON.stringify(s.arguments)} — {s.reason}
      <em> [{READ_ONLY.has(s.tool)?tr('只读，自动执行','read-only, runs automatically'):tr('需你批准','needs your approval')}]</em></li>)}</ol>:
     <pre>{JSON.stringify(proposal.arguments,null,2)}</pre>}
    <p className="aiws-os-muted">{tr('尚未执行，需先确认计划并提交任务。','Not executed; review and create a task first.')}</p>
    {proposal.tool==='refuse'?<p role="status">{tr('越权请求已拒绝；不会建立可执行任务','Out-of-scope request refused; no executable task created')}</p>:
     <button type="button" onClick={addProposal}>{tr('复制建议到任务草稿','Copy suggestion into draft')}</button>}
   </div>}
  </section>}
  <section className="aiws-os-card">
   <div className="aiws-os-studio-title"><h2><Plus size={18}/>{tr('创建持久化 AIWS 任务','Create a persistent AIWS task')}</h2>
    <button type="button" onClick={()=>void update()} title={tr('刷新','Refresh')} aria-label={tr('刷新','Refresh')}><RefreshCw size={15}/></button></div>
   <p className="aiws-os-muted">{tr('所有阶段、依赖、审批和审计在客户机 SQLite 中保留。文件写入需要审批，任何操作都不会触碰宿主机。',
    'Stages, DAG dependencies, approval and audit remain in guest-local SQLite. File writes require approval; host access is never exposed.')}</p>
   <label>{tr('任务标题','Task title')}<input value={title} maxLength={160} onChange={e=>setTitle(e.target.value)}/></label>
   <label>{tr('任务目标','Goal')}<textarea value={goal} onChange={e=>setGoal(e.target.value)} maxLength={4000} rows={2}/></label>
   {drafts.map((d,i)=><div key={i} className="aiws-os-stage-draft">
    <div className="aiws-os-studio-title"><strong>{tr('阶段','Stage')} {i+1}</strong>
     {drafts.length>1&&<button type="button" onClick={()=>setDrafts(x=>x.filter((_,j)=>j!==i))}>{tr('移除','Remove')}</button>}</div>
    <label>{tr('阶段标识','Key')}<input value={d.key} onChange={e=>setDrafts(x=>x.map((y,j)=>i===j?{...y,key:e.target.value}:y))}/></label>
    <label>{tr('阶段说明','Label')}<input value={d.label} onChange={e=>setDrafts(x=>x.map((y,j)=>i===j?{...y,label:e.target.value}:y))}/></label>
    <label>{tr('工具','Tool')}<select value={d.tool} onChange={e=>setDrafts(x=>x.map((y,j)=>i===j?{...y,tool:e.target.value}:y))}>
     {choices.map(x=><option value={x.name} key={x.name}>{x.name}</option>)}</select></label>
    {capabilities.find(c=>c.name===d.tool)?.inputSchema.properties.path&&
     <label>{tr('工作区相对路径','Relative guest path')}<input value={d.path} onChange={e=>setDrafts(x=>x.map((y,j)=>i===j?{...y,path:e.target.value}:y))}/></label>}
    {(capabilities.find(c=>c.name===d.tool)?.inputSchema.properties.query||
      capabilities.find(c=>c.name===d.tool)?.inputSchema.properties.symbol)&&
     <label>{tr('查询或符号','Query or symbol')}<input value={d.query} onChange={e=>setDrafts(x=>x.map((y,j)=>i===j?{...y,query:e.target.value}:y))}/></label>}
    <label>{tr('依赖前一个阶段','Depends on earlier stage')}<select value={d.dependsOn}
      onChange={e=>setDrafts(x=>x.map((y,j)=>i===j?{...y,dependsOn:e.target.value}:y))}>
      <option value="">{tr('无','None')}</option>
      {drafts.slice(0,i).map(s=><option value={s.key} key={s.key}>{s.key}</option>)}
    </select></label>
   </div>)}
   <div className="aiws-os-studio-actions">
    <button type="button" disabled={drafts.length>=32} onClick={()=>setDrafts(x=>[...x,newStage(x.length+1)])}>
     <Plus size={15}/>{tr('添加阶段','Add stage')}</button>
    <button type="button" className="aiws-os-primary" disabled={!title.trim()||!csrf||busy}
     onClick={()=>void create()}>{tr('保存任务与 DAG','Save task and DAG')}</button>
   </div>
  </section>
  <section className="aiws-os-card">
   <h2>{tr('客体持久任务','Guest persistent tasks')}</h2>
   {taskList.map(task=><button className="aiws-os-task" type="button" key={task.id} onClick={()=>void open(task.id)}>
    <span><Clock3 size={15}/>{task.title}</span><ChevronRight size={14}/></button>)}
   {!taskList.length&&<p className="aiws-os-muted">{tr('暂无持久任务','No saved guest tasks')}</p>}
  </section>
  {detail&&<section className="aiws-os-card">
   <h2>{detail.task.title}</h2><p>{detail.task.goal}</p>
   {detail.stages.map(s=><div className="aiws-os-stage-status" key={s.id}>
    <div><strong>{s.stage_key}: {s.label}</strong><span>{s.state.toUpperCase()}</span></div>
    <p>{s.tool}{s.dependsOn.length?' ← '+s.dependsOn.join(', '):''}</p>
    {!READ_ONLY.has(s.tool)&&<pre className="aiws-os-result" aria-label={tr('将要执行的参数','Arguments to be executed')}>{JSON.stringify(s.arguments,null,2)}</pre>}
    {s.error&&<p className="aiws-os-error">{s.error}</p>}
    {s.result!==null&&<pre className="aiws-os-result">{JSON.stringify(s.result,null,2)}</pre>}
    {(s.state==='pending'||s.state==='interrupted')&&s.approval===0?
      <><button type="button" disabled={busy} onClick={()=>void command(s,'approve')}><ShieldCheck size={15}/>{tr('批准客体写操作','Approve guest write')}</button>
       {s.dependsOn.every(k=>detail.stages.find(x=>x.stage_key===k)?.state==='completed')&&
        <button type="button" className="aiws-os-primary" disabled={busy} onClick={()=>void approveAndRun(s)}>
         <Play size={15}/>{tr('批准并运行','Approve & run')}</button>}</>:
      (s.state==='pending'||s.state==='interrupted')?
       <button type="button" className="aiws-os-primary" disabled={busy} onClick={()=>void command(s,'dispatch')}>
        <Play size={15}/>{tr('运行客户机阶段','Run guest stage')}</button>:null}
   </div>)}
   <h2><CheckCircle2 size={17}/>{tr('审计证据','Audit evidence')}</h2>
   {audit.slice(-12).map(e=><p className="aiws-os-muted" key={e.seq}>#{e.seq} {e.action} · {e.entry_hash.slice(0,12)}…</p>)}
  </section>}
 </div>;
}
