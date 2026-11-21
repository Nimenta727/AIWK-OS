# AIWS Code: provenance and licensing

AIWS Code is a **rebranded build of the open-source "Code - OSS" project**
(https://github.com/microsoft/vscode), which is licensed under the **MIT License**, Copyright (c) 2015 - present
Microsoft Corporation.

**It is not a Microsoft product, it is not "Visual Studio Code", and it is not endorsed by Microsoft.**

## What the MIT license requires, and what we do
* The upstream copyright notice and the MIT permission notice must be included in all copies or substantial portions
  of the software. Every AIWS Code package therefore ships `LICENSE.txt` (the upstream MIT text, unchanged) and
  `ThirdPartyNotices.txt` (upstream's notices for the many components it bundles). **These files are never removed or edited.**
* AIWS's own additions (branding, launcher, build scripts, patches) are licensed under this repository's own `LICENSE` (Apache-2.0); the upstream Code - OSS code stays MIT.

## What we deliberately do NOT reuse
* Microsoft's names, logos, icons and other trademarks ("Visual Studio Code", "VS Code", the blue logo, ...).
  They are not licensed by the MIT license. AIWS Code uses its own name and its own original artwork
  (`branding/aiws-code.svg`).
* Microsoft's proprietary distribution and services: the "Visual Studio Marketplace", Microsoft's update service,
  telemetry endpoints, GitHub Copilot defaults and the vscode-cdn.net webview CDN. Extensions come from the open
  registry Open VSX (or local .vsix files).
* Microsoft's proprietary extensions (for example Pylance, C# Dev Kit, Remote-SSH) are not included and generally
  cannot be used with this build.

## Rebrand is not relicensing
Changing names and icons does not change the license of the code, and nothing here removes the original authors' credit.
If you redistribute AIWS Code, keep `LICENSE.txt`, `ThirdPartyNotices.txt` and this file with it.
