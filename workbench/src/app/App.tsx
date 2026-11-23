import {useCallback,useEffect,useMemo,useState} from 'react';
import '../ui/base.css';
import '../ui/kit.css';
import '../ui/layout.css';
import './app.css';
import './viewer.css';
import '../os/OsWorkbench.css';
import {ActivityBar,BottomPanel,Palette,Sash,SideBar,StatusBar,Tabs} from '../ui/Layout';
import type {Command,Tab} from '../ui/Layout';
import {Button,IconButton,Icon,Notice,Row,Section} from '../ui/kit';
import Home from './Home';
import Plans from './Plans';
import AgentTree from './AgentTree';
import ChangesPage from './Changes';
import SystemPage from './System';
import Build from './Build';
import ProjectPreview from './ProjectPreview';
import IdeView from './IdeView';
import Assistant from './Assistant';
import FileViewer from '../os/FileViewer';
import BrowserView from '../os/BrowserView';
import GuestFiles from '../os/GuestFiles';
import GuestTaskStudio from '../os/GuestTaskStudio';
import GuestSystemConsole from '../os/GuestSystemConsole';
import useObservatoryData from '../os/useObservatoryData';
import {api,onCsrfChange,refreshCsrf} from '../os/api';
import {buildTree,parseCommand} from '../model/fileOps.mjs';
import {closeTab,cycleTab,fileTabId,fileTitle,flattenTree,isEditableTarget,loadPrefs,matchKey,openTab,savePrefs} from '../model/shell.mjs';
import {msg} from './common';
import {LangProvider} from '../ui/lang';
import {setLang} from '../os/lang';

type TreeNode={name:string;path:string;type:'dir'|'file';children:TreeNode[]};
type AppRow={id:string;kind:string;category:string;zh:string;en:string;installed:boolean;path:string|null;launchable:boolean};
type Cap={name:string;description:string};
type View={id:string;zh:string;en:string;icon:string};
const VIEWS:View[]=[
 {id:'home',zh:'总览',en:'Overview',icon:'pulse'},{id:'plans',zh:'计划审核',en:'Plan review',icon:'checklist'},{id:'agents',zh:'云端智能体',en:'Cloud agents',icon:'type-hierarchy'},
 {id:'changes',zh:'变更审查',en:'Review changes',icon:'diff'},{id:'build',zh:'构建',en:'Build',icon:'rocket'},{id:'files',zh:'AI 文件管理',en:'AI files',icon:'files'},
 {id:'tasks',zh:'持久任务与 DAG',en:'Persistent tasks',icon:'list-tree'},{id:'assistant',zh:'本地助手',en:'Local assistant',icon:'hubot'},{id:'model',zh:'本地模型开关',en:'Model switch',icon:'settings'},
 {id:'ide',zh:'代码编辑器',en:'Code editor',icon:'code'},{id:'system',zh:'系统',en:'System',icon:'settings-gear'},{id:'advanced',zh:'系统服务与内核',en:'Services & kernel',icon:'server-process'},{id:'browser',zh:'内置浏览器',en:'Preview browser',icon:'globe'}];
const ACTIVITIES=[{id:'home',zh:'总览',en:'Overview',icon:'pulse'},{id:'plans',zh:'计划',en:'Plans',icon:'checklist'},{id:'agents',zh:'智能体',en:'Agents',icon:'type-hierarchy'},
 {id:'changes',zh:'变更',en:'Changes',icon:'diff'},{id:'explorer',zh:'文件',en:'Files',icon:'files'},{id:'system',zh:'系统',en:'System',icon:'settings-gear'}];
const isView=(id:string|null)=>VIEWS.some(v=>v.id===id);
const store=():Storage|null=>{try{return window.localStorage;}catch{return null;}};
const readNum=(k:string,d:number)=>{try{const v=Number(window.localStorage.getItem(k));return Number.isFinite(v)&&v>0?v:d;}catch{return d;}};
const writeNum=(k:string,v:number)=>{try{window.localStorage.setItem(k,String(v));}catch{/* optional */}};

