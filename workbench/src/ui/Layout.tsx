import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {Icon,IconButton} from './kit';
import {filterCommands} from '../model/shell.mjs';

export type Tab={id:string;title:string;icon?:string;pinned?:boolean;dirty?:boolean};
export type Command={id:string;label:string;keywords?:string;hint?:string;run:()=>void};

/** Draggable divider. Pointer drag + arrow keys; `value` is the size in px of the pane it resizes. */
export function Sash({dir,value,min,max,onChange,invert,label}:{dir:'x'|'y';value:number;min:number;max:number;onChange:(v:number)=>void;invert?:boolean;label:string}){
 const start=useRef<{p:number;v:number}|null>(null);
 const clamp=(v:number)=>Math.max(min,Math.min(max,v));
 return <div className={'sash sash-'+dir} role="separator" aria-orientation={dir==='x'?'vertical':'horizontal'} aria-label={label} aria-valuenow={value} aria-valuemin={min} aria-valuemax={max} tabIndex={0}
  onPointerDown={e=>{(e.target as HTMLElement).setPointerCapture(e.pointerId);start.current={p:dir==='x'?e.clientX:e.clientY,v:value};document.body.classList.add('is-sashing-'+dir);}}
  onPointerMove={e=>{if(!start.current)return;const d=(dir==='x'?e.clientX:e.clientY)-start.current.p;onChange(clamp(start.current.v+(invert?-d:d)));}}
  onPointerUp={()=>{start.current=null;document.body.classList.remove('is-sashing-x','is-sashing-y');}}
  onDoubleClick={()=>onChange(clamp(dir==='x'?260:240))}
  onKeyDown={e=>{const k=dir==='x'?['ArrowLeft','ArrowRight']:['ArrowUp','ArrowDown'];if(!k.includes(e.key))return;e.preventDefault();const s=(e.key===k[1]?1:-1)*(invert?-1:1)*(e.shiftKey?40:10);onChange(clamp(value+s));}}/>;
}

export function ActivityBar({items,active,open,onSelect,bottom}:{items:{id:string;label:string;icon:string;badge?:number}[];active:string;open:boolean;onSelect:(id:string)=>void;bottom:{id:string;label:string;icon:string;onClick:()=>void}[]}){
 return <nav className="ab" aria-label="Views">
  <div>{items.map(i=><button key={i.id} type="button" className={'ab-item'+(open&&active===i.id?' on':'')} title={i.label} aria-label={i.label} aria-pressed={open&&active===i.id} onClick={()=>onSelect(i.id)}>
   <Icon name={i.icon}/>{i.badge?<span className="ab-badge">{i.badge>99?'99+':i.badge}</span>:null}</button>)}</div>
  <div>{bottom.map(b=><button key={b.id} type="button" className="ab-item" title={b.label} aria-label={b.label} onClick={b.onClick}><Icon name={b.icon}/></button>)}</div>
 </nav>;
}

export function SideBar({title,actions,children}:{title:string;actions?:ReactNode;children:ReactNode}){
 return <aside className="sb" aria-label={title}><header><span>{title}</span><div>{actions}</div></header><div className="sb-body">{children}</div></aside>;
}

/** Editor tabs: click to activate, middle-click or × to close, Ctrl+Tab cycling is handled by the app. */
export function Tabs({tabs,active,onActivate,onClose,closeLabel}:{tabs:Tab[];active:string|null;onActivate:(id:string)=>void;onClose:(id:string)=>void;closeLabel:string}){
 return <div className="tabs" role="tablist">
  {tabs.map(t=><div key={t.id} role="tab" aria-selected={t.id===active} className={'tab'+(t.id===active?' on':'')} title={t.title}
   onClick={()=>onActivate(t.id)} onMouseDown={e=>{if(e.button===1&&!t.pinned){e.preventDefault();onClose(t.id);}}}
   onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onActivate(t.id);}}} tabIndex={t.id===active?0:-1}>
   {t.icon&&<Icon name={t.icon}/>}<span className="tab-title">{t.title}</span>
   {!t.pinned&&<button type="button" className="tab-close" aria-label={closeLabel+' '+t.title} onClick={e=>{e.stopPropagation();onClose(t.id);}}><Icon name="close"/></button>}
  </div>)}
 </div>;
}

