---
name: check-resources
title: Check memory, disk and model load
keywords: memory, disk, cpu, slow, resource, 内存, 磁盘, 卡顿, 资源
requires: system.info, runtime.detect
---
1. Read system.info for memory, disk and CPU.
2. Flag memory above 85 percent, disk above 90 percent.
3. State plainly which resource is the limit; suggest closing the local model (it unloads when idle) before anything else.
