import {useMemo,useState} from 'react';
import {buildLanes,formatSpan,seriesPath,tokenSeries} from '../model/timeline.mjs';
import {clock,formatTokens} from '../model/observatory.mjs';
import type {EventRow} from './observatoryTypes';

type Row={ts:number;source:string;label:string;status:string};
const LANE_ZH:Record<string,string>={model:'模型',tool:'工具/任务',builder:'构建',system:'系统',error:'错误'};
const LANE_EN:Record<string,string>={model:'Model',tool:'Tools/Tasks',builder:'Build',system:'System',error:'Errors'};

/** Activity on one shared time axis: what ran, in which lane, where it failed, and where nothing happened.
 *  Every mark is a real event; hovering/focusing shows its time and label. No animation, no decoration. */
export function ActivityTimeline({rows,english}:{rows:Row[];english:boolean}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const t=useMemo(()=>buildLanes(rows),[rows]);
 const [pick,setPick]=useState<{ts:number;label:string;source:string;status:string}|null>(null);
 if(!t.lanes.length)return <p className="muted pad">{tr('暂无活动。','No activity yet.')}</p>;
 const names=english?LANE_EN:LANE_ZH;
 return <div className="aiws-tl" data-aiws="timeline">
  <div className="aiws-tl-head"><span>{clock(t.start as number)}</span>
   <span>{tr('跨度 ','span ')}{formatSpan(t.spanSec)}{t.gaps.length>0&&' · '+tr('静默段 ','quiet gaps ')+t.gaps.length}</span><span>{clock(t.end as number)}</span></div>
  {t.lanes.map(l=><div className="aiws-tl-lane" key={l.lane}><b>{names[l.lane]}</b>
   <svg viewBox="0 0 100 12" preserveAspectRatio="none" role="img" aria-label={names[l.lane]+' '+l.items.length}>
    <line x1="0" y1="6" x2="100" y2="6" className="axis"/>
    {t.gaps.map((g,i)=>{const x1=(g.from-(t.start as number))/Math.max(t.spanSec,1)*100,x2=(g.to-(t.start as number))/Math.max(t.spanSec,1)*100;
     return <rect key={i} x={x1} y="0" width={Math.max(x2-x1,0.5)} height="12" className="gap"><title>{tr('无事件 ','no events for ')+formatSpan(g.sec)}</title></rect>;})}
    {l.items.map((it,i)=><rect key={i} x={Math.min(it.x,99.2)} y="1.5" width="0.8" height="9" tabIndex={0} className={'tick '+(it.status==='error'||it.status==='failed'?'bad':'')}
      onMouseEnter={()=>setPick(it)} onFocus={()=>setPick(it)}><title>{clock(it.ts)+' '+it.label}</title></rect>)}
   </svg><em>{l.items.length}</em></div>)}
  <p className="aiws-tl-pick" aria-live="polite">{pick?clock(pick.ts)+' · '+pick.source+' · '+pick.label+(pick.status?' · '+pick.status:''):tr('把鼠标移到刻度上查看详情；灰色区段表示这段时间没有任何事件。','Hover a mark for details; shaded stretches mean no events were recorded.')}</p>
 </div>;
}

/** Cumulative tokens of one session, with the granted budget as a reference line when there is one. */
export function TokenBurn({events,limit,english}:{events:EventRow[];limit:number|null;english:boolean}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const s=useMemo(()=>tokenSeries(events),[events]);
 const p=useMemo(()=>seriesPath(s,limit),[s,limit]);
 if(s.points.length<2)return <p className="muted pad">{s.unknown?tr('该会话没有上报用量，无法绘制。','No usage reported for this session; nothing to plot.'):tr('用量点不足，无法绘制曲线。','Not enough usage points to plot.')}</p>;
 return <div className="aiws-tb" data-aiws="token-burn">
  <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={tr('累计 token','cumulative tokens')}>
   {p.limitY!==null&&<line x1="0" x2="100" y1={p.limitY} y2={p.limitY} className="limit"/>}
   <polyline points={p.line} className="line"/></svg>
  <p className="muted pad">{tr('累计 ','cumulative ')}{formatTokens(s.max)}{limit?' / '+formatTokens(limit):''}
   {s.unknown>0&&' · '+tr('未上报 ','unreported ')+s.unknown}{s.unverified&&' · '+tr('逐轮语义未验证','per-turn semantics unverified')}</p>
 </div>;
}
