import {defineConfig} from '@playwright/test';

// Windows CI already ships Microsoft Edge; no Chromium download is needed.
// This exercises the compiled, offline AIWS React bundle with a deterministic
// *fake* native bridge. It does not execute Git, shell, or any model request.
export default defineConfig({
 testDir:'./tests/e2e',
 testMatch:'*.spec.mjs',
 timeout:30_000,
 expect:{timeout:8_000},
 workers:1,
 reporter:'list',
 use:{baseURL:'http://127.0.0.1:4173',browserName:'chromium',channel:'msedge',headless:true,viewport:{width:1440,height:900},trace:'retain-on-failure'},
 webServer:{command:'npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',url:'http://127.0.0.1:4173',reuseExistingServer:!process.env.CI,timeout:30_000},
});
