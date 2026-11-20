/** Pure local projections: do not invoke the host bridge or any model. */
export function missionTotals(task){
 const steps=task?.steps||[];
 return {total:steps.length,done:steps.filter(x=>x.status==='Completed').length,
  running:steps.filter(x=>x.status==='Running').length,
  attention:steps.filter(x=>x.status==='Failed'||x.status==='Interrupted').length,
  plans:task?.unified?.plans?.length||0,
  unknownUsage:steps.filter(x=>x.agent!=='Manual'&&!(x.usage?.isMeasured||
   (x.usage?.input!=null&&x.usage?.output!=null))).length};
}
export function dispatchLabel(code){
 const labels={ready:'可排队',queued:'等待人工启动',approval:'待审批',waiting:'依赖未满足',
  capacity:'并行容量已满',isolation:'工作区隔离限制',unavailable:'执行器不可用',
  budget:'预算阻止',running:'正在执行',completed:'已完成',failed:'失败待处理',interrupted:'中断待核查'};
 return labels[code]||'未知状态';
}
export function nextAction(plan){
 const steps=plan?.stages||[];
 return steps.find(x=>x.status==='queued')||steps.find(x=>x.status==='ready')||
  steps.find(x=>x.status==='approval')||null;
}
