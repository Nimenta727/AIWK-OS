import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {Badge,Button,Empty,Icon,Notice,Row,Section,Select} from '../ui/kit';
import {Dialog} from '../ui/Layout';
import {api} from '../os/api';
import {msg} from './common';
import type {Tr} from './common';

type Metrics={readyMs:number|null;firstTokenMs:number|null;toolMs:number|null;doneMs:number|null;steps:number;calls:number;repairs:number;degraded:string[];prefixBreaks:number;cacheHitRatio:number|null;compacted:boolean;usage:{promptTokens:number|null;completionTokens:number|null}};
type Item={seq:number;type:string;text?:string;tools?:string[];skills?:string[];command?:string;action?:string;raw?:string;callId?:string;tool?:string;args?:Record<string,string>;status?:string;pruned?:boolean;fullChars?:number;id?:string;source?:string;
 outcome?:string;proposal?:{steps?:{tool:string;arguments:Record<string,string>;reason:string}[];reason:string};sources?:{tool:string;path:string}[];metrics?:Metrics;taskId?:string|null;title?:string;error?:string};
type Thread={id:string;items:Item[];running:boolean;truncated:boolean};
type ThreadRow={id:string;items:number;title:string;updated:number};
type Command={id:string;description:string;argumentHint:string};
type Skill={id:string;description:string;source:string};
type Status={enabled:boolean;busy:boolean;model:{state:string;ctx:number|null;server:string|null;model:string|null};skills:Skill[];commands:Command[];plugins:{total:number;enabled:number};
 route:{decisions:number;local:number;flash:number;pro:number;overrides:number;overrideRate:number|null;localShare:number|null;localCompleted:number};limits:{maxSteps:number;maxCalls:number;maxSeconds:number}};
type Plugin={name:string;version:string;description:string;source:'system'|'user';status:string;treeSha256:string|null;files:number;skills:string[];commands:string[];guards:{tool:string;path:string|null;why:string}[];routeHints:number;ignored:{what:string;why:string}[];problems:string[]};
type Decision={tier:'local'|'flash'|'pro';thinking:boolean;cloud:{model:string;thinking:boolean}|null;source:string;modelTier:string|null;markers:string[];advisories:string[];why:{zh:string;en:string}};

const TIER_TONE:Record<string,'ok'|'warn'|'info'>={local:'ok',flash:'info',pro:'warn'};
const STATUS_TONE:Record<string,'ok'|'warn'|'err'|undefined>={enabled:'ok',disabled:undefined,changed:'warn',invalid:'err'};
const argText=(a?:Record<string,string>)=>a?Object.entries(a).map(([k,v])=>k+'='+(v.length>40?v.slice(0,40)+'…':v)).join(', '):'';
const ms=(n:number|null|undefined)=>n==null?'–':n>=1000?(n/1000).toFixed(1)+' s':n+' ms';

