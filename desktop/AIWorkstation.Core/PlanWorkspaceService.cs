using System.Security.Cryptography;
using System.Text;

namespace AIWorkstation.Core;

/// <summary>
/// Read-only, workspace-scoped access to Markdown plans. This is local file evidence,
/// never an AI-generated summary or a request to a model. The UI only observes files
/// while its plan page is open. All paths are checked again on each read.
/// </summary>
public static class PlanWorkspaceService
{
    public const int MaxDocuments = 80;
    public const long MaxDocumentBytes = 256 * 1024;

    public sealed record PlanFile(string Path, string Name, long Bytes, DateTimeOffset UpdatedAt, string Version);
    public sealed record PlanCatalog(string Workspace, IReadOnlyList<PlanFile> Files, DateTimeOffset CheckedAt, IReadOnlyList<string> Notices);
    public sealed record PlanDocument(string Path, string Text, string Version, DateTimeOffset UpdatedAt, long Bytes, string Sha256);

    // Explicitly scoped candidate directories. No recursive repository traversal or home-directory scans.
    private static readonly string[] PlanDirectories =
    [
        "", "docs", "plans", "planning", "docs/plans", "docs/planning", "docs/roadmaps",
        ".aiws/plans", ".claude/plans"
    ];

    public static PlanCatalog List(string workspace)
    {
        var root = WorkspaceGuard.RequireTrustedDirectory(workspace);
        var plans = new List<PlanFile>();
        var notices = new List<string>();
        var seen = new HashSet<string>(OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);
        foreach (var relativeDirectory in PlanDirectories)
        {
            if (plans.Count >= MaxDocuments) break;
            if (!TrySafeDirectory(root, relativeDirectory, out var directory)) continue;
            IEnumerable<string> files;
            try { files = Directory.EnumerateFiles(directory, "*", SearchOption.TopDirectoryOnly).ToArray(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                notices.Add("部分计划目录无读取权限，已跳过。");
                continue;
            }
            foreach (var path in files)
            {
                if (plans.Count >= MaxDocuments) break;
                var name = Path.GetFileName(path);
                if (!LooksLikePlan(name, relativeDirectory)) continue;
                var relative = Path.GetRelativePath(root, path).Replace('\\', '/');
                if (!IsAllowedPlanPath(relative) || !seen.Add(relative)) continue;
                try
                {
                    var safe = ProjectWorkspaceService.RequireSafeFile(root, relative);
                    var metadata = new FileInfo(safe);
                    if (!metadata.Exists || metadata.Attributes.HasFlag(FileAttributes.ReparsePoint)) continue;
                    if (metadata.Length > MaxDocumentBytes)
                    {
                        notices.Add("有计划文件超过 256 KiB 的展示上限，已跳过。");
                        continue;
                    }
                    plans.Add(new PlanFile(relative, name, metadata.Length, metadata.LastWriteTimeUtc,
                        $"{metadata.LastWriteTimeUtc.Ticks:x}-{metadata.Length:x}"));
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or InvalidOperationException)
                {
                    notices.Add("部分计划文件在扫描期间移动或被拒绝，已跳过。");
                }
            }
        }
        if (plans.Count >= MaxDocuments) notices.Add("达到 80 份文档展示上限；请按目录归档旧计划。");
        return new PlanCatalog(root, plans.OrderByDescending(x => x.UpdatedAt).ThenBy(x => x.Path, StringComparer.Ordinal).ToArray(),
            DateTimeOffset.UtcNow, notices.Distinct().Take(5).ToArray());
    }

    public static async Task<PlanDocument> ReadAsync(string workspace, string relative, CancellationToken cancellationToken = default)
    {
        if (!IsAllowedPlanPath(relative)) throw new ArgumentException("只允许查看当前工作区内约定位置的 Markdown 计划文件。", nameof(relative));
        var root = WorkspaceGuard.RequireTrustedDirectory(workspace);
        var full = ProjectWorkspaceService.RequireSafeFile(root, relative);
        // Explicit directory checks remain necessary even when the file is read via its resolved name.
        if (!TrySafeDirectory(root, Path.GetDirectoryName(relative)?.Replace('\\','/') ?? "", out _))
            throw new InvalidOperationException("计划文件的目录不安全或不存在。");
        var info = new FileInfo(full);
        if (!info.Exists || info.Attributes.HasFlag(FileAttributes.ReparsePoint))
            throw new FileNotFoundException("计划文件不存在或是符号链接。", relative);
        if (info.Length > MaxDocumentBytes) throw new InvalidDataException("计划文件超过 256 KiB 安全上限。请先拆分文档。");
        await using var stream = new FileStream(full, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete,
            16 * 1024, FileOptions.SequentialScan | FileOptions.Asynchronous);
        using var memory = new MemoryStream((int)Math.Min(info.Length, MaxDocumentBytes));
        var buffer = new byte[16 * 1024];
        while (true)
        {
            var count = await stream.ReadAsync(buffer, cancellationToken).ConfigureAwait(false);
            if (count == 0) break;
            if (memory.Length + count > MaxDocumentBytes) throw new InvalidDataException("计划文件在读取期间超过 256 KiB 上限。");
            memory.Write(buffer, 0, count);
        }
        var bytes = memory.ToArray();
        var text = new UTF8Encoding(false, true).GetString(bytes).TrimStart('\uFEFF');
        var sha = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        var finalInfo = new FileInfo(full);
        if (!finalInfo.Exists || finalInfo.Length != bytes.LongLength || finalInfo.LastWriteTimeUtc != info.LastWriteTimeUtc)
            throw new IOException("计划文件在读取期间发生变化，请在下一次刷新时重试。");
        var lastWrite = info.LastWriteTimeUtc;
        return new PlanDocument(relative, text, $"{lastWrite.Ticks:x}-{bytes.LongLength:x}", lastWrite, bytes.LongLength, sha);
    }

    public static bool IsAllowedPlanPath(string relative)
    {
        if (!ProjectWorkspaceService.IsSafeRelativePath(relative) || ProjectWorkspaceService.IsSensitiveName(relative)) return false;
        var segments = relative.Split('/');
        if (segments.Length == 0 || segments.Length > 4) return false;
        var dir = string.Join('/', segments.SkipLast(1));
        return PlanDirectories.Contains(dir, StringComparer.OrdinalIgnoreCase) && LooksLikePlan(segments[^1], dir);
    }

    private static bool LooksLikePlan(string name, string directory)
    {
        if (!name.EndsWith(".md", StringComparison.OrdinalIgnoreCase) &&
            !name.EndsWith(".markdown", StringComparison.OrdinalIgnoreCase)) return false;
        var stem = Path.GetFileNameWithoutExtension(name);
        if (string.IsNullOrWhiteSpace(stem) || stem.StartsWith('.')) return false;
        // Inside dedicated plan directories any Markdown filename is a plan.
        if (!string.IsNullOrEmpty(directory) && !directory.Equals("docs", StringComparison.OrdinalIgnoreCase)) return true;
        return stem.Contains("plan", StringComparison.OrdinalIgnoreCase)
            || stem.Contains("roadmap", StringComparison.OrdinalIgnoreCase)
            || stem.Equals("TODO", StringComparison.OrdinalIgnoreCase)
            || stem.Equals("TASKS", StringComparison.OrdinalIgnoreCase)
            || stem.Contains("计划", StringComparison.Ordinal)
            || stem.Contains("路线图", StringComparison.Ordinal)
            || stem.Contains("任务清单", StringComparison.Ordinal);
    }

    private static bool TrySafeDirectory(string root, string relative, out string directory)
    {
        directory = root;
        if (relative.Length == 0) return true;
        if (!ProjectWorkspaceService.IsSafeRelativePath(relative)) return false;
        foreach (var segment in relative.Split('/'))
        {
            directory = Path.Combine(directory, segment);
            if (!Directory.Exists(directory)) return false;
            try { if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0) return false; }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return false; }
        }
        return true;
    }
}
