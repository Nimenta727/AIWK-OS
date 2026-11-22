import {forwardRef,useId,useState} from 'react';
import type {ButtonHTMLAttributes,InputHTMLAttributes,ReactNode,SelectHTMLAttributes} from 'react';

/** Codicon by name, e.g. <Icon name="git-compare"/>. Decorative unless a label is given. */
export function Icon({name,label,spin}:{name:string;label?:string;spin?:boolean}){
 return <span className={'codicon codicon-'+name+(spin?' codicon-modifier-spin':'')} role={label?'img':undefined} aria-label={label} aria-hidden={label?undefined:true}/>;
}

type BtnProps=ButtonHTMLAttributes<HTMLButtonElement>&{variant?:'primary'|'secondary'|'ghost';icon?:string};
export const Button=forwardRef<HTMLButtonElement,BtnProps>(function Button({variant='secondary',icon,children,className,type='button',...p},ref){
 return <button ref={ref} type={type} className={'k-btn k-btn-'+variant+(className?' '+className:'')} {...p}>{icon&&<Icon name={icon}/>}{children&&<span>{children}</span>}</button>;
});
/** Icon-only button. `label` is required: it is the tooltip and the accessible name. */
export function IconButton({icon,label,on,...p}:Omit<ButtonHTMLAttributes<HTMLButtonElement>,'children'>&{icon:string;label:string;on?:boolean}){
 return <button type="button" className={'k-ibtn'+(on?' on':'')} title={label} aria-label={label} aria-pressed={on} {...p}><Icon name={icon}/></button>;
}
export function Badge({children,tone}:{children:ReactNode;tone?:'ok'|'warn'|'err'|'info'}){return <span className={'k-badge'+(tone?' '+tone:'')}>{children}</span>;}
export function Input(p:InputHTMLAttributes<HTMLInputElement>){return <input className="k-input" spellCheck={false} {...p}/>;}
export function Select(p:SelectHTMLAttributes<HTMLSelectElement>){return <select className="k-input k-select" {...p}/>;}
export function Check({label,checked,onChange,disabled}:{label:string;checked:boolean;onChange:(v:boolean)=>void;disabled?:boolean}){
 const id=useId();
 return <label className="k-check" htmlFor={id}><input id={id} type="checkbox" checked={checked} disabled={disabled} onChange={e=>onChange(e.target.checked)}/><span>{label}</span></label>;
}
export function Progress({value,max,tone}:{value:number;max:number;tone?:'ok'|'warn'|'err'}){
 const pct=max>0?Math.max(0,Math.min(100,value*100/max)):0;
 return <div className={'k-progress'+(tone?' '+tone:'')} role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}><i style={{width:pct+'%'}}/></div>;
}
/** Collapsible section header like the Explorer's "OUTLINE" blocks. */
export function Section({title,count,defaultOpen=true,actions,children}:{title:string;count?:number;defaultOpen?:boolean;actions?:ReactNode;children:ReactNode}){
 const [open,setOpen]=useState(defaultOpen);
 return <section className="k-section">
  <div className="k-section-head"><button type="button" aria-expanded={open} onClick={()=>setOpen(o=>!o)}><Icon name={open?'chevron-down':'chevron-right'}/><span>{title}</span>{count!==undefined&&<em>{count}</em>}</button><div>{actions}</div></div>
  {open&&<div className="k-section-body">{children}</div>}
 </section>;
}
export function Row({icon,tone,label,detail,on,depth=0,onClick,onDoubleClick,title,right,expanded}:{icon?:string;tone?:'ok'|'warn'|'err'|'off';label:ReactNode;detail?:ReactNode;on?:boolean;depth?:number;onClick?:()=>void;onDoubleClick?:()=>void;title?:string;right?:ReactNode;expanded?:boolean}){
 const interactive=!!onClick;
 return <div className={'k-row'+(on?' on':'')+(interactive?'':' static')+(tone?' t-'+tone:'')} role={interactive?'treeitem':undefined} aria-selected={interactive?!!on:undefined} aria-expanded={expanded}
  tabIndex={interactive?0:undefined} style={{paddingLeft:8+depth*12}} title={title} onClick={onClick} onDoubleClick={onDoubleClick}
  onKeyDown={e=>{if(interactive&&(e.key==='Enter'||e.key===' ')){e.preventDefault();onClick?.();}}}>
  {expanded!==undefined?<Icon name={expanded?'chevron-down':'chevron-right'}/>:<span className="k-row-gap"/>}
  {icon&&<Icon name={icon}/>}<span className="k-row-label">{label}</span>{detail&&<span className="k-row-detail">{detail}</span>}{right&&<span className="k-row-right">{right}</span>}
 </div>;
}
export function Empty({icon='info',title,children}:{icon?:string;title:string;children?:ReactNode}){
 return <div className="k-empty"><Icon name={icon}/><h3>{title}</h3>{children&&<p>{children}</p>}</div>;
}
export function Notice({tone='info',children}:{tone?:'info'|'warn'|'err'|'ok';children:ReactNode}){
 const icon={info:'info',warn:'warning',err:'error',ok:'pass'}[tone];
 return <div className={'k-notice '+tone} role={tone==='err'?'alert':'status'}><Icon name={icon}/><div>{children}</div></div>;
}
