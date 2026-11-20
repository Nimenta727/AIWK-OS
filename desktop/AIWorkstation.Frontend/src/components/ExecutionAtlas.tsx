import {useEffect,useMemo,useState} from 'react';
import {Activity,ArrowRight,ChevronDown,ChevronRight,FileCode2,FileDiff,Folder,FolderOpen,GitBranch,GitCommitHorizontal,GitMerge,Info,Layers3,LockKeyhole,RefreshCcw,Search,ShieldAlert,TerminalSquare,Workflow} from 'lucide-react';
import {bridge,type AtlasFlow,type ContextReport,type FileReview,type FlowNode,type RelatedStageLookup,type StructureEntry,type StructureReport,type WorkTask} from '../bridge';
import {buildStructureTree,evidenceLabel,isVisibleInMode,matchesPath,providerEventLabel,measuredEventTokens,structureLabel} from '../model/atlas.mjs';

type TreeItem = StructureEntry & {children:TreeItem[];changedCount:number};
type TreeMode = 'changes'|'before'|'after';
const phaseText:Record<string,string>={Routing:'执行器分配',Context:'上下文构建',Launcher:'CLI 启动',Provider:'模型与工具证据',Handoff:'阶段交接'};
const fmt=(value:number|null|undefined)=>value==null?'未知':value.toLocaleString('zh-CN');

function StructureTreeRow({item,depth,mode,selected,onPick,expanded,toggle,query}:{item:TreeItem;depth:number;mode:TreeMode;selected:string;onPick:(path:string)=>void;expanded:Set<string>;toggle:(path:string)=>void;query:string}){
 if(query ? !matchesPath(item,query) : !isVisibleInMode(item,mode))return null;
 const children=item.children.filter(x=>query?matchesPath(x,query):isVisibleInMode(x,mode));
 const opened=expanded.has(item.path);
 return <div className="atlas-tree-rowgroup">
  <div className={`atlas-tree-row ${selected===item.path?'selected':''}`} style={{paddingLeft:12+Math.min(depth,12)*16}}>
   <button className="atlas-tree-target" onClick={()=>item.isDirectory?toggle(item.path):onPick(item.path)} aria-label={`${item.path} ${structureLabel[item.change]||item.change}`} title={`${item.path} · ${item.evidence}`}>
    {item.isDirectory?(opened?<ChevronDown size={14}/>:<ChevronRight size={14}/>):<span className="atlas-chevron-space"/>}
    {item.isDirectory?(opened?<FolderOpen size={15}/>:<Folder size={15}/>):<FileCode2 size={14}/>}
    <span className="atlas-file-name">{item.path.split('/').at(-1)}</span>
   </button>
   <span className={`atlas-diff-tag ${item.change}`}>{structureLabel[item.change]||'未知'}</span>
   {item.isDirectory&&item.changedCount>0&&<span className="atlas-folder-count">{item.changedCount}</span>}
  </div>
  {item.isDirectory&&opened&&children.map(x=><StructureTreeRow key={x.path} item={x} depth={depth+1} mode={mode} selected={selected} onPick={onPick} expanded={expanded} toggle={toggle} query={query}/>)}
 </div>;
}

