import {useCallback,useEffect,useRef,useState} from 'react';
import {api} from './api';
import type {BuilderInfo,Summary} from './observatoryTypes';

/** One poll loop for the whole shell. Resource-saving: it only runs while the tab is visible, and refreshes at once when the tab returns. */
export default function useObservatoryData(intervalMs=5000){
 const [summary,setSummary]=useState<Summary|null>(null);
 const [builder,setBuilder]=useState<BuilderInfo|null>(null);
 const [error,setError]=useState('');
 const timer=useRef<number|undefined>(undefined);
 const reload=useCallback(async()=>{
  try{const [a,b]=await Promise.all([api<Summary>('/observatory'),api<BuilderInfo>('/builder')]);setSummary(a);setBuilder(b);setError('');}
  catch(e){setError(String(e instanceof Error?e.message:e));}
 },[]);
 useEffect(()=>{
  const start=()=>{window.clearInterval(timer.current);timer.current=window.setInterval(()=>{if(!document.hidden)void reload();},intervalMs);};
  const onVisible=()=>{if(!document.hidden)void reload();};
  void reload();start();document.addEventListener('visibilitychange',onVisible);
  return()=>{window.clearInterval(timer.current);document.removeEventListener('visibilitychange',onVisible);};
 },[reload,intervalMs]);
 return {summary,builder,error,reload};
}

export type ObservatoryData=ReturnType<typeof useObservatoryData>&{reload:()=>Promise<void>};
