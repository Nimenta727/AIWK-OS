import React from 'react';
import {createRoot} from 'react-dom/client';
import OsWorkbench from './os/OsWorkbench';

createRoot(document.getElementById('root')!).render(<React.StrictMode><OsWorkbench/></React.StrictMode>);
