import {useCallback,useState} from 'react';
import {api} from '../os/api';

/** `tr(zh,en)` helper type shared by every page. */
export type Tr=(zh:string,en:string)=>string;
export const msg=(e:unknown)=>String(e instanceof Error?e.message:e);

/** Run one POST at a time with a busy flag and an error string. Pages never hand-build headers: api() adds the CSRF token. */
export function useAction(after?:()=>Promise<void>|void){
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const post=useCallback(async(path:string,body:object={})=>{
  if(busy)return false;
  setBusy(true);setError('');
  try{await api(path,{method:'POST',body:JSON.stringify(body)});if(after)await after();return true;}
  catch(e){setError(msg(e));return false;}
  finally{setBusy(false);}
 },[busy,after]);
 return {busy,error,setError,post};
}
