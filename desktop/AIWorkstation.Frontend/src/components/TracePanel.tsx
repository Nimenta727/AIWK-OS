import {Clock3, FileSearch, Gauge, ShieldCheck} from 'lucide-react';
import type {WorkTask} from '../bridge';
import {sumMeasuredUsage} from '../model/workflow.mjs';
export function TracePanel({task}:{task:WorkTask}){
  const totals=sumMeasuredUsage(task);
  return <div className="trace-content">
    <div className="kpi-grid"><div className="kpi"><span>已测输入</span><strong>{totals.input.toLocaleString()}</strong><small>来自导入的结构化日志</small></div><div className="kpi"><span>已测输出</span><strong>{totals.output.toLocaleString()}</strong><small>来自导入的结构化日志</small></div><div className="kpi"><span>未知用量阶段</span><strong>{totals.missing}</strong><small>未知 ≠ 0 Token</small></div></div>
    <div className="subheading"><span>请求与操作时间线</span><small>{task.requestEvents?.length||0} 条本地记录</small></div>
    <div className="trace-timeline">
    {(task.requestEvents||[]).length===0?<div className="empty-small"><FileSearch size={24}/> 尚无可观察事件。审批与 CLI 启动只产生本地记录；模型用量需要官方结构化日志。</div>:
      [...task.requestEvents].reverse().map((event,index)=><div className="trace-event" key={event.at+index}><span className="trace-marker"><Clock3 size={13}/></span><div><strong>{event.kind}</strong><small>{new Date(event.at).toLocaleString('zh-CN')}</small><p>{event.summary}</p></div></div>)}
    </div>
    <div className="trace-hint"><Gauge size={17}/><div><strong>减少重复 Token</strong><p>交接时只带最近两步结果；输入、输出、缓存用量仅在获得可信来源时呈现。平台没有监控或拦截外部 CLI 内部的全部请求。</p></div></div>
    <div className="trace-hint"><ShieldCheck size={17}/><div><strong>数据边界</strong><p>不保存 Claude / ChatGPT 登录凭据，不自动访问其会话目录，不把启动进程记为模型调用。</p></div></div>
  </div>;
}
