import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {Activity, ArrowRight, BadgeCheck, Boxes, CheckCircle2, ChevronDown, CircleHelp, Code2, Folder, GitBranch, LayoutDashboard, ListTodo, Plus, RefreshCw, Settings2, Sparkles, Terminal, GitCompare, Workflow, Layers3, BookOpenCheck, X, Search, Keyboard, PanelRightOpen, PanelRightClose, AlertTriangle} from 'lucide-react';
import {bridge, type Snapshot, type WorkTask} from './bridge';
import {WorkflowCanvas} from './components/WorkflowCanvas';
import {DagCanvas} from './components/DagCanvas';
import {WorkflowDesigner} from './components/WorkflowDesigner';
import {TerminalPanel} from './components/TerminalPanel';
import {ExecutionTimeline} from './components/ExecutionTimeline';
import {TracePanel} from './components/TracePanel';
import {TaskInspector} from './components/TaskInspector';
import {DevToolsPanel} from './components/DevToolsPanel';
import {ProjectExplorer} from './components/ProjectExplorer';
import {ExecutionAtlas} from './components/ExecutionAtlas';
import {PlanCenter} from './components/PlanCenter';
import {MissionControl} from './components/MissionControl';
import {UnifiedTaskPanel} from './components/UnifiedTaskPanel';
import {T3Skeleton} from './components/T3Skeleton';
import {T3StatusDot} from './components/T3StatusDot';
import {sumMeasuredUsage} from './model/workflow.mjs';
import {filterTaskList,shouldActivateShortcut} from './model/interaction.mjs';

type Page = 'mission'|'overview'|'plans'|'atlas'|'flow'|'trace'|'project'|'tools'|'integrations'|'terminal'|'ledger';
const nav=[{id:'mission',label:'AI 协作总控台',icon:LayoutDashboard},{id:'overview',label:'工作台概览',icon:Sparkles},{id:'plans',label:'AI 计划中心',icon:BookOpenCheck},{id:'atlas',label:'AI 调用与结构',icon:Layers3},{id:'flow',label:'可视化工作流',icon:Workflow},{id:'trace',label:'调用追踪',icon:Activity},{id:'project',label:'文件与 Git 变更',icon:Code2},{id:'tools',label:'Git 只读控制台',icon:GitCompare},{id:'terminal',label:'Windows 内置终端',icon:Terminal},{id:'ledger',label:'执行事件账本',icon:ListTodo},{id:'integrations',label:'Agent 与能力',icon:Boxes}] as const;
const navigationGroups=[{title:'核心工作区',ids:['mission','plans','atlas','flow']},{title:'项目与证据',ids:['project','trace','ledger']},{title:'开发工具',ids:['terminal','tools','integrations','overview']}] as const;
function TitleLogo(){return <span className="brand-mark" aria-hidden="true"><Layers3 size={20} strokeWidth={2}/></span>}

