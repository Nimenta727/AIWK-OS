import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {AlertTriangle, ArrowRight, CheckCheck, ChevronRight, ChevronDown, Code2, File, FileDiff, Folder, GitBranch, GitCommit, RefreshCw} from 'lucide-react';
import {bridge, type FileReview, type ProjectOverview, type ProjectFile, type StageChangeReport, type WorkTask} from '../bridge';
import {describeGitStatus,describeObservedChange,formatShortHead,visibleProjectFiles} from '../model/projectEvidence.mjs';

function DiffLines({text}:{text:string}) {
  const lines=text.split('\n').slice(0,1800);
  return <div className="project-code" role="region" aria-label="本地代码差异" tabIndex={0}>
    {lines.map((line,i)=><div key={i} className={line.startsWith('+++')||line.startsWith('---')?'code-meta':line.startsWith('+')?'code-add':line.startsWith('-')?'code-del':line.startsWith('@@')?'code-hunk':''}>
      <span className="code-line-number">{i+1}</span><code>{line||' '}</code>
    </div>)}
    {text.split('\n').length>1800&&<div className="project-limit">显示前 1,800 行。请使用 Git 工具查看完整差异。</div>}
  </div>;
}
function FileRow({item,active,collapsed,onClick}:{item:ProjectFile;active:boolean;collapsed:boolean;onClick:()=>void}){
  const name=item.path.split('/').at(-1)||item.path;
  const status=describeGitStatus(item.status);
  return <button type="button" className={`project-file ${active?'selected':''}`} style={{paddingLeft:11+Math.min(item.path.split('/').length-1,8)*13}} title={item.path} onClick={onClick} >
    {item.isDirectory?(collapsed?<ChevronRight size={13}/>:<ChevronDown size={13}/>):null}{item.isDirectory?<Folder size={15}/>:<File size={14}/>}<span>{name}</span>
    {!item.isDirectory&&item.status&&<em className={`file-status ${status.tone}`} title={status.label}>{status.short}</em>}
    {item.isLink&&<small>link</small>}
  </button>;
}

