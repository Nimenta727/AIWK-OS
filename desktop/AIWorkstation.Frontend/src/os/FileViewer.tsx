import {useEffect,useState} from 'react';
import {api} from './api';

type FileDetail={path:string;text:string;sha256:string};

/** Read-only viewer for one workspace file (the guest API refuses binaries, symlinks and files over 128 KiB). */
export default function FileViewer({path,english}:{path:string;english:boolean}){
 const tr=(zh:string,en:string)=>english?en:zh;
 const [detail,setDetail]=useState<FileDetail|null>(null);
 const [error,setError]=useState('');
 useEffect(()=>{
  let active=true;
  setDetail(null);setError('');
  api<FileDetail>('/workspace/file?path='+encodeURIComponent(path))
   .then(d=>{if(active)setDetail(d);}).catch(e=>{if(active)setError(String(e instanceof Error?e.message:e));});
  return()=>{active=false;};
 },[path]);
 if(error)return <div className="aiws-os-error" role="alert">{tr('无法读取：','Cannot read: ')}{error}</div>;
 if(!detail)return <p className="aiws-os-muted">{tr('正在读取…','Reading…')}</p>;
 const lines=detail.text.split('\n');
 return <div className="aiws-sh-file">
  <header><strong>{detail.path}</strong><span>{lines.length} {tr('行','lines')} · SHA-256 {detail.sha256.slice(0,12)}…</span></header>
  <div className="aiws-sh-code" role="region" aria-label={detail.path}>
   <ol>{lines.map((_,i)=><li key={i}>{i+1}</li>)}</ol><pre>{detail.text}</pre></div>
 </div>;
}
