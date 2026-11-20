using System.Security.Cryptography;
using System.Text;

namespace AIWorkstation.Core;

/// <summary>
/// Read-only workspace evidence, never an Agent execution API. Git status/HEAD are local
/// observations, not proof that a provider authored any particular change.
/// </summary>
public static class ProjectWorkspaceService
{
    public sealed record ProjectFile(string Path, bool IsDirectory, string Status, long? Size, bool IsLink);
    public sealed record ProjectOverview(string Workspace, string RootName, string Branch, string Head,
        IReadOnlyList<ProjectFile> Files, int ChangedCount, bool Truncated, IReadOnlyList<string> Notices);
    public sealed record FileReview(string Path, string Status, string Diff, bool Truncated, bool IsPreview, string Note);
    public sealed record GitObservedFile(string Path, string Status, string Signature);
    public sealed class GitCheckpoint
    {
        public DateTimeOffset CapturedAt { get; set; } = DateTimeOffset.UtcNow;
        public string Head { get; set; } = "";
        public List<GitObservedFile> Files { get; set; } = [];
        public bool Partial { get; set; }
        public string Problem { get; set; } = "";
    }
    public sealed record ObservedChange(string Path, string Kind, string Before, string After);
    public sealed record StageChangeReport(string StageId, string StageTitle, string FromHead, string ToHead,
        bool HeadChanged, IReadOnlyList<ObservedChange> Files, IReadOnlyList<string> CommittedFiles, bool Partial, string Notice,
        DateTimeOffset? StartedAt, DateTimeOffset? CompletedAt);

    private const int MaxNodes = 2500;
    private const int MaxDepth = 10;
    private const int MaxGitFiles = 800;
    private const long MaxHashBytes = 2_000_000;
    private const int MaxPreviewBytes = 24_000;
    private static readonly HashSet<string> SkippedDirectories = new(StringComparer.OrdinalIgnoreCase)
        { ".git", "node_modules", ".venv", "venv", "__pycache__", "bin", "obj", ".next", "dist", ".idea" };
    private static readonly HashSet<string> TextExtensions = new(StringComparer.OrdinalIgnoreCase)
        { ".cs", ".tsx", ".ts", ".js", ".jsx", ".mjs", ".py", ".json", ".md", ".txt", ".yaml", ".yml", ".xml", ".xaml", ".css", ".html", ".ps1", ".toml", ".sh", ".gitignore" };

