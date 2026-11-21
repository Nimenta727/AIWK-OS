/** Single place for calls to the guest-local service. Never sends credentials; always bypasses the HTTP cache.
 *
 * CSRF: the service issues a per-process token at GET /session. It changes whenever the service restarts, so a
 * token fetched once at page load can go stale ("Invalid CSRF"). All mutating calls therefore go through here:
 * the token is attached automatically (callers' own X-AIWS-CSRF headers are overridden), fetched lazily when
 * missing, and refreshed + retried exactly once when the service answers 403 "Invalid CSRF". */
let csrfToken='';
let csrfPending:Promise<string>|null=null;
const listeners=new Set<(token:string)=>void>();

export function onCsrfChange(listener:(token:string)=>void):()=>void{
 listeners.add(listener);
 return()=>{listeners.delete(listener);};
}
function setToken(token:string){
 if(token===csrfToken)return;
 csrfToken=token;
 listeners.forEach(l=>{try{l(token);}catch{/* a listener must never break a request */}});
}
/** Fetch (or re-fetch) the CSRF token. Concurrent callers share one request. */
export function refreshCsrf():Promise<string>{
 if(!csrfPending){
  csrfPending=fetch('/api/v1/session',{cache:'no-store',credentials:'omit'})
   .then(async r=>{
    const body=await r.json() as {csrf?:string;error?:string};
    if(!r.ok||typeof body.csrf!=='string'||!body.csrf)throw new Error(body.error||'Session unavailable');
    setToken(body.csrf);
    return body.csrf;
   })
   .finally(()=>{csrfPending=null;});
 }
 return csrfPending;
}

function isMutating(options?:RequestInit){
 const method=(options?.method||'GET').toUpperCase();
 return method!=='GET'&&method!=='HEAD';
}
async function send(url:string,options:RequestInit|undefined,mutating:boolean){
 const init:RequestInit={cache:'no-store',credentials:'omit',...options};
 if(mutating){
  const headers=new Headers(options?.headers);
  if(!csrfToken)await refreshCsrf();
  headers.set('X-AIWS-CSRF',csrfToken);
  if(!headers.has('Content-Type'))headers.set('Content-Type','application/json');
  init.headers=headers;
 }
 return fetch('/api/v1'+url,init);
}
export async function api<T>(url:string,options?:RequestInit):Promise<T>{
 const mutating=isMutating(options);
 let response=await send(url,options,mutating);
 let data=await response.json().catch(()=>({error:'Invalid response from guest service'})) as T&{error?:string};
 if(mutating&&response.status===403&&data.error==='Invalid CSRF'){
  await refreshCsrf();
  response=await send(url,options,true);
  data=await response.json().catch(()=>({error:'Invalid response from guest service'})) as T&{error?:string};
 }
 if(!response.ok)throw new Error(data.error||'Guest service request failed');
 return data;
}
