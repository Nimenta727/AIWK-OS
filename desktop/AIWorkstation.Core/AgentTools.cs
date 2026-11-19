using System.Diagnostics;

namespace AIWorkstation.Core;

public static class AgentTools
{
    private static readonly string[] Extensions = OperatingSystem.IsWindows()
        ? [".exe", ".cmd", ".bat"] : [""];

    public static string? Locate(string name)
    {
        if (name is not ("claude" or "codex" or "t3" or "openclaw"))
            throw new ArgumentException("仅支持固定白名单中的官方工具。", nameof(name));
        foreach (var directory in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
        {
            if (string.IsNullOrWhiteSpace(directory) || directory.Trim() is "." or "..") continue;
            string folder;
            try { folder = Path.GetFullPath(directory.Trim().Trim('"')); }
            catch (Exception ex) when (ex is ArgumentException or NotSupportedException or PathTooLongException) { continue; }
            foreach (var ext in Extensions)
            {
                var candidate = Path.Combine(folder, name + ext);
                if (File.Exists(candidate)) return candidate;
            }
        }
        return null;
    }

    public static void LaunchInteractive(AgentKind agent, string workspace)
    {
        if (agent == AgentKind.Manual) return;
        var directory = WorkspaceGuard.RequireTrustedDirectory(workspace);
        var program = Locate(agent == AgentKind.ClaudeCode ? "claude" : "codex")
            ?? throw new FileNotFoundException($"未找到 {AgentLabel.Name(agent)}。请先通过官方安装程序安装并登录。");
        Process.Start(new ProcessStartInfo
        {
            FileName = program,
            WorkingDirectory = directory,
            UseShellExecute = true,
            ErrorDialog = false
        }) ?? throw new IOException("无法启动外部 Agent 进程。");
    }

    public static void LaunchCompanion(string name)
    {
        if (name is not ("t3" or "openclaw")) throw new ArgumentException("程序不在允许列表中。");
        var program = Locate(name) ?? throw new FileNotFoundException($"未安装 {name}。请先参照官方文档安装。");
        Process.Start(new ProcessStartInfo { FileName = program, UseShellExecute = true, WorkingDirectory = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) })
            ?? throw new IOException("无法启动集成工具。");
    }
}
