namespace AIWorkstation.Core;

public static class WorkspaceGuard
{
    public static string RequireTrustedDirectory(string path)
    {
        if (string.IsNullOrWhiteSpace(path)) throw new ArgumentException("请选择工作目录。");
        var resolved = Path.GetFullPath(path.Trim());
        if (!Directory.Exists(resolved)) throw new DirectoryNotFoundException("工作目录不存在。");
        var root = Path.GetPathRoot(resolved)!;
        if (string.Equals(root.TrimEnd(Path.DirectorySeparatorChar), resolved.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("不可将整个磁盘根目录作为 Agent 工作区。");
        if (OperatingSystem.IsWindows())
        {
            foreach (var restricted in new[] { Environment.GetFolderPath(Environment.SpecialFolder.Windows), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) })
            {
                if (!string.IsNullOrWhiteSpace(restricted) && IsWithin(resolved, restricted))
                    throw new InvalidOperationException("系统目录和应用数据目录不能作为工作区。");
            }
        }
        return resolved;
    }

    private static bool IsWithin(string path, string root)
    {
        var normalized = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        return path.Equals(normalized, StringComparison.OrdinalIgnoreCase)
            || path.StartsWith(normalized + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
    }
}
