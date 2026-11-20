import React from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import OsWorkbench from './os/OsWorkbench';
import './styles.css';
// Both Windows WebView2 and Linux guest use the same React workspace bundle.
// Only the guest-local service injects /os-bridge.js to activate Linux mode.
declare global {interface Window {__AIWS_OS_WORKBENCH__?:boolean}}
const guest=window.__AIWS_OS_WORKBENCH__===true;
createRoot(document.getElementById('root')!).render(<React.StrictMode>{guest?<OsWorkbench/>:<App/>}</React.StrictMode>);
