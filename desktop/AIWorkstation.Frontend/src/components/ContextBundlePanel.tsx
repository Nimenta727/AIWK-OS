import {useEffect,useState} from 'react';
import {BookOpen,ChevronDown,ChevronRight,Eye,FileText,ShieldCheck} from 'lucide-react';
import {bridge,type ContextReport,type HandoffSummary,type WorkTask,type WorkStep} from '../bridge';
export function ContextBundlePanel({task,step}:{task:WorkTask;step:WorkStep}){
 const [bundle,setBundle]=useState<HandoffSummary|null>(null);
 const [preview,setPreview]=useState<ContextReport|null>(null);
 const [expanded,setExpanded]=useState(false);
 const [error,setError]=useState('');
 useEffect(()=>{
  let active=true;setBundle(null);setPreview(null);setExpanded(false);setError('');
  void bridge.call<HandoffSummary>('context.bundle',{taskId:task.id,stepId:step.id}).then(result=>{if(active)setBundle(result)}).catch(e=>{if(active)setError(String(e))});
  return()=>{active=false};
 },[task.id,step.id,step.agent,step.status,task.unified.goal,task.unified.acceptanceCriteria,task.unified.plans.length,task.completedCount]);
 const loadPreview=async()=>{
  if(expanded){setExpanded(false);return;}
  setError('');try{if(!preview)setPreview(await bridge.call<ContextReport>('context.bundle.preview',{taskId:task.id,stepId:step.id}));setExpanded(true);}
  catch(e){setError(String(e));}
 };
 return <div className="handoff-bundle"><div className="field"><label><BookOpen size={14}/> 结构化交接包（本地）</label>
  {bundle?<><p className="supporting">{bundle.manifest.filter(m=>m.included).length} 项已选择来源 · 预估 {bundle.approxTokens.toLocaleString()} Token · 已省略 {bundle.savedCharacters.toLocaleString()} 字符</p>
   <div className="handoff-sources">{bundle.manifest.map((entry,i)=><div key={`${entry.reference}:${i}`} className={entry.included?'':'muted'}><FileText size={12}/><span>{entry.kind} · {entry.reference}</span><small>{entry.included?'已选':'省略'}</small></div>)}</div>
   <button type="button" className="button secondary small" onClick={()=>void loadPreview()}>{expanded?<ChevronDown size={14}/>:<Eye size={14}/>} {expanded?'收起完整草稿':'主动展开交接全文'}</button>
   {expanded&&preview&&<pre className="handoff-preview" tabIndex={0}>{preview.text}</pre>}
   <small><ShieldCheck size={12}/> {bundle.evidenceNotice}</small></>:<p className="supporting">{error||'生成本地交接来源清单…'}</p>}
 </div></div>;
}
