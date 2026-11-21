import {test} from 'node:test';
import assert from 'node:assert/strict';
import {transformSync} from 'esbuild';
import {readFileSync} from 'node:fs';

// api.ts is TypeScript; compile it on the fly so the real module is what gets tested.
const code=transformSync(readFileSync(new URL('../src/os/api.ts',import.meta.url),'utf8'),{loader:'ts',format:'esm'}).code;
const load=()=>import('data:text/javascript;base64,'+Buffer.from(code).toString('base64')+'#'+Math.random());

function fakeServer(){
 const state={token:'t1',calls:[]};
 globalThis.fetch=async(url,init={})=>{
  const method=(init.method||'GET').toUpperCase();
  const h=new Headers(init.headers);
  state.calls.push({url,method,csrf:h.get('X-AIWS-CSRF')});
  const reply=(status,body)=>({ok:status<300,status,json:async()=>body});
  if(url==='/api/v1/session')return reply(200,{csrf:state.token});
  if(method==='POST'&&h.get('X-AIWS-CSRF')!==state.token)return reply(403,{error:'Invalid CSRF'});
  return reply(200,{ok:true});
 };
 return state;
}

test('POST fetches the token lazily and sends it',async()=>{
 const s=fakeServer();const {api}=await load();
 assert.deepEqual(await api('/x',{method:'POST',body:'{}'}),{ok:true});
 assert.equal(s.calls.at(-1).csrf,'t1');
});
test('a stale token is refreshed and the request retried exactly once',async()=>{
 const s=fakeServer();const {api,refreshCsrf}=await load();
 await refreshCsrf();s.token='t2';   // service restarted
 assert.deepEqual(await api('/x',{method:'POST',body:'{}',headers:{'X-AIWS-CSRF':'caller-supplied-stale'}}),{ok:true});
 const posts=s.calls.filter(c=>c.method==='POST');
 assert.equal(posts.length,2);assert.equal(posts[1].csrf,'t2');
});
test('a persistent 403 is surfaced, not retried forever',async()=>{
 const s=fakeServer();const {api}=await load();
 globalThis.fetch=async(url)=>url==='/api/v1/session'?{ok:true,status:200,json:async()=>({csrf:'a'})}:{ok:false,status:403,json:async()=>({error:'Invalid CSRF'})};
 await assert.rejects(api('/x',{method:'POST',body:'{}'}),/Invalid CSRF/);
});
test('GET never sends a token and listeners hear token changes',async()=>{
 const s=fakeServer();const {api,onCsrfChange,refreshCsrf}=await load();
 await api('/snapshot');assert.equal(s.calls[0].csrf,null);
 const seen=[];onCsrfChange(t=>seen.push(t));await refreshCsrf();assert.deepEqual(seen,['t1']);
});