export function ExecutionAtlas({task,preferredStageId}:{task:WorkTask|null;preferredStageId?:string|null}){
 const [stageId,setStageId]=useState('');
 const [flow,setFlow]=useState<AtlasFlow|null>(null);
 const [structure,setStructure]=useState<StructureReport|null>(null);
 const [focusNode,setFocusNode]=useState<FlowNode|null>(null);
 const [context,setContext]=useState<ContextReport|null>(null);
 const [file,setFile]=useState('');
 const [fileReview,setFileReview]=useState<FileReview|null>(null);
 const [related,setRelated]=useState<RelatedStageLookup|null>(null);
 const [mode,setMode]=useState<TreeMode>('changes');
 const [expanded,setExpanded]=useState<Set<string>>(()=>new Set());
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(false);
 const [filter,setFilter]=useState('');
 const [revision,setRevision]=useState(0);
 const taskId=task?.id;
 useEffect(()=>{
  setStageId(task?.steps.find(x=>x.id===preferredStageId)?.id||task?.steps.find(x=>x.status==='Running')?.id||[...(task?.steps||[])].reverse().find(x=>x.startedAt)?.id||task?.steps[0]?.id||'');
  setFile('');setFileReview(null);setRelated(null);setContext(null);setFocusNode(null);
 },[taskId,preferredStageId]);
 useEffect(()=>{
  let live=true;setFlow(null);
  if(task)void bridge.call<AtlasFlow>('atlas.flow',{taskId:task.id}).then(v=>{if(live)setFlow(v);}).catch(e=>{if(live)setError(String(e));});
  return()=>{live=false;};
 },[task,revision]);
 useEffect(()=>{
  let live=true;setStructure(null);setContext(null);setFocusNode(null);setError('');setLoading(true);
  if(task&&stageId){void bridge.call<StructureReport>('atlas.structure',{taskId:task.id,stepId:stageId}).then(v=>{
   if(!live)return;setStructure(v);
   // Expand directories affected by changes; keep long unchanged structures collapsed.
   const folders=v.entries.filter(e=>e.isDirectory&&e.change!=='unchanged'&&e.change!=='unknown').map(e=>e.path);
   setExpanded(new Set(folders));
  }).catch(e=>{if(live)setError(String(e));}).finally(()=>{if(live)setLoading(false);});}
  else setLoading(false);
  return()=>{live=false;};
 },[taskId,stageId,revision]);
 useEffect(()=>{
  let live=true;setFileReview(null);setRelated(null);
  if(task&&stageId&&file){
   void bridge.call<FileReview>('atlas.fileDiff',{taskId:task.id,stepId:stageId,path:file}).then(v=>{if(live)setFileReview(v);}).catch(e=>{if(live)setError(String(e));});
   void bridge.call<RelatedStageLookup>('atlas.fileStages',{taskId:task.id,path:file}).then(v=>{if(live)setRelated(v);}).catch(e=>{if(live)setError(String(e));});
  }
  return()=>{live=false;};
 },[taskId,stageId,file,revision]);
 const selectedLane=flow?.lanes.find(l=>l.stepId===stageId);
 const stage=task?.steps.find(s=>s.id===stageId);
 const tree=useMemo(()=>buildStructureTree(structure?.entries||[]) as TreeItem[],[structure]);
 const toggle=(path:string)=>setExpanded(previous=>{const next=new Set(previous);next.has(path)?next.delete(path):next.add(path);return next;});
 const showContext=async()=>{
  if(!task||!stageId)return;
  setError('');try{setContext(await bridge.call<ContextReport>('atlas.context',{taskId:task.id,stepId:stageId}));}
  catch(e){setError(String(e));}
 };
 if(!task)return <div className="atlas-page"><div className="page-heading"><div><div className="eyebrow">EXECUTION ATLAS</div><h1>AI 调用与项目演化</h1></div></div><div className="blank-state">先创建或选择一个项目任务。</div></div>;
 return <div className="atlas-page">
  <header className="atlas-heading"><div><div className="eyebrow">EXECUTION ATLAS / LOCAL EVIDENCE</div><h1>AI 调用与项目演化</h1><p>{task.title} · 将阶段证据、Token、上下文与目录变化关联展示</p></div>
   <button className="button secondary small" onClick={()=>setRevision(v=>v+1)}><RefreshCcw size={15}/>刷新本地证据</button></header>
  <div className="atlas-stats">
   <div><span>已导入输入 Token</span><strong>{fmt(flow?.importedInput)}</strong><small>官方格式的用户导入日志</small></div>
   <div><span>已导入输出 Token</span><strong>{fmt(flow?.importedOutput)}</strong><small>不包括内部未知请求</small></div>
   <div><span>用量未知阶段</span><strong>{fmt(flow?.unknownUsageStages)}</strong><small>未知不等于零</small></div>
   <div><span>当前阶段结构变化</span><strong>{structure?`${structure.added+structure.removed+structure.modified} 文件`:'未知'}</strong><small>{structure?.partial?'结构证据不完整':'阶段快照对比'}</small></div>
  </div>
  {error&&<div role="alert" className="tool-error">{error}</div>}
  <div className="atlas-columns">
   <section className="atlas-panel atlas-calls">
    <div className="atlas-panel-title"><div><strong><Workflow size={17}/>AI 执行调用树</strong><small>阶段 → 路由 / 上下文 / CLI / 导入事件 / 交接</small></div></div>
    <div className="atlas-calls-scroll">{flow?.lanes.map(lane=><div className={`atlas-agent ${lane.stepId===stageId?'active':''}`} key={lane.stepId}>
     <button className="atlas-agent-head" onClick={()=>{setStageId(lane.stepId);setFile('');}}><GitBranch size={17}/><span><strong>{lane.header}</strong><small>{lane.agent} · {lane.state}</small></span><ChevronRight size={15}/></button>
     {lane.stepId===stageId&&<div className="atlas-phase-list">{lane.nodes.map(node=><div key={node.id}>
      <button onClick={()=>{setFocusNode(node);if(node.phase==='Context')void showContext();}} className={`atlas-phase ${focusNode?.id===node.id?'selected':''}`}>
       <span className={`atlas-evidence-dot ${node.state.toLowerCase()}`}/><span><strong>{phaseText[node.phase]||node.title}</strong><small>{node.subtitle}</small></span>
       <em>{evidenceLabel[node.state]||node.state}</em>
      </button>
      {node.phase==='Provider'&&lane.importedEvents.length>0&&<div className="atlas-provider-events">{lane.importedEvents.map((event,i)=><div key={event.sequence+':'+i}><Activity size={11}/><span>{providerEventLabel(event)}</span><small>{measuredEventTokens(event)?`入 ${fmt(event.input)} / 出 ${fmt(event.output)}`:'次数或用量未观测'}</small></div>)}</div>}
     </div>)}</div>}
    </div>)}{!flow&&<div className="project-empty">正在整理本地调用证据…</div>}</div>
   </section>
   <section className="atlas-panel atlas-structure">
    <div className="atlas-panel-title"><div><strong><Layers3 size={17}/>项目结构变化树</strong><small>修改前 / 修改后 / 发生变化的目录与文件</small></div><span className="atlas-stage-name">{stage?.title||'未选中阶段'}</span></div>
    <div className="atlas-structure-tools">
     <div className="atlas-mode-switch">{([['changes','结构差异'],['before','修改前'],['after','修改后']] as const).map(([value,name])=><button key={value} className={mode===value?'active':''} onClick={()=>setMode(value)}>{name}</button>)}</div>
     <label className="atlas-filter"><Search size={14}/><input aria-label="筛选路径" value={filter} onChange={e=>setFilter(e.target.value)} placeholder="查找目录或文件"/></label>
    </div>
    {structure&&<div className="atlas-structure-metrics"><span>新增 {structure.added}</span><span>删除 {structure.removed}</span><span>修改 {structure.modified}</span><span>受影响目录 {structure.changedDirectories}</span><span>Git 确认移动 {structure.renamedFiles?.length??0}</span></div>}
    {structure?.partial&&<div className="atlas-evidence-warning"><ShieldAlert size={15}/> {structure.notice}</div>}
    <div className="atlas-directory-list">{loading?<div className="project-empty">正在读取阶段结构快照…</div>:structure?<>
      {structure.entries.length>0?tree.filter(n=>matchesPath(n,filter)).map(node=><StructureTreeRow key={node.path} item={node} depth={0} mode={mode} query={filter} selected={file} onPick={setFile} expanded={filter.trim()?new Set(structure.entries.filter(e=>e.isDirectory).map(e=>e.path)):expanded} toggle={toggle}/>):<div className="project-empty">没有可比较的目录清单。老任务需要在新版完成新阶段才会形成前后快照。</div>}
     </>:<div className="project-empty">选择一个阶段查看项目结构。</div>}</div>
    <div className="atlas-structure-foot"><Info size={14}/>目录变化来自两个本地快照；文件修改结合 Git 状态和提交路径推断。不能仅据时间证明作者。Git 不直接跟踪目录。</div>
   </section>
  </div>
  <div className="atlas-detail-grid">
   <section className="atlas-panel atlas-detail"><div className="atlas-panel-title"><div><strong><FileDiff size={16}/>文件改动 / 阶段反向定位</strong><small>点击右侧目录树中的文件</small></div></div>
    {file?<><div className="atlas-detail-path"><FileCode2 size={14}/><strong>{file}</strong></div>
     <div className="atlas-link-pills"><span>相关阶段：</span>{related?.stages.length?related.stages.map(item=><button key={item.stageId} onClick={()=>setStageId(item.stageId)} className={item.stageId===stageId?'active':''} title={`${item.workspace} · ${item.evidence}`}>{item.title} <ArrowRight size={11}/></button>):<span>{related?.partial?'相关阶段不完整或未知':'未发现有证据支持的阶段变更'}</span>}{related?.partial&&<small title={related.notice}>（部分证据）</small>}</div>
     <p className="atlas-review-note">{fileReview?.note||'正在获取本地 Git Diff…'}</p>
     <pre className="atlas-code-preview">{fileReview?.diff||'没有可展示的差异。已提交历史或其他 Worktree 可能需要另外核对。'}</pre>
     {fileReview?.truncated&&<p className="atlas-evidence-warning">输出被限制长度，请用 Git 查看完整文件。</p>}
    </>:<div className="project-empty">选择某个文件，可看逐行 Diff，并定位它在哪个 Agent 阶段被观察到变化。</div>}
   </section>
   <section className="atlas-panel atlas-detail"><div className="atlas-panel-title"><div><strong><Activity size={16}/>请求与上下文检查器</strong><small>可见的证据与真实发送的模型请求必须区分</small></div></div>
    <div className="atlas-insight-body">{focusNode?<div className="atlas-insight-meta"><strong>{focusNode.title}</strong><p>{focusNode.detail}</p><small>证据：{focusNode.evidence}</small><small>用量：{focusNode.usageText}</small><small>{focusNode.durationText}</small></div>:<div className="atlas-insight-meta"><strong>{stage?.title||'选择阶段'}</strong><p>在调用树中选择任意步骤查看节点证据。</p></div>}
     <button className="button secondary small" onClick={()=>void showContext()}><LockKeyhole size={14}/>查看本地交接上下文</button>
     {context&&<div className="atlas-context"><div className="atlas-context-metrics"><span>当前草稿：{context.characters} 字符</span><span>约 {context.approxTokens} Token（估算）</span><span>重复裁剪：{context.savedCharacters} 字符</span></div>
      {context.parts.map((p,i)=><div key={i} className="atlas-context-part"><strong>{p.title}</strong><small>{p.included?`${p.characters} 字符 · ${p.source}`:'未引用'}</small><p>{p.evidence}</p></div>)}
      <details><summary>展开交接文本（仅本机生成的草稿）</summary><pre>{context.text}</pre></details>{context.truncated&&<p>文本已截断；完整内容不会自动发送。</p>}
      <p className="atlas-context-note">{context.notice}</p></div>}
    </div>
   </section>
  </div>
  <div className="atlas-footer"><GitMerge size={15}/> 文件扫描与请求树投影都是本地只读操作，无新增模型 Token。模型内部不可观察的请求、上下文和耗时始终标注为未知。</div>
 </div>;
}
