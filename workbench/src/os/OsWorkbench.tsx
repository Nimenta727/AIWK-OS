import {useCallback,useEffect,useMemo,useState} from 'react';
import {Activity,BrainCircuit,ChevronDown,ChevronRight,Eye,File as FileIcon,Folder,FolderTree,Layers3,Globe,Moon,Play,RefreshCw,ShieldCheck,SquareTerminal,Sun,Wrench} from 'lucide-react';
import './OsWorkbench.css';
import './shell.css';
import {ActivityBar,CommandPalette,Panel,SideBar,StatusBar,TabBar} from './Shell';
import type {Command,Tab} from './Shell';
import FileViewer from './FileViewer';
import BrowserView from './BrowserView';
import useObservatoryData from './useObservatoryData';
import {api} from './api';
import {buildTree,parseCommand} from '../model/fileOps.mjs';
import {closeTab,cycleTab,fileTabId,fileTitle,flattenTree,isEditableTarget,loadPrefs,matchKey,openTab,savePrefs} from '../model/shell.mjs';
import GuestFiles from './GuestFiles';
import GuestTaskStudio from './GuestTaskStudio';
import GuestSystemConsole from './GuestSystemConsole';
import Observatory from './Observatory';

type Tool={name:string;description:string;inputSchema:{properties:Record<string,{type:string}>;required:string[]}};
type Job={id:string;tool:string;status:string;result:unknown;error:string|null;submittedAt:number};
type Health={mode:string;workspace:string;agent:string;toolCount:number;guestOnly:boolean;agentPrivileged:boolean;llmConnected:boolean;brokerReady?:boolean;brokerScope?:string};
type Snapshot={health:Health;capabilities:Tool[];jobs:Job[]};
type View='browser'|'observatory'|'overview'|'files'|'tasks'|'plans'|'local'|'system';
type Language='zh'|'en';
type TreeNode={name:string;path:string;type:'dir'|'file';children:TreeNode[]};
type AppRow={id:string;kind:string;category:string;zh:string;en:string;installed:boolean;path:string|null;launchable:boolean};
type IdeState={installed:boolean;running:boolean;version?:string|null};
const VIEWS:{id:View;zh:string;en:string;icon:typeof Activity}[]=[
 {id:'observatory',zh:'观察台',en:'Observatory',icon:Eye},
 {id:'overview',zh:'系统概览',en:'System overview',icon:Layers3},
 {id:'browser',zh:'内置浏览器',en:'Preview browser',icon:Globe},
 {id:'files',zh:'AI 文件管理',en:'AI Files',icon:FolderTree},
 {id:'tasks',zh:'任务与证据',en:'Tasks & evidence',icon:BrainCircuit},
 {id:'plans',zh:'持久任务与 DAG',en:'Persistent DAG',icon:Layers3},
 {id:'local',zh:'本地 AI 助手',en:'Local AI assistant',icon:BrainCircuit},
 {id:'system',zh:'系统与安全',en:'System & security',icon:ShieldCheck}
];
const isView=(id:string|null):id is View=>VIEWS.some(v=>v.id===id);
const safeStorage=():Storage|null=>{try{return window.localStorage;}catch{return null;}};

