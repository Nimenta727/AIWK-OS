---
name: read-log
description: Find out why a job failed from a long log file. Use when the user asks to read, check or explain a log, build output, test output or crash output. 排查日志、构建输出、测试输出或崩溃输出里失败的原因，用于“读日志”“看报错”“为什么失败”。
license: Apache-2.0
allowed-tools: log.digest log.lines code.search file.stat
---
1. Call log.digest on the file first. It merges repeated messages and shows each one with the FIRST line number where it appeared.
2. The cause is usually the FIRST sign of trouble, not the last error. Harmless "error" lines that appear early and never change the outcome
   (a missing optional plugin, a skipped cache) are not the cause. Warnings about space, memory, permissions, connections or empty files
   often come just before the failure and are easy to miss because they do not say "error".
3. Open the real lines around the likely cause with log.lines (about 10 lines before and 10 after). Quote them as they are.
4. Answer in the user's language with: what failed, the line number(s), and the exact log line(s) in quotes. If you are not sure, say so
   and give the next line range worth opening. Never invent a line that is not in the log.
