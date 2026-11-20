# T3 Code source attribution

Source: https://github.com/pingdotgg/t3code
Pinned review revision: `8e8ff9b243e5a4c3a837c9033a134b62aac7dade`
License: MIT — copyright © 2026 T3 Tools Inc.

Only two small presentational primitives are adapted into AIWS-owned React modules:

- `apps/web/src/components/ConnectionStatusDot.tsx` -> `desktop/AIWorkstation.Frontend/src/components/T3StatusDot.tsx`
- `apps/web/src/components/ui/skeleton.tsx` -> `desktop/AIWorkstation.Frontend/src/components/T3Skeleton.tsx`

These files were ported to remove T3 RPC, application state, Tailwind / Base UI hooks and imports.
No T3 server, entire application, OAuth store, or T3-internal API is bundled or rehosted.

The upstream MIT license (verbatim) is retained below:

MIT License

Copyright (c) 2026 T3 Tools Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