    public static async Task<ProjectOverview> InspectAsync(string workspace, CancellationToken cancellationToken = default)
    {
        var root = WorkspaceGuard.RequireTrustedDirectory(workspace);
        var notices = new List<string>();
        var checkpoint = await CaptureAsync(root, cancellationToken).ConfigureAwait(false);
        if (!string.IsNullOrEmpty(checkpoint.Problem)) notices.Add(checkpoint.Problem);
        if (checkpoint.Partial) notices.Add("Git 状态超出采集上限，显示的是部分变更。不要据此判断仓库完全干净。");
        var status = checkpoint.Files.ToDictionary(x => x.Path, StringComparer.Ordinal);
        var tree = new List<ProjectFile>();
        var visited = new HashSet<string>(StringComparer.Ordinal);
        var pending = new Stack<(string Folder, int Depth)>();
        pending.Push((root, 0));
        var truncated = false;
        while (pending.Count > 0)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var (folder, depth) = pending.Pop();
            string[] children;
            try { children = Directory.EnumerateFileSystemEntries(folder).OrderBy(x => x, StringComparer.OrdinalIgnoreCase).ToArray(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                truncated = true;
                notices.Add("部分目录无法读取；请检查 Windows 文件权限。");
                continue;
            }
            foreach (var child in children)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (tree.Count >= MaxNodes) { truncated = true; break; }
                var name = Path.GetFileName(child);
                FileAttributes attr;
                try { attr = File.GetAttributes(child); }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
                {
                    truncated = true;
                    notices.Add("部分项目文件在扫描时已移动或无法读取。");
                    continue;
                }
                var directory = attr.HasFlag(FileAttributes.Directory);
                if (directory && SkippedDirectories.Contains(name)) continue;
                var link = attr.HasFlag(FileAttributes.ReparsePoint);
                var relative = Path.GetRelativePath(root, child).Replace('\\', '/');
                if (!IsSafeRelativePath(relative)) continue;
                visited.Add(relative);
                long? size = null;
                if (!directory && !link)
                {
                    try { size = new FileInfo(child).Length; }
                    catch (IOException) { /* Display file without size if it changed during scan. */ }
                }
                tree.Add(new ProjectFile(relative, directory, status.GetValueOrDefault(relative)?.Status ?? "", size, link));
                if (directory && !link)
                {
                    if (depth < MaxDepth) pending.Push((child, depth + 1));
                    else truncated = true;
                }
            }
            if (truncated) break;
        }
        foreach (var entry in checkpoint.Files)
        {
            if (!visited.Contains(entry.Path) && IsSafeRelativePath(entry.Path) && tree.Count < MaxNodes)
                tree.Add(new ProjectFile(entry.Path, false, entry.Status, null, false));
        }
        if (tree.Count >= MaxNodes) truncated = true;
        if (truncated) notices.Add("项目文件较多，文件树已限制数量或深度；Git 变更需结合状态检查。");
        var branch = "";
        if (string.IsNullOrEmpty(checkpoint.Problem))
        {
            try { branch = (await GitWorkspaceService.InspectAsync(root, "branch", cancellationToken).ConfigureAwait(false)).Output.Trim(); }
            catch (Exception ex) when (ex is IOException or InvalidOperationException or TimeoutException) { notices.Add("分支信息不可用。"); }
        }
        return new ProjectOverview(root, Path.GetFileName(root.TrimEnd(Path.DirectorySeparatorChar)), branch,
            checkpoint.Head, tree.OrderBy(x => x.Path, StringComparer.OrdinalIgnoreCase).ToList(),
            checkpoint.Files.Count, truncated || checkpoint.Partial, notices);
    }

    public static async Task<GitCheckpoint> CaptureAsync(string workspace, CancellationToken cancellationToken = default)
    {
        var root = WorkspaceGuard.RequireTrustedDirectory(workspace);
        var snapshot = new GitCheckpoint();
        try
        {
            var status = await GitWorkspaceService.InspectAsync(root, "porcelain", cancellationToken).ConfigureAwait(false);
            snapshot.Partial = status.Truncated;
            var parsed = ParsePorcelain(status.Output);
            if (parsed.Count > MaxGitFiles) snapshot.Partial = true;
            foreach (var item in parsed.Take(MaxGitFiles))
            {
                if (!IsSafeRelativePath(item.Path)) { snapshot.Partial = true; continue; }
                snapshot.Files.Add(new GitObservedFile(item.Path, item.Status, FileSignature(root, item.Path)));
            }
            try { snapshot.Head = (await GitWorkspaceService.InspectAsync(root, "head", cancellationToken).ConfigureAwait(false)).Output.Trim(); }
            catch (InvalidOperationException) { /* Repository may have an unborn HEAD. */ }
        }
        catch (Exception ex) when (ex is FileNotFoundException or InvalidOperationException or TimeoutException or IOException)
        {
            snapshot.Problem = "Git 状态不可用（不是 Git 仓库、Git 未安装或读取失败）：" + ex.Message;
            snapshot.Partial = true;
        }
        return snapshot;
    }

    /// <summary>Parse porcelain v1 -z. Rename/copy records carry an extra old path.</summary>
    public static IReadOnlyList<(string Path, string Status)> ParsePorcelain(string output)
    {
        var result = new List<(string Path, string Status)>();
        var chunks = output.Split('\0');
        for (var i = 0; i < chunks.Length; i++)
        {
            var item = chunks[i];
            if (item.Length < 4 || item[2] != ' ') continue;
            var state = item[..2];
            var name = item[3..];
            if (state.Contains('R') || state.Contains('C')) i++; // Next NUL item is old pathname.
            if (IsSafeRelativePath(name)) result.Add((name, state));
        }
        return result;
    }

    public static async Task<FileReview> ReviewAsync(string workspace, string relative, CancellationToken cancellationToken = default)
    {
        var root = WorkspaceGuard.RequireTrustedDirectory(workspace);
        var full = RequireSafeFile(root, relative);
        var checkpoint = await CaptureAsync(root, cancellationToken).ConfigureAwait(false);
        var status = checkpoint.Files.FirstOrDefault(x => x.Path == relative)?.Status ?? "";
        if (status == "??")
        {
            // The user explicitly selected this file. Never auto-ingest new files into Agent context.
            if (IsSensitiveName(relative)) return new FileReview(relative, status, "", false, false,
                "敏感文件只展示路径和 Git 状态，不预览内容。");
            if (!File.Exists(full)) return new FileReview(relative, status, "", false, false, "文件在读取前已移动或删除。");
            var info = new FileInfo(full);
            if (info.Length > MaxPreviewBytes || !TextExtensions.Contains(info.Extension))
                return new FileReview(relative, status, "", false, false, "新文件尚未加入 Git；文件过大或类型不支持安全文本预览。");
            var content = await File.ReadAllTextAsync(full, cancellationToken).ConfigureAwait(false);
            return new FileReview(relative, status, content, false, true, "未追踪文件的只读预览，不属于 Git Diff，也不会自动发送给模型。");
        }
        var working = await GitWorkspaceService.InspectFileAsync(root, relative, false, cancellationToken).ConfigureAwait(false);
        var staged = await GitWorkspaceService.InspectFileAsync(root, relative, true, cancellationToken).ConfigureAwait(false);
        var diff = new StringBuilder();
        if (!string.IsNullOrWhiteSpace(staged.Output) && staged.Output != "（无输出）") diff.AppendLine("[STAGED / 已暂存]").AppendLine(staged.Output);
        if (!string.IsNullOrWhiteSpace(working.Output) && working.Output != "（无输出）") diff.AppendLine("[WORKTREE / 未暂存]").AppendLine(working.Output);
        if (diff.Length == 0) diff.Append("当前工作区无该文件的未提交 Git Diff；可在 Git 历史中查看已提交变更。");
        return new FileReview(relative, status, diff.ToString(), staged.Truncated || working.Truncated, false,
            "本地只读 Git Diff；不会自动传给任何模型。工作区文件可能在读取时继续变化。");
    }

    public static StageChangeReport Compare(string stepId, string stepTitle, GitCheckpoint? before, GitCheckpoint? after,
        DateTimeOffset? started = null, DateTimeOffset? completed = null)
    {
        if (before is null || after is null)
            return new StageChangeReport(stepId, stepTitle, before?.Head ?? "", after?.Head ?? "", false, [], [], true,
                "缺少阶段 Git 检查点。仅展示可验证的本地证据，不能推断 AI 是否修改了文件。", started, completed);
        var left = before.Files.ToDictionary(x => x.Path, StringComparer.Ordinal);
        var right = after.Files.ToDictionary(x => x.Path, StringComparer.Ordinal);
        var entries = new List<ObservedChange>();
        foreach (var name in left.Keys.Union(right.Keys, StringComparer.Ordinal).OrderBy(x => x, StringComparer.Ordinal))
        {
            left.TryGetValue(name, out var a);
            right.TryGetValue(name, out var b);
            if (a?.Status == b?.Status && a?.Signature == b?.Signature) continue;
            var kind = a is null ? "appeared" : b is null ? "cleared" : "changed";
            entries.Add(new ObservedChange(name, kind, a?.Status ?? "", b?.Status ?? ""));
        }
        var changedHead = !string.IsNullOrEmpty(before.Head) && !string.IsNullOrEmpty(after.Head)
            && before.Head != after.Head;
        var partial = before.Partial || after.Partial || before.Problem.Length > 0 || after.Problem.Length > 0;
        var note = partial ? "Git 证据不完整，不能据此证明没有其他修改。"
            : "只表示这两个检查点之间工作区观察到的变化；不能证明由哪个 Agent 或用户产生。中途改动又撤销也可能无法呈现。";
        return new StageChangeReport(stepId, stepTitle, before.Head, after.Head, changedHead, entries, [], partial,
            note, started, completed);
    }

    /// <summary>Enrich checkpoint comparison with the set of paths in commits created between HEADs.</summary>
    public static async Task<StageChangeReport> AnalyzeStageAsync(string workspace, string stepId, string stepTitle,
        GitCheckpoint? before, GitCheckpoint? after, DateTimeOffset? started = null,
        DateTimeOffset? completed = null, CancellationToken cancellationToken = default)
    {
        var baseReport = Compare(stepId, stepTitle, before, after, started, completed);
        if (!baseReport.HeadChanged) return baseReport;
        try
        {
            var inspection = await GitWorkspaceService.InspectCommitFilesAsync(workspace,
                baseReport.FromHead, baseReport.ToHead, cancellationToken).ConfigureAwait(false);
            var paths = ParseCommitPaths(inspection.Output);
            return baseReport with { CommittedFiles = paths,
                Partial = baseReport.Partial || inspection.Truncated,
                Notice = baseReport.Notice + (inspection.Truncated ? " 提交文件清单已截断。" : " 已追加实际提交涉及的文件路径。") };
        }
        catch (Exception ex) when (ex is IOException or InvalidOperationException or TimeoutException or ArgumentException)
        {
            return baseReport with { Partial = true, Notice = baseReport.Notice + " 提交路径无法核验，请检查 Git 历史。" };
        }
    }

    public static IReadOnlyList<string> ParseCommitPaths(string output)
    {
        var fields = output.Split('\0');
        var paths = new List<string>();
        for (var i = 0; i < fields.Length - 1;)
        {
            var status = fields[i++];
            if (status.Length == 0) continue;
            var rename = status.StartsWith('R') || status.StartsWith('C');
            if (i >= fields.Length) break;
            var path = fields[i++];
            if (rename && i < fields.Length) path = fields[i++]; // New path for rename/copy.
            if (IsSafeRelativePath(path)) paths.Add(path);
            if (paths.Count >= 300) break;
        }
        return paths;
    }

    public static string RequireSafeFile(string workspace, string relative)
    {
        if (!IsSafeRelativePath(relative)) throw new ArgumentException("文件路径不在当前工作区内。", nameof(relative));
        var root = WorkspaceGuard.RequireTrustedDirectory(workspace);
        var full = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
        var comparer = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        if (!full.StartsWith(Path.TrimEndingDirectorySeparator(root) + Path.DirectorySeparatorChar, comparer))
            throw new ArgumentException("文件路径越过工作区边界。", nameof(relative));
        var cursor = Path.GetDirectoryName(full);
        while (cursor is not null && !string.Equals(cursor, root, comparer))
        {
            if (Directory.Exists(cursor) && (File.GetAttributes(cursor) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidOperationException("文件路径经过符号链接或目录联接。拒绝访问。");
            cursor = Path.GetDirectoryName(cursor);
        }
        if (File.Exists(full) && (File.GetAttributes(full) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidOperationException("文件是符号链接。拒绝访问。");
        return full;
    }

    public static bool IsSafeRelativePath(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || path.Length > 1024 || path.Contains('\0') || path.Contains('\\')
            || path.Contains(':') || path.StartsWith('/') || Path.IsPathRooted(path)) return false;
        return path.Split('/').All(segment => segment is not ("" or "." or "..")
            && !segment.Equals(".git", StringComparison.OrdinalIgnoreCase));
    }

    private static bool IsSensitiveName(string path)
    {
        var name = Path.GetFileName(path);
        return name.StartsWith(".env", StringComparison.OrdinalIgnoreCase)
            || name.Contains("secret", StringComparison.OrdinalIgnoreCase)
            || name.Contains("credential", StringComparison.OrdinalIgnoreCase)
            || name.Contains("token", StringComparison.OrdinalIgnoreCase)
            || name.EndsWith(".key", StringComparison.OrdinalIgnoreCase)
            || name.EndsWith(".pem", StringComparison.OrdinalIgnoreCase);
    }

    private static string FileSignature(string root, string relative)
    {
        try
        {
            var path = RequireSafeFile(root, relative);
            if (!File.Exists(path)) return "missing";
            var info = new FileInfo(path);
            if (info.Length > MaxHashBytes) return "large:" + info.Length + ":" + info.LastWriteTimeUtc.Ticks;
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            return Convert.ToHexString(SHA256.HashData(stream));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            return "unreadable";
        }
    }
}
