import {useCallback,useEffect,useState} from 'react';
import {GitCompare,RefreshCw} from 'lucide-react';
import {api} from './api';

type Row={path:string;status:string;staged:boolean;added:number|null;removed:number|null;from?:string};
type Changes={project:string;files:Row[];truncated:boolean};
type Diff={file:string;diff:string;binary:boolean;truncated:boolean};

/** What did the AI change? One project folder at a time: files with +/- counts, click for the diff. Read-only. */
export default function ChangesView({english,folders}:{english:boolean;folders:string[]}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const [project,setProject]=useState(folders[0]||'.');
 const [data,setData]=useState<Changes|null>(null);
 const [diff,setDiff]=useState<Diff|null>(null);
 const [error,setError]=useState('');
 const load=useCallback(async(p:string)=>{
  setError('');setDiff(null);
  try{setData(await api<Changes>('/changes?path='+encodeURIComponent(p)));}
  catch(e){setData(null);setError(String(e instanceof Error?e.message:e));}
 },[]);
 useEffect(()=>{void load(project);},[project,load]);
 const open=async(file:string)=>{
  setError('');
  try{setDiff(await api<Diff>('/changes/diff?path='+encodeURIComponent(project)+'&file='+encodeURIComponent(file)));}
  catch(e){setError(String(e instanceof Error?e.message:e));}
 };
 const totals=(data?.files||[]).reduce((a,f)=>({add:a.add+(f.added||0),rem:a.rem+(f.removed||0)}),{add:0,rem:0});
 return <div className="aiws-ch">
  <header><h2><GitCompare size={16}/> {tr('变更审查','Review changes')}</h2>
   <select value={project} onChange={e=>setProject(e.target.value)} aria-label={tr('项目文件夹','Project folder')}>
    {[...new Set(['.',...folders])].map(f=><option key={f} value={f}>{f==='.'?tr('工作区根目录','Workspace root'):f}</option>)}</select>
   <button type="button" onClick={()=>void load(project)} title={tr('刷新','Refresh')}><RefreshCw size={14}/></button></header>
  {error&&<div className="aiws-os-error" role="alert">{error}</div>}
  {data&&<p className="aiws-os-muted">{data.files.length?data.files.length+tr(' 个文件有改动，','changed file(s), ')+'+'+totals.add+' −'+totals.rem+(data.truncated?tr('（已截断）',' (truncated)'):''):tr('没有未提交的改动。','No uncommitted changes.')}</p>}
  <div className="aiws-ch-body">
   <ul>{data?.files.map(f=><li key={f.path}><button type="button" className={diff?.file===f.path?'on':''} onClick={()=>void open(f.path)}>
    <span className={'st '+f.status}>{f.status}</span><span className="p">{f.path}</span>
    <em>{f.added===null?(f.status==='untracked'?tr('新文件','new'):'—'):'+'+f.added+' −'+f.removed}</em></button></li>)}</ul>
   {diff&&<pre className="aiws-ch-diff" aria-label={diff.file}>{diff.binary?tr('二进制文件，不显示内容。','Binary file; content not shown.'):
    diff.diff.split('\n').map((l,i)=><span key={i} className={l.startsWith('+')&&!l.startsWith('+++')?'add':l.startsWith('-')&&!l.startsWith('---')?'del':l.startsWith('@@')?'hunk':''}>{l+'\n'}</span>)}
    {diff.truncated&&tr('\n…已截断','\n…truncated')}</pre>}
  </div>
 </div>;
}
