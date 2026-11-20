import {ArrowRight, GitBranch, LockKeyhole} from 'lucide-react';
import type {WorkTask} from '../bridge';
import {graphLayers,agentName,readyStageIds} from '../model/workflow.mjs';
export function DagCanvas({task,selected,onPick}:{task:WorkTask;selected:string|null;onPick:(id:string)=>void}){
 const layers=graphLayers(task);const ready=new Set(readyStageIds(task));
 return <div className="dag-layers" role="group" aria-label="可视化多 Agent DAG 依赖流程">
  {layers.map((layer,index)=><div key={index} className="dag-layer"><div className="dag-column-label">阶段 {index+1}</div>
   {layer.map(s=><button className={`dag-stage ${selected===s.id?'selected':''}`} key={s.id} onClick={()=>onPick(s.id)}>
    <span className="dag-status">{s.status==='Completed'?'完成':s.status==='Running'?'执行中':ready.has(s.id)?'已就绪':s.status==='Pending'?'等待依赖':s.status}</span>
    <strong>{s.title}</strong><small>{agentName(s.agent)}</small>
    <span className="dag-deps"><GitBranch size={12}/>{s.dependsOn?.length?`依赖 ${s.dependsOn.length} 个阶段`:'无依赖'}</span>
    {!!s.worktreePath&&<span className="dag-isolation">独立 Worktree</span>}
    {s.requiresApproval&&!s.approvalGranted&&<LockKeyhole size={13}/>}</button>)}
   {index<layers.length-1&&<ArrowRight className="dag-next" size={18}/>}</div>)}
  <div className="dag-disclaimer">连线按声明的阶段依赖投影；并发运行要求两个执行阶段各自拥有独立 Worktree。</div>
 </div>;
}
