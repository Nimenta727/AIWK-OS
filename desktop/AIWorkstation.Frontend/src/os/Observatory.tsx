import {useCallback,useEffect,useRef,useState} from 'react';
import {Activity,AlertTriangle,Check,ChevronDown,ChevronRight,CircleDot,Send,ShieldCheck,X} from 'lucide-react';
import {agentBars,attentionFirst,basisText,budgetState,clock,formatTokens,lightTone,stateSegments} from '../model/observatory.mjs';

type Bilingual={zh:string;en:string};
type Totals={in:number|null;out:number|null;cacheRead:number|null;cacheWrite:number|null;knownSessions:number;unknownSessions:number;unverifiedSessions:number};
type SessionRow={session:string;agent:string;status:string;events:number;toolCalls:number;toolErrors:number;errors:number;unrecognizedEvents:number;
 tokens:{in:number|null;out:number|null;cacheRead:number|null;cacheWrite:number|null;basis:string;verified:boolean;unknownUsageEvents:number};costUsd:number|null;truncated:boolean};
type Waiting={taskId:string;stageKey:string;tool:string;label:string;taskTitle:string;ready:boolean};
type Failure={taskId:string;stageKey:string;tool:string;label:string;error:string};
type RecentTask={id:string;title:string;createdAt:number;stages:Record<string,number>};
type Summary={demo:boolean;
 status:{localModel:{configured:boolean;online:boolean;weightsPresent:boolean};builder:{state:string};router:{externalEnabled:boolean}};
 tokens:{total:Totals;byAgent:Record<string,Totals>;budget:{used:number|null;limit:number}|null};
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
 const headers={'Content-Type':'application/json','X-AIWS-CSRF':csrf};
 const timer=useRef<number|undefined>(undefined);
 const load=useCallback(async()=>{
  try{setSummary(await api<Summary>('/observatory'));setError('');}
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
    {tr('本地模型','Local model')}: {model?.online?tr('在线','online'):model?.configured?tr('未就绪','not ready'):tr('未启用','off')}</span>
   <span className="aiws-obs-chip off"><CircleDot size={13}/>{tr('构建通道','Builder')}: {tr('未配置','not configured')}</span>
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
     {budget.level==='none'?<p className="aiws-os-muted">{tr('预算：未设置（授权令牌上线后启用）','Budget: not set (arrives with the authorisation mandate)')}</p>:
      <><div className={'aiws-obs-meter '+budget.level}><i style={{width:Math.min(100,(budget.ratio||0)*100)+'%'}}/></div>
       <p className="aiws-os-muted">{formatTokens(s?.tokens.budget?.used)} / {formatTokens(s?.tokens.budget?.limit)}</p></>}
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
   <h2>{tr('需要你','Needs you')} <small>({(s?.tasks.needsApproval.length||0)+(s?.tasks.failures.length||0)})</small></h2>
   {!(s?.tasks.needsApproval.length||s?.tasks.failures.length)&&<p className="aiws-os-muted">{tr('现在没有需要你处理的事。','Nothing needs you right now.')}</p>}
   {s?.tasks.needsApproval.map(w=><div className="aiws-obs-row" key={w.taskId+w.stageKey}>
    <div><strong>{w.label}</strong><small>{w.tool} · {w.taskTitle}</small></div>
    {w.ready?<button type="button" className="aiws-os-primary" disabled={busy||!csrf} onClick={()=>void approveAndRun(w)}><Check size={15}/>{tr('批准并运行','Approve & run')}</button>:
     <span className="aiws-os-muted">{tr('等待前置步骤','Waiting for earlier steps')}</span>}</div>)}
   {s?.tasks.failures.map(f=><div className="aiws-obs-row fail" key={f.taskId+f.stageKey}>
    <div><strong>{f.label}</strong><small>{f.tool} · {f.error||tr('失败','failed')}</small></div>
    <button type="button" onClick={()=>onOpenAdvanced('plans')}>{tr('查看','Inspect')}</button></div>)}
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
