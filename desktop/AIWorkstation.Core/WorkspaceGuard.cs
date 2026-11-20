namespace AIWorkstation.Core;

public static class WorkspaceGuard
{
    /// <summary>
    /// Validates a user-selected, local, non-root workspace. This is a preflight check,
    /// NOT a sandbox: native CLI processes still inherit the Windows account's rights.
    /// </summary>
    public static string RequireTrustedDirectory(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path.Trim()))
            throw new ArgumentException("请选择绝对路径的本地工作目录。");
        var resolved = Path.GetFullPath(path.Trim());
        if (!Directory.Exists(resolved)) throw new DirectoryNotFoundException("工作目录不存在。");
        if (OperatingSystem.IsWindows() && (resolved.StartsWith(@"\\", StringComparison.Ordinal) || resolved.StartsWith("//", StringComparison.Ordinal)))
            throw new InvalidOperationException("默认不允许将网络共享目录作为 Agent 工作区。");
        var root = Path.GetPathRoot(resolved)!;
        if (SamePath(resolved, root)) throw new InvalidOperationException("不可将整个磁盘根目录作为 Agent 工作区。");

        if (OperatingSystem.IsWindows())
        {
            var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            if (!string.IsNullOrWhiteSpace(home) && SamePath(resolved, home))
                throw new InvalidOperationException("不可将整个 Windows 用户主目录作为 Agent 工作区。");
            foreach (var restricted in new[]
            {
                Environment.GetFolderPath(Environment.SpecialFolder.Windows),
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)
            })
            {
                if (!string.IsNullOrWhiteSpace(restricted) && IsWithin(resolved, restricted))
                    throw new InvalidOperationException("系统目录和应用数据目录不能作为工作区。");
            }
        }
        // Symbolic links and Windows junctions may jump out of a checked path after validation.
        // Reject any reparse point in the existing chain; evaluate every component, not just leaf.
        var cursor = new DirectoryInfo(resolved);
        while (cursor != null)
        {
            if ((cursor.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new InvalidOperationException("工作区路径包含符号链接或目录联接。请使用实际的本地路径。");
            cursor = cursor.Parent;
        }
        return resolved;
    }

    private static bool SamePath(string path, string other)
        => string.Equals(Path.TrimEndingDirectorySeparator(Path.GetFullPath(path)),
            Path.TrimEndingDirectorySeparator(Path.GetFullPath(other)),
            OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal);

    private static bool IsWithin(string path, string root)
    {
        var normalized = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        return path.Equals(normalized, comparison)
            || path.StartsWith(normalized + Path.DirectorySeparatorChar, comparison);
    }
}
