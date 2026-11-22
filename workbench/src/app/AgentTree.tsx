import {useCallback,useEffect,useState} from 'react';
import {Badge,Empty,Icon,Notice,Row,Select} from '../ui/kit';
import {api} from '../os/api';
import {formatTokens} from '../model/observatory.mjs';
import {formatSpan} from '../model/timeline.mjs';
import {msg} from './common';
import type {Tr} from './common';
import type {SessionRow} from '../os/observatoryTypes';

export type AgentNode={id:string;parent:string|null;label:string|null;model:string|null;modelInherited:boolean;state:string;tools:number;
 ctx:{kind:string;ref:string}[];tokens:{in:number|null;out:number|null};startedTs:number|null;endedTs:number|null;durationMs:number|null;inferred:boolean;depth:number;children:string[]};
type Tree={session:string;nodes:AgentNode[];count:number;droppedNodes:number;ended:boolean};
const STATE_ICON:Record<string,string>={running:'sync',done:'pass',error:'error',unknown:'question'};
const CTX_ICON:Record<string,string>={file:'file',search:'search',url:'globe',command:'terminal',prompt:'comment'};

/** Cloud sub-agents as a tree: who spawned whom, which model, what context each was given, how far along it is.
 *  Everything comes from what the CLI reported; "inherited" and "unknown" are shown as such, never filled in. */
