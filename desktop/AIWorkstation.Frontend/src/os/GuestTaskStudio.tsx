import {useCallback,useEffect,useState} from 'react';
import {BrainCircuit,CheckCircle2,ChevronRight,Clock3,Play,Plus,RefreshCw,ShieldCheck} from 'lucide-react';

type Capability={name:string;description:string;inputSchema:{properties:Record<string,{type:string}>;required:string[]}};
type StageDraft={key:string;label:string;tool:string;path:string;query:string;dependsOn:string};
type TaskHeader={id:string;title:string;goal:string;created_at:number};
type Stage={id:string;stage_key:string;label:string;tool:string;state:string;approval:number;dependsOn:string[];error:string|null;result:unknown};
type TaskDetail={task:TaskHeader;stages:Stage[]};
type ModelStatus={configured:boolean;online:boolean;cloudFallback:boolean;model:string;automaticExecution:boolean;cpuOnly:boolean;weightsPresent:boolean};
type Proposal={tool:string;arguments:Record<string,string>;reason:string;requiresReview:boolean;executed:boolean};

async function request<T>(url:string,opts?:RequestInit):Promise<T>{
 const r=await fetch('/api/v1'+url,{cache:'no-store',credentials:'omit',...opts});
 const data=await r.json() as T&{error?:string};
 if(!r.ok)throw new Error(data.error||'Local guest API error');
 return data;
}
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
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const headers={'Content-Type':'application/json','X-AIWS-CSRF':csrf};
 const update=useCallback(async()=>{
  try{
   const rows=await request<{tasks:TaskHeader[]}>('/tasks');
   setTaskList(rows.tasks);
   if(focus==='model')setModel(await request<ModelStatus>('/model/status'));
  }catch(e){setError(String(e));}
 },[focus]);
 useEffect(()=>{void update();},[update]);
 const open=useCallback(async(id:string)=>{
  try{
   setDetail(await request<TaskDetail>('/tasks/'+id));
   const records=await request<{events:typeof audit}>('/tasks/'+id+'/audit');
   setAudit(records.events);
  }catch(e){setError(String(e));}
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
  }catch(e){setError(String(e));}
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
  }catch(e){setError(String(e));}
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
  }catch(e){setError(String(e));}
  finally{setBusy(false);}
 };
 const suggest=async()=>{
  if(!csrf||busy||!instruction.trim())return;
  setBusy(true);setError('');setProposal(null);
  try{
   const result=await request<Proposal>('/model/suggest',{method:'POST',headers,
    body:JSON.stringify({instruction})});
   setProposal(result);
  }catch(e){setError(String(e));}
  finally{setBusy(false);}
 };
 const createOfflinePlan=async()=>{
  if(!csrf||busy||!model?.online||!instruction.trim())return;
  setBusy(true);setError('');
  try{
   // The model proposes ONE read-only tool. The server persists a pending,
   // audited DAG but never executes it without a separate user action.
   const item=await request<TaskDetail>('/model/plan',{
    method:'POST',headers,body:JSON.stringify({instruction})
   });
   await update();
   await open(item.task.id);
  }catch(e){setError(String(e));}
  finally{setBusy(false);}
 };
 const addProposal=()=>{
  if(!proposal)return;
  setTitle(instruction.slice(0,100));
  setGoal(proposal.reason);
  setDrafts([{key:'step1',label:proposal.reason.slice(0,140),tool:proposal.tool,
    path:proposal.arguments.path||'.',
    query:proposal.arguments.query||proposal.arguments.symbol||'',
    dependsOn:''}]);
 };
 const choices=capabilities.filter(t=>t.name!=='file.replace'||focus==='tasks');
 return <div className="aiws-os-stack aiws-os-studio">
  {error&&<div className="aiws-os-error" role="alert">{error}</div>}
  {focus==='model'&&<section className="aiws-os-card">
   <div className="aiws-os-studio-title"><h2><BrainCircuit size={18}/>{tr('本地 2B 智能助手','Local 2B assistant')}</h2>
    <span>{model?.online?'LOCAL ONLINE':model?.configured?'OFFLINE SERVICE NOT READY':'DISABLED'}</span></div>
   <div className="aiws-os-studio-actions">
     <button type="button" disabled={!csrf||busy||!model?.weightsPresent||Boolean(model?.configured)}
      onClick={()=>void toggleModel(true)}>{tr('申请启用模型（需审核）','Request model enable approval')}</button>
     <button type="button" disabled={!csrf||busy||!model?.configured}
      onClick={()=>void toggleModel(false)}>{tr('申请关闭模型（需审核）','Request model disable approval')}</button>
     <span className="aiws-os-muted">{model?.weightsPresent?tr('已发现客户机权重','Guest weights found'):tr('尚未安装客户机 GGUF 权重','Guest GGUF weights not provisioned')}</span>
    </div>
   <p>{tr('模型只提出工作区只读操作建议，不执行，也不自动调用云端。CPU 模式可用；权重需要在客户机内单独安装。',
    'The optional offline model only suggests read-only guest tools. No execution or cloud fallback; guest model weights are provisioned separately.')}</p>
   <label>{tr('希望 AI 完成什么？','What should the local assistant plan?')}
    <textarea value={instruction} onChange={e=>setInstruction(e.target.value)} rows={3} maxLength={1000}
     placeholder={tr('例如：查看项目中的 C# 文件结构','e.g. Inspect my guest C# project layout')}/></label>
   <button type="button" className="aiws-os-primary" disabled={!model?.online||!csrf||busy||!instruction.trim()}
    onClick={()=>void suggest()}><BrainCircuit size={16}/>{tr('生成本地工具建议','Suggest a local tool')}</button>
   <button type="button" disabled={!model?.online||!csrf||busy||!instruction.trim()}
    onClick={()=>void createOfflinePlan()}>{tr('生成并保存待审核任务','Create a pending audited task')}</button>
   {proposal&&<div className="aiws-os-proposal">
    <strong>{proposal.tool}</strong><p>{proposal.reason}</p>
    <pre>{JSON.stringify(proposal.arguments,null,2)}</pre>
    <p className="aiws-os-muted">{tr('尚未执行，需先确认计划并提交任务。','Not executed; review and create a task first.')}</p>
    <button type="button" onClick={addProposal}>{tr('复制建议到任务草稿','Copy suggestion into draft')}</button>
   </div>}
  </section>}
  <section className="aiws-os-card">
   <div className="aiws-os-studio-title"><h2><Plus size={18}/>{tr('创建持久化 AIWS 任务','Create a persistent AIWS task')}</h2>
    <button type="button" onClick={()=>void update()}><RefreshCw size={15}/></button></div>
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
    {s.error&&<p className="aiws-os-error">{s.error}</p>}
    {s.result!==null&&<pre className="aiws-os-result">{JSON.stringify(s.result,null,2)}</pre>}
    {(s.state==='pending'||s.state==='interrupted')&&s.approval===0?
      <button type="button" disabled={busy} onClick={()=>void command(s,'approve')}><ShieldCheck size={15}/>{tr('批准客体写操作','Approve guest write')}</button>:
      (s.state==='pending'||s.state==='interrupted')?
       <button type="button" className="aiws-os-primary" disabled={busy} onClick={()=>void command(s,'dispatch')}>
        <Play size={15}/>{tr('运行客户机阶段','Run guest stage')}</button>:null}
   </div>)}
   <h2><CheckCircle2 size={17}/>{tr('审计证据','Audit evidence')}</h2>
   {audit.slice(-12).map(e=><p className="aiws-os-muted" key={e.seq}>#{e.seq} {e.action} · {e.entry_hash.slice(0,12)}…</p>)}
  </section>}
 </div>;
}