export default function OsWorkbench(){
 const storage=useMemo(safeStorage,[]);
 const initial=useMemo(()=>storage?loadPrefs(storage):loadPrefs({getItem:()=>null} as unknown as Storage),[storage]);
 const [language,setLanguage]=useState<Language>('zh');
 const english=language==='en';
 const tr=(zh:string,en:string)=>english?en:zh;
 const [theme,setTheme]=useState<'dark'|'light'>(initial.theme as 'dark'|'light');
 const [sidebar,setSidebar]=useState<boolean>(initial.sidebar);
 const [panel,setPanel]=useState<boolean>(initial.panel);
 const [activity,setActivity]=useState<string>(initial.activity);
 const [panelTab,setPanelTab]=useState('jobs');
 const [tabs,setTabs]=useState<Tab[]>([{id:'observatory',kind:'observatory',title:'',pinned:true}]);
 const [active,setActive]=useState<string|null>('observatory');
 const [palette,setPalette]=useState(false);
 const [snapshot,setSnapshot]=useState<Snapshot|null>(null);
 const [csrf,setCsrf]=useState('');
 const [error,setError]=useState('');
 const [starting,setStarting]=useState(true);
 const [job,setJob]=useState<Job|null>(null);
 const [command,setCommand]=useState<{text:string;nonce:number}|null>(null);
 const [tree,setTree]=useState<TreeNode[]>([]);
 const [treeNote,setTreeNote]=useState('');
 const [expanded,setExpanded]=useState<Set<string>>(new Set());
 const [ide,setIde]=useState<IdeState|null>(null);
 const [ideNote,setIdeNote]=useState('');
 const [apps,setApps]=useState<AppRow[]>([]);
 const [appNote,setAppNote]=useState('');
 const data=useObservatoryData();

 useEffect(()=>{if(storage)savePrefs(storage,{theme,sidebar,panel,activity});},[storage,theme,sidebar,panel,activity]);

 const refresh=useCallback(async()=>{
  try{setSnapshot(await api<Snapshot>('/snapshot'));setError('');}
  catch(e){setError(e instanceof Error?e.message:String(e));}
 },[]);
 const loadTree=useCallback(async()=>{
  try{
   const t=await api<{files:string[];dirs?:string[];truncated:boolean}>('/workspace/tree');
   setTree(buildTree(t.files,t.dirs) as TreeNode[]);setTreeNote(t.truncated?tr('列表已截断，仅显示部分文件','List truncated: showing part of the files'):'');
  }catch(e){setTreeNote(String(e instanceof Error?e.message:e));}
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[english]);
 const loadApps=useCallback(async()=>{try{setApps((await api<{apps:AppRow[]}>('/apps')).apps);}catch{setApps([]);}},[]);
 const loadIde=useCallback(async()=>{try{setIde(await api<IdeState>('/ide'));}catch{setIde(null);}},[]);
 useEffect(()=>{
  let live=true;
  void Promise.all([api<Snapshot>('/snapshot'),api<{csrf:string}>('/session')])
   .then(([state,session])=>{if(live){setSnapshot(state);setCsrf(session.csrf);}})
   .catch(e=>{if(live)setError(String(e));})
   .finally(()=>{if(live)setStarting(false);});
  void loadTree();void loadIde();void loadApps();
  return()=>{live=false;};
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[]);
 useEffect(()=>{
  if(!job||!['queued','running'].includes(job.status))return;
  let live=true;
  const interval=window.setInterval(()=>{
   void api<Job>('/jobs/'+encodeURIComponent(job.id))
    .then(result=>{if(live){setJob(result);if(!['queued','running'].includes(result.status))void refresh();}})
    .catch(e=>{if(live)setError(String(e));});
  },1200);
  return()=>{live=false;window.clearInterval(interval);};
 },[job,refresh]);

 const tools=useMemo(()=>snapshot?.capabilities||[],[snapshot]);
 const health=snapshot?.health;
 const summary=data.summary;
 const viewTitle=(v:View)=>{const m=VIEWS.find(x=>x.id===v)!;return english?m.en:m.zh;};

 const openView=useCallback((v:View)=>{const r=openTab(tabs,{id:v,kind:v,title:v,pinned:v==='observatory'},active);setTabs(r.tabs);setActive(r.active);},[tabs,active]);
 const openFile=useCallback((p:string)=>{const r=openTab(tabs,{id:fileTabId(p),kind:'file',title:fileTitle(p),path:p},active);setTabs(r.tabs);setActive(r.active);},[tabs,active]);
 const close=useCallback((id:string)=>{const r=closeTab(tabs,active,id);setTabs(r.tabs);setActive(r.active);},[tabs,active]);
 const runCommand=(text:string)=>{
  if(!(parseCommand(text) as {ok:boolean}).ok)return false;
  openView('files');setCommand({text,nonce:Date.now()});return true;
 };
 const openIde=async()=>{
  setIdeNote('');
  try{await api('/ide/open',{method:'POST',headers:{'Content-Type':'application/json','X-AIWS-CSRF':csrf},body:'{}'});setIdeNote(tr('正在启动 AIWS Code…','Starting AIWS Code…'));window.setTimeout(()=>void loadIde(),2500);}
  catch(e){setIdeNote(String(e instanceof Error?e.message:e));}
 };
 const launchApp=async(id:string)=>{
  setAppNote('');
  try{
   const r=await api<{started:boolean;starting?:boolean}>('/apps/launch',{method:'POST',headers:{'Content-Type':'application/json','X-AIWS-CSRF':csrf},body:JSON.stringify({id})});
   setAppNote(r.started?tr('正在启动…','Starting…'):tr('刚刚已经启动过，请稍等。','Already starting, please wait.'));
  }catch(e){setAppNote(String(e instanceof Error?e.message:e));}
 };
 const selectActivity=(id:string)=>{
  if(sidebar&&activity===id){setSidebar(false);return;}
  setActivity(id);setSidebar(true);
 };
 const commands:Command[]=useMemo(()=>[
  ...VIEWS.map(v=>({id:'view:'+v.id,label:(english?'Open: ':'打开：')+(english?v.en:v.zh),keywords:v.zh+' '+v.en,run:()=>openView(v.id)})),
  {id:'sidebar',label:tr('切换侧边栏','Toggle side bar'),hint:'Ctrl+B',keywords:'sidebar',run:()=>setSidebar(x=>!x)},
  {id:'panel',label:tr('切换底部面板','Toggle panel'),hint:'Ctrl+J',keywords:'panel jobs',run:()=>setPanel(x=>!x)},
  {id:'theme',label:tr('切换深色/浅色主题','Toggle dark/light theme'),keywords:'theme dark light',run:()=>setTheme(x=>x==='dark'?'light':'dark')},
  {id:'lang',label:tr('切换语言 中文/English','Switch language'),keywords:'language',run:()=>setLanguage(x=>x==='zh'?'en':'zh')},
  {id:'refresh',label:tr('刷新状态','Refresh status'),keywords:'reload',run:()=>{void refresh();void data.reload();void loadTree();}},
  {id:'browser-cmd',label:tr('打开内置浏览器','Open preview browser'),keywords:'browser web preview localhost',run:()=>openView('browser')},
  {id:'ide',label:tr('打开 AIWS Code（完整代码编辑器）','Open AIWS Code (full code editor)'),keywords:'vscode editor ide code',run:()=>void openIde()},
  {id:'closetab',label:tr('关闭当前标签','Close current tab'),hint:'Alt+W',keywords:'close',run:()=>{if(active)close(active);}}
 // eslint-disable-next-line react-hooks/exhaustive-deps
 ],[english,active,tabs,csrf,openView,close]);

 useEffect(()=>{
  const onKey=(e:KeyboardEvent)=>{
   if(matchKey(e,'mod+shift+p')||matchKey(e,'f1')){e.preventDefault();setPalette(true);}
   else if(matchKey(e,'mod+b')){e.preventDefault();setSidebar(x=>!x);}
   else if(matchKey(e,'mod+j')){e.preventDefault();setPanel(x=>!x);}
   else if(matchKey(e,'alt+w')&&active){e.preventDefault();close(active);}
   else if(matchKey(e,'alt+arrowright')&&!isEditableTarget(e.target)){e.preventDefault();setActive(cycleTab(tabs,active,1));}
   else if(matchKey(e,'alt+arrowleft')&&!isEditableTarget(e.target)){e.preventDefault();setActive(cycleTab(tabs,active,-1));}
  };
  window.addEventListener('keydown',onKey);
  return()=>window.removeEventListener('keydown',onKey);
 },[active,tabs,close]);

 const waiting=summary?.tasks.needsApproval.length||0;
 const approvals=(summary?.runApprovals.length||0)+waiting;
 const tabsView:Tab[]=tabs.map(t=>isView(t.id)?{...t,title:viewTitle(t.id)}:t);
 const treeRows=flattenTree(tree,expanded) as (TreeNode&{depth:number})[];
 const toggleDir=(p:string)=>setExpanded(prev=>{const n=new Set(prev);if(n.has(p))n.delete(p);else n.add(p);return n;});

 const sideContent=()=>{
  if(activity==='explorer')return <SideBar title={tr('资源管理器','Explorer')}
    actions={<button type="button" title={tr('刷新','Refresh')} aria-label={tr('刷新','Refresh')} onClick={()=>void loadTree()}><RefreshCw size={14}/></button>}>
   <div className="aiws-sh-section">{health?.workspace?health.workspace.split('/').pop():tr('工作区','Workspace')}</div>
   {treeRows.map(r=><button type="button" key={r.path} className={'aiws-sh-row'+(active===fileTabId(r.path)?' on':'')} style={{paddingLeft:12+r.depth*14}}
     onClick={()=>r.type==='dir'?toggleDir(r.path):openFile(r.path)}>
    {r.type==='dir'?(expanded.has(r.path)?<ChevronDown size={14}/>:<ChevronRight size={14}/>):<span style={{width:14}}/>}
    {r.type==='dir'?<Folder size={14}/>:<FileIcon size={14}/>}<span>{r.name}</span></button>)}
   {!treeRows.length&&<div className="aiws-sh-list">{treeNote||tr('工作区为空','The workspace is empty')}</div>}
   {treeNote&&treeRows.length>0&&<div className="aiws-sh-list">{treeNote}</div>}
   <div className="aiws-sh-section">{tr('文件整理','File operations')}</div>
   <button type="button" className="aiws-sh-row" onClick={()=>openView('files')}><FolderTree size={14}/>{tr('AI 文件管理（需审批）','AI file manager (approval required)')}</button>
  </SideBar>;
  if(activity==='tools'){
   const group=(kind:string,zh:string,en:string)=>{const rows=apps.filter(a=>a.kind===kind);return rows.length?<><div className="aiws-sh-section">{tr(zh,en)}</div>
    {rows.map(a=>{const label=english?a.en:a.zh;
     if(kind==='builtin')return <button type="button" key={a.id} className="aiws-sh-row" onClick={()=>openView(a.id==='viewer'?'files':(a.id==='browser'?'browser':'files'))}>{a.id==='browser'?<Globe size={14}/>:<FileIcon size={14}/>}<span>{label}</span></button>;
     if(kind==='gui')return <button type="button" key={a.id} className="aiws-sh-row" disabled={!a.launchable||!csrf} title={a.installed?a.path||'':tr('本镜像未安装','Not installed in this image')} onClick={()=>void launchApp(a.id)}><Play size={14}/><span>{label}</span><small>{a.installed?tr('启动','start'):tr('未安装','missing')}</small></button>;
     return <div key={a.id} className="aiws-sh-row" title={a.path||''}><SquareTerminal size={14}/><span>{label}</span><small>{a.installed?'✓':tr('未安装','missing')}</small></div>;})}</>:null;};
   return <SideBar title={tr('工具','Tools')} actions={<button type="button" title={tr('刷新','Refresh')} aria-label={tr('刷新','Refresh')} onClick={()=>void loadApps()}><RefreshCw size={14}/></button>}>
    <div className="aiws-sh-list">{tr('读取类工具由 AI 通过受审计的工具接口自动调用；桌面程序只在你点击时启动，AI 不会自行启动。','The AI calls read-only tools through the audited tool plane; desktop apps start only when you click them, never started by the AI itself.')}</div>
    {group('builtin','内置','Built in')}{group('gui','桌面程序','Desktop apps')}{group('cli','命令行工具','Command-line tools')}
    {appNote&&<div className="aiws-sh-list" role="status">{appNote}</div>}
    {!apps.length&&<div className="aiws-sh-list">{tr('暂时读不到工具清单','The tool list is not available yet')}</div>}
   </SideBar>;
  }
  if(activity==='tasks')return <SideBar title={tr('任务','Tasks')}>
   <div className="aiws-sh-list">{summary?<>
    <div><b>{summary.tasks.tasks}</b> {tr('个任务','tasks')} · <b>{waiting}</b> {tr('待审批','awaiting approval')} · <b>{summary.tasks.failures.length}</b> {tr('失败','failed')}</div></>:tr('正在读取…','Reading…')}</div>
   {(summary?.tasks.recent||[]).slice(0,8).map(t=><button type="button" key={t.id} className="aiws-sh-row" onClick={()=>openView('plans')}><Layers3 size={14}/><span>{t.title}</span></button>)}
   <button type="button" className="aiws-sh-row" onClick={()=>openView('plans')}>{tr('打开持久任务与 DAG','Open persistent DAG')}</button>
   <button type="button" className="aiws-sh-row" onClick={()=>openView('tasks')}>{tr('打开任务与证据','Open tasks & evidence')}</button>
  </SideBar>;
  if(activity==='ai')return <SideBar title={tr('AI','AI')}>
   <div className="aiws-sh-list">{tr('本地小模型只做中转与本机文件/系统操作，不联网。云端构建通过官方 CLI，在你授权的预算内进行。','The local model only relays and does local file/system work, offline. Cloud building goes through the official CLI within the budget you grant.')}</div>
   <button type="button" className="aiws-sh-row" onClick={()=>openView('local')}><BrainCircuit size={14}/>{tr('本地 AI 助手','Local AI assistant')}</button>
   <div className="aiws-sh-section">{tr('代码编辑器','Code editor')}</div>
   <div className="aiws-sh-list">{ide?.installed?(ide.running?tr('AIWS Code 正在运行','AIWS Code is running'):tr('AIWS Code 已安装','AIWS Code is installed')):tr('AIWS Code 未安装在此镜像中','AIWS Code is not installed in this image')}</div>
   <button type="button" className="aiws-sh-btn" style={{margin:'2px 12px'}} disabled={!ide?.installed||!csrf} onClick={()=>void openIde()}>{tr('打开 AIWS Code','Open AIWS Code')}</button>
   {ideNote&&<div className="aiws-sh-list">{ideNote}</div>}
  </SideBar>;
  if(activity==='system')return <SideBar title={tr('系统','System')}>
   <button type="button" className="aiws-sh-row" onClick={()=>openView('overview')}><Activity size={14}/>{tr('系统概览','System overview')}</button>
   <button type="button" className="aiws-sh-row" onClick={()=>openView('system')}><ShieldCheck size={14}/>{tr('系统与安全','System & security')}</button>
   <div className="aiws-sh-list">{health?<>{tr('模式','Mode')}: <b>{health.mode}</b><br/>{tr('权限','Privileges')}: <b>{health.agentPrivileged?'ELEVATED':'USER ONLY'}</b></>:tr('正在检查系统服务…','Checking the service…')}</div>
  </SideBar>;
  return <SideBar title={tr('观察台','Observatory')}>
   <div className="aiws-sh-list">{summary?<>
    <div>{tr('结论','Verdict')}: <b>{summary.verdict.level}</b></div>
    <div>{summary.verdict.sentences.slice(0,2).map((x,i)=><div key={i}>{english?x.en:x.zh}</div>)}</div>
    <div>{tr('待处理','Needs you')}: <b>{approvals}</b></div></>:tr('正在读取…','Reading…')}</div>
   <button type="button" className="aiws-sh-row" onClick={()=>openView('observatory')}><Eye size={14}/>{tr('打开观察台','Open observatory')}</button>
  </SideBar>;
 };

 const viewBody=(id:string|null)=>{
  if(!id)return <div className="aiws-sh-welcome"><h1>AIWS OS</h1>
   <p>{tr('没有打开的标签。','No tab is open.')}</p>
   <ul><li><kbd>Ctrl+Shift+P</kbd> {tr('打开命令面板','open the command palette')}</li><li><kbd>Ctrl+B</kbd> {tr('侧边栏','side bar')} · <kbd>Ctrl+J</kbd> {tr('底部面板','panel')}</li></ul>
   <button type="button" className="aiws-sh-btn" onClick={()=>openView('observatory')}>{tr('回到观察台','Back to the observatory')}</button></div>;
  const t=tabs.find(x=>x.id===id);
  if(t?.kind==='file'&&t.path)return <FileViewer path={t.path} english={english}/>;
  const page=id as View;
  if(page==='browser')return <BrowserView english={english} canOpenExternal={apps.some(a=>a.id==='chromium'&&a.launchable)} openExternal={()=>void launchApp('chromium')}/>;
  return <div className={'aiws-os-content'+(page==='observatory'?' obs':'')}>
   {page!=='observatory'&&<div className="aiws-os-heading"><small>AIWS OS / LINUX GUEST</small><h1>{viewTitle(page)}</h1></div>}
   {page==='observatory'&&<Observatory csrf={csrf} english={english} data={data} onOpenAdvanced={openView} onCommand={runCommand}/>}
   {page==='overview'&&<div className="aiws-os-grid">
    <section><Activity size={21}/><h2>{tr('系统服务','OS service')}</h2><strong>{health?'CONNECTED':'DISCONNECTED'}</strong><p>{health?.mode||'–'}</p></section>
    <section><BrainCircuit size={21}/><h2>{tr('AI 调用能力','Tool capabilities')}</h2><strong>{health?.toolCount??'–'}</strong><p>{tr('只读接口','Read-only interfaces')}</p></section>
    <section><FolderTree size={21}/><h2>{tr('客户机工作区','Guest workspace')}</h2><strong className="aiws-os-path">{health?.workspace||'–'}</strong><p>{tr('不自动共享宿主文件夹','No host folder mount')}</p></section>
    <section><ShieldCheck size={21}/><h2>{tr('权限','Privileges')}</h2><strong>{health?.agentPrivileged?'ELEVATED':'USER ONLY'}</strong><p>{tr('默认无 root 权限','No root privileges by default')}</p></section>
    <section className="aiws-os-wide"><h2>{tr('系统运行架构','Unified execution route')}</h2>
     <p>{tr('自然语言 → 本地模型中转 → 审批 → 客户机工具 / 官方 CLI → 审计证据','Natural language → local relay model → approval → guest tools / official CLI → audit evidence')}</p></section>
   </div>}
   {page==='files'&&<GuestFiles csrf={csrf} english={english} command={command} onPlanCreated={()=>openView('plans')}/>}
   {page==='tasks'&&<div className="aiws-os-stack">
    <section className="aiws-os-card"><h2>{tr('任务队列','Task queue')}</h2>{snapshot?.jobs.length?snapshot.jobs.map(item=>
     <button type="button" className="aiws-os-task" key={item.id} onClick={()=>setJob(item)}><span>{item.tool}</span><strong>{item.status}</strong></button>)
     :<p>{tr('暂无任务','No tasks yet')}</p>}</section>
    {job&&<section className="aiws-os-card"><h2>{tr('任务详情','Task detail')} · {job.tool}</h2><p>{job.status}</p>
     {job.error&&<div className="aiws-os-error">{job.error}</div>}
     {job.result!==null&&<pre className="aiws-os-result">{JSON.stringify(job.result,null,2)}</pre>}</section>}
   </div>}
   {(page==='plans'||page==='local')&&<GuestTaskStudio csrf={csrf} english={english} capabilities={tools} focus={page==='local'?'model':'tasks'}/>}
   {page==='system'&&<GuestSystemConsole csrf={csrf} english={english} onPlanCreated={()=>openView('plans')}/>}
  </div>;
 };

 const recent=summary?.recent||[];
 const total=summary?.tokens.total;
 const tokenText=total&&total.in!==null&&total.out!==null?'↑'+total.in+' ↓'+total.out:tr('token 未知','tokens n/a');
 const level=summary?.verdict.level||'';
 return <div className="aiws-sh" data-theme={theme}>
  <ActivityBar active={activity} sidebarOpen={sidebar} onSelect={selectActivity}
   items={[{id:'observatory',label:tr('观察台','Observatory'),icon:<Eye size={22}/>,badge:approvals},
    {id:'explorer',label:tr('资源管理器','Explorer'),icon:<FolderTree size={22}/>},
    {id:'tools',label:tr('工具','Tools'),icon:<Wrench size={22}/>},
    {id:'tasks',label:tr('任务','Tasks'),icon:<Layers3 size={22}/>},
    {id:'ai',label:tr('AI','AI'),icon:<BrainCircuit size={22}/>},
    {id:'system',label:tr('系统','System'),icon:<ShieldCheck size={22}/>}]}
   bottom={[{id:'panel',label:tr('底部面板 (Ctrl+J)','Panel (Ctrl+J)'),icon:<SquareTerminal size={20}/>,onClick:()=>setPanel(x=>!x),pressed:panel},
    {id:'theme',label:tr('切换主题','Toggle theme'),icon:theme==='dark'?<Sun size={20}/>:<Moon size={20}/>,onClick:()=>setTheme(x=>x==='dark'?'light':'dark')}]}/>
  <div className="aiws-sh-main" style={sidebar?undefined:{gridTemplateColumns:'minmax(0,1fr)'}}>
   {sidebar&&sideContent()}
   <div className="aiws-sh-editor">
    <TabBar tabs={tabsView} active={active} onActivate={setActive} onClose={close} closeLabel={tr('关闭','Close')}/>
    <div className="aiws-sh-view" role="tabpanel">
     {starting&&<p className="aiws-os-muted" style={{padding:'12px 22px'}}>{tr('正在加载系统状态…','Loading guest status…')}</p>}
     {error&&<div className="aiws-os-error" role="alert" style={{margin:'12px 22px'}}>{error}</div>}
     {viewBody(active)}
    </div>
    {panel&&<Panel tabs={[{id:'jobs',label:tr('任务','Jobs')},{id:'events',label:tr('最近事件','Recent events')}]} active={panelTab} onSelect={setPanelTab} onClose={()=>setPanel(false)}>
     {panelTab==='jobs'?((snapshot?.jobs||[]).length?(snapshot?.jobs||[]).slice(0,30).map(j=><div key={j.id}>{j.status.padEnd(9)} {j.tool}</div>):<div>{tr('暂无任务','No tasks yet')}</div>)
      :(recent.length?recent.slice(0,30).map((r,i)=><div key={i}>{new Date(r.ts*1000).toLocaleTimeString()} {r.source} {r.label} {r.status}</div>):<div>{tr('暂无事件','No events yet')}</div>)}
    </Panel>}
   </div>
  </div>
  <StatusBar
   left={[{id:'svc',text:health?'● '+tr('系统服务正常','Service OK'):'○ '+tr('正在检查系统服务','Checking service'),tone:health?'':'warn',title:health?.mode},
    {id:'model',text:'◈ '+(summary?.status.localModel.online?tr('本地模型在线','Local model online'):summary?.status.localModel.configured?tr('本地模型待机','Local model idle'):tr('本地模型未配置','Local model not set')),onClick:()=>openView('local')},
    {id:'builder',text:'⚙ '+tr('构建','Builder')+' '+(summary?.status.builder.state||'–'),onClick:()=>openView('observatory')},
    ...(approvals?[{id:'appr',text:'⚠ '+approvals+' '+tr('待审批','to approve'),tone:'warn',onClick:()=>openView('observatory')}]:[])]}
   right={[{id:'tok',text:tokenText,title:tr('累计 token（仅统计已核实用量）','Total tokens (verified usage only)')},
    ...(level?[{id:'verdict',text:level,title:tr('审计结论','Audit verdict')}]:[]),
    {id:'ide',text:ide?.installed?'AIWS Code':tr('无编辑器','No editor'),onClick:ide?.installed?()=>void openIde():undefined,title:tr('打开完整代码编辑器','Open the full code editor')},
    {id:'lang',text:english?'EN':'中',onClick:()=>setLanguage(x=>x==='zh'?'en':'zh'),title:tr('切换语言','Switch language')},
    {id:'palette',text:'⌘ Ctrl+Shift+P',onClick:()=>setPalette(true)}]}/>
  {palette&&<CommandPalette commands={commands} onClose={()=>setPalette(false)} placeholder={tr('输入命令…','Type a command…')} empty={tr('没有匹配的命令','No matching command')}/>}
 </div>;
}
