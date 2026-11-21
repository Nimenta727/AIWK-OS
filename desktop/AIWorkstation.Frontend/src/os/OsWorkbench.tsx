import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {Activity,BrainCircuit,Code2,FolderTree,Layers3,Play,RefreshCw,ShieldCheck} from 'lucide-react';
import './OsWorkbench.css';
import GuestFiles from './GuestFiles';
import GuestTaskStudio from './GuestTaskStudio';
import GuestSystemConsole from './GuestSystemConsole';

type Tool={name:string;description:string;inputSchema:{properties:Record<string,{type:string}>;required:string[]}};
type Job={id:string;tool:string;status:string;result:unknown;error:string|null;submittedAt:number};
type Health={mode:string;workspace:string;agent:string;toolCount:number;guestOnly:boolean;agentPrivileged:boolean;llmConnected:boolean;desktopInstalled:boolean;displayManagerInstalled:boolean;uiBundled:boolean;brokerReady?:boolean;brokerScope?:string};
type Snapshot={health:Health;capabilities:Tool[];jobs:Job[]};
type Page='overview'|'files'|'code'|'tasks'|'plans'|'local'|'system';
type Language='zh'|'en';
const MENU:{id:Page;zh:string;en:string;icon:typeof Activity}[]=[
 {id:'overview',zh:'操作系统工作台',en:'OS Workbench',icon:Layers3},
 {id:'files',zh:'AI 文件管理',en:'AI Files',icon:FolderTree},
 {id:'code',zh:'跨平台代码智能',en:'Code Intelligence',icon:Code2},
 {id:'tasks',zh:'Agent 任务证据',en:'Agent Tasks',icon:BrainCircuit},
 {id:'plans',zh:'持久任务与 DAG',en:'Persistent DAG',icon:Layers3},
 {id:'local',zh:'本地 AI 助手',en:'Local AI Assistant',icon:BrainCircuit},
 {id:'system',zh:'系统与安全',en:'System & Security',icon:ShieldCheck}
];

async function api<T>(url:string,options?:RequestInit):Promise<T>{
 const response=await fetch('/api/v1'+url,{cache:'no-store',credentials:'omit',...options});
 const data=await response.json() as T&{error?:string};
 if(!response.ok)throw new Error(data.error||'Guest service request failed');
 return data;
}

