import {useState} from 'react';
import {Button,Empty,Icon,Input,Notice,Progress,Row,Section} from '../ui/kit';
import {agentBars,basisText,budgetState,formatTokens,lightTone} from '../model/observatory.mjs';
import {ActivityTimeline} from '../os/Timeline';
import {api} from '../os/api';
import {msg,useAction} from './common';
import type {Tr} from './common';
import type {ObservatoryData} from '../os/useObservatoryData';
import type {Bilingual,Waiting} from '../os/observatoryTypes';

/** The home page answers four questions in order: does anything need me? what is running? what did it cost? can I trust it? */
export default function Home({english,tr,data,onCommand,onOpen}:{english:boolean;tr:Tr;data:ObservatoryData;onCommand:(text:string)=>boolean;onOpen:(view:string,focus?:string)=>void}){
 const {summary:s,builder,reload}=data;
 const act=useAction(reload);
 const [text,setText]=useState('');
 const [reply,setReply]=useState('');
 const [sending,setSending]=useState(false);
 const [err,setErr]=useState('');
 const approveAndRun=async(w:Waiting)=>{const base='/tasks/'+w.taskId+'/stages/'+w.stageKey+'/';if(await act.post(base+'approve')) await act.post(base+'dispatch');};
 const send=async()=>{
  const value=text.trim();if(!value||sending)return;
  if(onCommand(value)){setText('');return;}
  setSending(true);setErr('');setReply('');
  try{
   const out=await api<Record<string,unknown>>('/model/plan',{method:'POST',body:JSON.stringify({instruction:value})});
   const dec=out.decision as {reason?:Bilingual}|undefined;const follow=out.followUp as {reason?:Bilingual}|undefined;
   if(out.refused)setReply(tr('已拒绝（最终结论，不会转交其他模型）：','Refused (final, never forwarded): ')+(out.proposal as {reason:string}).reason);
   else if(out.routed)setReply([dec?.reason?(english?dec.reason.en:dec.reason.zh):'',follow?.reason?(english?follow.reason.en:follow.reason.zh):'',out.error as string|undefined].filter(Boolean).join(' '));
   else{setReply(tr('已创建任务，去“计划”里审核。','Task created: review it under Plans.'));onOpen('plans');}
   setText('');await reload();
  }catch(e){setErr(msg(e));}finally{setSending(false);}
 };
 const needs=(s?.runApprovals.length||0)+(s?.tasks.needsApproval.length||0)+(s?.tasks.failures.length||0);
 const tone=s?lightTone(s.verdict.level):'green';
 const model=s?.status.localModel;
 const total=s?.tokens.total;
 const budget=s?.tokens.budget?budgetState(s.tokens.budget.used,s.tokens.budget.limit):{level:'none',ratio:null};
 const bars=agentBars(s?.tokens.byAgent);
 return <div className="home selectable">
  {s?.demo&&<Notice tone="warn">{tr('显示的是示例数据（合成样本回放），不是真实运行。','Showing demo data (synthetic replay), not a real run.')}</Notice>}
  {(act.error||data.error||err)&&<Notice tone="err">{act.error||err||data.error}</Notice>}

  <Section title={tr('需要你','Needs you')} count={needs}>
   {needs===0&&<p className="muted pad">{tr('现在没有需要你处理的事。','Nothing needs you right now.')}</p>}
   {(s?.runApprovals||[]).map(a=>{
    const label:Record<string,string>={plan:tr('提交了一份计划，等你批准','submitted a plan and waits for your approval'),delete:tr('想要删除文件','wants to delete a file'),write:tr('想要写入文件','wants to write a file')};
    const ends=a.terminates!==false;
    return <div className="inbox" key={a.runId}>
    <div><strong><Icon name="warning"/> {tr('构建','The build')} {label[a.category]||tr('想要执行敏感操作：','wants a sensitive action: ')+a.category}</strong><div className="muted">{a.tool} · {a.detail}</div>
     <div className="muted">{ends?tr('构建已暂停。操作可能在被发现前已经开始；批准只是让它继续。','Paused. The action may have started before it was noticed; approving lets it continue.'):tr('构建正在等你回答，批准之前这一步不会执行。拒绝只会拒绝这一步，运行会继续。','The build is waiting for your answer; this step does not run before you approve. Denying refuses only this step and the run continues.')}</div></div>
    <div className="btns"><Button variant="primary" icon="check" disabled={act.busy} onClick={()=>void act.post('/builder/runs/'+a.runId+'/approve')}>{tr('批准','Approve')}</Button>
     <Button icon="close" disabled={act.busy} onClick={()=>void act.post('/builder/runs/'+a.runId+'/deny')}>{ends?tr('拒绝并终止','Deny & stop'):tr('拒绝','Deny')}</Button></div></div>;})}
   {(s?.tasks.needsApproval||[]).map(w=><div className="inbox" key={w.taskId+w.stageKey}>
    <div><strong>{w.label}</strong><div className="muted">{w.tool} · {w.taskTitle}</div></div>
    <div className="btns">{w.ready?<Button variant="primary" icon="check" disabled={act.busy} onClick={()=>void approveAndRun(w)}>{tr('批准并运行','Approve & run')}</Button>:<span className="muted">{tr('等待前置步骤','waiting')}</span>}
     <Button variant="ghost" onClick={()=>onOpen('plans',w.taskId)}>{tr('在计划中查看','Open in plan')}</Button></div></div>)}
   {(s?.tasks.failures||[]).map(f=><div className="inbox fail" key={'f'+f.taskId+f.stageKey}><div><strong><Icon name="error"/> {f.label}</strong><div className="muted">{f.tool} · {f.error||tr('失败','failed')}</div></div>
    <Button variant="ghost" onClick={()=>onOpen('plans',f.taskId)}>{tr('查看','Inspect')}</Button></div>)}
  </Section>

  <Section title={tr('状态','Status')}>
   <Row icon="circle-filled" tone={model?.online?'ok':model?.configured?'warn':'off'} label={tr('本地模型','Local model')} detail={model?.online?tr('在线','online')+(model.gate?.loaded?' · '+tr('已加载','loaded')+(model.gate.rssMiB?' '+(model.gate.rssMiB>=1024?(model.gate.rssMiB/1024).toFixed(1)+'G':Math.round(model.gate.rssMiB)+'M'):''):''):model?.configured?tr('未就绪','not ready'):tr('未启用','off')} onClick={()=>onOpen('model')}/>
   <Row icon="circle-filled" tone={s?.status.builder.state==='running'?'ok':s?.status.builder.state==='awaiting-approval'?'warn':'off'} label={tr('构建通道','Builder')} detail={({disabled:tr('未启用','off'),idle:tr('空闲','idle'),running:tr('运行中','running'),'awaiting-approval':tr('等待批准','awaiting approval')} as Record<string,string>)[s?.status.builder.state||'disabled']} onClick={()=>onOpen('build')}/>
   <Row icon="circle-filled" tone={s?.status.router.externalEnabled?'warn':'ok'} label={tr('外部模型','External models')} detail={s?.status.router.externalEnabled?tr('已启用（需你确认）','enabled (needs consent)'):tr('关闭','off')} onClick={()=>onOpen('model')}/>
   <Row icon={tone==='red'?'error':tone==='yellow'?'warning':'pass'} label={tr('审计','Audit')} detail={(s?.verdict.sentences[0]?(english?s.verdict.sentences[0].en:s.verdict.sentences[0].zh):'')}/>
  </Section>

  <Section title={tr('Token','Tokens')}>
   <div className="nums"><span>{tr('输入','in')} <b>{formatTokens(total?.in)}</b></span><span>{tr('输出','out')} <b>{formatTokens(total?.out)}</b></span><span>{tr('缓存读','cache read')} <b>{formatTokens(total?.cacheRead)}</b></span></div>
   <p className="muted pad">{tr('只统计提供方上报的数字，不估算。','Only provider-reported numbers; nothing is estimated.')}{total&&total.unknownSessions>0&&' '+tr('用量未知的会话：','Sessions with unknown usage: ')+total.unknownSessions+'.'}</p>
   {bars.map(b=><div className="bar" key={b.agent}><span>{b.agent}</span><Progress value={b.pct} max={100}/><em>{formatTokens(b.total)}</em></div>)}
   {budget.level==='none'?<p className="muted pad">{tr('预算：尚无授权。','Budget: no mandate yet.')}</p>:
    <div className="bar"><span>{tr('预算','budget')}</span><Progress value={s?.tokens.budget?.used||0} max={s?.tokens.budget?.limit||1} tone={budget.level==='over'?'err':budget.level==='warn'?'warn':'ok'}/><em>{formatTokens(s?.tokens.budget?.used)} / {formatTokens(s?.tokens.budget?.limit)}</em></div>}
  </Section>

  <Section title={tr('活动','Activity')}><div className="pad"><ActivityTimeline rows={s?.recent||[]} english={english}/></div></Section>

  <Section title={tr('会话','Sessions')} count={s?.sessions.length}>
   {!s?.sessions.length&&<p className="muted pad">{tr('还没有会话记录。','No sessions recorded yet.')}</p>}
   {s?.sessions.map(x=><Row key={x.session} icon={x.agent==='claude'||x.agent==='codex'?'type-hierarchy':'pulse'} label={<><b>{x.agent}</b> {x.session}</>} detail={x.status+' · '+formatTokens(x.tokens.in)+'/'+formatTokens(x.tokens.out)+' · '+basisText(x.tokens,english)}
    onClick={()=>x.agent==='claude'||x.agent==='codex'?onOpen('agents',x.session):undefined}/>)}
  </Section>
  <div className="cmd"><form onSubmit={e=>{e.preventDefault();void send();}}>
   {reply&&<p className="reply" role="status">{reply}</p>}
   <div><Input value={text} onChange={e=>setText(e.target.value)} disabled={sending} maxLength={1000} aria-label={tr('用自然语言告诉我要做什么','Tell me what to do')} placeholder={tr('用自然语言说你要做什么，例如：整理一下下载文件夹','Say what you want, e.g. tidy my downloads folder')}/>
    <Button variant="primary" type="submit" icon="send" disabled={sending||!text.trim()}>{tr('发送','Send')}</Button></div></form></div>
  {!builder&&!s&&<Empty icon="loading" title={tr('正在连接…','Connecting…')}/>}
 </div>;
}
