---
name: summarize-project
title: Summarize an unfamiliar project
keywords: summary, overview, readme, project, 项目, 概览, 总结
requires: workspace.tree, file.read, ext.gitlog
---
1. workspace.tree with a small depth to see layout.
2. Read the README and the main manifest (package.json, pyproject.toml, Cargo.toml) only.
3. ext.gitlog for the last few commits to see what is active.
4. Output: purpose, how to run, main folders, current activity; at most 10 lines.