export function ProjectExplorer({task}:{task:WorkTask|null}) {
  const [overview,setOverview]=useState<ProjectOverview|null>(null);
  const [file,setFile]=useState('');
  const [review,setReview]=useState<FileReview|null>(null);
  const [stageId,setStageId]=useState('');
  const [report,setReport]=useState<StageChangeReport|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [filter,setFilter]=useState<'all'|'changed'>('all');
  const [collapsed,setCollapsed]=useState<Set<string>>(()=>new Set());
  const [reviewPending,setReviewPending]=useState(false);
  const [stageError,setStageError]=useState('');
  const overviewRequest=useRef(0);
  const reviewRequest=useRef(0);
  const stageRequest=useRef(0);
  const refresh=useCallback(async()=>{
    if(!task)return;
    const ticket=++overviewRequest.current;
    setBusy(true);setError('');
    try { const value=await bridge.call<ProjectOverview>('project.overview',{taskId:task.id,stepId:stageId});if(ticket===overviewRequest.current)setOverview(value); }
    catch(ex){if(ticket===overviewRequest.current)setError(ex instanceof Error?ex.message:String(ex));}
    finally{if(ticket===overviewRequest.current)setBusy(false);}
  },[task?.id,stageId]);
  useEffect(()=>{
    overviewRequest.current++;reviewRequest.current++;stageRequest.current++;
    setCollapsed(new Set());setOverview(null);setFile('');setReview(null);setReport(null);setReviewPending(false);
    setStageId(task?.steps.find(x=>x.status==='Running')?.id||[...(task?.steps||[])].reverse().find(x=>x.startedAt)?.id||task?.steps[0]?.id||'');
  },[task?.id]);
  useEffect(()=>{if(task&&stageId)void refresh();},[task?.id,stageId,refresh]);
  const openFile=async(path:string)=>{
    if(!task)return;
    const ticket=++reviewRequest.current;
    setFile(path);setReview(null);setError('');setReviewPending(true);
    try {const value=await bridge.call<FileReview>('project.review',{taskId:task.id,stepId:stageId,path});if(ticket===reviewRequest.current)setReview(value);}
    catch(ex){if(ticket===reviewRequest.current)setError(ex instanceof Error?ex.message:String(ex));}
    finally{if(ticket===reviewRequest.current)setReviewPending(false);}
  };
  const examineStage=useCallback(async()=>{
    if(!task||!stageId)return;
    const ticket=++stageRequest.current;
    setReport(null);setStageError('');
    try{const value=await bridge.call<StageChangeReport>('project.stageChanges',{taskId:task.id,stepId:stageId});if(ticket===stageRequest.current)setReport(value);}
    catch(ex){if(ticket===stageRequest.current)setStageError(ex instanceof Error?ex.message:String(ex));}
  },[task?.id,stageId]);
  useEffect(()=>{
    reviewRequest.current++;setFile('');setReview(null);setReviewPending(false);
    if(stageId)void examineStage();
  },[examineStage,stageId]);
  const list=useMemo(()=>visibleProjectFiles(overview?.files||[],filter,collapsed) as ProjectFile[],[overview,filter,collapsed]);
  if(!task)return <div className="project-page"><div className="eyebrow">PROJECT EVIDENCE</div><h1>项目文件与 Git 变更</h1><div className="blank-state">先选择一个任务及其受信任的工作目录。</div></div>;
  return <div className="project-page">
    <div className="project-top"><div><div className="eyebrow">PROJECT STRUCTURE / GIT EVIDENCE</div><h1>项目文件与 Git 变更</h1><p>将代码差异关联到工作流阶段，同时保留证据来源与观察边界。</p></div><button className="button secondary small" onClick={refresh} disabled={busy}><RefreshCw size={15}/>{busy?'读取中…':'刷新项目'}</button></div>
    <div className="project-repo-strip"><span><Folder size={15}/>{overview?.workspace||task.workspace}</span><span><GitBranch size={14}/>{overview?.branch||'Git 信息未知'}</span><span><GitCommit size={14}/>{formatShortHead(overview?.head||'')}</span><span className="project-count">{overview?`${overview.changedCount} 个 Git 状态条目`:'加载中…'}</span></div>
    <div className="project-truth-note"><AlertTriangle size={16}/><span>这里展示的是<strong>工作区与 Git 的真实观察结果</strong>，不是 AI 自述，也不能仅凭时间证明某个文件由 Agent 修改。不会自动发送代码内容给模型。</span></div>
    {error&&<div className="tool-error" role="alert">{error}</div>}
    {overview?.notices.map((x,i)=><div className="tool-note" role="status" key={i}>{x}</div>)}
    <div className="project-main">
      <section className="project-browser"><div className="project-panel-head"><div><strong>文件结构</strong><small>{overview?.files.length||0} 个可见项目条目</small></div><div className="project-filter"><button className={filter==='all'?'active':''} onClick={()=>setFilter('all')}>全部</button><button className={filter==='changed'?'active':''} onClick={()=>setFilter('changed')}>变更</button></div></div>
        <div className="project-files">{list.length?list.map(item=><FileRow item={item} key={item.path} active={file===item.path} collapsed={collapsed.has(item.path)} onClick={()=>item.isDirectory?setCollapsed(previous=>{
          const next=new Set(previous);next.has(item.path)?next.delete(item.path):next.add(item.path);return next;
        }):void openFile(item.path)}/>):<div className="project-empty">{overview?'没有符合筛选条件的文件。':'正在读取工作区…'}</div>}</div>
      </section>
      <section className="project-diff"><div className="project-panel-head"><div><strong>{file||'逐文件 Diff'}</strong><small>{review?review.isPreview?'未追踪文件 · 本地预览':'工作区 / 已暂存差异':'从左侧选择文件查看 Git 补丁'}</small></div><FileDiff size={17}/></div>
        {reviewPending?<div className="project-empty" role="status">正在读取选中文件的 Git 差异…</div>:review?<><div className="project-review-note">{review.note}{review.truncated?' 输出已截断。':''}</div><DiffLines text={review.diff||'当前没有可展示的补丁内容。'}/></>:<div className="project-empty project-diff-placeholder"><Code2 size={28}/><strong>查看真实文件改动</strong><p>支持 Git 修改与已暂存补丁；新建文件只在明确点选后进行安全范围内的只读预览。</p></div>}
      </section>
    </div>
    <div className="project-stage-card"><div className="project-stage-head"><div><div className="eyebrow">WORKFLOW ↔ GIT</div><h2>阶段变更关联</h2><p>从启动检查点到完成检查点；正在运行的阶段使用实时 Git 状态。</p></div><div className="project-stage-select"><select aria-label="选择工作流阶段" value={stageId} onChange={e=>{overviewRequest.current++;stageRequest.current++;reviewRequest.current++;setStageId(e.target.value);setOverview(null);setReport(null);setFile('');setReview(null);}}>{task.steps.map((x,i)=><option key={x.id} value={x.id}>{i+1}. {x.title}</option>)}</select><button className="icon-button" title="重新采集" aria-label="刷新阶段变化" onClick={()=>void examineStage()}><RefreshCw size={15}/></button></div></div>
      {stageError&&<div className="tool-error" role="alert">{stageError}</div>}
      {report?<><div className="project-stage-metrics"><span>前后快照 <strong>{report.startedAt?'已建立起点':'缺少起点'}</strong></span><span>观察到的状态变化 <strong>{report.files.length}</strong></span><span>HEAD 变化 <strong>{report.headChanged?'是':'否'}</strong></span>{report.partial&&<span className="project-caution">证据不完整</span>}</div>
        {report.files.length?<div className="project-changes">{report.files.slice(0,120).map(x=><button key={x.path} onClick={()=>void openFile(x.path)} className="project-change"><span>{describeObservedChange(x.kind)}</span><strong>{x.path}</strong><small>{x.before||'无'} <ArrowRight size={12}/> {x.after||'无'}</small><ChevronRight size={15}/></button>)}</div>:<div className="project-empty">{report.partial?'缺少完整快照，不能判断是否有其他修改。':'两个检查点之间没有观察到工作区状态差异。'}</div>}
        {report.headChanged&&<div className="project-review-note">检测到提交 HEAD 改变：{formatShortHead(report.fromHead)} → {formatShortHead(report.toHead)}。
          {report.committedFiles.length>0?<div className="project-commits">{report.committedFiles.map(path=><button key={path} onClick={()=>void openFile(path)}><GitCommit size={13}/>{path}</button>)}</div>:'暂未获取到提交涉及的文件列表；可通过 Git 历史核对。'}</div>}
        <div className="project-stage-foot"><CheckCheck size={15}/>{report.notice}</div>
      </>:!stageError&&<div className="project-empty">读取阶段 Git 检查点…</div>}
    </div>
  </div>;
}
