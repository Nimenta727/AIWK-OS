/** Single place for calls to the guest-local service. Never sends credentials; always bypasses the HTTP cache. */
export async function api<T>(url:string,options?:RequestInit):Promise<T>{
 const response=await fetch('/api/v1'+url,{cache:'no-store',credentials:'omit',...options});
 const data=await response.json() as T&{error?:string};
 if(!response.ok)throw new Error(data.error||'Guest service request failed');
 return data;
}