export default function App(){
 const storage=useMemo(store,[]);
 const initial=useMemo(()=>loadPrefs(storage||({getItem:()=>null} as unknown as Storage)),[storage]);
 const [english,setEnglish]=useState<boolean>(()=>{try{const v=window.localStorage.getItem('aiws.lang');if(v==='en')return true;if(v==='zh')return false;}catch{/* optional */}return !(navigator.language||'zh').toLowerCase().startsWith('zh');});
 const tr=useCallback((zh:string,en:string)=>english?en:zh,[english]);
 const [theme,setTheme]=useState<'dark'|'light'>(initial.theme as 'dark'|'light');
 const [sidebar,setSidebar]=useState<boolean>(initial.sidebar);
 const [panel,setPanel]=useState<boolean>(initial.panel);
 const [activity,setActivity]=useState<string>(initial.activity);
 const [sbW,setSbW]=useState(()=>readNum('aiws.sbw',260));
 const [bpH,setBpH]=useState(()=>readNum('aiws.bph',220));
 const [tabs,setTabs]=useState<Tab[]>([{id:'home',title:'',pinned:true}]);
 const [active,setActive]=useState<string|null>('home');
 const [focus,setFocus]=useState<Record<string,string>>({});
 const [palette,setPalette]=useState(false);
 const [csrf,setCsrf]=useState('');
 const [caps,setCaps]=useState<Cap[]>([]);
 const [workspace,setWorkspace]=useState('');
 type Health={systemVerify:{ok:boolean;modified:string[];missing:string[];unlisted:string[];error:string|null}|null;workDisk:boolean};
 const [health,setHealth]=useState<Health|null>(null);
 const [tree,setTree]=useState<TreeNode[]>([]);
 const [expanded,setExpanded]=useState<Set<string>>(new Set());
 const [apps,setApps]=useState<AppRow[]>([]);
 const [note,setNote]=useState('');
 const [nav,setNav]=useState<{url:string;nonce:number}|null>(null);
 const [cmd,setCmd]=useState<{text:string;nonce:number}|null>(null);
 const data=useObservatoryData();
 const s=data.summary;

 useEffect(()=>{document.documentElement.dataset.theme=theme;document.documentElement.lang=english?'en':'zh-CN';document.title=english?'AIWS · AI Workbench':'AIWS · AI 工作台';setLang(english?'en':'zh');try{window.localStorage.setItem('aiws.lang',english?'en':'zh');}catch{/* optional */}},[theme,english]);
 useEffect(()=>{if(storage)savePrefs(storage,{theme,sidebar,panel,activity});},[storage,theme,sidebar,panel,activity]);
 useEffect(()=>{writeNum('aiws.sbw',sbW);},[sbW]);useEffect(()=>{writeNum('aiws.bph',bpH);},[bpH]);
 const loadTree=useCallback(async()=>{try{const t=await api<{files:string[];dirs?:string[]}>('/workspace/tree');setTree(buildTree(t.files,t.dirs) as TreeNode[]);}catch(e){setNote(msg(e));}},[]);
 useEffect(()=>{
  const off=onCsrfChange(setCsrf);
  void refreshCsrf().catch(e=>setNote(msg(e)));
  void api<{capabilities:Cap[];health:{workspace:string}&Health}>('/snapshot').then(x=>{setCaps(x.capabilities);setWorkspace(x.health.workspace||'');setHealth(x.health);}).catch(e=>setNote(msg(e)));
  void api<{apps:AppRow[]}>('/apps').then(x=>setApps(x.apps)).catch(()=>setApps([]));
  void loadTree();
  return off;
 },[loadTree]);

 const open=useCallback((id:string,focusId?:string)=>{
  if(focusId)setFocus(f=>({...f,[id]:focusId}));
  const r=openTab(tabs,{id,title:id,pinned:id==='home'},active);setTabs(r.tabs);setActive(r.active);
 },[tabs,active]);
 const openFile=useCallback((p:string)=>{const r=openTab(tabs,{id:fileTabId(p),title:fileTitle(p)},active);setTabs(r.tabs);setActive(r.active);},[tabs,active]);
 const close=useCallback((id:string)=>{const r=closeTab(tabs,active,id);setTabs(r.tabs);setActive(r.active);},[tabs,active]);
 const runCommand=(text:string)=>{if(!(parseCommand(text) as {ok:boolean}).ok)return false;open('files');setCmd({text,nonce:Date.now()});return true;};
 const launch=async(id:string)=>{
  setNote('');
  try{const r=await api<{started:boolean}>(id==='aiws-code'?'/ide/open':'/apps/launch',{method:'POST',body:id==='aiws-code'?'{}':JSON.stringify({id})});
   setNote(r.started?tr('正在启动……使用 Alt+Tab 切换，Super+Home 回到工作台。','Starting… use Alt+Tab to switch, Super+Home to come back.'):tr('刚刚已启动过，请稍等。','Already starting, please wait.'));}
  catch(e){setNote(msg(e));}
 };
 const stopRun=(runId:string)=>{void api('/builder/runs/'+runId+'/stop',{method:'POST',body:'{}'}).then(()=>data.reload()).catch(e=>setNote(msg(e)));};
 const select=(id:string)=>{if(sidebar&&activity===id){setSidebar(false);return;}setActivity(id);setSidebar(true);if(id!=='explorer'&&id!=='home')open(id==='agents'?'agents':id);};

 const approvals=(s?.runApprovals.length||0)+(s?.tasks.needsApproval.length||0);
 const title=(id:string)=>{const v=VIEWS.find(x=>x.id===id);return v?(english?v.en:v.zh):id;};
 const tabList:Tab[]=tabs.map(t=>isView(t.id)?{...t,title:title(t.id),icon:VIEWS.find(v=>v.id===t.id)!.icon}:{...t,icon:'file'});
 const folders=tree.filter(n=>n.type==='dir').map(n=>n.path);
 const rows=flattenTree(tree,expanded) as (TreeNode&{depth:number})[];
 const toggleDir=(p:string)=>setExpanded(prev=>{const n=new Set(prev);if(n.has(p))n.delete(p);else n.add(p);return n;});
 const agentSessions=(s?.sessions||[]).filter(x=>x.agent==='claude'||x.agent==='codex');

 const commands:Command[]=useMemo(()=>[
  ...VIEWS.map(v=>({id:'view:'+v.id,label:(english?'Open: ':'打开：')+(english?v.en:v.zh),keywords:v.zh+' '+v.en,run:()=>open(v.id)})),
  {id:'sidebar',label:tr('切换侧边栏','Toggle side bar'),hint:'Ctrl+B',run:()=>setSidebar(x=>!x)},
  {id:'panel',label:tr('切换底部面板','Toggle panel'),hint:'Ctrl+J',run:()=>setPanel(x=>!x)},
  {id:'theme',label:tr('切换深色/浅色主题','Toggle dark/light theme'),keywords:'theme dark light',run:()=>setTheme(x=>x==='dark'?'light':'dark')},
  {id:'lang',label:tr('切换语言 中文/English','Switch language'),keywords:'language',run:()=>setEnglish(x=>!x)},
  {id:'refresh',label:tr('刷新','Refresh'),keywords:'reload',run:()=>{void data.reload();void loadTree();}},
  {id:'ide',label:tr('打开 AIWS Code（完整代码编辑器）','Open AIWS Code'),keywords:'vscode editor ide code',run:()=>void launch('aiws-code')},
  {id:'closetab',label:tr('关闭当前标签','Close current tab'),hint:'Alt+W',run:()=>{if(active)close(active);}}
  // eslint-disable-next-line react-hooks/exhaustive-deps
 ],[english,active,open,close,data.reload,loadTree]);
 useEffect(()=>{
  const onKey=(e:KeyboardEvent)=>{
   if(matchKey(e,'mod+shift+p')||matchKey(e,'f1')){e.preventDefault();setPalette(true);}
   else if(matchKey(e,'mod+b')){e.preventDefault();setSidebar(x=>!x);}
   else if(matchKey(e,'mod+j')){e.preventDefault();setPanel(x=>!x);}
   else if(matchKey(e,'alt+w')&&active){e.preventDefault();close(active);}
   else if(matchKey(e,'alt+arrowright')&&!isEditableTarget(e.target)){e.preventDefault();setActive(cycleTab(tabs,active,1));}
   else if(matchKey(e,'alt+arrowleft')&&!isEditableTarget(e.target)){e.preventDefault();setActive(cycleTab(tabs,active,-1));}
  };
  window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey);
 },[tabs,active,close]);

 const side=()=>{
  if(activity==='explorer')return <SideBar title={tr('文件','Files')} actions={<IconButton icon="refresh" label={tr('刷新','Refresh')} onClick={()=>void loadTree()}/>}>
   <div role="tree" aria-label={tr('工作区文件','Workspace files')}>{rows.map(r=><Row key={r.path} depth={r.depth} icon={r.type==='dir'?(expanded.has(r.path)?'folder-opened':'folder'):'file'} expanded={r.type==='dir'?expanded.has(r.path):undefined}
    label={r.name} on={active===fileTabId(r.path)} onClick={()=>r.type==='dir'?toggleDir(r.path):openFile(r.path)}/>)}
   {!rows.length&&<p className="muted pad">{tr('工作区为空','The workspace is empty')}</p>}</div></SideBar>;
  if(activity==='agents')return <SideBar title={tr('云端智能体','Cloud agents')}>{!agentSessions.length&&<p className="muted pad">{tr('还没有云端运行','No cloud runs yet')}</p>}
   {agentSessions.map(x=><Row key={x.session} icon="type-hierarchy" label={x.session} detail={x.status} onClick={()=>open('agents',x.session)}/>)}
   <Row icon="rocket" label={tr('授权并开始构建…','Grant & start a build…')} onClick={()=>open('build')}/></SideBar>;
  if(activity==='plans')return <SideBar title={tr('计划','Plans')}>
   <Row icon="checklist" label={tr('全部计划','All plans')} onClick={()=>open('plans')}/>
   {(s?.tasks.recent||[]).slice(0,10).map(t=><Row key={t.id} icon="circle-small" label={t.title} onClick={()=>open('plans',t.id)}/>)}
   <Row icon="list-tree" label={tr('持久任务与 DAG（高级）','Persistent tasks (advanced)')} onClick={()=>open('tasks')}/></SideBar>;
  if(activity==='changes')return <SideBar title={tr('变更','Changes')}><Row icon="diff" label={tr('工作区根目录','Workspace root')} onClick={()=>open('changes')}/>{folders.map(f=><Row key={f} icon="folder" label={f} onClick={()=>open('changes')}/>)}</SideBar>;
  if(activity==='system')return <SideBar title={tr('系统','System')}>
   <Row icon="settings-gear" label={tr('显示 · 输入法 · 网络 · 电源','Display · input · network · power')} onClick={()=>open('system')}/>
   <Row icon="server-process" label={tr('系统服务与内核','Services & kernel')} onClick={()=>open('advanced')}/>
   <Row icon="hubot" label={tr('本地助手','Local assistant')} onClick={()=>open('assistant')}/>
   <Row icon="settings" label={tr('本地模型开关','Model switch')} onClick={()=>open('model')}/>
   <Section title={tr('程序','Programs')}>{apps.filter(a=>a.kind==='gui').map(a=><Row key={a.id} icon="play" label={english?a.en:a.zh} detail={a.installed?'':tr('未安装','missing')} onClick={a.launchable?()=>void launch(a.id):undefined}/>)}
    <Row icon="code" label="AIWS Code" onClick={()=>void launch('aiws-code')}/></Section>
   {note&&<p className="muted pad">{note}</p>}</SideBar>;
  return <SideBar title={tr('总览','Overview')}>
   <Row icon="pulse" label={tr('总览','Overview')} onClick={()=>open('home')}/><Row icon="rocket" label={tr('构建','Build')} onClick={()=>open('build')}/><Row icon="hubot" label={tr('本地助手','Local assistant')} onClick={()=>open('assistant')}/>
   <Row icon="files" label={tr('AI 文件管理','AI files')} onClick={()=>open('files')}/><Row icon="globe" label={tr('预览浏览器','Preview browser')} onClick={()=>open('browser')}/><Row icon="code" label={tr('代码编辑器（AIWS Code）','Code editor (AIWS Code)')} onClick={()=>open('ide')}/></SideBar>;
 };
 const pageOf=(id:string|null)=>{
  if(id&&id.startsWith('file:'))return <div className="legacy fill"><FileViewer path={id.slice(5)} english={english}/></div>;
  switch(id){
   case 'home':return <Home english={english} tr={tr} data={data} onCommand={runCommand} onOpen={(v,f)=>open(v,f)}/>;
   case 'plans':return <Plans tr={tr} focus={focus.plans||null} onStop={stopRun} activeRun={s?.status.builder.runId||null} reload={data.reload}/>;
   case 'agents':return <AgentTree tr={tr} sessions={s?.sessions||[]} focus={focus.agents||null} onOpenFile={openFile}/>;
   case 'changes':return <ChangesPage tr={tr} folders={folders}/>;
   case 'build':return <Build tr={tr} english={english} data={data}/>;
   case 'system':return <SystemPage tr={tr}/>;
   case 'files':return <div className="legacy"><GuestFiles csrf={csrf} english={english} command={cmd} onPlanCreated={()=>open('plans')}/></div>;
   case 'assistant':return <Assistant tr={tr} english={english} onPlan={tid=>open('plans',tid)} onModelSwitch={()=>open('model')}/>;
   case 'tasks':case 'model':return <div className="legacy"><GuestTaskStudio csrf={csrf} english={english} capabilities={caps as never} focus={id==='model'?'model':'tasks'}/></div>;
   case 'advanced':return <div className="legacy"><GuestSystemConsole csrf={csrf} english={english} onPlanCreated={()=>open('plans')}/></div>;
   case 'browser':return <div className="legacy fill"><ProjectPreview tr={tr} folders={folders} onUrl={u=>setNav({url:u,nonce:Date.now()})}/><BrowserView english={english} navigateTo={nav} openExternal={()=>void launch('chromium')} canOpenExternal={apps.some(a=>a.id==='chromium'&&a.launchable)}/></div>;
   case 'ide':return <IdeView tr={tr} folders={folders}/>;
   default:return null;
  }
 };
 const modelOnline=s?.status.localModel.online;
 return <LangProvider english={english}><div className="app">
  <a className="skip" href="#editor">{tr('跳到内容','Skip to content')}</a>
  <header className="titlebar"><Icon name="circuit-board"/><strong>AIWS</strong><span className="grow">{workspace?workspace.split('/').pop():''}</span>
   <Button variant="ghost" icon="search" onClick={()=>setPalette(true)}>{tr('命令','Commands')} <kbd>Ctrl+Shift+P</kbd></Button></header>
  <div className="main">
   <ActivityBar items={ACTIVITIES.map(a=>({id:a.id,label:english?a.en:a.zh,icon:a.icon,badge:a.id==='plans'?approvals:undefined}))} active={activity} open={sidebar} onSelect={select}
    bottom={[{id:'theme',label:tr('切换主题','Toggle theme'),icon:'color-mode',onClick:()=>setTheme(x=>x==='dark'?'light':'dark')},{id:'lang',label:tr('切换语言','Language'),icon:'globe',onClick:()=>setEnglish(x=>!x)}]}/>
   {sidebar&&<><div style={{width:sbW,display:'flex'}}>{side()}</div><Sash dir="x" value={sbW} min={180} max={520} onChange={setSbW} label={tr('调整侧边栏宽度','Resize side bar')}/></>}
   <div className="center">
    {health?.systemVerify&&!health.systemVerify.ok&&<Notice tone="err">{tr('系统文件与镜像清单不一致：','System files differ from the image manifest: ')}{health.systemVerify.error||[...health.systemVerify.modified.map(x=>x+' ('+tr('被改','modified')+')'),...health.systemVerify.missing.map(x=>x+' ('+tr('缺失','missing')+')'),...health.systemVerify.unlisted.map(x=>x+' ('+tr('多出','unlisted')+')')].slice(0,4).join(', ')}</Notice>}
    <Tabs tabs={tabList} active={active} onActivate={setActive} onClose={close} closeLabel={tr('关闭','Close')}/>
    <main id="editor" className="editor" tabIndex={-1}>{pageOf(active)}</main>
    {panel&&<><Sash dir="y" value={bpH} min={80} max={480} invert onChange={setBpH} label={tr('调整面板高度','Resize panel')}/>
     <div style={{height:bpH,display:'flex',flexDirection:'column'}}><BottomPanel tabs={[{id:'activity',label:tr('活动','Activity'),count:s?.recent.length}]} active="activity" onSelect={()=>undefined} onClose={()=>setPanel(false)}>
      <ul className="feed selectable">{(s?.recent||[]).map((r,i)=><li key={i} className={r.status==='error'?'bad':''}><time>{new Date(r.ts*1000).toLocaleTimeString()}</time><b>{r.source}</b><span>{r.label}</span></li>)}</ul></BottomPanel></div></>}
   </div>
  </div>
  <StatusBar left={[
   {id:'model',icon:'hubot',text:modelOnline?tr('本地模型在线','Local model online'):s?.status.localModel.configured?tr('本地模型待机','Local model idle'):tr('本地模型未配置','Local model off'),onClick:()=>open('assistant')},
   {id:'build',icon:'rocket',text:tr('构建 ','Build ')+(s?.status.builder.state||'–'),onClick:()=>open('build')},
   ...(health?.systemVerify?[{id:'wd',icon:'database',text:health.workDisk?tr('工作盘','Work disk'):tr('无工作盘','No work disk'),tone:health.workDisk?undefined:('warn' as const),title:tr('AI 的工作区放在独立的工作盘上（只读系统盘、工作盘不可执行）','The AI works on a separate disk (system read-only, work disk noexec)')}]:[]),
   ...(approvals?[{id:'appr',icon:'bell',text:approvals+' '+tr('待审批','to review'),tone:'warn' as const,onClick:()=>open('plans')}]:[])]}
   right={[{id:'audit',icon:s?.verdict.level==='red'?'error':s?.verdict.level==='yellow'?'warning':'pass',tone:s?.verdict.level==='red'?'err':s?.verdict.level==='yellow'?'warn':'ok',text:tr('审计','Audit'),title:s?.verdict.sentences[0]?(english?s.verdict.sentences[0].en:s.verdict.sentences[0].zh):undefined},
    {id:'panel',icon:'layout-panel',text:tr('面板','Panel'),onClick:()=>setPanel(x=>!x)}]}/>
  {palette&&<Palette commands={commands} onClose={()=>setPalette(false)} placeholder={tr('输入命令…','Type a command…')} empty={tr('没有匹配的命令','No matching command')}/>}
 </div></LangProvider>;
}