export function BottomPanel({tabs,active,onSelect,onClose,children,actions}:{tabs:{id:string;label:string;count?:number}[];active:string;onSelect:(id:string)=>void;onClose:()=>void;children:ReactNode;actions?:ReactNode}){
 return <section className="bp" aria-label="Panel">
  <header><div role="tablist">{tabs.map(t=><button key={t.id} type="button" role="tab" aria-selected={t.id===active} className={t.id===active?'on':''} onClick={()=>onSelect(t.id)}>{t.label}{t.count?<em>{t.count}</em>:null}</button>)}</div>
   <div>{actions}<IconButton icon="close" label="Close panel" onClick={onClose}/></div></header>
  <div className="bp-body">{children}</div>
 </section>;
}

export type StatusItem={id:string;text:string;icon?:string;tone?:'warn'|'err'|'ok';title?:string;onClick?:()=>void};
export function StatusBar({left,right}:{left:StatusItem[];right:StatusItem[]}){
 const item=(i:StatusItem)=>{const body=<>{i.icon&&<Icon name={i.icon}/>}<span>{i.text}</span></>;
  return i.onClick?<button key={i.id} type="button" className={'si '+(i.tone||'')} title={i.title} onClick={i.onClick}>{body}</button>:<span key={i.id} className={'si static '+(i.tone||'')} title={i.title}>{body}</span>;};
 return <footer className="st" role="status"><div>{left.map(item)}</div><div>{right.map(item)}</div></footer>;
}

/** Command palette: type to filter, ↑/↓ to move, Enter to run, Esc to close; focus returns to the opener. */
export function Palette({commands,onClose,placeholder,empty}:{commands:Command[];onClose:()=>void;placeholder:string;empty:string}){
 const [q,setQ]=useState('');const [i,setI]=useState(0);const input=useRef<HTMLInputElement>(null);
 const opener=useRef<Element|null>(document.activeElement);
 const shown=useMemo(()=>(filterCommands(commands,q) as Command[]).slice(0,12),[commands,q]);
 useEffect(()=>{input.current?.focus();return()=>{(opener.current as HTMLElement|null)?.focus?.();};},[]);
 useEffect(()=>setI(0),[q]);
 const run=useCallback((c?:Command)=>{if(!c)return;onClose();c.run();},[onClose]);
 return <div className="pal-back" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}>
  <div className="pal" role="dialog" aria-modal="true" aria-label="Command palette">
   <input ref={input} className="k-input" value={q} placeholder={placeholder} aria-label={placeholder} role="combobox" aria-expanded="true" aria-controls="pal-list" aria-activedescendant={shown[i]?'pal-'+shown[i].id:undefined}
    onChange={e=>setQ(e.target.value)} onKeyDown={e=>{
     if(e.key==='Escape'){e.preventDefault();onClose();}
     else if(e.key==='ArrowDown'){e.preventDefault();setI(x=>Math.min(x+1,Math.max(0,shown.length-1)));}
     else if(e.key==='ArrowUp'){e.preventDefault();setI(x=>Math.max(0,x-1));}
     else if(e.key==='Enter'){e.preventDefault();run(shown[i]);}}}/>
   <ul id="pal-list" role="listbox">{shown.map((c,n)=><li key={c.id} id={'pal-'+c.id} role="option" aria-selected={n===i} className={n===i?'on':''} onMouseEnter={()=>setI(n)} onMouseDown={e=>{e.preventDefault();run(c);}}>
    <span>{c.label}</span>{c.hint&&<kbd>{c.hint}</kbd>}</li>)}{!shown.length&&<li className="empty">{empty}</li>}</ul>
  </div></div>;
}

/** Modal confirmation for approvals. Focus starts on the safe choice; Esc cancels. */
export function Dialog({title,children,onClose,actions}:{title:string;children:ReactNode;onClose:()=>void;actions:ReactNode}){
 useEffect(()=>{const h=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose();};window.addEventListener('keydown',h);return()=>window.removeEventListener('keydown',h);},[onClose]);
 return <div className="pal-back" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}>
  <div className="dlg" role="alertdialog" aria-modal="true" aria-label={title}><h2>{title}</h2><div className="dlg-body">{children}</div><footer>{actions}</footer></div></div>;
}
