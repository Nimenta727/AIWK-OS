using System.IO;

namespace AIWorkstation.Core;

/// <summary>
/// Projects two bounded, local directory inventories and Git checkpoints into a structural
/// change tree. Observations are never proof that a specific model wrote the files.
/// No source contents are retained and no model is called.
/// </summary>
public static class WorkspaceEvolutionService
{
    public sealed record StructureEntry(string Path, bool IsDirectory, bool Before, bool After,
        string Change, string Evidence);
    public sealed record StructureReport(string StageId, string StageTitle, string Workspace,
        bool HasBefore, bool HasAfter, bool Partial, string Notice,
        DateTimeOffset? BeforeAt, DateTimeOffset? AfterAt,
        IReadOnlyList<StructureEntry> Entries, int Added, int Removed, int Modified, int ChangedDirectories,
        IReadOnlyList<string> CommittedFiles,
        IReadOnlyList<ProjectWorkspaceService.ObservedRename> RenamedFiles);
    public sealed record RelatedStage(string StageId, string Title, string Agent,
        string Workspace, string Evidence, bool Partial);
    public sealed record RelatedStageLookup(IReadOnlyList<RelatedStage> Stages, bool Partial, string Notice);

    public static StructureReport Compare(WorkTask task, WorkflowStep step,
        ProjectWorkspaceService.GitCheckpoint? before,
        ProjectWorkspaceService.GitCheckpoint? after,
        ProjectWorkspaceService.StageChangeReport evidence)
    {
        bool hasBefore = before?.TreeCaptured == true;
        bool hasAfter = after?.TreeCaptured == true;
        bool comparable = hasBefore && hasAfter;
        var left = (hasBefore ? before!.Tree : new List<ProjectWorkspaceService.StructurePath>())
            .Where(x => ProjectWorkspaceService.IsSafeRelativePath(x.Path))
            .ToDictionary(x => x.Path, x => x.IsDirectory, StringComparer.Ordinal);
        var right = (hasAfter ? after!.Tree : new List<ProjectWorkspaceService.StructurePath>())
            .Where(x => ProjectWorkspaceService.IsSafeRelativePath(x.Path))
            .ToDictionary(x => x.Path, x => x.IsDirectory, StringComparer.Ordinal);
        var changed = new HashSet<string>(evidence.Files.Select(x => x.Path), StringComparer.Ordinal);
        changed.UnionWith(evidence.CommittedFiles, evidence.RenamedFiles);
        var knownGit = new HashSet<string>(changed.Where(ProjectWorkspaceService.IsSafeRelativePath), StringComparer.Ordinal);
        var entries = new List<StructureEntry>();
        var movedIn = evidence.RenamedFiles.ToDictionary(x => x.ToPath, x => x.FromPath, StringComparer.Ordinal);
        var movedOut = evidence.RenamedFiles.ToDictionary(x => x.FromPath, x => x.ToPath, StringComparer.Ordinal);
        foreach (var path in left.Keys.Union(right.Keys, StringComparer.Ordinal).OrderBy(x => x, StringComparer.Ordinal))
        {
            var inLeft = left.TryGetValue(path, out var ld);
            var inRight = right.TryGetValue(path, out var rd);
            var directory = inRight ? rd : ld;
            string change;
            string source;
            if (!comparable)
            {
                change = "unknown";
                source = "目录快照不完整，不能把缺失的一侧当作删除或新增";
            }
            else if (!inLeft && before?.TreePartial == true) { change = "unknown"; source = "起点目录扫描被截断"; }
            else if (!inLeft && movedIn.TryGetValue(path, out var sourcePath))
            { change = "moved-in"; source = "Git 明确认定重命名：" + sourcePath; }
            else if (!inLeft) { change = "added"; source = "目录前后快照"; }
            else if (!inRight && after?.TreePartial == true) { change = "unknown"; source = "终点目录扫描被截断"; }
            else if (!inRight && movedOut.TryGetValue(path, out var destinationPath))
            { change = "moved-out"; source = "Git 明确认定重命名至：" + destinationPath; }
            else if (!inRight) { change = "removed"; source = "目录前后快照"; }
            else if (ld != rd) { change = "replaced"; source = "目录/文件类型变化"; }
            else if (!directory && knownGit.Contains(path))
            {
                change = "modified";
                source = evidence.CommittedFiles.Contains(path, StringComparer.Ordinal)
                    ? "Git HEAD 对比中的提交路径；不证明作者"
                    : "阶段 Git 状态或文件签名；不证明作者";
            }
            else { change = "unchanged"; source = "目录存在性快照"; }
            entries.Add(new StructureEntry(path, directory, inLeft, inRight, change, source));
        }

        // Git can report tracked paths deleted from both inventories, or paths inside skipped folders.
        // Keep them as evidence, but do not invent their before/after existence.
        foreach (var path in knownGit.OrderBy(x => x, StringComparer.Ordinal))
        {
            if (entries.Any(x => x.Path == path)) continue;
            entries.Add(new StructureEntry(path, false, false, false, "unknown", "Git 变更路径（目录采集未覆盖）"));
        }
        if (comparable)
        {
            var touched = entries.Where(x => !x.IsDirectory && x.Change is not "unchanged" and not "unknown")
                .SelectMany(x => Ancestors(x.Path)).ToHashSet(StringComparer.Ordinal);
            for (int i = 0; i < entries.Count; i++)
            {
                var item = entries[i];
                if (item.IsDirectory && item.Change == "unchanged" && touched.Contains(item.Path))
                    entries[i] = item with { Change = "touched", Evidence = "子文件或子目录发生变化" };
            }
        }
        var partial = !comparable || before?.Partial == true || after?.Partial == true
            || before?.TreePartial == true || after?.TreePartial == true || evidence.Partial;
        var notice = !comparable
            ? "当前阶段缺少至少一个完整目录检查点。老任务或未结束任务只显示已有结构，不推断缺失路径的增删。"
            : partial
                ? "结构或 Git 证据被截断、不可读或缺失。所列差异仅为已经观察到的部分。"
                : "比较两个本地目录快照及 Git 证据；表示结构变化，不证明某个 Agent 是代码作者。";
        return new StructureReport(step.Id, step.Title, task.WorkspaceFor(step), hasBefore, hasAfter,
            partial, notice, hasBefore ? before?.CapturedAt : null, hasAfter ? after?.CapturedAt : null,
            entries.OrderBy(x => x.Path, StringComparer.Ordinal).ToArray(),
            entries.Count(x => !x.IsDirectory && x.Change == "added"),
            entries.Count(x => !x.IsDirectory && x.Change == "removed"),
            entries.Count(x => !x.IsDirectory && x.Change == "modified"),
            entries.Count(x => x.IsDirectory && x.Change is "touched" or "added" or "removed" or "replaced"),
            evidence.CommittedFiles, evidence.RenamedFiles);
    }

