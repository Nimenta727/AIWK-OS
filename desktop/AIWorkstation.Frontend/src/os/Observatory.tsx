import {useCallback,useEffect,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {Activity,AlertTriangle,Check,ChevronDown,ChevronRight,CircleDot,Send,ShieldCheck,X} from 'lucide-react';
import {agentBars,attentionFirst,basisText,budgetState,clock,formatTokens,lightTone,stateSegments} from '../model/observatory.mjs';

type Bilingual={zh:string;en:string};
type Totals={in:number|null;out:number|null;cacheRead:number|null;cacheWrite:number|null;knownSessions:number;unknownSessions:number;unverifiedSessions:number};
type SessionRow={session:string;agent:string;status:string;events:number;toolCalls:number;toolErrors:number;errors:number;unrecognizedEvents:number;
 tokens:{in:number|null;out:number|null;cacheRead:number|null;cacheWrite:number|null;basis:string;verified:boolean;unknownUsageEvents:number};costUsd:number|null;truncated:boolean};
type Waiting={taskId:string;stageKey:string;tool:string;label:string;taskTitle:string;ready:boolean};
type Failure={taskId:string;stageKey:string;tool:string;label:string;error:string};
type RecentTask={id:string;title:string;createdAt:number;stages:Record<string,number>};
type Budget={mandateId:string;used:number;limit:number;input:{used:number;limit:number};output:{used:number;limit:number}};
type RunApproval={runId:string;category:string;tool:string;detail:string};
type Mandate={id:string;provider:string;projectDir:string;allowedTools:string[];tokenBudget:{input:number;output:number};used:{input:number;output:number};state:string;wallClockMinutes:number;maxTurns:number};
type BuilderInfo={enabled:boolean;providers:Record<string,{installed:boolean}>;mandates:Mandate[];status:{isolation?:{mode:string;user:string};active:{runId:string;state:string;turns:number;usedInput:number;usedOutput:number}|null}};
type Summary={demo:boolean;runApprovals:RunApproval[];
 status:{localModel:{configured:boolean;online:boolean;weightsPresent:boolean;gate?:{loaded:boolean;rssMiB?:number}|null};builder:{state:string;enabled?:boolean;runId?:string|null;turns?:number};router:{externalEnabled:boolean}};
 tokens:{total:Totals;byAgent:Record<string,Totals>;budget:Budget|null};
 tasks:{tasks:number;stages:Record<string,number>;needsApproval:Waiting[];failures:Failure[];recent:RecentTask[]};
 sessions:SessionRow[];recent:Array<{ts:number;source:string;label:string;status:string}>;
 verdict:{level:string;sentences:Bilingual[]};audit:{valid:boolean;events:number}};
type EventRow={seq:number;ts:number;kind:string;tool?:string;status?:string;detail?:string;tokens?:{in:number|null;out:number|null;source:string;scope:string}};

async function api<T>(url:string,options?:RequestInit):Promise<T>{
 const response=await fetch('/api/v1'+url,{cache:'no-store',credentials:'omit',...options});
 const data=await response.json() as T&{error?:string};
 if(!response.ok)throw new Error(data.error||'Guest service request failed');
 return data;
}

export default function Observatory({csrf,english,onOpenAdvanced,onCommand}:{
 csrf:string;english:boolean;onOpenAdvanced:(page:'files'|'plans'|'tasks'|'local'|'system')=>void;onCommand:(text:string)=>boolean
}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const [summary,setSummary]=useState<Summary|null>(null);
 const [error,setError]=useState('');
 const [open,setOpen]=useState<string|null>(null);
 const [events,setEvents]=useState<EventRow[]>([]);
 const [showAll,setShowAll]=useState(false);
 const [text,setText]=useState('');
 const [reply,setReply]=useState<string>('');
 const [busy,setBusy]=useState(false);
 const [builder,setBuilder]=useState<BuilderInfo|null>(null);
 const [form,setForm]=useState({provider:'claude',projectDir:'',prompt:'',inputK:'200',outputK:'60',minutes:'30',turns:'30',tools:'Read,Edit,Write,Bash(npm test)',
  del:true,install:true,push:true});
 const [formOpen,setFormOpen]=useState(false);
 const [inboxAll,setInboxAll]=useState(false);
 const headers={'Content-Type':'application/json','X-AIWS-CSRF':csrf};
 const timer=useRef<number|undefined>(undefined);
 const load=useCallback(async()=>{
  try{const [a,b]=await Promise.all([api<Summary>('/observatory'),api<BuilderInfo>('/builder')]);setSummary(a);setBuilder(b);setError('');}
  catch(e){setError(String(e instanceof Error?e.message:e));}
 },[]);
 // Resource-saving: poll only while the tab is visible; refresh immediately when it becomes visible again.
 useEffect(()=>{
  const start=()=>{window.clearInterval(timer.current);timer.current=window.setInterval(()=>{if(!document.hidden)void load();},5000);};
  const onVisible=()=>{if(!document.hidden)void load();};
  void load();start();document.addEventListener('visibilitychange',onVisible);
  return()=>{window.clearInterval(timer.current);document.removeEventListener('visibilitychange',onVisible);};
 },[load]);
 const openSession=async(id:string)=>{
  if(open===id){setOpen(null);return;}
  setOpen(id);setEvents([]);
  try{setEvents((await api<{events:EventRow[]}>('/observatory/events?session='+encodeURIComponent(id))).events);}
  catch(e){setError(String(e instanceof Error?e.message:e));}
 };
 const approveAndRun=async(w:Waiting)=>{
  if(busy||!csrf||!w.ready)return;
  setBusy(true);setError('');
  try{
   const base='/tasks/'+w.taskId+'/stages/'+w.stageKey+'/';
   await api(base+'approve',{method:'POST',headers,body:'{}'});
   await api(base+'dispatch',{method:'POST',headers,body:'{}'});
   await new Promise(r=>setTimeout(r,400));await load();
  }catch(e){setError(String(e instanceof Error?e.message:e));}
  finally{setBusy(false);}
 };
 const decide=async(runId:string,action:'approve'|'deny')=>{
  if(busy||!csrf)return;
  setBusy(true);setError('');
  try{await api('/builder/runs/'+runId+'/'+action,{method:'POST',headers,body:'{}'});await new Promise(r=>setTimeout(r,300));await load();}
  catch(e){setError(String(e instanceof Error?e.message:e));}
  finally{setBusy(false);}
 };
 const stopRun=async(runId:string)=>{
  if(busy||!csrf)return;
  setBusy(true);
  try{await api('/builder/runs/'+runId+'/stop',{method:'POST',headers,body:'{}'});await new Promise(r=>setTimeout(r,500));await load();}
  catch(e){setError(String(e instanceof Error?e.message:e));}
  finally{setBusy(false);}
 };
 const revoke=async(id:string)=>{
  if(busy||!csrf)return;
  try{await api('/builder/mandates/'+id+'/revoke',{method:'POST',headers,body:'{}'});await load();}
  catch(e){setError(String(e instanceof Error?e.message:e));}
 };
 const grantAndStart=async()=>{
  if(busy||!csrf||!form.prompt.trim()||!form.projectDir.trim())return;
  setBusy(true);setError('');
  try{
   const approvals=['network','shell','outside-project',...(form.del?['delete']:[]),...(form.install?['install-dependency']:[]),...(form.push?['git-push']:[])];
   const m=await api<{id:string}>('/builder/mandates',{method:'POST',headers,body:JSON.stringify({
    provider:form.provider,projectDir:form.projectDir.trim(),allowedTools:form.tools.split(',').map(x=>x.trim()).filter(Boolean),
    permissionMode:'default',maxTurns:Number(form.turns),wallClockMinutes:Number(form.minutes),
    tokenBudget:{input:Number(form.inputK)*1000,output:Number(form.outputK)*1000},needApprovalFor:approvals})});
   await api('/builder/runs',{method:'POST',headers,body:JSON.stringify({mandateId:m.id,prompt:form.prompt})});
   setFormOpen(false);setForm(f=>({...f,prompt:''}));await load();
  }catch(e){setError(String(e instanceof Error?e.message:e));}
  finally{setBusy(false);}
 };
 const send=async()=>{
  const value=text.trim();
  if(!value||busy||!csrf)return;
  if(onCommand(value)){setText('');return;}       // exact file commands never cost a model call
  setBusy(true);setError('');setReply('');
  try{
   const out=await api<Record<string,unknown>>('/model/plan',{method:'POST',headers,body:JSON.stringify({instruction:value})});
   const dec=out.decision as {reason?:Bilingual}|undefined;
   const follow=out.followUp as {reason?:Bilingual}|undefined;
   if(out.refused){
    const p=out.proposal as {reason:string};
    setReply(tr('已拒绝（最终结论，不会转交其他模型）：','Refused (final, never forwarded): ')+p.reason);
   }else if(out.routed){
    const why=dec?.reason?(english?dec.reason.en:dec.reason.zh):'';
    const more=follow?.reason?(english?follow.reason.en:follow.reason.zh):'';
    setReply([why,more,out.error as string|undefined].filter(Boolean).join(' '));
   }else{
    setReply(tr('已创建任务。需要你批准的步骤会出现在上方“需要你”。','Task created. Steps that need your approval appear under "Needs you".'));
   }
   setText('');await load();
  }catch(e){setError(String(e instanceof Error?e.message:e));}
  finally{setBusy(false);}
 };

 const inboxItems:ReactNode[]=[
  ...(summary?.runApprovals||[]).map(a=><div className="aiws-obs-row" key={'run'+a.runId} data-aiws="run-approval">
   <div><strong>{tr('构建任务想要执行敏感操作：','The build wants a sensitive action: ')}{a.category}</strong><small>{a.tool} · {a.detail}</small>
    <small>{tr('构建已暂停。注意：操作可能在被发现前已经开始，批准只是让它继续。','The build is paused. The action may have started before it was noticed; approving lets it continue.')}</small></div>
   <span><button type="button" className="aiws-os-primary" disabled={busy||!csrf} onClick={()=>void decide(a.runId,'approve')}><Check size={15}/>{tr('批准继续','Approve')}</button>
    <button type="button" disabled={busy||!csrf} onClick={()=>void decide(a.runId,'deny')}><X size={15}/>{tr('拒绝并终止','Deny & stop')}</button></span></div>),
  ...(summary?.tasks.needsApproval||[]).map(w=><div className="aiws-obs-row" key={w.taskId+w.stageKey}>
   <div><strong>{w.label}</strong><small>{w.tool} · {w.taskTitle}</small></div>
   {w.ready?<button type="button" className="aiws-os-primary" disabled={busy||!csrf} onClick={()=>void approveAndRun(w)}><Check size={15}/>{tr('批准并运行','Approve & run')}</button>:
    <span className="aiws-os-muted">{tr('等待前置步骤','Waiting for earlier steps')}</span>}</div>),
  ...(summary?.tasks.failures||[]).map(f=><div className="aiws-obs-row fail" key={'f'+f.taskId+f.stageKey}>
   <div><strong>{f.label}</strong><small>{f.tool} · {f.error||tr('失败','failed')}</small></div>
   <button type="button" onClick={()=>onOpenAdvanced('plans')}>{tr('查看','Inspect')}</button></div>)
 ];
 const s=summary;
 const tone=s?lightTone(s.verdict.level):'green';
 const tasks=attentionFirst(s?.tasks.recent,5);
 const segs=stateSegments(s?.tasks.stages);
 const bars=agentBars(s?.tokens.byAgent);
 const budget=s?.tokens.budget?budgetState(s.tokens.budget.used,s.tokens.budget.limit):{level:'none',ratio:null};
 const total=s?.tokens.total;
 const model=s?.status.localModel;
 return <div className="aiws-obs" data-aiws="observatory">
  {s?.demo&&<div className="aiws-os-error" role="status">{tr('显示的是示例数据（合成样本回放），不是真实运行。','Showing demo data (synthetic replay), not a real run.')}</div>}
  {error&&<div className="aiws-os-error" role="alert"><AlertTriangle size={16}/> {error}</div>}

  <section className="aiws-obs-strip" aria-label={tr('状态','Status')}>
   <span className={'aiws-obs-chip '+(model?.online?'ok':model?.configured?'warn':'off')}><CircleDot size={13}/>
    {tr('本地模型','Local model')}: {model?.online?tr('在线','online'):model?.configured?tr('未就绪','not ready'):tr('未启用','off')}
    {model?.online&&model.gate&&(model.gate.loaded?' · '+tr('已加载','loaded')+(model.gate.rssMiB?' '+(model.gate.rssMiB>=1024?(model.gate.rssMiB/1024).toFixed(1)+'G':Math.round(model.gate.rssMiB)+'M'):''):' · '+tr('空闲，已卸载','idle, unloaded'))}</span>
   <span className={'aiws-obs-chip '+(s?.status.builder.state==='running'?'ok':s?.status.builder.state==='awaiting-approval'?'warn':'off')} data-aiws="builder-chip"><CircleDot size={13}/>
    {tr('构建通道','Builder')}: {({disabled:tr('未启用','off'),idle:tr('空闲','idle'),running:tr('运行中','running'),'awaiting-approval':tr('等待批准','awaiting approval')} as Record<string,string>)[s?.status.builder.state||'disabled']||s?.status.builder.state}</span>
   <span className={'aiws-obs-chip '+(s?.status.router.externalEnabled?'warn':'ok')}><CircleDot size={13}/>
    {tr('外部模型','External')}: {s?.status.router.externalEnabled?tr('已启用（需你确认）','enabled (needs consent)'):tr('关闭','off')}</span>
   <span className={'aiws-obs-chip light '+tone} data-aiws="audit-light"><ShieldCheck size={13}/>{tr('审计','Audit')}: {tone==='red'?tr('异常','problem'):tone==='yellow'?tr('需注意','attention'):tr('正常','ok')}</span>
  </section>

  <div className="aiws-obs-grid">
   <section className="aiws-os-card" data-aiws="tokens">
    <h2>{tr('Token 用量','Token usage')}</h2>
    <div className="aiws-obs-big"><span>{tr('输入','in')} <strong>{formatTokens(total?.in)}</strong></span>
     <span>{tr('输出','out')} <strong>{formatTokens(total?.out)}</strong></span>
     <span>{tr('缓存读','cache read')} <strong>{formatTokens(total?.cacheRead)}</strong></span></div>
    <p className="aiws-os-muted">{tr('只统计提供方上报的数字，不估算。','Only provider-reported numbers; nothing is estimated.')}
     {total&&total.unknownSessions>0&&' '+tr('用量未知的会话：','Sessions with unknown usage: ')+total.unknownSessions+'.'}
     {total&&total.unverifiedSessions>0&&' '+tr('语义未验证：','Unverified semantics: ')+total.unverifiedSessions+'.'}</p>
    {bars.map(b=><div className="aiws-obs-bar" key={b.agent}><span>{b.agent}</span>
     <div><i style={{width:b.pct+'%'}}/></div><em>{formatTokens(b.total)}</em></div>)}
    <div className="aiws-obs-budget" data-aiws="budget">
     {budget.level==='none'?<p className="aiws-os-muted">{tr('预算：尚无授权（在下方“构建”里授权后显示）','Budget: no mandate yet (grant one under "Build" below)')}</p>:
      <><div className={'aiws-obs-meter '+budget.level}><i style={{width:Math.min(100,(budget.ratio||0)*100)+'%'}}/></div>
       <p className="aiws-os-muted">{formatTokens(s?.tokens.budget?.used)} / {formatTokens(s?.tokens.budget?.limit)} {tr('（输入+输出，已授权总预算）','(input+output, granted total)')}</p></>}
    </div>
   </section>

   <section className="aiws-os-card" data-aiws="tasks">
    <h2>{tr('任务','Tasks')} <small>({s?.tasks.tasks??0})</small></h2>
    {segs.length?<div className="aiws-obs-stack" role="img" aria-label={segs.map(x=>x.state+' '+x.count).join(', ')}>
     {segs.map(x=><i key={x.state} className={'seg '+x.state} style={{width:x.pct+'%'}} title={x.state+': '+x.count}/>)}</div>:
     <p className="aiws-os-muted">{tr('还没有任务。','No tasks yet.')}</p>}
    <p className="aiws-os-muted">{segs.map(x=>x.state+' '+x.count).join(' · ')}</p>
    {(showAll?[...tasks.shown,...(s?.tasks.recent||[]).filter(t=>!tasks.shown.includes(t))]:tasks.shown).map(t=>
     <div className="aiws-obs-task" key={t.id}><span>{t.title}</span>
      <em>{Object.entries(t.stages).map(([k,v])=>k+' '+v).join(' · ')}</em></div>)}
    {tasks.hidden>0&&<button type="button" className="aiws-obs-link" onClick={()=>setShowAll(v=>!v)}>
     {showAll?tr('收起','Collapse'):tr('展开全部','Show all')+' ('+tasks.hidden+')'}</button>}
   </section>
  </div>

  <section className="aiws-os-card" data-aiws="inbox">
   <h2>{tr('需要你','Needs you')} <small>({inboxItems.length})</small></h2>
   {!inboxItems.length&&<p className="aiws-os-muted">{tr('现在没有需要你处理的事。','Nothing needs you right now.')}</p>}
   <div className="aiws-obs-rows">{inboxItems.slice(0,inboxAll?inboxItems.length:6)}</div>
   {inboxItems.length>6&&<button type="button" className="aiws-obs-link" onClick={()=>setInboxAll(v=>!v)}>
    {inboxAll?tr('收起','Collapse'):tr('展开全部','Show all')+' ('+(inboxItems.length-6)+')'}</button>}
  </section>

  <section className={'aiws-os-card'+(formOpen?' wide':'')} data-aiws="builder">
   <h2>{tr('构建','Build')} <small>{tr('（官方 CLI，在你的授权范围内工作）','(official CLI, inside your mandate)')}</small></h2>
   {!builder?.enabled?<p className="aiws-os-muted">{tr('构建通道默认关闭。要启用，请在 ~/.config/aiws/builder.json 写入 {"enabled": true}。注意：默认不隔离，CLI 以当前客户机用户的权限运行；要使用专用用户与域名白名单网络，请在镜像里完成 O4 配置并在 builder.json 设置 isolation.mode。',
     'The builder is off by default. Enable it with {"enabled": true} in ~/.config/aiws/builder.json. By default there is no isolation and the CLI runs with this guest user\'s privileges; for the dedicated user and domain-allowlisted network, finish the O4 setup in the image and set isolation.mode in builder.json.')}</p>:<>
    <p className={'aiws-obs-iso '+(builder.status.isolation?.mode==='user'?'ok':'warn')} data-aiws="isolation">{builder.status.isolation?.mode==='user'?
     tr('隔离：专用用户 ','Isolation: dedicated user ')+builder.status.isolation.user+tr('，只能经域名白名单代理联网','; network only through the domain-allowlist proxy'):
     tr('隔离：无——CLI 以当前用户权限运行（在 builder.json 设置 isolation.mode="user" 启用专用用户隔离）','Isolation: none: the CLI runs with your own privileges (set isolation.mode="user" in builder.json)')}</p>
    <p className="aiws-os-muted">{Object.entries(builder.providers).map(([k,v])=>k+': '+(v.installed?tr('已安装','installed'):tr('本机未安装','not installed'))).join(' · ')}
     {' · '}{tr('有效授权','active mandates')}: {builder.mandates.length}</p>
    {builder.status.active?<div className="aiws-obs-row"><div><strong>{tr('正在构建','Building')} · {builder.status.active.state}</strong>
      <small>{tr('轮次','turns')} {builder.status.active.turns} · {tr('已用','used')} {formatTokens(builder.status.active.usedInput)}/{formatTokens(builder.status.active.usedOutput)}</small></div>
      <button type="button" disabled={busy||!csrf} onClick={()=>void stopRun(builder.status.active!.runId)}><X size={15}/>{tr('停止','Stop')}</button></div>:
     <button type="button" className="aiws-obs-link" onClick={()=>setFormOpen(v=>!v)}>{formOpen?tr('收起','Close'):tr('授权并开始构建…','Grant a mandate and start a build…')}</button>}
    {formOpen&&!builder.status.active&&<div className="aiws-obs-form">
     <label>{tr('云端模型（官方 CLI）','Provider (official CLI)')}<select value={form.provider} onChange={e=>setForm({...form,provider:e.target.value})}>
      {Object.entries(builder.providers).map(([k,v])=><option key={k} value={k}>{k}{v.installed?'':tr('（本机未安装）',' (not installed)')}</option>)}</select></label>
     <label>{tr('项目文件夹（工作区内的子文件夹）','Project folder (a sub-folder of the workspace)')}<input value={form.projectDir} onChange={e=>setForm({...form,projectDir:e.target.value})} placeholder="app"/></label>
     <label>{tr('要构建什么','What to build')}<textarea rows={3} maxLength={4000} value={form.prompt} onChange={e=>setForm({...form,prompt:e.target.value})}/></label>
     <div className="aiws-obs-form-grid">
      <label>{tr('输入预算 (k token)','Input budget (k)')}<input value={form.inputK} onChange={e=>setForm({...form,inputK:e.target.value})}/></label>
      <label>{tr('输出预算 (k token)','Output budget (k)')}<input value={form.outputK} onChange={e=>setForm({...form,outputK:e.target.value})}/></label>
      <label>{tr('最长时间 (分钟)','Max minutes')}<input value={form.minutes} onChange={e=>setForm({...form,minutes:e.target.value})}/></label>
      <label>{tr('最多轮次','Max turns')}<input value={form.turns} onChange={e=>setForm({...form,turns:e.target.value})}/></label></div>
     <label>{tr('允许的工具（逗号分隔；不能授予不受限的 Bash）','Allowed tools (comma separated; unrestricted Bash can never be granted)')}<input value={form.tools} onChange={e=>setForm({...form,tools:e.target.value})}/></label>
     <p className="aiws-os-muted">{tr('下列操作发生时暂停并问你：','Pause and ask me before:')}
      <label className="aiws-obs-check"><input type="checkbox" checked={form.del} onChange={e=>setForm({...form,del:e.target.checked})}/>{tr('删除','delete')}</label>
      <label className="aiws-obs-check"><input type="checkbox" checked={form.install} onChange={e=>setForm({...form,install:e.target.checked})}/>{tr('安装依赖','install dependencies')}</label>
      <label className="aiws-obs-check"><input type="checkbox" checked={form.push} onChange={e=>setForm({...form,push:e.target.checked})}/>git push</label><br/>
      {tr('联网、shell、越出项目文件夹：始终需要批准，无法关闭。','Network, shell and leaving the project folder always need approval and cannot be switched off.')}</p>
     <button type="button" className="aiws-os-primary" disabled={busy||!csrf||!form.prompt.trim()||!form.projectDir.trim()} onClick={()=>void grantAndStart()}>
      {tr('授权并开始','Grant and start')}</button></div>}
    {builder.mandates.length>3&&<p className="aiws-os-muted">{tr('仅显示最近 3 个授权，另有 ','Showing the 3 newest mandates; ')}{builder.mandates.length-3}{tr(' 个。',' more.')}</p>}
    {builder.mandates.slice(0,3).map(m=><div className="aiws-obs-task" key={m.id}><span>{m.provider} · {m.projectDir} · {formatTokens(m.used.input+m.used.output)}/{formatTokens(m.tokenBudget.input+m.tokenBudget.output)}</span>
     <button type="button" className="aiws-obs-link" onClick={()=>void revoke(m.id)}>{tr('撤销授权','Revoke')}</button></div>)}</>}
  </section>

  <section className="aiws-os-card" data-aiws="verdict">
   <h2><ShieldCheck size={16}/> {tr('审计结论','Audit verdict')}</h2>
   <div className={'aiws-obs-verdict '+tone}><i/>{s?.verdict.sentences.map((x,i)=><p key={i}>{english?x.en:x.zh}</p>)}</div>
   <button type="button" className="aiws-obs-link" onClick={()=>onOpenAdvanced('plans')}>{tr('查看审计详情（高级）','Open audit details (advanced)')}</button>
  </section>

  <section className="aiws-os-card" data-aiws="activity">
   <h2><Activity size={16}/> {tr('正在发生','Activity')}</h2>
   {s?.recent.length?<ul className="aiws-obs-feed">{s.recent.map((r,i)=><li key={i} className={r.status==='error'?'fail':''}>
    <time>{clock(r.ts)}</time><b>{r.source}</b><span>{r.label}</span></li>)}</ul>:<p className="aiws-os-muted">{tr('暂无活动。','No activity yet.')}</p>}
  </section>

  <section className="aiws-os-card" data-aiws="sessions">
   <h2>{tr('会话','Sessions')} <small>{tr('（点开才看事件详情）','(open one for event details)')}</small></h2>
   {!s?.sessions.length&&<p className="aiws-os-muted">{tr('还没有会话记录。','No sessions recorded yet.')}</p>}
   {s?.sessions.map(x=><div key={x.session}>
    <button type="button" className="aiws-obs-session" onClick={()=>void openSession(x.session)}>
     {open===x.session?<ChevronDown size={14}/>:<ChevronRight size={14}/>}
     <b>{x.agent}</b><span>{x.session}</span><em>{x.status}</em>
     <small>{formatTokens(x.tokens.in)}/{formatTokens(x.tokens.out)} · {basisText(x.tokens,english)}</small></button>
    {open===x.session&&<table className="aiws-obs-events"><tbody>{events.map(e=><tr key={e.seq}>
     <td>{clock(e.ts)}</td><td>{e.kind}</td><td>{e.tool||''}</td><td>{e.status||''}</td>
     <td>{e.tokens?(e.tokens.source==='unknown'?tr('用量未知','usage unknown'):formatTokens(e.tokens.in)+'/'+formatTokens(e.tokens.out)+' '+e.tokens.scope):(e.detail||'')}</td></tr>)}
     {!events.length&&<tr><td>{tr('没有事件','No events')}</td></tr>}</tbody></table>}</div>)}
  </section>

  <form className="aiws-obs-input" onSubmit={e=>{e.preventDefault();void send();}}>
   {reply&&<p className="aiws-obs-reply" role="status">{reply}<button type="button" aria-label={tr('关闭','Close')} onClick={()=>setReply('')}><X size={13}/></button></p>}
   <div><input value={text} onChange={e=>setText(e.target.value)} disabled={busy} maxLength={1000} spellCheck={false}
     aria-label={tr('用自然语言告诉我要做什么','Tell me what to do in plain language')}
     placeholder={tr('用自然语言说你要做什么，例如：整理一下下载文件夹','Say what you want, e.g. tidy my downloads folder')}/>
    <button type="submit" className="aiws-os-primary" disabled={busy||!csrf||!text.trim()}><Send size={15}/>{tr('发送','Send')}</button></div>
  </form>
 </div>;
}