export default function App(){
 const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
 const [selectedTask,setSelectedTask]=useState<string|null>(null);
 const [selectedNode,setSelectedNode]=useState<string|null>(null);
 const [page,setPage]=useState<Page>('mission');
 const [busy,setBusy]=useState(false);
 const [refreshing,setRefreshing]=useState(false);
 const [initializing,setInitializing]=useState(true);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [showCreate,setShowCreate]=useState(false);
 const [showHelp,setShowHelp]=useState(false);
 const [inspectorOpen,setInspectorOpen]=useState(false);
 const [search,setSearch]=useState('');
 const [title,setTitle]=useState('');
 const [workspace,setWorkspace]=useState('');
 const [template,setTemplate]=useState('lean');
 const [pickerBusy,setPickerBusy]=useState(false);
 const pendingMutation=useRef(false);
 const pickerPending=useRef(false);
 const requestVersion=useRef(0);
 const searchRef=useRef<HTMLInputElement|null>(null);
 const titleRef=useRef<HTMLInputElement|null>(null);
 const dialogRef=useRef<HTMLDivElement|null>(null);
 const previousFocus=useRef<HTMLElement|null>(null);

 // A slower read must never replace a newer snapshot. Read-only refresh is local
 // and may overlap file watchers; writes invalidate all preceding reads.
 const load=useCallback(async(forceAfterWrite=false)=>{
   if(pendingMutation.current&&!forceAfterWrite)return;
   const version=++requestVersion.current;
   try {
     const data=await bridge.call<Snapshot>('state');
     if(version!==requestVersion.current)return;
     setSnapshot(data);
     setSelectedTask(current=>current&&data.tasks.some(x=>x.id===current)?current:(data.tasks[0]?.id??null));
     setInitializing(false);
   } catch(err){
     if(version!==requestVersion.current)return;
     setInitializing(false);
     setError(err instanceof Error?err.message:String(err));
   }
 },[]);
 useEffect(()=>{void load();},[load]);
 const task=useMemo(()=>snapshot?.tasks.find(x=>x.id===selectedTask)||null,[snapshot,selectedTask]);
 const step=useMemo(()=>task?.steps.find(x=>x.id===selectedNode)||null,[task,selectedNode]);
 const filteredTasks=useMemo(()=>filterTaskList(snapshot?.tasks||[],search) as WorkTask[],[snapshot,search]);
 const navigate=useCallback((id:Page)=>{setPage(id);setNotice('');},[]);
 const chooseTask=useCallback((id:string)=>{setSelectedTask(id);setSelectedNode(null);setInspectorOpen(false);navigate('mission');},[navigate]);
 const openCreate=useCallback(()=>{
   if(pendingMutation.current)return;
   previousFocus.current=document.activeElement instanceof HTMLElement?document.activeElement:null;
   setShowCreate(true);setError('');setNotice('');
 },[]);
 const closeCreate=useCallback(()=>{if(!pendingMutation.current&&!pickerPending.current)setShowCreate(false);},[]);

 // Ref gate is synchronous: two quick clicks cannot launch two mutations before
 // React has committed its disabled state. The native host has its own gate too.
 const action=useCallback(async(name:string,payload:Record<string,unknown>={})=>{
   if(pendingMutation.current){setNotice('上一项操作仍在执行，请等待本地确认。');return;}
   pendingMutation.current=true;requestVersion.current++;
   setBusy(true);setError('');setNotice('');
   try{
     const response=await bridge.call<{id?:string}>(name,payload);
     await load(true);
     if(name==='tasks.create'){
       setShowCreate(false);setTitle('');setWorkspace('');
       if(response?.id){setSelectedTask(response.id);setSelectedNode(null);setInspectorOpen(false);navigate('mission');}
     }
     setNotice(name==='tasks.create'?'任务已创建，已切换到新任务。':'本地操作已确认并保存。');
   }catch(e){setError(e instanceof Error?e.message:String(e));}
   finally{pendingMutation.current=false;setBusy(false);}
 },[load,navigate]);
 const create=async()=>{
   if(!workspace||!title.trim()||pendingMutation.current||pickerPending.current)return;
   await action('tasks.create',{title:title.trim(),workspace,template});
 };
 const pickWorkspace=async()=>{
   if(pickerPending.current||pendingMutation.current)return;
   pickerPending.current=true;setPickerBusy(true);setError('');
   try{const result=await bridge.call<{path:string}>('workspaces.pick');if(result?.path)setWorkspace(result.path);}
   catch(e){setError(e instanceof Error?e.message:String(e));}
   finally{pickerPending.current=false;setPickerBusy(false);}
 };
 const refreshClick=async()=>{
   if(refreshing||pendingMutation.current)return;
   setRefreshing(true);setError('');
   try{await load();}finally{setRefreshing(false);}
 };
 const openStep=useCallback((id:string)=>{setSelectedNode(id);setInspectorOpen(true);navigate('flow');},[navigate]);
 useEffect(()=>{
   if(showCreate){const original=previousFocus.current;titleRef.current?.focus();return()=>{original?.focus();};}
 },[showCreate]);
 // Desktop keyboard flows: Ctrl+K task search, Ctrl+N create, Escape close;
 // Tab stays in a modal instead of silently moving to obscured controls.
 useEffect(()=>{
   const keydown=(e:KeyboardEvent)=>{
     if(e.key==='Escape'){
       if(showHelp){e.preventDefault();setShowHelp(false);}
       else if(showCreate){e.preventDefault();closeCreate();}
       else if(inspectorOpen){setInspectorOpen(false);}
       return;
     }
     if((showCreate||showHelp)&&e.key==='Tab'){
       const items=Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]')||[]);
       if(!items.length)return;
       const first=items[0],last=items[items.length-1];
       if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
       else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
       return;
     }
     if(showCreate||showHelp||!shouldActivateShortcut(e))return;
     if(e.key.toLowerCase()==='k'){e.preventDefault();searchRef.current?.focus();searchRef.current?.select();}
     if(e.key.toLowerCase()==='n'){e.preventDefault();openCreate();}
   };
   window.addEventListener('keydown',keydown);
   return()=>window.removeEventListener('keydown',keydown);
 },[showCreate,showHelp,inspectorOpen,closeCreate,openCreate]);
 const measured=task?sumMeasuredUsage(task):null;
 const hasInspector=page==='flow'&&Boolean(task);
 return <div className={`app-shell ${hasInspector?'has-inspector':''} ${page==='project'?'project-active':''} ${page==='atlas'?'atlas-active':''} ${page==='plans'?'plan-active':''} ${page==='mission'?'mission-active':''}`}>
   <aside className="sidebar">
     <div className="brand"><TitleLogo/><div className="brand-copy"><strong>AI Workstation</strong><small>COMMAND CENTER <span className="brand-version">/ 01</span></small></div></div>
     <div className="sidebar-scroll">
      {navigationGroups.map((group,index)=><section className="nav-group" key={group.title}>
       <div className="sidebar-section"><span>{group.title}</span><small>0{index+1}</small></div>
       <nav className="nav" aria-label={group.title}>{group.ids.map(id=>{
        const item=nav.find(n=>n.id===id)!;
        return <button type="button" key={id} title={item.label} aria-current={page===id?'page':undefined} className={`nav-link ${page===id?'active':''}`} onClick={()=>navigate(id)}><item.icon size={17} strokeWidth={1.8}/><span>{item.label}</span>{page===id&&<span className="nav-active-dot" aria-hidden="true"/>}</button>;
       })}</nav>
      </section>)}
      <section className="recent-section">
       <div className="sidebar-section section-project"><span>最近任务</span><button type="button" className="icon-button new-task-inline" aria-label="新建任务" title="新建任务 Ctrl+N" onClick={openCreate} disabled={busy}><Plus size={16}/></button></div>
       <label className="sidebar-search"><Search size={15}/><input ref={searchRef} value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜索任务..." aria-label="搜索最近任务"/><kbd>⌘ K</kbd></label>
       <div className="task-nav" role="list" aria-label="任务列表">{filteredTasks.length?filteredTasks.slice(0,50).map(t=><button type="button" key={t.id} className={`task-link ${selectedTask===t.id?'picked':''}`} onClick={()=>chooseTask(t.id)} title={t.title}><span className="task-glyph"><GitBranch size={13}/></span><span>{t.title}</span>{selectedTask===t.id&&<span className="task-selected" aria-hidden="true"/>}</button>):<div className="no-tasks">{search?'没有匹配的任务。':'还没有任务，点击 + 新建。'}</div>}</div>
      </section>
     </div>
     <div className="sidebar-bottom"><div className="system-line"><span className="system-pulse"/> LOCAL ENGINE <span>· 受控执行</span></div><div className="profile" aria-label="本地个人工作台"><span className="avatar">AI</span><span>个人工作台<small>Windows · 本地运行</small></span><Settings2 size={16}/></div></div>
   </aside>
   <main className="main-view"><header className="topbar"><div className="breadcrumb"><span className="breadcrumb-home">WORKSPACE</span><ArrowRight size={13}/><strong>{nav.find(n=>n.id===page)?.label}</strong>{task&&<span className="breadcrumb-task">/ {task.title}</span>}</div><div className="top-actions"><span className="mode-label"><span className="mode-dot"/> LOCAL FIRST</span>
      {hasInspector&&<button type="button" className="icon-button inspector-toggle" aria-label={inspectorOpen?'关闭阶段详情':'打开阶段详情'} title="阶段详情" onClick={()=>setInspectorOpen(v=>!v)}>{inspectorOpen?<PanelRightClose size={18}/>:<PanelRightOpen size={18}/>}</button>}
      <button type="button" className="icon-button top-help" onClick={()=>{previousFocus.current=document.activeElement instanceof HTMLElement?document.activeElement:null;setShowHelp(true);}} aria-label="键盘快捷键与帮助" title="键盘快捷键"><Keyboard size={18}/></button>
      <button type="button" className={`icon-button top-refresh ${refreshing?'is-spinning':''}`} disabled={refreshing||busy} onClick={()=>void refreshClick()} aria-label="刷新本地任务" title="刷新本地状态"><RefreshCw size={18}/></button>
      <button type="button" className="button dark small top-create" onClick={openCreate} disabled={busy}><Plus size={17}/> 新建任务</button></div></header>
     {busy&&<div className="operation-strip" role="status"><span className="operation-spinner"/>正在执行已确认的本地操作，请勿重复提交…</div>}
     {error&&<div className="error-toast" role="alert"><AlertTriangle size={17}/><span>{error}</span><button type="button" onClick={()=>setError('')} aria-label="关闭错误信息"><X size={16}/></button></div>}
     {notice&&!error&&<div className="success-toast" role="status"><CheckCircle2 size={17}/><span>{notice}</span><button type="button" onClick={()=>setNotice('')} aria-label="关闭操作反馈"><X size={16}/></button></div>}
     {!snapshot?(initializing?<div className="loading"><T3Skeleton className="skeleton-heading"/><T3Skeleton className="skeleton-card"/><T3Skeleton className="skeleton-card"/></div>:<div className="connection-error"><AlertTriangle size={27}/><h2>本地任务服务暂不可用</h2><p>如果正在浏览器中预览，请改从 WindowsAIWorkstation.exe 启动；否则检查安装目录与本地 WebView2。</p><button className="button dark" onClick={()=>void refreshClick()} disabled={refreshing}><RefreshCw size={16}/>重新连接</button></div>):
     <div className="content">
       {page==='overview'&&<div className="overview"><div className="eyebrow">YOUR PERSONAL AI DESK</div><h1>把复杂工作，交给有序协作。</h1><p className="lead">统一规划 Claude 与 Codex 的任务，在 Windows 本地管理工作区、权限、请求链路和交付结果。</p>
         <div className="overview-toolbar"><button className="button dark" onClick={openCreate}><Plus size={17}/> 创建协作任务</button><button className="button secondary" onClick={()=>task&&setPage('flow')} disabled={!task}><Workflow size={16}/> 打开工作流</button></div>
         <div className="metric-grid"><div className="metric"><span>总任务</span><strong>{snapshot.tasks.length}</strong><small>本地保存</small></div><div className="metric"><span>已完成阶段</span><strong>{snapshot.tasks.reduce((n,t)=>n+t.completedCount,0)}</strong><small>经确认后计入</small></div><div className="metric"><span>可用 CLI</span><strong>{Object.values(snapshot.agents).filter(Boolean).length}</strong><small>检测本机安装</small></div></div>
         <div className="section-title"><span>当前工作流</span><button disabled={!task} onClick={()=>navigate('flow')}>查看流程 <ArrowRight size={14}/></button></div>
         {task?<button type="button" className="overview-task" onClick={()=>navigate('flow')}><div className="task-top"><span className="task-icon"><Code2 size={20}/></span><div><strong>{task.title}</strong><small>{task.workspace}</small></div><span className="subtle-chip">{task.completedCount}/{task.steps.length} 阶段</span></div><div className="step-mini">{task.steps.map((s,i)=><div key={s.id}><span className={`mini-number ${s.status==='Completed'?'done':''}`}>{i+1}</span><span>{s.title}</span>{i<task.steps.length-1&&<span className="mini-line"/>}</div>)}</div></button>:<div className="blank-state"><Sparkles size={25}/><strong>你的第一条工作流，从这里开始</strong><p>选择项目文件夹，AIWS 会为你准备轻量的 Codex + 人工验收流程。</p><button className="button dark" onClick={openCreate}>创建工作流</button></div>}
       </div>}
       {page==='mission'&&<MissionControl task={task} action={action} busy={busy} onOpenStep={openStep} onOpenPlans={()=>navigate('plans')} onOpenProject={()=>navigate('project')}/>}
       {page==='plans'&&<PlanCenter task={task} action={action} onRefresh={load} onOpenStep={openStep} onOpenAtlas={()=>setPage('atlas')}/>}
       {page==='atlas'&&<ExecutionAtlas task={task} preferredStageId={selectedNode}/>}
       {page==='flow'&&<div className="workspace-page">{task?<><div className="page-heading"><div><div className="eyebrow">VISUAL WORKFLOW</div><h1>{task.title}</h1><p><Folder size={14}/>{task.workspace}</p></div><div className="right-chip">{task.completedCount} / {task.steps.length} 已完成 <ChevronDown size={14}/></div></div><UnifiedTaskPanel task={task} action={action} busy={busy}/><div className="editor-card"><div className="editor-header"><div><strong>任务协作流程</strong><small>选择节点查看状态、审批和调用证据</small></div><div className="editor-link-tools"><span className="editor-badge"><T3StatusDot phase="connected" label="本地控制层已连接"/> 本地流程引擎</span><button className="button secondary small" onClick={()=>setPage('atlas')}><Layers3 size={14}/> 调用与结构全景</button><button className="button secondary small" onClick={()=>setPage('project')}><GitCompare size={14}/> 查看项目变更</button></div></div>{task.graphMode?<DagCanvas task={task} selected={selectedNode} onPick={id=>{setSelectedNode(id);setInspectorOpen(true)}}/>:<WorkflowCanvas task={task} selected={selectedNode} onPick={id=>{setSelectedNode(id);setInspectorOpen(true)}}/>}
 <WorkflowDesigner task={task} action={action} busy={busy}/></div></>:<div className="blank-state"><Workflow size={27}/><strong>还没有工作流</strong><button className="button dark" onClick={openCreate}>创建任务</button></div>}</div>}
       {page==='trace'&&<div className="trace-page"><div className="page-heading"><div><div className="eyebrow">REQUEST OBSERVABILITY</div><h1>AI 请求链路</h1><p>区分本地事件、官方结构化日志与不可观测的模型请求。</p></div></div>{task?<TracePanel task={task}/>:<div className="blank-state">创建任务后即可查看调用链。</div>}</div>}
       {page==='project'&&<ProjectExplorer task={task}/>}
       {page==='tools'&&<DevToolsPanel task={task} onOpenTerminal={()=>navigate('terminal')}/>}
       {page==='terminal'&&<TerminalPanel task={task}/>}
       {page==='ledger'&&<ExecutionTimeline task={task}/>}
       {page==='integrations'&&<div className="integrations"><div className="eyebrow">INTEGRATIONS</div><h1>Agent 与系统能力</h1><p className="lead">AIWS 不共享账号密钥，只调用你明确安装和登录的官方 CLI。</p><div className="integrations-grid">{(snapshot.providers||[]).filter(p=>p.agent!=='Manual').map(p=><div className="integration" key={p.id}><div className="integration-mark"><Terminal size={23}/></div><div><strong>{p.name}</strong><p>{p.available?'已安装 · 需要官方账号登录':'本机未发现 · 需安装官方工具'}</p></div><T3StatusDot phase={p.available?'connected':'unknown'} label={p.available?'已检测':'未检测'}/></div>)}</div><div className="notice"><CircleHelp size={18}/><div><strong>源代码拆分与重组</strong><p>这不是 T3 Code 或 OpenClaw 的内嵌界面。UI 与工作流属于 AIWS；少量 T3 UI 原语依据 MIT 协议适配，Windows 任务由自己的 .NET 核心控制。</p></div></div></div>}
     </div>}
   </main>
   {hasInspector&&<><button className={`inspector-scrim ${inspectorOpen?'visible':''}`} type="button" onClick={()=>setInspectorOpen(false)} aria-label="关闭阶段详情"/><aside className={`inspector ${inspectorOpen?'is-open':''}`} aria-label="阶段检查器"><div className="inspector-top"><strong>阶段检查器</strong><button className="icon-button inspector-close" type="button" onClick={()=>setInspectorOpen(false)} aria-label="关闭阶段详情"><X size={16}/></button><span>EXECUTION EVIDENCE</span></div>{task?<TaskInspector task={task} step={step} providers={snapshot?.providers||[]} action={action} busy={busy}/>:<div className="inspector-placeholder"><Sparkles size={26}/><strong>请选择阶段</strong></div>}<div className="inspector-bottom"><BadgeCheck size={16}/> 不存储模型账号凭据{measured&&<span className="inspector-usage">· 已测 {measured.stages} 阶段</span>}</div></aside></>}
   {showCreate&&<div className="modal-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)closeCreate();}}>
     <div className="modal" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="create-title">
      <div className="modal-heading"><div><div className="eyebrow">NEW WORKFLOW</div><h2 id="create-title">创建协作任务</h2><p>一个任务，统一管理所有 Agent 和交付证据。</p></div><button className="icon-button" type="button" onClick={closeCreate} disabled={busy||pickerBusy} aria-label="关闭弹窗"><X size={20}/></button></div>
      <form onSubmit={e=>{e.preventDefault();void create();}}>
       {error&&<div className="form-error" role="alert"><AlertTriangle size={16}/>{error}</div>}
       <label htmlFor="create-name">任务名称 <span className="field-required">*</span></label>
       <input id="create-name" ref={titleRef} required minLength={1} maxLength={120} value={title} onChange={e=>setTitle(e.target.value)} placeholder="例如：重构 Windows AI Workstation" disabled={busy||pickerBusy}/>
       <label htmlFor="create-workspace">Windows 工作目录 <span className="field-required">*</span></label>
       <div className="folder-input"><input id="create-workspace" readOnly value={workspace} placeholder="选择受信任的本地目录" aria-label="已选工作目录"/><button type="button" className="button secondary" onClick={()=>void pickWorkspace()} disabled={busy||pickerBusy}><Folder size={15}/>{pickerBusy?'选择中…':'选择目录'}</button></div>
       <fieldset className="template-fieldset"><legend>预设流程</legend><div className="template-switch">{([['lean','轻量协作','Codex + 人工验收'],['dual','完整交接','Claude → Codex → Claude'],['research','研究分析','交叉验证'],['dag','并行工作','DAG + 双 Agent']] as const).map(([id,name,description])=><button type="button" key={id} className={template===id?'selected':''} aria-pressed={template===id} onClick={()=>setTemplate(id)} disabled={busy||pickerBusy}><strong>{name}</strong><small>{description}</small></button>)}</div></fieldset>
       <p className="modal-note"><BadgeCheck size={15}/> 创建任务只写入本地；执行 CLI 前仍需要确认。</p>
       <div className="modal-actions"><button type="button" className="button secondary" onClick={closeCreate} disabled={busy||pickerBusy}>取消</button><button className="button dark" type="submit" disabled={busy||pickerBusy||!title.trim()||!workspace}>{busy?'正在创建…':'创建任务'} <ArrowRight size={16}/></button></div>
      </form>
     </div>
    </div>}
   {showHelp&&<div className="modal-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setShowHelp(false)}}><div className="help-dialog" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="help-title"><div className="modal-heading"><div><div className="eyebrow">WORKSPACE GUIDE</div><h2 id="help-title">快捷操作与交互说明</h2></div><button type="button" className="icon-button" onClick={()=>setShowHelp(false)} aria-label="关闭帮助"><X size={19}/></button></div><div className="help-shortcuts"><span>定位任务搜索</span><kbd>Ctrl + K</kbd><span>新建协作任务</span><kbd>Ctrl + N</kbd><span>关闭对话框</span><kbd>Esc</kbd><span>键盘访问控件</span><kbd>Tab / Enter</kbd></div><p className="help-note">本界面所有任务、计划和 Git 面板都运行在本地。启动外部 Agent 或修改项目时会经过独立的权限确认。</p><button type="button" className="button dark full" onClick={()=>setShowHelp(false)}>知道了</button></div></div>}

 </div>;
}
