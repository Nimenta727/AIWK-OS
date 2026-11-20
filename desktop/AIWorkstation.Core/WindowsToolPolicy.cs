using System.Diagnostics;

namespace AIWorkstation.Core;

/// <summary>Windows-specific capabilities with explicit human-owned boundaries.</summary>
public static class WindowsToolPolicy
{
    public sealed record Capability(string Id, string Label, string Access, bool Available,
        bool RequiresUserConfirmation, string Detail);

    public static IReadOnlyList<Capability> Describe()
    {
        return
        [
            new("git.read", "Git 审查", "ReadOnly", AgentTools.Locate("git") is not null, false,
                "仅运行固定的本地 Git 查看命令；不执行 Git hooks、提交、推送或网络操作。"),
            new("shell.user", "PowerShell 交互终端", "UserInitiated", OperatingSystem.IsWindows() && File.Exists(GetPowerShellPath()), true,
                "用户明确确认后打开独立 PowerShell 窗口。不会将命令输入接口提供给 Agent。"),
            new("agent.claude", "Claude Code", "ExternalCli", AgentTools.Locate("claude") is not null, true,
                "通过官方客户端登录；CLI 进程以当前 Windows 用户权限运行。"),
            new("agent.codex", "Codex CLI", "ExternalCli", AgentTools.Locate("codex") is not null, true,
                "通过官方客户端登录；平台不读取订阅或 API 凭据。")
        ];
    }

    public static void OpenUserPowerShell(string workspace)
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("仅 Windows 支持 PowerShell 桌面终端。");
        var folder = WorkspaceGuard.RequireTrustedDirectory(workspace);
        var program = GetPowerShellPath();
        if (!File.Exists(program)) throw new FileNotFoundException("Windows PowerShell 不存在。", program);
        var start = new ProcessStartInfo(program)
        {
            WorkingDirectory = folder,
            UseShellExecute = true,
            ErrorDialog = false
        };
        start.ArgumentList.Add("-NoProfile");
        start.ArgumentList.Add("-NoExit");
        if (Process.Start(start) is null) throw new IOException("PowerShell 终端未能启动。");
    }

    private static string GetPowerShellPath() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.System),
        "WindowsPowerShell", "v1.0", "powershell.exe");
}
