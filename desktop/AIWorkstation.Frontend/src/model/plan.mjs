/** Deterministic Markdown outline parser. Never sends a plan to an AI model. */
export function parsePlanMarkdown(markdown) {
  const lines=String(markdown||'').replace(/\r\n?/g,'\n').split('\n');
  const sections=[];
  let current=null, codeFence=null, done=0, tracked=0, untracked=0, clipped=false;
  const addSection=(title,level,line)=>{
    if(sections.length>=180){clipped=true;return;}
    current={id:`section-${line}`,title,level,line,items:[],notes:[]};sections.push(current);
  };
  for(let i=0;i<lines.length;i++){
    if(i>=5000){clipped=true;break;}
    const raw=lines[i];
    const fence=raw.trimStart().match(/^(`{3,}|~{3,})/);
    if(fence){
      if(!codeFence)codeFence=fence[1][0];
      else if(codeFence===fence[1][0])codeFence=null;
      continue;
    }
    if(codeFence)continue;
    const heading=raw.match(/^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
    if(heading){addSection(heading[2].trim().slice(0,180),heading[1].length,i+1);continue;}
    if(!raw.trim())continue;
    if(!current)addSection('概览',1,i+1);
    if(!current)continue;
    const check=raw.match(/^(\s*)(?:[-*+]\s+|\d+[.)]\s+)\[([xX ])\]\s+(.+)$/);
    const bullet=check?null:raw.match(/^(\s*)(?:[-*+]\s+|\d+[.)]\s+)(.+)$/);
    if(check||bullet){
      if(current.items.length>=300||sections.reduce((n,s)=>n+s.items.length,0)>=1000){clipped=true;continue;}
      const text=(check?check[3]:bullet[2]).trim().replace(/\s+$/,'').slice(0,400);
      if(!text)continue;
      const isTracked=Boolean(check),completed=Boolean(check&&check[2].toLowerCase()==='x');
      if(isTracked){tracked++;if(completed)done++;}else untracked++;
      current.items.push({id:`line-${i+1}`,line:i+1,text,tracked:isTracked,completed,indent:Math.min(5,Math.floor((check?check[1]:bullet[1]).replace(/\t/g,'  ').length/2))});
    } else if(raw.trim()&&current.notes.length<8){
      current.notes.push(raw.trim().slice(0,420));
    }
  }
  return {sections,tracked,done,pending:tracked-done,untracked,clipped,lines:Math.min(lines.length,5000),progress:tracked?Math.round(done/tracked*100):null};
}

export function summarizeWorkflowPlan(task){
  const steps=task?.steps||[];
  const completed=steps.filter(s=>s.status==='Completed').length;
  const running=steps.filter(s=>s.status==='Running').length;
  const interrupted=steps.filter(s=>s.status==='Failed'||s.status==='Interrupted').length;
  const statuses=steps.map((step,index)=>{
    const blocked=step.status==='Pending'&&(task?.graphMode
      ?(step.dependsOn||[]).some(id=>!steps.some(s=>s.id===id&&s.status==='Completed'))
      :steps.slice(0,index).some(s=>s.status!=='Completed'));
    const state=step.status==='Completed'?'done':step.status==='Running'?'running':interrupted&&step.status==='Interrupted'?'attention':step.status==='Failed'?'attention':blocked?'blocked':'ready';
    return {...step,state,index:index+1};
  });
  return {total:steps.length,completed,running,interrupted,pending:steps.length-completed-running-interrupted,progress:steps.length?Math.round(completed/steps.length*100):0,steps:statuses};
}

export function isNewerVersion(previous,next){return Boolean(next)&&previous!==next;}
