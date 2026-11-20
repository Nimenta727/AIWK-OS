import { Activity, ArrowDown, Check, CircleDashed, GitMerge, LockKeyhole, RadioTower, Route, TerminalSquare } from 'lucide-react';
import type { WorkTask } from '../bridge';
import {flowNodes, findDuplicates} from '../model/workflow.mjs';
import {T3StatusDot} from './T3StatusDot';

export function WorkflowCanvas({task,selected,onPick}:{task:WorkTask;selected:string|null;onPick:(id:string)=>void}){
  const nodes=flowNodes(task);
  const duplicateIds=new Set(findDuplicates(task));
  return <div className="flow-scroll">
    <div className="flow-legend"><span><i className="legend-dot success"/> 已完成</span><span><i className="legend-dot running"/> 执行中</span><span><i className="legend-dot waiting"/> 待批准</span><span><i className="legend-dot neutral"/> 待启动</span></div>
    <div className="flow-rail">
      {nodes.map((node,index)=><div className="flow-row" key={node.id}>
        <button type="button" onClick={()=>onPick(node.id)} className={`flow-node ${node.kind} ${selected===node.id?'selected':''} ${node.status==='completed'?'finished':''}`} aria-label={`查看节点 ${node.title}`}>
          <span className={`flow-icon ${node.kind}`}>
            {node.kind==='entry'?<RadioTower size={18}/>:node.kind==='router'?<Route size={18}/>:node.kind==='output'?<GitMerge size={18}/>:node.agent==='Codex'?<TerminalSquare size={18}/>:<Activity size={18}/>}</span>
          <span className="flow-node-text"><strong>{node.title}</strong><small>{node.label}</small></span>
          {node.kind==='agent' && <span className="node-meta">{node.measured?node.tokens.toLocaleString()+' tokens':'用量未知'}</span>}
          {node.needsApproval&&<LockKeyhole size={15} className="node-lock"/>}
          {duplicateIds.has(node.id)&&<span className="duplicate-label">重复上下文</span>}
          <T3StatusDot phase={node.status==='completed'?'connected':node.status==='running'?'connecting':node.status==='failed'?'error':'unknown'} label={node.status}/>
        </button>
        {index<nodes.length-1&&<div className="flow-connector"><span className="connector-line"/><ArrowDown size={14}/></div>}
      </div>)}
    </div>
    <div className="flow-footer"><CircleDashed size={14}/> 连线代表 AIWS 的计划和已记录状态，不等于已经发生模型请求。<Check size={14}/> 点击节点查看数据证据。</div>
  </div>;
}
