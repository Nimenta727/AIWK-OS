import {useCallback,useEffect,useState} from 'react';
import {api} from './api';
import {Badge,Button,Empty,Icon,IconButton,Input,Notice,Row,Section,Select} from '../ui/kit';

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
const STAGE_STATE:Record<string,{zh:string;en:string;tone?:'ok'|'warn'|'err'|'info'}>={
 pending:{zh:'待执行',en:'Pending'},queued:{zh:'排队中',en:'Queued',tone:'info'},running:{zh:'执行中',en:'Running',tone:'info'},
 completed:{zh:'已完成',en:'Completed',tone:'ok'},failed:{zh:'失败',en:'Failed',tone:'err'},interrupted:{zh:'已中断',en:'Interrupted',tone:'warn'}};
const errText=(e:unknown)=>e instanceof Error?e.message:String(e);
const newStage=(n:number):StageDraft=>({key:'step'+n,label:'Step '+n,tool:'workspace.tree',path:'.',query:'',dependsOn:n>1?'step'+(n-1):''});

/** Persistent tasks (hand-built DAGs, approvals, audit) and, with focus="model", the local model switch.
 *  `.aiws-os-studio` and `.aiws-os-stage-status[data-state]` are hooks of the in-image GUI smoke test. */
export default function GuestTaskStudio({english,capabilities,focus='tasks'}:{
 csrf?:string;english:boolean;capabilities:Capability[];focus?:'tasks'|'model'
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
 const update=useCallback(async()=>{
  try{
   setTaskList((await api<{tasks:TaskHeader[]}>('/tasks')).tasks);
   if(focus==='model'){setModel(await api<ModelStatus>('/model/status'));
    setRouteCfg((await api<{config:{externalEnabled:boolean}}>('/route/config')).config);}
  }catch(e){setError(errText(e));}
 },[focus]);
 useEffect(()=>{void update();},[update]);
 const open=useCallback(async(id:string)=>{
  try{
   setDetail(await api<TaskDetail>('/tasks/'+id));
   setAudit((await api<{events:typeof audit}>('/tasks/'+id+'/audit')).events);
  }catch(e){setError(errText(e));}
 },[]);
 useEffect(()=>{
  if(!detail||!detail.stages.some(s=>s.state==='queued'||s.state==='running'))return;
  const interval=window.setInterval(()=>{void open(detail.task.id);},1400);
  return()=>window.clearInterval(interval);
 },[detail,open]);
 /** One action at a time: busy flag, error capture. */
 const act=async(fn:()=>Promise<void>)=>{
  if(busy)return;
  setBusy(true);setError('');
  try{await fn();}catch(e){setError(errText(e));}finally{setBusy(false);}
 };
 const create=()=>act(async()=>{
  const stages=drafts.map(d=>{
   const spec=capabilities.find(c=>c.name===d.tool);
   const args:Record<string,string>={};
   if(spec?.inputSchema.properties.path)args.path=d.path||'.';
   if(spec?.inputSchema.properties.query)args.query=d.query;
   if(spec?.inputSchema.properties.symbol)args.symbol=d.query;
   if(spec?.inputSchema.properties.view)args.view='status';
   return {key:d.key,label:d.label,tool:d.tool,arguments:args,dependsOn:d.dependsOn?[d.dependsOn]:[]};
  });
  const next=await api<TaskDetail>('/tasks',{method:'POST',body:JSON.stringify({title,goal,stages})});
  setDetail(next);setDrafts([newStage(1)]);setTitle('');setGoal('');
  await update();await open(next.task.id);
 });
 const stageCall=(stage:Stage,actions:('approve'|'dispatch')[])=>act(async()=>{
  if(!detail)return;
  for(const a of actions)await api('/tasks/'+detail.task.id+'/stages/'+stage.stage_key+'/'+a,{method:'POST',body:'{}'});
  await open(detail.task.id);
 });
 const toggleModel=(value:boolean)=>act(async()=>{
  const plan=await api<TaskDetail>('/model/'+(value?'enable':'disable'),{method:'POST',body:'{}'});
  await update();await open(plan.task.id);
 });
 const suggest=()=>act(async()=>{
  if(!instruction.trim())return;
  setProposal(null);
  setProposal(await api<Proposal>('/model/suggest',{method:'POST',body:JSON.stringify({instruction})}));
 });
 const createOfflinePlan=()=>act(async()=>{
  if(!model?.online||!instruction.trim())return;
  // The model proposes one tool or an ordered plan. The server persists an audited DAG:
  // local read-only stages run automatically; file-changing stages wait for approval.
  setRouteInfo(null);
  const item=await api<TaskDetail|{refused:true;proposal:Proposal;decision:Decision;followUp:FollowUp}|
   {routed:string;decision:Decision;followUp?:FollowUp;error?:string}>('/model/plan',{method:'POST',body:JSON.stringify({instruction})});
  if('refused' in item){setProposal(item.proposal);setRouteInfo({decision:item.decision,followUp:item.followUp,refused:true});return;}
  if('routed' in item){setRouteInfo({decision:item.decision,followUp:item.followUp,error:item.error});return;}
  await update();await open(item.task.id);
 });
 const createHandoff=(agent:string)=>act(async()=>{
  if(!instruction.trim())return;
  const out=await api<{task:{id:string}}>('/route/handoff',{method:'POST',body:JSON.stringify({instruction,agent})});
  await update();await open(out.task.id);
 });
 const addProposal=()=>{
  if(!proposal||proposal.tool==='refuse'||proposal.steps)return;
  setTitle(instruction.slice(0,100));setGoal(proposal.reason);
  setDrafts([{key:'step1',label:proposal.reason.slice(0,140),tool:proposal.tool,path:proposal.arguments.path||'.',
   query:proposal.arguments.query||proposal.arguments.symbol||'',dependsOn:''}]);
 };
 const setDraft=(i:number,change:Partial<StageDraft>)=>setDrafts(x=>x.map((y,j)=>i===j?{...y,...change}:y));
 const needWhy=!model?.online?tr('本地模型没有在线：先导入权重并启用','The local model is not online: import weights and enable it first'):!instruction.trim()?tr('先写下希望完成什么','Describe what you want first'):undefined;
 const choices=capabilities.filter(t=>t.name!=='file.replace'||focus==='tasks');
 const modelState=model?.online?{text:tr('在线','Online'),tone:'ok' as const}:model?.configured?{text:tr('已启用，服务未就绪','Enabled, service not ready'),tone:'warn' as const}:{text:tr('未启用','Off'),tone:undefined};
 const stateOf=(s:string)=>STAGE_STATE[s]||{zh:s,en:s};

 return <div className="gp aiws-os-studio">
  <header><h2>{focus==='model'?tr('本地模型开关','Model switch'):tr('持久任务与 DAG','Persistent tasks')}</h2>
   <IconButton icon="refresh" label={tr('刷新','Refresh')} onClick={()=>void update()}/></header>
  {error&&<Notice tone="err">{error}</Notice>}

  {focus==='model'&&<Section title={tr('本地模型','Local model')}>
   <div className="kv"><Icon name="hubot"/><span>{tr('模型','Model')}</span><code>Qwen3.5-9B</code><span className="muted">Q4_K_M · GGUF</span></div>
   <div className="kv"><Icon name="pulse"/><span>{tr('状态','State')}</span><Badge tone={modelState.tone}>{modelState.text}</Badge>
    <span className="muted">{model?.weightsPresent?tr('已发现客户机权重','Guest weights found'):tr('尚未导入模型权重（见 docs/AIWS_MODEL_WEIGHTS.md）','No model weights imported (see docs/AIWS_MODEL_WEIGHTS.md)')}</span></div>
   <div className="form">
    <Button icon="play" disabled={busy||!model?.weightsPresent||Boolean(model?.configured)}
     title={!model?.weightsPresent?tr('还没有导入模型权重：步骤见 docs/AIWS_MODEL_WEIGHTS.md','No model weights imported yet: see docs/AIWS_MODEL_WEIGHTS.md'):model?.configured?tr('模型已经启用','The model is already enabled'):undefined}
     onClick={()=>void toggleModel(true)}>{tr('申请启用模型（需审核）','Request model enable approval')}</Button>
    <Button icon="circle-slash" disabled={busy||!model?.configured} title={!model?.configured?tr('模型没有启用，无需关闭','The model is not enabled'):undefined}
     onClick={()=>void toggleModel(false)}>{tr('申请关闭模型（需审核）','Request model disable approval')}</Button>
   </div>
   <p className="muted pad">{tr('模型完全在本机离线运行，不联网、不下载、不调用云端。它可以读取系统与网络状态、查看下载进度，并提出文件整理计划：只读步骤自动执行，任何会改动文件的步骤都要你逐项批准，删除只会进回收站。',
    'The model runs fully offline on this machine: no network, no downloading, no cloud. It can read system and network state, check download progress and plan file organisation. Read-only steps run automatically; every file change needs your approval, and deleting only moves to trash.')}</p>
   <div className="form col"><label className="gp-label" htmlFor="gp-instruction">{tr('希望本地模型规划什么？','What should the local model plan?')}</label>
    <textarea id="gp-instruction" className="k-input gp-text" value={instruction} onChange={e=>setInstruction(e.target.value)} rows={3} maxLength={1000}
     placeholder={tr('例如：看看下载进度，把已完成的下载移到 isos 文件夹','e.g. Check download progress and move finished downloads into isos/')}/></div>
   <div className="form">
    <Button variant="primary" icon="sparkle" disabled={!model?.online||busy||!instruction.trim()} title={needWhy} onClick={()=>void suggest()}>{tr('生成本地工具建议','Suggest a local tool')}</Button>
    <Button icon="checklist" disabled={!model?.online||busy||!instruction.trim()} title={needWhy} onClick={()=>void createOfflinePlan()}>{tr('生成并保存待审核任务','Create a pending audited task')}</Button>
   </div>
   <p className="muted pad">{routeCfg?.externalEnabled?
    tr('外部官方 CLI 已在 routes.json 启用：仅在你确认后生成交接文件，AIWS 不会自动调用它们。','External official CLIs are enabled in routes.json: a handoff file is only prepared after your consent; AIWS never launches them.'):
    tr('外部模型默认关闭，所有请求只在本机离线处理（可在 ~/.config/aiws/routes.json 启用交接）。','External models are off by default: everything stays on this machine (enable handoff in ~/.config/aiws/routes.json).')}</p>
   {routeInfo&&<div className="gp-card" role="status" data-aiws="route-card"><div className="gp-card-main">
    <strong>{tr('路由决定','Routing decision')}: {routeInfo.decision.route}{routeInfo.decision.agent!=='local'?' → '+routeInfo.decision.agent:''}</strong>
    <p>{english?routeInfo.decision.reason.en:routeInfo.decision.reason.zh}</p>
    {routeInfo.decision.forbidden.length>0&&<p className="muted">{tr('命中受限类别：','Restricted categories: ')}{routeInfo.decision.forbidden.join(', ')}</p>}
    {routeInfo.error&&<p className="muted">{routeInfo.error}</p>}
    {routeInfo.followUp?.reason&&<p>{english?routeInfo.followUp.reason.en:routeInfo.followUp.reason.zh}</p>}
    {Object.entries(routeInfo.decision.providers).map(([name,p])=><span key={name} className="muted"> {name}: {p.enabled?tr('已启用','enabled'):tr('未启用','disabled')} / {p.installed?tr('已安装','installed'):tr('本机未安装','not installed here')} </span>)}</div>
    {(routeInfo.decision.route==='external'||routeInfo.followUp?.action==='propose-handoff')&&routeInfo.decision.externalAllowed&&<div className="gp-actions">
     <p className="muted">{tr('将写入工作区 handoff/ 的文件只含指令和文件名，不含文件内容或凭据；写入本身需要你批准。','The file written to handoff/ holds only your instruction and file names: no contents or credentials; writing it needs your approval.')}</p>
     <Button disabled={busy} onClick={()=>void createHandoff(routeInfo.followUp?.agent||routeInfo.decision.agent)}>{tr('生成交接文件（需批准）','Prepare handoff file (needs approval)')}</Button></div>}
   </div>}
   {proposal&&<div className="gp-card"><div className="gp-card-main">
    <strong>{proposal.steps?tr('多步计划','Multi-step plan')+' ('+proposal.steps.length+')':proposal.tool}</strong><p>{proposal.reason}</p>
    {proposal.steps?<ol className="gp-steps">{proposal.steps.map((s,i)=><li key={i}><code>{s.tool}</code> {JSON.stringify(s.arguments)} — {s.reason}
      <Badge tone={READ_ONLY.has(s.tool)?undefined:'warn'}>{READ_ONLY.has(s.tool)?tr('只读，自动执行','read-only, runs automatically'):tr('需你批准','needs your approval')}</Badge></li>)}</ol>:
     <pre className="gp-pre">{JSON.stringify(proposal.arguments,null,2)}</pre>}
    <p className="muted">{tr('尚未执行，需先确认计划并提交任务。','Not executed; review and create a task first.')}</p></div>
    <div className="gp-actions">{proposal.tool==='refuse'?<Notice tone="warn">{tr('越权请求已拒绝；不会建立可执行任务','Out-of-scope request refused; no executable task created')}</Notice>:
     <Button icon="copy" onClick={addProposal}>{tr('复制建议到任务草稿','Copy suggestion into draft')}</Button>}</div>
   </div>}
  </Section>}

  <Section title={tr('创建持久化任务','Create a persistent task')}>
   <p className="muted pad">{tr('所有阶段、依赖、审批和审计都保存在客户机 SQLite 里。文件写入需要审批，任何操作都不会碰宿主机。',
    'Stages, DAG dependencies, approval and audit remain in guest-local SQLite. File writes require approval; host access is never exposed.')}</p>
   <div className="form col">
    <label className="gp-label" htmlFor="gp-title">{tr('任务标题','Task title')}</label>
    <Input id="gp-title" value={title} maxLength={160} onChange={e=>setTitle(e.target.value)}/>
    <label className="gp-label" htmlFor="gp-goal">{tr('任务目标','Goal')}</label>
    <textarea id="gp-goal" className="k-input gp-text" value={goal} onChange={e=>setGoal(e.target.value)} maxLength={4000} rows={2}/>
   </div>
   {drafts.map((d,i)=>{const props=capabilities.find(c=>c.name===d.tool)?.inputSchema.properties;return <div key={i} className="gp-card gp-stage">
    <div className="gp-stage-head"><strong>{tr('阶段','Stage')} {i+1}</strong>
     {drafts.length>1&&<IconButton icon="close" label={tr('移除这个阶段','Remove this stage')} onClick={()=>setDrafts(x=>x.filter((_,j)=>j!==i))}/>}</div>
    <div className="gp-grid">
     <label>{tr('阶段标识','Key')}<Input value={d.key} onChange={e=>setDraft(i,{key:e.target.value})}/></label>
     <label>{tr('阶段说明','Label')}<Input value={d.label} onChange={e=>setDraft(i,{label:e.target.value})}/></label>
     <label>{tr('工具','Tool')}<Select value={d.tool} onChange={e=>setDraft(i,{tool:e.target.value})}>{choices.map(x=><option value={x.name} key={x.name}>{x.name}</option>)}</Select></label>
     <label>{tr('依赖前一个阶段','Depends on')}<Select value={d.dependsOn} onChange={e=>setDraft(i,{dependsOn:e.target.value})}>
      <option value="">{tr('无','None')}</option>{drafts.slice(0,i).map(s=><option value={s.key} key={s.key}>{s.key}</option>)}</Select></label>
     {props?.path&&<label>{tr('工作区相对路径','Relative guest path')}<Input value={d.path} onChange={e=>setDraft(i,{path:e.target.value})}/></label>}
     {(props?.query||props?.symbol)&&<label>{tr('查询或符号','Query or symbol')}<Input value={d.query} onChange={e=>setDraft(i,{query:e.target.value})}/></label>}
    </div>
   </div>;})}
   <div className="form">
    <Button icon="add" disabled={drafts.length>=32} onClick={()=>setDrafts(x=>[...x,newStage(x.length+1)])}>{tr('添加阶段','Add stage')}</Button>
    <Button variant="primary" icon="save" disabled={!title.trim()||busy} title={title.trim()?undefined:tr('先填写任务标题','Enter a task title first')}
     onClick={()=>void create()}>{tr('保存任务与 DAG','Save task and DAG')}</Button>
   </div>
  </Section>

  <Section title={tr('已保存的任务','Saved tasks')} count={taskList.length}>
   {taskList.map(task=><Row key={task.id} icon="list-tree" label={task.title} on={detail?.task.id===task.id} onClick={()=>void open(task.id)}
     detail={new Date(task.created_at*1000).toLocaleString()}/>)}
   {!taskList.length&&<p className="muted pad">{tr('还没有保存的任务','No saved tasks yet')}</p>}
  </Section>

  {detail?<Section title={detail.task.title}>
   {detail.task.goal&&<p className="muted pad">{detail.task.goal}</p>}
   {detail.stages.map(s=>{const st=stateOf(s.state);const depsDone=s.dependsOn.every(k=>detail.stages.find(x=>x.stage_key===k)?.state==='completed');
    return <div className="gp-card aiws-os-stage-status" key={s.id} data-state={s.state}><div className="gp-card-main">
     <strong>{s.stage_key}: {s.label}</strong> <Badge tone={st.tone}>{english?st.en:st.zh}</Badge>
     <p className="muted"><code>{s.tool}</code>{s.dependsOn.length?' ← '+s.dependsOn.join(', '):''}{READ_ONLY.has(s.tool)?' · '+tr('只读','read-only'):' · '+tr('会改动，需要批准','changes things, needs approval')}</p>
     {!READ_ONLY.has(s.tool)&&<pre className="gp-pre" aria-label={tr('将要执行的参数','Arguments to be executed')}>{JSON.stringify(s.arguments,null,2)}</pre>}
     {s.error&&<p className="gp-err">{s.error}</p>}
     {s.result!==null&&<details><summary>{tr('结果','Result')}</summary><pre className="gp-pre selectable">{JSON.stringify(s.result,null,2)}</pre></details>}</div>
     <div className="gp-actions">
      {(s.state==='pending'||s.state==='interrupted')&&s.approval===0?<>
       <Button icon="shield" disabled={busy} onClick={()=>void stageCall(s,['approve'])}>{tr('批准客体写操作','Approve guest write')}</Button>
       {depsDone&&<Button variant="primary" icon="play" disabled={busy} onClick={()=>void stageCall(s,['approve','dispatch'])}>{tr('批准并运行','Approve & run')}</Button>}</>
      :(s.state==='pending'||s.state==='interrupted')?
       <Button variant="primary" icon="play" disabled={busy||!depsDone} title={depsDone?undefined:tr('要等它依赖的阶段先完成','Waits for the stages it depends on')}
        onClick={()=>void stageCall(s,['dispatch'])}>{tr('运行客户机阶段','Run guest stage')}</Button>:null}
     </div></div>;})}
   <Section title={tr('审计证据','Audit evidence')} count={audit.length} defaultOpen={false}>
    {audit.slice(-12).map(e=><div className="kv" key={e.seq}><code>#{e.seq}</code><span>{e.action}</span><span className="muted">{e.entry_hash.slice(0,12)}…</span></div>)}
   </Section>
  </Section>:focus==='tasks'&&taskList.length>0&&<Empty icon="list-tree" title={tr('选择一个任务查看阶段和审计','Pick a task to see its stages and audit')}/>}
 </div>;
}