    private static IEnumerable<string> Ancestors(string path)
    {
        var index = path.IndexOf('/');
        while (index > 0)
        {
            yield return path[..index];
            index = path.IndexOf('/', index + 1);
        }
    }

    public static async Task<StructureReport> InspectStageAsync(WorkTask task, WorkflowStep step,
        CancellationToken cancellationToken = default)
    {
        var workspace = task.WorkspaceFor(step);
        var after = step.Status == StepStatus.Running
            ? await ProjectWorkspaceService.CaptureAsync(workspace, cancellationToken).ConfigureAwait(false)
            : step.GitAfter;
        var evidence = await ProjectWorkspaceService.AnalyzeStageAsync(workspace, step.Id, step.Title,
            step.GitBefore, after, step.StartedAt, step.CompletedAt, cancellationToken).ConfigureAwait(false);
        return Compare(task, step, step.GitBefore, after, evidence);
    }

    public static async Task<RelatedStageLookup> FindRelatedStagesAsync(WorkTask task, string path,
        CancellationToken cancellationToken = default)
    {
        if (!ProjectWorkspaceService.IsSafeRelativePath(path))
            throw new ArgumentException("拒绝不安全的相对路径。", nameof(path));
        var found = new List<RelatedStage>();
        var incomplete = task.Steps.Count > 40;
        // This runs only on an explicit file selection. Avoid unbounded Git queries.
        foreach (var step in task.Steps.Take(40))
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (step.GitBefore is null) continue;
            try
            {
                var report = await InspectStageAsync(task, step, cancellationToken).ConfigureAwait(false);
                incomplete |= report.Partial;
                var entry = report.Entries.FirstOrDefault(x => x.Path == path && x.Change is not "unchanged" and not "unknown");
                if (entry is not null)
                    found.Add(new RelatedStage(step.Id, step.Title, AgentLabel.Name(step.Agent),
                        report.Workspace, entry.Evidence, report.Partial));
            }
            catch (Exception ex) when (ex is IOException or InvalidOperationException or UnauthorizedAccessException or TimeoutException or ArgumentException)
            {
                incomplete = true; // Missing worktree/modified Git history is not proof of no change.
            }
        }
        return new RelatedStageLookup(found, incomplete,
            incomplete ? "阶段证据不完整或超过前 40 个阶段的检索上限，未列出的阶段仍可能相关。" :
                "仅表示阶段前后检查点或提交路径中观察到变化；不能证明该 Agent 是作者。");
    }
}
