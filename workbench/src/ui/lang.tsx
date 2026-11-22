import {createContext,useContext} from 'react';
import type {ReactNode} from 'react';

/** Language for components that carry their own built-in text (labels, tooltips, dialogs). Pages keep using tr(zh,en). */
const Ctx=createContext<boolean>(false);
export function LangProvider({english,children}:{english:boolean;children:ReactNode}){return <Ctx.Provider value={english}>{children}</Ctx.Provider>;}
export function useTr(){const en=useContext(Ctx);return (zh:string,e:string)=>en?e:zh;}
