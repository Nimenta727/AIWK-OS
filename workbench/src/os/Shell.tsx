import {useEffect,useMemo,useRef,useState} from 'react';
import type {ReactNode} from 'react';
import {X} from 'lucide-react';
import {filterCommands} from '../model/shell.mjs';

export type Tab={id:string;kind:string;title:string;pinned?:boolean;path?:string};
export type Command={id:string;label:string;keywords?:string;hint?:string;run:()=>void};

/** Left strip of icons (the "activity bar"). Buttons are real <button>s so keyboard and screen readers work. */
export function ActivityBar({items,active,sidebarOpen,onSelect,bottom}:{
 items:{id:string;label:string;icon:ReactNode;badge?:number}[];active:string;sidebarOpen:boolean;
 onSelect:(id:string)=>void;bottom:{id:string;label:string;icon:ReactNode;onClick:()=>void;pressed?:boolean}[]
}){
 return <nav className="aiws-sh-activity" aria-label="Views">
  <div>{items.map(i=><button key={i.id} type="button" title={i.label} aria-label={i.label} aria-pressed={sidebarOpen&&active===i.id}
    className={sidebarOpen&&active===i.id?'on':''} onClick={()=>onSelect(i.id)}>{i.icon}
    {i.badge?<span className="aiws-sh-badge">{i.badge>9?'9+':i.badge}</span>:null}</button>)}</div>
  <div>{bottom.map(b=><button key={b.id} type="button" title={b.label} aria-label={b.label} aria-pressed={b.pressed}
    className={b.pressed?'on':''} onClick={b.onClick}>{b.icon}</button>)}</div>
 </nav>;
}

export function SideBar({title,actions,children}:{title:string;actions?:ReactNode;children:ReactNode}){
 return <aside className="aiws-sh-side" aria-label={title}>
  <header><span>{title}</span><div>{actions}</div></header>
  <div className="aiws-sh-side-body">{children}</div>
 </aside>;
}

export function TabBar({tabs,active,onActivate,onClose,closeLabel}:{
 tabs:Tab[];active:string|null;onActivate:(id:string)=>void;onClose:(id:string)=>void;closeLabel:string
}){
 return <div className="aiws-sh-tabs" role="tablist">
  {tabs.map(t=><div key={t.id} role="tab" aria-selected={t.id===active} className={'aiws-sh-tab'+(t.id===active?' on':'')}
    onMouseDown={e=>{if(e.button===1&&!t.pinned){e.preventDefault();onClose(t.id);}}}>
   <button type="button" className="aiws-sh-tab-title" onClick={()=>onActivate(t.id)} title={t.path||t.title}>{t.title}</button>
   {!t.pinned&&<button type="button" className="aiws-sh-tab-close" aria-label={closeLabel+' '+t.title} onClick={()=>onClose(t.id)}><X size={12}/></button>}
  </div>)}
 </div>;
}

export function Panel({tabs,active,onSelect,onClose,children}:{
 tabs:{id:string;label:string}[];active:string;onSelect:(id:string)=>void;onClose:()=>void;children:ReactNode
}){
 return <section className="aiws-sh-panel" aria-label="Panel">
  <header><div role="tablist">{tabs.map(t=><button key={t.id} type="button" role="tab" aria-selected={t.id===active}
    className={t.id===active?'on':''} onClick={()=>onSelect(t.id)}>{t.label}</button>)}</div>
   <button type="button" className="aiws-sh-panel-close" aria-label="Close panel" onClick={onClose}><X size={14}/></button></header>
  <div className="aiws-sh-panel-body">{children}</div>
 </section>;
}

export function StatusBar({left,right}:{left:{id:string;text:string;tone?:string;title?:string;onClick?:()=>void}[];right:{id:string;text:string;title?:string;onClick?:()=>void}[]}){
 const item=(i:{id:string;text:string;tone?:string;title?:string;onClick?:()=>void})=>i.onClick?
  <button key={i.id} type="button" className={'aiws-sh-status-item '+(i.tone||'')} title={i.title} onClick={i.onClick}>{i.text}</button>:
  <span key={i.id} className={'aiws-sh-status-item '+(i.tone||'')} title={i.title}>{i.text}</span>;
 return <footer className="aiws-sh-status" role="status"><div>{left.map(item)}</div><div>{right.map(item)}</div></footer>;
}

/** Command palette: type to filter, Up/Down to move, Enter to run, Escape to close. Focus is trapped in the input. */
export function CommandPalette({commands,onClose,placeholder,empty}:{commands:Command[];onClose:()=>void;placeholder:string;empty:string}){
 const [query,setQuery]=useState('');
 const [index,setIndex]=useState(0);
 const input=useRef<HTMLInputElement>(null);
 const shown=useMemo(()=>filterCommands(commands,query) as Command[],[commands,query]);
 useEffect(()=>{input.current?.focus();},[]);
 useEffect(()=>{setIndex(0);},[query]);
 const run=(c?:Command)=>{if(!c)return;onClose();c.run();};
 return <div className="aiws-sh-palette-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}>
  <div className="aiws-sh-palette" role="dialog" aria-modal="true" aria-label="Command palette">
   <input ref={input} value={query} placeholder={placeholder} aria-label={placeholder} spellCheck={false}
    onChange={e=>setQuery(e.target.value)}
    onKeyDown={e=>{
     if(e.key==='Escape'){e.preventDefault();onClose();}
     else if(e.key==='ArrowDown'){e.preventDefault();setIndex(i=>Math.min(i+1,Math.max(0,shown.length-1)));}
     else if(e.key==='ArrowUp'){e.preventDefault();setIndex(i=>Math.max(0,i-1));}
     else if(e.key==='Enter'){e.preventDefault();run(shown[index]);}
    }}/>
   <ul role="listbox">{shown.slice(0,12).map((c,i)=><li key={c.id} role="option" aria-selected={i===index} className={i===index?'on':''}
     onMouseEnter={()=>setIndex(i)} onMouseDown={e=>{e.preventDefault();run(c);}}><span>{c.label}</span>{c.hint&&<kbd>{c.hint}</kbd>}</li>)}
    {!shown.length&&<li className="empty">{empty}</li>}</ul>
  </div>
 </div>;
}
