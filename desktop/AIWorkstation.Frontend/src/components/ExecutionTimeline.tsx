import {useEffect,useState} from 'react';
import {bridge,type ExecutionRecord,type WorkTask} from '../bridge';
import {Activity,ShieldCheck} from 'lucide-react';
export function ExecutionTimeline({task}:{task:WorkTask|null}){
 const [rows,setRows]=useState<ExecutionRecord[]>([]),[error,setError]=useState('');
 useEffect(()=>{setRows([]);if(task)void bridge.call<ExecutionRecord[]>('ledger.timeline',{taskId:task.id}).then(setRows).catch(e=>setError(String(e)));},[task]);
 return <div className="ledger-panel"><div className="page-heading"><div><div className="eyebrow">EXECUTION EVIDENCE</div><h1>统一执行事件账本</h1><p>按真实的本地操作顺序排列，模型内部请求未被观察时不做推断。</p></div></div>
 {error&&<div className="tool-error">{error}</div>}{!task?<div className="blank-state">选择任务查看事件证据。</div>:
 <div className="ledger-list">{rows.map(e=><div className="ledger-entry" key={e.id}><Activity size={15}/><div><strong>{e.kind}</strong><small>{e.stageId?`阶段 ${e.stageId.slice(0,8)} · `:''}{e.metadata||e.evidence}</small></div><time>{new Date(e.at).toLocaleString()}</time><span className="pill">{e.evidence}</span></div>)}{rows.length===0&&<div className="blank-state"><ShieldCheck size={20}/>此任务还没有新格式事件。</div>}</div>}</div>;
}
