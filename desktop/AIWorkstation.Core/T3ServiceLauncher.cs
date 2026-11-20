using System.Diagnostics;

namespace AIWorkstation.Core;

/// <summary>
/// Starts the user-installed official T3 CLI on a loopback-only endpoint.
/// The UI never proxies subscription tokens and never starts multiple servers on purpose.
/// </summary>
public static class T3ServiceLauncher
{
    public static bool IsInstalled => AgentTools.Locate("t3") is not null;

    public static void StartLoopback(int port)
    {
        if (port is < 1024 or > 65535)
            throw new ArgumentOutOfRangeException(nameof(port), "请选择 1024–65535 之间的本机端口。");

        var program = AgentTools.Locate("t3")
            ?? throw new FileNotFoundException("未找到官方 T3 Code CLI。请先通过官方安装程序安装。", "t3");
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        if (string.IsNullOrWhiteSpace(home) || !Directory.Exists(home))
            throw new DirectoryNotFoundException("当前 Windows 用户目录不存在。");

        var process = Process.Start(new ProcessStartInfo
        {
            FileName = program,
            Arguments = $"serve --host 127.0.0.1 --port {port}",
            WorkingDirectory = home,
            UseShellExecute = true,
            ErrorDialog = false
        });
        if (process is null)
            throw new IOException("无法启动官方 T3 Code CLI。");
        // The upstream CLI owns its lifecycle. The workbench intentionally does not kill it.
    }
}