export default function OsWorkbench(){
 const [language,setLanguage]=useState<Language>('zh');
 const tr=(zh:string,en:string)=>language==='zh'?zh:en;
 const [page,setPage]=useState<Page>('overview');
 const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
 const [csrf,setCsrf]=useState('');
 const [error,setError]=useState('');
 const [tool,setTool]=useState('code.symbols');
 const [path,setPath]=useState('.');
 const [query,setQuery]=useState('');
 const [job,setJob]=useState<Job|null>(null);
 const [submitting,setSubmitting]=useState(false);
 const pending=useRef(false);
 const [starting,setStarting]=useState(true);
 const refresh=useCallback(async()=>{
  try{setSnapshot(await api<Snapshot>('/snapshot'));setError('');}
  catch(e){setError(e instanceof Error?e.message:String(e));}
 },[]);
 useEffect(()=>{
  let active=true;
  void Promise.all([api<Snapshot>('/snapshot'),api<{csrf:string}>('/session')])
   .then(([state,session])=>{if(active){setSnapshot(state);setCsrf(session.csrf);}})
   .catch(e=>{if(active)setError(String(e));})
   .finally(()=>{if(active)setStarting(false);});
  return()=>{active=false;};
 },[]);
 useEffect(()=>{
  if(!job||!['queued','running'].includes(job.status))return;
  let active=true;
  const interval=window.setInterval(()=>{
   void api<Job>('/jobs/'+encodeURIComponent(job.id))
    .then(result=>{if(active){setJob(result);if(!['queued','running'].includes(result.status))void refresh();}})
    .catch(e=>{if(active)setError(String(e));});
  },1200);
  return()=>{active=false;window.clearInterval(interval);};
 },[job,refresh]);
 const tools=useMemo(()=>snapshot?.capabilities||[],[snapshot]);
 const chosen=tools.find(t=>t.name===tool);
 const run=async()=>{
  if(pending.current||!csrf||!chosen)return;
  const params:Record<string,string>={};
  if(chosen.inputSchema.properties.path)params.path=path||'.';
  if(chosen.inputSchema.properties.query)params.query=query;
  if(chosen.inputSchema.properties.symbol)params.symbol=query;
  if(chosen.inputSchema.properties.view)params.view='status';
  if(chosen.inputSchema.required.some(k=>!params[k])){setError(tr('请填写必填参数','Please enter the required argument'));return;}
  pending.current=true;setSubmitting(true);setError('');
  try{
   const result=await api<Job>('/jobs',{method:'POST',
    headers:{'Content-Type':'application/json','X-AIWS-CSRF':csrf},
    body:JSON.stringify({tool,arguments:params})});
   setJob(result);setPage('tasks');await refresh();
  }catch(e){setError(String(e));}
  finally{pending.current=false;setSubmitting(false);}
 };
 const health=snapshot?.health;
 return <div className="aiws-os">
   <aside className="aiws-os-sidebar">
    <div className="aiws-os-brand"><div className="aiws-os-mark"><Layers3 size={22}/></div><span><strong>AIWS OS</strong><small>AI-NATIVE WORKSTATION</small></span></div>
    <div className="aiws-os-category">{tr('统一操作入口','UNIFIED SYSTEM INTERFACE')}</div>
    <nav aria-label={tr('工作台导航','Workbench navigation')}>{MENU.map(({id,zh,en,icon:Icon})=>
     <button type="button" key={id} className={page===id?'active':''} onClick={()=>setPage(id)}><Icon size={17}/>{language==='zh'?zh:en}</button>)}</nav>
    <div className="aiws-os-foot">{health?tr('本地系统服务已响应','GUEST SERVICE RESPONDING'):tr('正在检查系统服务','CHECKING SERVICE')}<small>127.0.0.1 · {health?.mode||'not connected'}</small></div>
   </aside>
   <main className="aiws-os-body">
    <header className="aiws-os-top"><span>AIWS / <strong>{MENU.find(x=>x.id===page)?.[language]}</strong></span><div>
     <button type="button" onClick={()=>setLanguage(x=>x==='zh'?'en':'zh')}>{language==='zh'?'EN':'中文'}</button>
     <button type="button" onClick={()=>void refresh()} title={tr('刷新','Refresh')} aria-label={tr('刷新','Refresh')}><RefreshCw size={16}/></button></div></header>
    <div className="aiws-os-content">
     <div className="aiws-os-heading"><small>AIWS OS / LINUX GUEST</small>
      <h1>{page==='overview'?tr('工作台与操作系统，真正贯通','One workspace, integrated with Linux'):
        page==='files'?tr('AI 工作区文件管理','AI-managed guest files'):
        page==='code'?tr('跨平台代码智能引擎','Cross-platform code intelligence'):
        page==='tasks'?tr('Agent 任务与执行证据','Agent tasks and execution evidence'):
        page==='plans'?tr('持久任务与 DAG 审计','Persistent tasks and DAG audit'):
        page==='local'?tr('本地小模型与离线规划','Local model and offline planning'):
        tr('系统服务与安全边界','System services and security')}</h1>
      <p>{tr('通过同一套工作台调度 Linux 能力；所有执行结果都可查看。','Call guest-native capabilities from one workbench and inspect every result.')}</p>
     </div>
     {starting&&<p>{tr('正在加载系统状态…','Loading guest status…')}</p>}
     {error&&<div className="aiws-os-error" role="alert">{error}</div>}
     {page==='overview'&&<div className="aiws-os-grid">
      <section><Activity size={21}/><h2>{tr('系统服务','OS service')}</h2><strong>{health?'CONNECTED':'DISCONNECTED'}</strong><p>{health?.mode||'–'}</p></section>
      <section><BrainCircuit size={21}/><h2>{tr('AI 调用能力','Tool capabilities')}</h2><strong>{health?.toolCount??'–'}</strong><p>{tr('只读接口','Read-only interfaces')}</p></section>
      <section><FolderTree size={21}/><h2>{tr('客户机工作区','Guest workspace')}</h2><strong className="aiws-os-path">{health?.workspace||'–'}</strong><p>{tr('不自动共享宿主文件夹','No host folder mount')}</p></section>
      <section><ShieldCheck size={21}/><h2>{tr('权限','Privileges')}</h2><strong>{health?.agentPrivileged?'ELEVATED':'USER ONLY'}</strong><p>{tr('默认无 root 权限','No root privileges by default')}</p></section>
      <section><ShieldCheck size={21}/><h2>{tr('独立权限 Broker','Independent Permission Broker')}</h2>
       <strong>{health?.brokerReady?'CONNECTED':'UNAVAILABLE'}</strong>
       <p>{tr('已接入独立用户态决策服务；不构成内核强制隔离','Independent same-UID policy process; not mandatory OS isolation')}</p></section>
      <section className="aiws-os-wide"><h2>{tr('系统运行架构','Unified execution route')}</h2>
       <p>{tr('工作台 → 持久 Agent → 独立权限 Broker → 客户机工具 → 审计证据',
        'Workbench → persistent Agent → independent permission broker → guest tools → audit evidence')}</p>
       <button type="button" className="aiws-os-primary" onClick={()=>setPage('code')}>{tr('打开代码智能','Open code intelligence')}</button>
      </section>
     </div>}
     {page==='files'&&<GuestFiles csrf={csrf} english={language==='en'} onPlanCreated={()=>setPage('plans')}/>}
     {page==='code'&&<section className="aiws-os-card">
      <h2>{tr('通过 Agent 调用代码能力','Call a code tool through the task controller')}</h2>
      <label>{tr('能力','Capability')}<select value={tool} onChange={e=>setTool(e.target.value)}>{tools.map(item=><option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
      {chosen?.inputSchema.properties.path&&<label>{tr('相对路径','Relative path')}<input value={path} onChange={e=>setPath(e.target.value)}/></label>}
      {(chosen?.inputSchema.properties.query||chosen?.inputSchema.properties.symbol)&&<label>{chosen.inputSchema.properties.symbol?'Symbol':'Query'}<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="ContentView"/></label>}
      <p className="aiws-os-muted">{chosen?.description}</p>
      <button type="button" className="aiws-os-primary" disabled={submitting||!chosen||!csrf} onClick={()=>void run()}><Play size={16}/>{tr('提交只读任务','Run read-only task')}</button>
     </section>}
     {page==='tasks'&&<div className="aiws-os-stack">
      <section className="aiws-os-card"><h2>{tr('任务队列','Task queue')}</h2>{snapshot?.jobs.length? snapshot.jobs.map(item=>
       <button type="button" className="aiws-os-task" key={item.id} onClick={()=>setJob(item)}><span>{item.tool}</span><strong>{item.status}</strong></button>)
       :<p>{tr('暂无任务','No tasks yet')}</p>}</section>
      {job&&<section className="aiws-os-card"><h2>{tr('任务详情','Task detail')} · {job.tool}</h2><p>{job.status}</p>
       {job.error&&<div className="aiws-os-error">{job.error}</div>}
       {job.result!==null&&<pre className="aiws-os-result">{JSON.stringify(job.result,null,2)}</pre>}</section>}
     </div>}
     {(page==='plans'||page==='local')&&<GuestTaskStudio csrf={csrf} english={language==='en'} capabilities={tools} focus={page==='local'?'model':'tasks'}/>}
     {page==='system'&&<GuestSystemConsole csrf={csrf} english={language==='en'} onPlanCreated={()=>setPage('plans')}/>}

    </div>
   </main>
  </div>;
}
