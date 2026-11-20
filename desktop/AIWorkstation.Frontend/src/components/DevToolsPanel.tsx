import {useEffect,useState} from 'react';
import {CheckCircle2, Clipboard, GitCompare, Play, RefreshCw, ShieldCheck, TerminalSquare} from 'lucide-react';
import {bridge, type WorkTask} from '../bridge';
import {READ_ONLY_VIEWS,resolveReadOnlyView,normalizeOutput} from '../model/toolCommands.mjs';
import {ReviewTable,ReviewTableBody,ReviewTableCell,ReviewTableHead,ReviewTableHeader,ReviewTableRow} from './T3ReviewTable';

type Inspection = { view:string;command:string;output:string;truncated:boolean;exitCode:number;durationMs:number };
type Capability = {id:string;label:string;access:string;available:boolean;requiresUserConfirmation:boolean;detail:string};
type Tab = 'git'|'terminal'|'permissions';
export function DevToolsPanel({task}:{task:WorkTask|null}){
  const [tab,setTab]=useState<Tab>('git');
  const [view,setView]=useState('status');
  const [inspection,setInspection]=useState<Inspection|null>(null);
  const [capabilities,setCapabilities]=useState<Capability[]|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  useEffect(()=>{setInspection(null);setError('');setNotice('');},[task?.id]);
  useEffect(()=>{if(tab==='permissions')bridge.call<Capability[]>('tools.capabilities').then(setCapabilities).catch(e=>setError(String(e)));},[tab]);
  const inspect=async()=>{
    if(!task||!resolveReadOnlyView(view))return;
    setBusy(true);setError('');setNotice('');
    try{const result=await bridge.call<Inspection>('tools.gitInspect',{taskId:task.id,view});setInspection(result);}catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };
  const openShell=async()=>{
    if(!task)return;
    setBusy(true);setError('');setNotice('');
    try{await bridge.call('tools.openShell',{taskId:task.id});setNotice('已请求打开 Windows PowerShell；新终端由你本人操作。');}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };
  return <div className="devtools-page">
    <div className="eyebrow">DEVELOPER WORKBENCH</div>
    <h1>代码审查与工具控制台</h1>
    <p className="lead">查看真实工作区的 Git 状态、Diff 和历史；所有命令都在本机运行，不发起模型调用。</p>
    <div className="tools-tabs" role="tablist" aria-label="开发工具">
      <button className={tab==='git'?'selected':''} role="tab" aria-selected={tab==='git'} onClick={()=>setTab('git')}><GitCompare size={16}/> Git 审查</button>
      <button className={tab==='terminal'?'selected':''} role="tab" aria-selected={tab==='terminal'} onClick={()=>setTab('terminal')}><TerminalSquare size={16}/> 终端</button>
      <button className={tab==='permissions'?'selected':''} role="tab" aria-selected={tab==='permissions'} onClick={()=>setTab('permissions')}><ShieldCheck size={16}/> Windows 权限</button>
    </div>
    {!task?<div className="blank-state">先选择或创建一项任务，工作台才能确定受信任的项目目录。</div>:<>
      <div className="tool-workspace"><span>目标工作区</span><strong title={task.workspace}>{task.workspace}</strong></div>
      {error&&<div className="tool-error" role="alert">{error}</div>}
      {notice&&<div className="tool-note" role="status">{notice}</div>}
      {tab==='git'&&<div className="devtools-card">
        <div className="tool-title"><div><strong>本地 Git 只读命令</strong><small>不允许自定义 shell 参数、git push 或远端网络命令</small></div><button className="button dark small" onClick={inspect} disabled={busy}><Play size={15}/>{busy?'正在读取…':'运行查询'}</button></div>
        <div className="git-command-list">{READ_ONLY_VIEWS.map(item=><button key={item.id} className={view===item.id?'selected':''} onClick={()=>{setView(item.id);setInspection(null)}}><span>{item.label}</span><code>{item.command}</code></button>)}</div>
        <div className="terminal-heading"><span><TerminalSquare size={15}/> Git 输出 {inspection?`· ${inspection.durationMs} ms`:''}</span>{inspection&&<button aria-label="复制 Git 输出" onClick={()=>navigator.clipboard.writeText(inspection.output).catch(()=>setError('无法复制，请检查剪贴板权限。'))}><Clipboard size={14}/> 复制</button>}</div>
        <pre className="terminal-output" aria-live="polite">{inspection?normalizeOutput(inspection.output):'选择一个预设 Git 命令，然后点击「运行查询」。\n输出仅显示在本机界面，不写入模型上下文。'}</pre>
        {inspection?.truncated&&<div className="tool-note">输出达到 120,000 字符上限，已截断。可切换「变更概览」查看摘要。</div>}
      </div>}
      {tab==='terminal'&&<div className="devtools-card tool-terminal-launch"><TerminalSquare size={31}/><h2>由用户控制的交互式终端</h2><p>当前版本在应用内提供受限 Git 命令输出。完整交互式 PowerShell 会打开独立桌面窗口，而不是模拟 Agent 自动执行。点击后仍需经过 Windows 应用内的明确确认。</p><button className="button dark" disabled={busy} onClick={openShell}><TerminalSquare size={16}/> 打开 Windows PowerShell</button><div className="tool-note">没有自动执行任意脚本的接口；PowerShell 进程继承你当前 Windows 账号的权限。</div></div>}
      {tab==='permissions'&&<div className="devtools-card"><div className="tool-title"><div><strong>Windows 工具能力</strong><small>查看系统当前已开放的本机操作，不是提升权限的开关</small></div><button className="button secondary small" onClick={()=>bridge.call<Capability[]>('tools.capabilities').then(setCapabilities).catch(e=>setError(String(e)))}><RefreshCw size={14}/> 刷新</button></div>
        <ReviewTable><ReviewTableHead><ReviewTableRow><ReviewTableHeader>能力</ReviewTableHeader><ReviewTableHeader>级别</ReviewTableHeader><ReviewTableHeader>检测结果</ReviewTableHeader></ReviewTableRow></ReviewTableHead><ReviewTableBody>{(capabilities??[]).map(item=><ReviewTableRow key={item.id}><ReviewTableCell><strong>{item.label}</strong><small>{item.detail}</small></ReviewTableCell><ReviewTableCell>{item.access}</ReviewTableCell><ReviewTableCell><span className={item.available?'tool-available':'tool-unavailable'}>{item.available?<><CheckCircle2 size={13}/> 已安装</>:'未提供'}</span>{item.requiresUserConfirmation&&<small>需用户确认</small>}</ReviewTableCell></ReviewTableRow>)}</ReviewTableBody></ReviewTable>
      </div>}
    </>}
  </div>;
}
