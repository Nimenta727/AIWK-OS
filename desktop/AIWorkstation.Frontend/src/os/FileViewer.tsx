import {useEffect,useState} from 'react';
import {api} from './api';
import {parseMarkdown,parseTable,rawUrl,safeHref,viewerKind} from '../model/apps.mjs';

type FileDetail={path:string;text:string;sha256:string};
type DocDetail={path:string;text:string;source:string;truncated:boolean;bytes:number};
type Span={t:string;v:string;href?:string};
type Block={type:string;level?:number;spans?:Span[];items?:Span[][];ordered?:boolean;text?:string;lang?:string};

function Spans({spans}:{spans:Span[]}){
 return <>{spans.map((s,i)=>s.t==='code'?<code key={i}>{s.v}</code>:s.t==='strong'?<strong key={i}>{s.v}</strong>:s.t==='em'?<em key={i}>{s.v}</em>:
  s.t==='link'?(safeHref(s.href||'')?<a key={i} href={safeHref(s.href||'')||undefined} target="_blank" rel="noopener noreferrer">{s.v}</a>:<span key={i} title={s.href}>{s.v}</span>):<span key={i}>{s.v}</span>)}</>;
}
function Markdown({text}:{text:string}){
 const blocks=parseMarkdown(text) as Block[];
 return <article className="aiws-sh-md">{blocks.map((b,i)=>{
  if(b.type==='h'){const H=('h'+Math.min(6,b.level||1)) as 'h1';return <H key={i}><Spans spans={b.spans||[]}/></H>;}
  if(b.type==='p')return <p key={i}><Spans spans={b.spans||[]}/></p>;
  if(b.type==='quote')return <blockquote key={i}><Spans spans={b.spans||[]}/></blockquote>;
  if(b.type==='code')return <pre key={i} className="aiws-sh-md-code"><code>{b.text}</code></pre>;
  if(b.type==='hr')return <hr key={i}/>;
  const items=(b.items||[]).map((it,j)=><li key={j}><Spans spans={it}/></li>);
  return b.ordered?<ol key={i}>{items}</ol>:<ul key={i}>{items}</ul>;
 })}</article>;
}
function Table({text,english}:{text:string;english:boolean}){
 const t=parseTable(text) as {header:string[];rows:string[][];truncated:boolean;columnsTruncated:boolean};
 return <div className="aiws-sh-table-wrap"><table className="aiws-sh-table"><thead><tr>{t.header.map((h,i)=><th key={i}>{h}</th>)}</tr></thead>
  <tbody>{t.rows.map((r,i)=><tr key={i}>{r.map((c,j)=><td key={j}>{c}</td>)}</tr>)}</tbody></table>
  {(t.truncated||t.columnsTruncated)&&<p className="aiws-os-muted">{english?'Only the first rows/columns are shown.':'只显示前面的行/列。'}</p>}</div>;
}
function Code({text,path,sha,english}:{text:string;path:string;sha?:string;english:boolean}){
 const lines=text.split('\n');
 return <div className="aiws-sh-file"><header><strong>{path}</strong><span>{lines.length} {english?'lines':'行'}{sha?' · SHA-256 '+sha.slice(0,12)+'…':''}</span></header>
  <div className="aiws-sh-code" role="region" aria-label={path}><ol>{lines.map((_,i)=><li key={i}>{i+1}</li>)}</ol><pre>{text}</pre></div></div>;
}

/** Read-only viewer for one workspace file. Binary previews come from a sandboxed endpoint; text goes through the audited reader. */
export default function FileViewer({path,english}:{path:string;english:boolean}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const kind=viewerKind(path) as string;
 const [text,setText]=useState<FileDetail|null>(null);
 const [doc,setDoc]=useState<DocDetail|null>(null);
 const [source,setSource]=useState(false);
 const [error,setError]=useState('');
 useEffect(()=>{
  let live=true;
  setText(null);setDoc(null);setError('');setSource(false);
  const fail=(e:unknown)=>{if(live)setError(String(e instanceof Error?e.message:e));};
  if(kind==='document')api<DocDetail>('/workspace/doc?path='+encodeURIComponent(path)).then(d=>{if(live)setDoc(d);}).catch(fail);
  else if(kind==='pdf')api<DocDetail>('/workspace/doc?path='+encodeURIComponent(path)).then(d=>{if(live)setDoc(d);}).catch(()=>{/* the PDF frame still works without text */});
  else if(kind!=='image'&&kind!=='html')api<FileDetail>('/workspace/file?path='+encodeURIComponent(path)).then(d=>{if(live)setText(d);}).catch(fail);
  return()=>{live=false;};
 },[path,kind]);
 if(error)return <div className="aiws-os-error" role="alert">{tr('无法读取：','Cannot read: ')}{error}</div>;
 const bar=<header className="aiws-sh-viewbar"><strong>{path}</strong><span>{kind}</span></header>;
 if(kind==='image')return <div className="aiws-sh-file">{bar}<div className="aiws-sh-image"><img src={rawUrl(path)} alt={path}/></div></div>;
 if(kind==='pdf')return <div className="aiws-sh-file aiws-sh-fill">{bar}
  <iframe className="aiws-sh-frame" title={path} src={rawUrl(path)}/>
  {doc&&<details className="aiws-sh-doc"><summary>{tr('提取的文字','Extracted text')} ({doc.source})</summary><pre>{doc.text}{doc.truncated?'\n…':''}</pre></details>}</div>;
 if(kind==='html')return <div className="aiws-sh-file aiws-sh-fill">{bar}
  <iframe className="aiws-sh-frame" title={path} src={rawUrl(path)} sandbox="allow-scripts"/>
  <p className="aiws-os-muted" style={{padding:'4px 16px'}}>{tr('在隔离沙箱中运行：不能访问系统接口，也不能联网。','Runs in an isolated sandbox: no access to the system API and no network.')}</p></div>;
 if(kind==='document'){
  if(!doc)return <p className="aiws-os-muted">{tr('正在转换…','Converting…')}</p>;
  return <div className="aiws-sh-file">{bar}<article className="aiws-sh-md"><pre className="aiws-sh-doc-text">{doc.text}{doc.truncated?'\n…':''}</pre></article></div>;
 }
 if(!text)return <p className="aiws-os-muted">{tr('正在读取…','Reading…')}</p>;
 if(kind==='markdown')return <div className="aiws-sh-file">{bar}
  <div style={{padding:'6px 16px'}}><button type="button" className="aiws-sh-btn" onClick={()=>setSource(x=>!x)}>{source?tr('渲染视图','Rendered'):tr('查看源码','Source')}</button></div>
  {source?<Code text={text.text} path={path} sha={text.sha256} english={english}/>:<Markdown text={text.text}/>}</div>;
 if(kind==='table')return <div className="aiws-sh-file">{bar}<Table text={text.text} english={english}/></div>;
 if(kind==='json'){
  let pretty=text.text;
  try{pretty=JSON.stringify(JSON.parse(text.text),null,2);}catch{/* show the raw text */}
  return <Code text={pretty} path={path} sha={text.sha256} english={english}/>;
 }
 return <Code text={text.text} path={path} sha={text.sha256} english={english}/>;
}
