import {useCallback,useEffect,useMemo,useState} from 'react';
import {Activity, ArrowRight, BadgeCheck, Boxes, ChevronDown, CircleHelp, Code2, Folder, GitBranch, LayoutDashboard, ListTodo, Plus, RefreshCw, Settings2, Sparkles, Terminal, GitCompare, Workflow, X} from 'lucide-react';
import {bridge, type Snapshot, type WorkTask, type WorkStep} from './bridge';
import {WorkflowCanvas} from './components/WorkflowCanvas';
import {DagCanvas} from './components/DagCanvas';
import {WorkflowDesigner} from './components/WorkflowDesigner';
import {TerminalPanel} from './components/TerminalPanel';
import {ExecutionTimeline} from './components/ExecutionTimeline';
import {TracePanel} from './components/TracePanel';
import {TaskInspector} from './components/TaskInspector';
import {DevToolsPanel} from './components/DevToolsPanel';
import {ProjectExplorer} from './components/ProjectExplorer';
import {T3Skeleton} from './components/T3Skeleton';
import {T3StatusDot} from './components/T3StatusDot';
import {sumMeasuredUsage} from './model/workflow.mjs';

type Page = 'overview'|'flow'|'trace'|'project'|'tools'|'integrations'|'terminal'|'ledger';
const nav=[{id:'overview',label:'工作台概览',icon:LayoutDashboard},{id:'flow',label:'可视化工作流',icon:Workflow},{id:'trace',label:'调用追踪',icon:Activity},{id:'project',label:'文件与 Git 变更',icon:Code2},{id:'tools',label:'Git 只读控制台',icon:GitCompare},{id:'terminal',label:'Windows 内置终端',icon:Terminal},{id:'ledger',label:'执行事件账本',icon:ListTodo},{id:'integrations',label:'Agent 与能力',icon:Boxes}] as const;
function TitleLogo(){return <span className="brand-mark"><Sparkles size={19} strokeWidth={1.9}/></span>}
export default function App(){
 const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
 const [selectedTask,setSelectedTask]=useState<string|null>(null);
 const [selectedNode,setSelectedNode]=useState<string|null>(null);
 const [page,setPage]=useState<Page>('overview');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [showCreate,setShowCreate]=useState(false);
 const [title,setTitle]=useState('');
 const [workspace,setWorkspace]=useState('');
 const [template,setTemplate]=useState('dual');
 const load=useCallback(async()=>{const data=await bridge.call<Snapshot>('state');setSnapshot(data);setSelectedTask(current=>current&&data.tasks.some(x=>x.id===current)?current:(data.tasks[0]?.id??null));},[]);
 useEffect(()=>{load().catch(err=>setError(String(err.message||err)));},[load]);
 const task=useMemo(()=>snapshot?.tasks.find(x=>x.id===selectedTask)||null,[snapshot,selectedTask]);
 const step=useMemo(()=>task?.steps.find(x=>x.id===selectedNode)||null,[task,selectedNode]);
 const action=useCallback(async(name:string,payload:Record<string,unknown>={})=>{
   setBusy(true);setError('');try{
     const response=await bridge.call<{id?:string}>(name,payload);
     await load();
     if(name==='tasks.create'){setShowCreate(false);setTitle('');if(response?.id){setSelectedTask(response.id);setSelectedNode(null);setPage('flow');}}
   }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
 },[load]);
 const create=async()=>{if(!workspace||!title.trim())return;await action('tasks.create',{title,workspace,template});};
 const pickWorkspace=async()=>{try{const result=await bridge.call<{path:string}>('workspaces.pick');if(result?.path)setWorkspace(result.path);}catch(e){setError(String(e));}};
 const measured=task?sumMeasuredUsage(task):null;
 return <div className={`app-shell ${page==='project'?'project-active':''}`}>
   <aside className="sidebar"><div className="brand"><TitleLogo/><div><strong>AI Workstation</strong><small>Windows · Personal Console</small></div></div>
     <div className="sidebar-section">工作空间</div>
     <nav className="nav">{nav.map(n=><button key={n.id} className={`nav-link ${page===n.id?'active':''}`} onClick={()=>setPage(n.id)}><n.icon size={18} strokeWidth={1.8}/><span>{n.label}</span>{page===n.id&&<span className="nav-active-dot"/>}</button>)}</nav>
     <div className="sidebar-section section-project"><span>最近任务</span><button className="icon-button" aria-label="新建任务" onClick={()=>setShowCreate(true)}><Plus size={16}/></button></div>
     <div className="task-nav">{snapshot?.tasks.length?snapshot.tasks.slice().sort((a,b)=>String(b.createdAt).localeCompare(String(a.createdAt))).slice(0,12).map(t=><button key={t.id} className={`task-link ${selectedTask===t.id?'picked':''}`} onClick={()=>{setSelectedTask(t.id);setSelectedNode(null);setPage('flow');}}><GitBranch size={15}/><span title={t.title}>{t.title}</span></button>):<div className="no-tasks">暂无任务。创建你的第一个工作流。</div>}</div>
     <div className="sidebar-bottom"><div className="system-line"><span className="system-pulse"/> 本地运行 · 不调用云端 UI</div><button className="profile"><span className="avatar">AI</span><span>个人工作台<small>Hyper-V Windows</small></span><Settings2 size={16}/></button></div>
   </aside>
   <main className="main-view"><header className="topbar"><div className="breadcrumb"><span>AIWS</span><ArrowRight size={13}/><strong>{nav.find(n=>n.id===page)?.label}</strong></div><div className="top-actions"><span className="mode-label">Local-first</span><button className="icon-button" onClick={()=>load().catch(e=>setError(String(e)))} aria-label="刷新任务"><RefreshCw size={16}/></button><button className="button dark small" onClick={()=>setShowCreate(true)}><Plus size={16}/> 新建任务</button></div></header>
     {error&&<div className="error-toast" role="alert">{error}<button onClick={()=>setError('')} aria-label="关闭"><X size={16}/></button></div>}
     {!snapshot?<div className="loading"><T3Skeleton className="skeleton-heading"/><T3Skeleton className="skeleton-card"/><T3Skeleton className="skeleton-card"/></div>:
     <div className="content">
       {page==='overview'&&<div className="overview"><div className="eyebrow">YOUR PERSONAL AI DESK</div><h1>把复杂工作，交给有序协作。</h1><p className="lead">统一规划 Claude 与 Codex 的任务，在 Windows 本地管理工作区、权限、请求链路和交付结果。</p>
         <div className="overview-toolbar"><button className="button dark" onClick={()=>setShowCreate(true)}><Plus size={17}/> 创建协作任务</button><button className="button secondary" onClick={()=>task&&setPage('flow')} disabled={!task}><Workflow size={16}/> 打开工作流</button></div>
         <div className="metric-grid"><div className="metric"><span>总任务</span><strong>{snapshot.tasks.length}</strong><small>本地保存</small></div><div className="metric"><span>已完成阶段</span><strong>{snapshot.tasks.reduce((n,t)=>n+t.completedCount,0)}</strong><small>经确认后计入</small></div><div className="metric"><span>可用 CLI</span><strong>{Object.values(snapshot.agents).filter(Boolean).length}</strong><small>检测本机安装</small></div></div>
         <div className="section-title"><span>当前工作流</span><button onClick={()=>setPage('flow')}>查看流程 <ArrowRight size={14}/></button></div>
         {task?<div className="overview-task" onClick={()=>setPage('flow')} role="button" tabIndex={0} onKeyDown={e=>e.key==='Enter'&&setPage('flow')}><div className="task-top"><span className="task-icon"><Code2 size={20}/></span><div><strong>{task.title}</strong><small>{task.workspace}</small></div><span className="subtle-chip">{task.completedCount}/{task.steps.length} 阶段</span></div><div className="step-mini">{task.steps.map((s,i)=><div key={s.id}><span className={`mini-number ${s.status==='Completed'?'done':''}`}>{i+1}</span><span>{s.title}</span>{i<task.steps.length-1&&<span className="mini-line"/>}</div>)}</div></div>:<div className="blank-state"><Sparkles size={25}/><strong>你的第一条工作流，从这里开始</strong><p>选择项目文件夹，AIWS 会准备 Claude → Codex → 审查流程。</p><button className="button dark" onClick={()=>setShowCreate(true)}>创建工作流</button></div>}
       </div>}
       {page==='flow'&&<div className="workspace-page">{task?<><div className="page-heading"><div><div className="eyebrow">VISUAL WORKFLOW</div><h1>{task.title}</h1><p><Folder size={14}/>{task.workspace}</p></div><div className="right-chip">{task.completedCount} / {task.steps.length} 已完成 <ChevronDown size={14}/></div></div><div className="editor-card"><div className="editor-header"><div><strong>任务协作流程</strong><small>选择节点查看状态、审批和调用证据</small></div><div className="editor-link-tools"><span className="editor-badge"><T3StatusDot phase="connected" label="本地控制层已连接"/> 本地流程引擎</span><button className="button secondary small" onClick={()=>setPage('project')}><GitCompare size={14}/> 查看项目变更</button></div></div>{task.graphMode?<DagCanvas task={task} selected={selectedNode} onPick={setSelectedNode}/>:<WorkflowCanvas task={task} selected={selectedNode} onPick={setSelectedNode}/>}
 <WorkflowDesigner task={task} action={action} busy={busy}/></div></>:<div className="blank-state"><Workflow size={27}/><strong>还没有工作流</strong><button className="button dark" onClick={()=>setShowCreate(true)}>创建任务</button></div>}</div>}
       {page==='trace'&&<div className="trace-page"><div className="page-heading"><div><div className="eyebrow">REQUEST OBSERVABILITY</div><h1>AI 请求链路</h1><p>区分本地事件、官方结构化日志与不可观测的模型请求。</p></div></div>{task?<TracePanel task={task}/>:<div className="blank-state">创建任务后即可查看调用链。</div>}</div>}
       {page==='project'&&<ProjectExplorer task={task}/>}
       {page==='tools'&&<DevToolsPanel task={task}/>}
       {page==='terminal'&&<TerminalPanel task={task}/>}
       {page==='ledger'&&<ExecutionTimeline task={task}/>}
       {page==='integrations'&&<div className="integrations"><div className="eyebrow">INTEGRATIONS</div><h1>Agent 与系统能力</h1><p className="lead">AIWS 不共享账号密钥，只调用你明确安装和登录的官方 CLI。</p><div className="integrations-grid">{Object.entries(snapshot.agents).map(([name,available])=><div className="integration" key={name}><div className="integration-mark"><Terminal size={23}/></div><div><strong>{name}</strong><p>{available?'已安装 · 需要官方账号登录':'本机未发现 · 需安装官方工具'}</p></div><T3StatusDot phase={available?'connected':'unknown'} label={available?'已检测':'未检测'}/></div>)}</div><div className="notice"><CircleHelp size={18}/><div><strong>源代码拆分与重组</strong><p>这不是 T3 Code 或 OpenClaw 的内嵌界面。UI 与工作流属于 AIWS；少量 T3 UI 原语依据 MIT 协议适配，Windows 任务由自己的 .NET 核心控制。</p></div></div></div>}
     </div>}
   </main>
   <aside className="inspector"><div className="inspector-top"><strong>Inspector</strong><span>执行证据</span></div>{task&&page==='flow'?<TaskInspector task={task} step={step} action={action} busy={busy}/>:<div className="inspector-placeholder"><Sparkles size={26}/><strong>可观察、可控制</strong><p>选择一个流程阶段，就能查看审批、调用状态与 Token 数据。</p>{task&&measured&&<div className="observability-summary"><span>已测用量阶段 {measured.stages}</span><span>未知阶段 {measured.missing}</span></div>}</div>}<div className="inspector-bottom"><BadgeCheck size={16}/> 不存储模型账号凭据</div></aside>
   {showCreate&&<div className="modal-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setShowCreate(false)}}><div className="modal" role="dialog" aria-modal="true" aria-label="创建协作任务"><div className="modal-heading"><div><div className="eyebrow">NEW WORKFLOW</div><h2>创建一个 AI 协作任务</h2></div><button className="icon-button" onClick={()=>setShowCreate(false)} aria-label="关闭"><X size={20}/></button></div><label>任务名称</label><input value={title} autoFocus maxLength={120} onChange={e=>setTitle(e.target.value)} placeholder="例如：审查并重构 GitHub 项目"/><label>Windows 工作目录</label><div className="folder-input"><input readOnly value={workspace} placeholder="选择受信任的本地目录"/><button className="button secondary" onClick={pickWorkspace}><Folder size={15}/> 选择</button></div><label>预设流程</label><div className="template-switch"><button className={template==='dual'?'selected':''} onClick={()=>setTemplate('dual')}>Claude → Codex → Claude</button><button className={template==='research'?'selected':''} onClick={()=>setTemplate('research')}>研究与交叉验证</button><button className={template==='dag'?'selected':''} onClick={()=>setTemplate('dag')}>并行 DAG · 双 Agent 审核</button></div><p className="modal-note">创建任务只是本地记录，不产生模型 Token。启动外部 CLI 前会再请求确认。</p><div className="modal-actions"><button className="button secondary" onClick={()=>setShowCreate(false)}>取消</button><button className="button dark" disabled={busy||!title.trim()||!workspace} onClick={create}>创建工作流 <ArrowRight size={16}/></button></div></div></div>}
 </div>;
}
