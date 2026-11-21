---
name: review-changes
title: Review what changed in a project
keywords: review, diff, changes, git, 变更, 审查, 改动
requires: git.inspect, ext.gitlog, file.read
---
1. Run git.inspect to list changed files and the current branch.
2. For each changed file read only the changed region with file.read; do not read whole files.
3. Report per file: what changed, whether it matches the task, and anything risky (deleted data, widened permissions, new network access).
4. Never modify anything while reviewing.