/** The local assistant: threads, a live view of what the model reads and proposes, plugins and skills. Nothing here changes a file by itself. */
export default function Assistant({tr,english,onPlan,onModelSwitch}:{tr:Tr;english:boolean;onPlan:(taskId:string)=>void;onModelSwitch:()=>void}){
 const [status,setStatus]=useState<Status|null>(null);
 const [threads,setThreads]=useState<ThreadRow[]>([]);
 const [sel,setSel]=useState<string|null>(null);
 const [thread,setThread]=useState<Thread|null>(null);
 const [plugins,setPlugins]=useState<Plugin[]>([]);
 const [text,setText]=useState('');
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const [decision,setDecision]=useState<{text:string;d:Decision}|null>(null);
 const [override,setOverride]=useState('');
 const [confirm,setConfirm]=useState<Plugin|null>(null);
 const bottom=useRef<HTMLDivElement|null>(null);
 const loadStatus=useCallback(async()=>{try{setStatus(await api<Status>('/assistant/status'));}catch(e){setError(msg(e));}},[]);
 const loadThreads=useCallback(async()=>{try{setThreads((await api<{threads:ThreadRow[]}>('/assistant/threads')).threads);}catch(e){setError(msg(e));}},[]);
 const loadPlugins=useCallback(async()=>{try{setPlugins((await api<{plugins:Plugin[]}>('/assistant/plugins')).plugins);}catch(e){setError(msg(e));}},[]);
 const loadThread=useCallback(async(id:string)=>{try{setThread(await api<Thread>('/assistant/thread?id='+encodeURIComponent(id)));}catch(e){setError(msg(e));}},[]);
 useEffect(()=>{void loadStatus();void loadThreads();void loadPlugins();},[loadStatus,loadThreads,loadPlugins]);
 useEffect(()=>{const t=window.setInterval(()=>{if(!document.hidden){void loadStatus();void loadThreads();}},6000);return()=>window.clearInterval(t);},[loadStatus,loadThreads]);
 useEffect(()=>{if(sel)void loadThread(sel);else setThread(null);},[sel,loadThread]);
 // follow a running turn: the thread file is written item by item, so reading it again IS the live view
 useEffect(()=>{if(!sel||!thread?.running)return;const t=window.setInterval(()=>void loadThread(sel),1200);return()=>window.clearInterval(t);},[sel,thread?.running,loadThread]);
 useEffect(()=>{bottom.current?.scrollIntoView({block:'end'});},[thread?.items.length]);
 const suggest=useMemo(()=>text.startsWith('/')?(status?.commands||[]).filter(c=>('/'+c.id).startsWith(text.split(/\s/)[0])||('/'+c.id.split(':')[1]).startsWith(text.split(/\s/)[0])).slice(0,5):[],[text,status?.commands]);

 const send=async()=>{
  const t=text.trim();if(!t||busy)return;
  setBusy(true);setError('');
  try{
   const r=await api<{threadId:string}>('/assistant/turn',{method:'POST',body:JSON.stringify({text:t,...(sel?{threadId:sel}:{}),...(decision&&decision.text===t?{tier:override||decision.d.tier}:{})})});
   setText('');setDecision(null);setOverride('');setSel(r.threadId);await loadThread(r.threadId);await loadThreads();await loadStatus();
  }catch(e){setError(msg(e));}finally{setBusy(false);}
 };
 const route=async()=>{
  const t=text.trim();if(!t||busy)return;
  setBusy(true);setError('');
  try{setDecision({text:t,d:await api<Decision>('/assistant/route',{method:'POST',body:JSON.stringify({text:t})})});setOverride('');await loadStatus();}
  catch(e){setError(msg(e));}finally{setBusy(false);}
 };
 const applyOverride=async(to:string)=>{
  setOverride(to);
  if(decision&&to&&to!==decision.d.tier){try{await api('/assistant/route/override',{method:'POST',body:JSON.stringify({from:decision.d.tier,to})});await loadStatus();}catch(e){setError(msg(e));}}
 };
 const togglePlugin=async(p:Plugin,enable:boolean)=>{
  setBusy(true);setError('');
  try{await api('/assistant/plugins/'+(enable?'enable':'disable'),{method:'POST',body:JSON.stringify(enable&&p.source==='user'?{name:p.name,treeSha256:p.treeSha256}:{name:p.name})});setConfirm(null);await loadPlugins();await loadStatus();}
  catch(e){setError(msg(e));}finally{setBusy(false);}
 };
 const stepLine=(it:Item)=>{try{const a=JSON.parse(it.raw||'{}') as {type:string;tool?:string;args?:Record<string,string>;calls?:{tool:string;args:Record<string,string>}[];name?:string};
  if(a.type==='call')return a.tool+'('+argText(a.args)+')';if(a.type==='calls')return (a.calls||[]).map(c=>c.tool+'('+argText(c.args)+')').join('  +  ');if(a.type==='skill')return tr('加载技能 ','load skill ')+a.name;return a.type;}catch{return it.action||'';}};
 const metricLine=(m:Metrics)=>[tr('就绪 ','ready ')+ms(m.readyMs),tr('首字 ','first token ')+ms(m.firstTokenMs),tr('首个工具 ','first tool ')+ms(m.toolMs),tr('完成 ','done ')+ms(m.doneMs)].join(' · ');
 const disabled=!status?.enabled;
 const modelBadge=!status?<Badge>…</Badge>:disabled?<Badge tone="warn">{tr('本地模型已关闭','Local model off')}</Badge>:status.model.state==='ready'?<Badge tone="ok">{tr('模型就绪','Model ready')}</Badge>:status.model.state==='loading'?<Badge tone="warn">{tr('模型加载中','Model loading')}</Badge>:status.model.state==='idle'?<Badge>{tr('待机（首次请求时加载）','Idle (loads on first request)')}</Badge>:<Badge tone="err">{tr('模型未运行','Model not running')}</Badge>;
 const renderItem=(it:Item)=>{
  switch(it.type){
   case 'user':return <div key={it.seq} className="as-user"><Icon name="account"/><div><p className="selectable">{it.text}</p>
    <small className="muted">{it.command&&<><Icon name="terminal"/> {it.command} · </>}{tr('可见工具 ','tools shown: ')}{(it.tools||[]).length}{(it.skills||[]).length>0&&' · '+tr('相关技能 ','skills: ')+(it.skills||[]).join(', ')}</small></div></div>;
   case 'step':{ // the result row (observation / skill) already says what was called; show the call itself only while its result is still pending
    const pending=!!thread?.running&&thread.items[thread.items.length-1]?.seq===it.seq&&['call','calls','skill'].includes(it.action||'');
    return pending?<div key={it.seq} className="as-step"><Icon name="loading" spin/><code>{stepLine(it)}</code></div>:null;}
   case 'observation':return <details key={it.seq} className={'as-obs '+(it.status||'')}><summary><Icon name={it.status==='ok'?'pass':it.status==='error'?'error':it.status==='blocked'?'shield':'circle-slash'}/> <b>{it.tool}</b> <span className="muted">{argText(it.args)}</span>
     {it.status!=='ok'&&<Badge tone={it.status==='error'||it.status==='rejected'?'err':'warn'}>{it.status}</Badge>}{it.pruned&&<Badge>{tr('已裁剪','trimmed')} · {it.fullChars}</Badge>}</summary><pre className="selectable">{it.text}</pre></details>;
   case 'skill':return <div key={it.seq} className="as-step"><Icon name="book"/><span>{tr('加载了技能 ','Loaded skill ')}<b>{it.id}</b> <Badge>{it.source}</Badge></span></div>;
   case 'final':return <div key={it.seq} className={'as-final '+(it.outcome==='refused'?'refused':'')}><Icon name={it.outcome==='refused'?'circle-slash':'hubot'}/><div><p className="selectable">{it.text}</p>
     {it.metrics&&<details className="as-metrics"><summary className="muted">{metricLine(it.metrics)}</summary><dl>
      <dt>{tr('步数 / 工具调用','steps / calls')}</dt><dd>{it.metrics.steps} / {it.metrics.calls}</dd>
      <dt>{tr('令牌 入 / 出','tokens in / out')}</dt><dd>{it.metrics.usage.promptTokens??'–'} / {it.metrics.usage.completionTokens??'–'} <span className="muted">({tr('服务端报告，缺失显示 –','as reported by the server, – if missing')})</span></dd>
      <dt>{tr('缓存命中','cache hit')}</dt><dd>{it.metrics.cacheHitRatio==null?tr('服务端未报告','not reported'):Math.round(it.metrics.cacheHitRatio*100)+'%'}</dd>
      <dt>{tr('前缀变化 / 修复 / 压缩','prefix breaks / repairs / compaction')}</dt><dd>{it.metrics.prefixBreaks} / {it.metrics.repairs} / {it.metrics.compacted?tr('是','yes'):tr('否','no')}</dd>
      {it.metrics.degraded.length>0&&<><dt>{tr('降级','degraded')}</dt><dd>{it.metrics.degraded.join(', ')}</dd></>}</dl></details>}</div></div>;
   case 'proposed':return <div key={it.seq} className="as-proposal"><header><Icon name="checklist"/><b>{tr('提案（等你审核，模型没有动任何文件）','Proposal (awaiting your review; the model changed nothing)')}</b></header>
     <p className="selectable">{it.text}</p>
     <ul>{(it.proposal?.steps||[]).map((s,i)=><li key={i}><code>{s.tool}({argText(s.arguments)})</code> <span className="muted">{s.reason}</span></li>)}</ul>
     {(it.sources||[]).length>0&&<small className="muted">{tr('提出这份提案之前读过：','Read before proposing: ')}{(it.sources||[]).map(x=>x.path).join(', ')}</small>}</div>;
   case 'plan':return <div key={it.seq} className="as-step"><Icon name="link"/><span>{tr('已生成计划：','Plan created: ')}{it.title}</span>{it.taskId&&<Button icon="link-external" onClick={()=>onPlan(it.taskId as string)}>{tr('去审核','Review')}</Button>}</div>;
   case 'error':case 'limit':return <Notice key={it.seq} tone={it.type==='limit'?'warn':'err'}>{it.text}</Notice>;
   default:return null;
  }
 };
 return <div className="as">
  <aside className="as-side">
   <div className="as-actions"><Button icon="add" disabled={!sel&&!thread&&!text} title={!sel&&!thread&&!text?tr('已经是新对话','Already a new conversation'):undefined} onClick={()=>{setSel(null);setThread(null);setText('');}}>{tr('新对话','New')}</Button>{modelBadge}</div>
   <div role="list" aria-label={tr('对话','Threads')}>{threads.map(t=><Row key={t.id} icon="comment" label={t.title||t.id} on={t.id===sel} onClick={()=>setSel(t.id)} right={<span className="muted">{t.items}</span>}/>)}
    {!threads.length&&<p className="muted pad">{tr('还没有对话','No conversations yet')}</p>}</div>
   <Section title={tr('插件','Plugins')} count={plugins.length} defaultOpen={false}>
    {plugins.map(p=><div key={p.name} className="as-plugin"><Row icon="extensions" label={p.name} detail={p.version} right={<Badge tone={STATUS_TONE[p.status]}>{({enabled:tr('已启用','on'),disabled:tr('未启用','off'),changed:tr('已改动','changed'),invalid:tr('无效','invalid')} as Record<string,string>)[p.status]||p.status}</Badge>} onClick={()=>setConfirm(p)}/></div>)}
    {!plugins.length&&<p className="muted pad">{tr('没有插件。把插件文件夹放进 ~/.local/state/aiws/assistant/plugins/。','No plugins. Put a plugin folder into ~/.local/state/aiws/assistant/plugins/.')}</p>}</Section>
   <Section title={tr('技能','Skills')} count={status?.skills.length} defaultOpen={false}>
    {(status?.skills||[]).map(s=><Row key={s.id} icon="book" label={s.id} detail={s.description.slice(0,60)} right={<Badge>{s.source.startsWith('plugin')?tr('插件','plugin'):tr('系统','system')}</Badge>}/>)}</Section>
   {status&&<p className="as-stats muted pad">{tr('路由统计：','Router: ')}{status.route.decisions} {tr('次决定','decisions')} · {tr('本地 ','local ')}{status.route.localShare==null?'–':Math.round(status.route.localShare*100)+'%'} · {tr('被你改过 ','overridden ')}{status.route.overrideRate==null?'–':Math.round(status.route.overrideRate*100)+'%'} · {tr('本地完成 ','completed locally ')}{status.route.localCompleted}</p>}
  </aside>
  <section className="as-main">
   {error&&<Notice tone="err">{error}</Notice>}
   {disabled&&<Notice tone="warn">{tr('本地模型已关闭。先在“本地模型开关”里启用它（需要你批准）。','The local model is off. Turn it on in “Model switch” first (needs your approval).')} <Button onClick={onModelSwitch}>{tr('打开模型开关','Open model switch')}</Button></Notice>}
   <div className="as-thread" aria-live="polite">
    {!thread&&<Empty icon="hubot" title={tr('本地助手','Local assistant')}>{tr('它在本机读文件、读日志、检索，并把要改动的事写成提案交给你审核。它自己不会改任何东西。试试：“这个日志为什么失败 build.log”，或输入 / 查看命令。','It reads files and logs on this machine and turns anything that needs changing into a proposal for you to review. It never changes anything itself. Try: “why did build.log fail”, or type / for commands.')}</Empty>}
    {thread?.items.map(renderItem)}
    {thread?.running&&<p className="muted as-working"><Icon name="loading" spin/> {tr('模型在工作…（CPU 上可能需要几分钟）','The model is working… (can take minutes on a CPU)')}</p>}
    <div ref={bottom}/>
   </div>
   {decision&&<div className="as-route"><header><Badge tone={TIER_TONE[override||decision.d.tier]}>{override||decision.d.tier}</Badge>
     {(override||decision.d.tier)!=='local'&&<span>{decision.d.cloud?decision.d.cloud.model:''} · {tr('思考 ','thinking ')}{(override||decision.d.tier)==='pro'?tr('开','on'):tr('关','off')}</span>}
     <label className="grow">{tr('改成','Change to')} <Select value={override} onChange={e=>void applyOverride(e.target.value)}><option value="">–</option><option value="local">local</option><option value="flash">flash</option><option value="pro">pro</option></Select></label></header>
     <p>{english?decision.d.why.en:decision.d.why.zh}</p>
     {decision.d.source==='rules-fallback'&&<Notice tone="warn">{tr('本地模型不可用，这只是按规则的默认值。','The local model was unavailable; this is only the rule-based default.')}</Notice>}
     {(override||decision.d.tier)!=='local'&&<small className="muted">{tr('这类任务适合在“构建”页交给云端智能体；本地助手仍可读文件并给出提案。','This kind of work belongs to the cloud agent on the Build page; the local assistant can still read files and make proposals.')}</small>}</div>}
   <form className="as-compose" onSubmit={e=>{e.preventDefault();void send();}}>
    {suggest.length>0&&<ul className="as-suggest" role="listbox">{suggest.map(c=><li key={c.id}><button type="button" onClick={()=>setText('/'+c.id+' ')}><b>/{c.id}</b> {c.argumentHint&&<code>{c.argumentHint}</code>} <span className="muted">{c.description}</span></button></li>)}</ul>}
    <textarea className="k-input" rows={2} value={text} maxLength={2000} placeholder={tr('问点什么，或输入 / 使用插件命令… Enter 发送，Shift+Enter 换行','Ask something, or type / for plugin commands… Enter sends, Shift+Enter adds a line')}
     onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void send();}}} aria-label={tr('给本地助手的请求','Request for the local assistant')}/>
    <div className="as-buttons"><Button icon="compass" disabled={busy||!text.trim()} onClick={()=>void route()}>{tr('建议用哪档模型','Suggest a model tier')}</Button>
     <Button variant="primary" icon="send" type="submit" disabled={busy||disabled||!text.trim()||!!status?.busy||!!thread?.running}>{tr('发送','Send')}</Button></div>
   </form>
  </section>
  {confirm&&<Dialog title={confirm.name+(confirm.version?' '+confirm.version:'')} onClose={()=>setConfirm(null)}
   actions={<>{confirm.status==='enabled'?<Button variant="primary" disabled={busy} onClick={()=>void togglePlugin(confirm,false)}>{tr('停用','Turn off')}</Button>
    :confirm.status!=='invalid'&&<Button variant="primary" disabled={busy} onClick={()=>void togglePlugin(confirm,true)}>{confirm.source==='system'?tr('启用','Turn on'):tr('我看过了，启用','I reviewed it, turn on')}</Button>}<Button onClick={()=>setConfirm(null)}>{tr('关闭','Close')}</Button></>}>
   <p className="selectable">{confirm.description}</p>
   <dl className="as-dl"><dt>{tr('来源','Source')}</dt><dd>{confirm.source==='system'?tr('系统镜像（只读，哈希已固定）','System image (read-only, hash pinned)'):tr('用户文件夹','User folder')}</dd>
    <dt>{tr('文件 / 指纹','Files / fingerprint')}</dt><dd>{confirm.files} · <code>{(confirm.treeSha256||'').slice(0,12)}</code></dd>
    <dt>{tr('技能','Skills')}</dt><dd>{confirm.skills.join(', ')||'–'}</dd><dt>{tr('命令','Commands')}</dt><dd>{confirm.commands.map(c=>'/'+c).join(', ')||'–'}</dd>
    <dt>{tr('守卫（只能拒绝）','Guards (can only deny)')}</dt><dd>{confirm.guards.length?confirm.guards.map(g=>g.tool+(g.path?' '+g.path:'')).join('; '):'–'}</dd><dt>{tr('路由提示（只能升档）','Route hints (can only raise)')}</dt><dd>{confirm.routeHints}</dd></dl>
   {confirm.ignored.length>0&&<details><summary>{tr('不会被使用的部分（插件里有，但从不运行）','Parts that are NOT used (in the plugin, never run)')} · {confirm.ignored.length}</summary><ul className="as-ignored">{confirm.ignored.map((x,i)=><li key={i}><code>{x.what}</code> <span className="muted">{x.why}</span></li>)}</ul></details>}
   {confirm.problems.length>0&&<Notice tone="warn">{confirm.problems.slice(0,4).join(' · ')}</Notice>}
   {confirm.status==='changed'&&<Notice tone="warn">{tr('启用之后这个插件的文件变了，已被自动停用；请重新查看。','This plugin changed after it was enabled and was switched off automatically; please review it again.')}</Notice>}
   <Notice>{tr('插件只带文字：技能是给本地模型的说明，命令是提示词模板。它们不能增加工具，也不能运行任何代码。','A plugin carries text only: skills are instructions for the local model and commands are prompt templates. They cannot add tools or run any code.')}</Notice></Dialog>}
 </div>;
}