export default function AgentTree({english,tr,sessions,focus,onOpenFile}:{english:boolean;tr:Tr;sessions:SessionRow[];focus:string|null;onOpenFile:(path:string)=>void}){
 const agentSessions=sessions.filter(s=>s.agent==='claude'||s.agent==='codex');
 const [session,setSession]=useState<string>(focus||agentSessions[0]?.session||'');
 const [tree,setTree]=useState<Tree|null>(null);
 const [error,setError]=useState('');
 const [open,setOpen]=useState<string>('root');
 const [collapsed,setCollapsed]=useState<Set<string>>(new Set());
 useEffect(()=>{if(focus)setSession(focus);},[focus]);
 useEffect(()=>{if(!session&&agentSessions[0])setSession(agentSessions[0].session);},[session,agentSessions]);
 const load=useCallback(async()=>{
  if(!session)return;
  try{setTree(await api<Tree>('/observatory/tree?session='+encodeURIComponent(session)));setError('');}catch(e){setError(msg(e));}
 },[session]);
 useEffect(()=>{void load();},[load]);
 const running=!!tree?.nodes.some(n=>n.state==='running');
 useEffect(()=>{if(!running)return;const t=window.setInterval(()=>{if(!document.hidden)void load();},3000);return()=>window.clearInterval(t);},[running,load]);

 if(!agentSessions.length&&!session)return <Empty icon="type-hierarchy" title={tr('还没有云端运行','No cloud runs yet')}>{tr('在“构建”里授权并开始后，云端智能体及其子智能体会以树的形式显示在这里。','Once a build is granted and started, the cloud agent and its sub-agents appear here as a tree.')}</Empty>;
 const nodes=tree?.nodes||[];
 const hidden=new Set<string>();
 for(const n of nodes){if(n.parent&&(collapsed.has(n.parent)||hidden.has(n.parent)))hidden.add(n.id);}
 const shown=nodes.filter(n=>!hidden.has(n.id));
 const sel=nodes.find(n=>n.id===open)||nodes[0];
 const stateLabel=(s:string)=>({running:tr('进行中','running'),done:tr('完成','done'),error:tr('出错','failed'),unknown:tr('未报告结果','no result reported')} as Record<string,string>)[s]||s;
 const toggle=(id:string)=>setCollapsed(prev=>{const n=new Set(prev);if(n.has(id))n.delete(id);else n.add(id);return n;});
 return <div className="at">
  <header><Select value={session} onChange={e=>{setSession(e.target.value);setOpen('root');}} aria-label={tr('运行','Run')}>
   {agentSessions.map(s=><option key={s.session} value={s.session}>{s.agent} · {s.session} · {s.status}</option>)}{!agentSessions.some(s=>s.session===session)&&session&&<option value={session}>{session}</option>}</Select>
   {tree&&<span className="muted">{tree.count} {tr('个智能体','agents')}{tree.droppedNodes>0?' (+'+tree.droppedNodes+' '+tr('未显示','not shown')+')':''}</span>}</header>
  {error&&<Notice tone="err">{error}</Notice>}
  {tree&&tree.count<=1&&<Notice>{tr('这次运行没有派出子智能体（或 CLI 没有报告）。','This run spawned no sub-agents (or the CLI did not report any).')}</Notice>}
  <div className="at-body">
   <div className="at-tree" role="tree" aria-label={tr('智能体树','Agent tree')}>
    {shown.map(n=><Row key={n.id} depth={n.depth} on={n.id===sel?.id} expanded={n.children.length?!collapsed.has(n.id):undefined}
     icon={STATE_ICON[n.state]||'circle-large-outline'} onClick={()=>{setOpen(n.id);if(n.children.length&&n.id===sel?.id)toggle(n.id);}}
     label={<>{n.label||n.id}{n.inferred&&<em className="muted"> ({tr('推断','inferred')})</em>}</>}
     detail={<>{n.model?<span className={n.modelInherited?'muted-i':''}>{n.model}{n.modelInherited?' ↑':''}</span>:tr('模型未报告','model n/a')}</>}
     right={<>{n.tools>0&&<span>{n.tools} {tr('次调用','calls')} · </span>}{formatTokens(n.tokens.in)}/{formatTokens(n.tokens.out)}</>}/>)}
   </div>
   {sel&&<aside className="at-detail selectable" aria-label={tr('智能体详情','Agent detail')}>
    <h3>{sel.label||sel.id}</h3>
    <dl>
     <dt>{tr('状态','State')}</dt><dd><Icon name={STATE_ICON[sel.state]||'circle-large-outline'} spin={sel.state==='running'}/> {stateLabel(sel.state)}</dd>
     <dt>{tr('模型','Model')}</dt><dd>{sel.model?<>{sel.model}{sel.modelInherited&&<Badge>{tr('继承自上级','inherited')}</Badge>}</>:tr('CLI 未报告','not reported by the CLI')}</dd>
     <dt>{tr('进展','Progress')}</dt><dd>{sel.tools} {tr('次工具调用','tool calls')}{sel.durationMs!==null&&' · '+formatSpan(sel.durationMs/1000)}</dd>
     <dt>Token</dt><dd>{tr('输入','in')} {formatTokens(sel.tokens.in)} · {tr('输出','out')} {formatTokens(sel.tokens.out)}</dd>
     <dt>{tr('上级','Parent')}</dt><dd>{sel.parent?(nodes.find(n=>n.id===sel.parent)?.label||sel.parent):'—'}</dd>
    </dl>
    <h4>{tr('上下文','Context')} <span className="muted">({sel.ctx.length})</span></h4>
    {!sel.ctx.length&&<p className="muted">{tr('没有记录到它读取的文件或收到的提示。','No files or prompts were recorded for this agent.')}</p>}
    <ul className="at-ctx">{sel.ctx.map((c,i)=><li key={i}><Icon name={CTX_ICON[c.kind]||'circle-small'}/>
     {c.kind==='file'&&!c.ref.startsWith('/')&&!c.ref.includes('..')?<a role="button" tabIndex={0} onClick={()=>onOpenFile(c.ref)} onKeyDown={e=>{if(e.key==='Enter')onOpenFile(c.ref);}}>{c.ref}</a>:<span>{c.ref}</span>}
     <em className="muted"> {c.kind}</em></li>)}</ul>
    {sel.children.length>0&&<><h4>{tr('派出的子智能体','Spawned')}</h4><ul className="at-ctx">{sel.children.map(id=>{const c=nodes.find(n=>n.id===id);return c?<li key={id}><Icon name={STATE_ICON[c.state]||'circle-large-outline'}/><a role="button" tabIndex={0} onClick={()=>setOpen(id)} onKeyDown={e=>{if(e.key==='Enter')setOpen(id);}}>{c.label||id}</a></li>:null;})}</ul></>}
   </aside>}
  </div>
 </div>;
}
