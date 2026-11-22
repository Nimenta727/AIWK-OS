import {useCallback,useEffect,useState} from 'react';
import {Button,Empty,IconButton,Notice,Row,Select} from '../ui/kit';
import {api} from '../os/api';
import {msg} from './common';
import type {Tr} from './common';

type FileRow={path:string;status:string;staged:boolean;added:number|null;removed:number|null};
type Changes={project:string;files:FileRow[];truncated:boolean};
type Diff={file:string;diff:string;binary:boolean;truncated:boolean};
const STATUS_ICON:Record<string,string>={modified:'diff-modified',added:'diff-added',untracked:'diff-added',deleted:'diff-removed',renamed:'diff-renamed',conflict:'warning'};

/** What did the AI change? Files with +/- counts on the left, the selected file's diff on the right. Read-only. */
export default function ChangesPage({tr,folders}:{tr:Tr;folders:string[]}){
 const [project,setProject]=useState(folders[0]||'.');
 const [data,setData]=useState<Changes|null>(null);
 const [diff,setDiff]=useState<Diff|null>(null);
 const [error,setError]=useState('');
 const load=useCallback(async(p:string)=>{setError('');setDiff(null);try{setData(await api<Changes>('/changes?path='+encodeURIComponent(p)));}catch(e){setData(null);setError(msg(e));}},[]);
 useEffect(()=>{void load(project);},[project,load]);
 const open=async(file:string)=>{setError('');try{setDiff(await api<Diff>('/changes/diff?path='+encodeURIComponent(project)+'&file='+encodeURIComponent(file)));}catch(e){setError(msg(e));}};
 const sum=(data?.files||[]).reduce((a,f)=>({add:a.add+(f.added||0),rem:a.rem+(f.removed||0)}),{add:0,rem:0});
 return <div className="ch">
  <header><Select value={project} onChange={e=>setProject(e.target.value)} aria-label={tr('项目文件夹','Project folder')}>
   {[...new Set(['.',...folders])].map(f=><option key={f} value={f}>{f==='.'?tr('工作区根目录','Workspace root'):f}</option>)}</Select>
   <IconButton icon="refresh" label={tr('刷新','Refresh')} onClick={()=>void load(project)}/>
   {data&&<span className="muted">{data.files.length?data.files.length+tr(' 个文件有改动  ','  file(s) changed  ')+'+'+sum.add+' −'+sum.rem+(data.truncated?tr('（已截断）',' (truncated)'):''):tr('没有未提交的改动','No uncommitted changes')}</span>}</header>
  {error&&<Notice tone="err">{error}</Notice>}
  {data&&!data.files.length&&!error&&<Empty icon="pass" title={tr('工作区是干净的','Working tree is clean')}/>}
  <div className="ch-body">
   <div className="ch-list" role="tree">{data?.files.map(f=><Row key={f.path} icon={STATUS_ICON[f.status]||'diff'} label={f.path} on={diff?.file===f.path} onClick={()=>void open(f.path)}
     right={f.added===null?(f.status==='untracked'?tr('新文件','new'):'—'):<><span className="add">+{f.added}</span> <span className="del">−{f.removed}</span></>}/>)}</div>
   {diff&&<pre className="ch-diff selectable" aria-label={diff.file}>{diff.binary?tr('二进制文件，不显示内容。','Binary file; content not shown.'):
    diff.diff.split('\n').map((l,i)=><span key={i} className={l.startsWith('+')&&!l.startsWith('+++')?'add':l.startsWith('-')&&!l.startsWith('---')?'del':l.startsWith('@@')?'hunk':''}>{l+'\n'}</span>)}{diff.truncated&&tr('\n…已截断','\n…truncated')}</pre>}
  </div>
  {!diff&&data&&data.files.length>0&&<Button variant="ghost" onClick={()=>void open(data.files[0].path)}>{tr('查看第一个文件的 diff','Show the first file’s diff')}</Button>}
 </div>;
}
