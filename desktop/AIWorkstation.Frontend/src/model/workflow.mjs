/** Pure AIWS graph projection. No provider API calls, tokens or network access. */
export function graphLayers(task){
 if(!task?.graphMode)return [];
 const steps=task.steps||[];
 const byId=new Map(steps.map(s=>[s.id,s]));
 const depths=new Map();const visiting=new Set();
 function depth(id){if(depths.has(id))return depths.get(id);if(visiting.has(id))throw new Error('依赖存在环');
  const stage=byId.get(id);if(!stage)throw new Error('依赖不存在');visiting.add(id);
  const result=Math.max(0,...(stage.dependsOn||[]).map(dep=>depth(dep)+1));visiting.delete(id);depths.set(id,result);return result;}
 for(const stage of steps)depth(stage.id);
 const layers=[];for(const stage of steps){const pos=depths.get(stage.id);(layers[pos]??=[]).push(stage);}
 return layers;
}
export function readyStageIds(task){if(!task)return [];
 return (task.steps||[]).filter((s,index)=>s.status==='Pending'&&(
  task.graphMode?(s.dependsOn||[]).every(id=>task.steps.some(p=>p.id===id&&p.status==='Completed')):
    task.steps.slice(0,index).every(p=>p.status==='Completed'))).map(s=>s.id);
}

export function flowNodes(task) {
  if (!task) return [];
  const stages = Array.isArray(task.steps) ? task.steps : [];
  return [
    { id: 'entry', kind: 'entry', title: '任务输入', status: 'completed', label: '本地指令' },
    { id: 'router', kind: 'router', title: '模型路由', status: 'completed', label: '规则分配 · 不消耗 Token' },
    ...stages.map((s, index) => ({
      id: s.id, kind: 'agent', title: s.title, status: String(s.status || 'pending').toLowerCase(),
      label: agentName(s.agent), agent: String(s.agent || ''), index,
      measured: s.usage?.isMeasured === true || (s.usage?.input != null && s.usage?.output != null),
      tokens: (s.usage?.input || 0) + (s.usage?.output || 0),
      needsApproval: Boolean(s.requiresApproval && !s.approvalGranted),dependsOn:s.dependsOn||[],
    })),
    { id: 'output', kind: 'output', title: '结果交付', status: stages.every(s => String(s.status).toLowerCase() === 'completed') ? 'completed' : 'pending', label: '记录、日志与文件' },
  ];
}
export function agentName(kind) {
  const x = String(kind || '').toLowerCase();
  return x === 'claudecode' ? 'Claude Code' : x === 'codex' ? 'Codex CLI' : '人工确认';
}
export function sumMeasuredUsage(task) {
  const measured = (task?.steps || []).filter(s => s.usage && s.usage.input != null && s.usage.output != null);
  return { stages: measured.length, input: measured.reduce((n,s) => n + s.usage.input, 0), output: measured.reduce((n,s) => n + s.usage.output, 0), missing: (task?.steps || []).length - measured.length };
}
export function findDuplicates(task) {
  const seen = new Set(); const duplicates = [];
  for (const step of task?.steps || []) {
    const fingerprint = (step.lastPromptFingerprint || '').trim();
    if (fingerprint && seen.has(fingerprint)) duplicates.push(step.id);
    if (fingerprint) seen.add(fingerprint);
  }
  return duplicates;
}
