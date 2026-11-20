using System.Diagnostics;
using System.Text;

namespace AIWorkstation.Core;

/// <summary>
/// Read-only Git diagnostics for the selected, trusted workspace. There is no shell,
/// no user-supplied argv, no network operation, and no agent tool dispatch.
/// Output is returned to the current UI only; it is not written to task history.
/// </summary>
public static class GitWorkspaceService
{
    public sealed record Inspection(string View, string Command, string Output, bool Truncated,
        int ExitCode, long DurationMs);

    // Explicit command and argument allowlist. Do not accept a command line from WebView.
    private static readonly IReadOnlyDictionary<string, string[]> Views = new Dictionary<string, string[]>(StringComparer.Ordinal)
    {
        ["status"] = ["status", "--short", "--untracked-files=normal"],
        ["summary"] = ["diff", "--no-ext-diff", "--no-textconv", "--no-color", "--stat", "--", "."],
        ["diff"] = ["diff", "--no-ext-diff", "--no-textconv", "--no-color", "--unified=3", "--", "."],
        ["staged"] = ["diff", "--cached", "--no-ext-diff", "--no-textconv", "--no-color", "--unified=3", "--", "."],
        ["history"] = ["log", "-n", "12", "--pretty=format:%h %s (%cr)"],
        ["branch"] = ["branch", "--show-current"],
        ["head"] = ["rev-parse", "--verify", "HEAD"],
        ["porcelain"] = ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "."]
    };

    public static IReadOnlyList<string> SupportedViews => Views.Keys.ToArray();
    private const int MaxOutputChars = 120_000;
    private static readonly SemaphoreSlim Slots = new(2, 2);

    public static async Task<Inspection> InspectAsync(string workspace, string view, CancellationToken cancellationToken = default)
    {
        if (!Views.TryGetValue(view, out var arguments))
            throw new ArgumentException("未知 Git 查看操作；只允许预设的只读命令。", nameof(view));
        return await ExecuteAsync(workspace, view, arguments, cancellationToken);
    }

    public static Task<Inspection> InspectFileAsync(string workspace, string relative, bool staged, CancellationToken cancellationToken = default)
    {
        ProjectWorkspaceService.RequireSafeFile(workspace, relative);
        var args = new List<string> { "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--unified=3" };
        if (staged) args.Add("--cached");
        args.Add("--");
        args.Add(relative);
        return ExecuteAsync(workspace, staged ? "file.staged" : "file.worktree", args, cancellationToken);
    }

    public static Task<Inspection> InspectCommitFilesAsync(string workspace, string fromHead, string toHead,
        CancellationToken cancellationToken = default)
    {
        static bool IsHash(string hash) => hash.Length is >= 7 and <= 64 && hash.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
        if (!IsHash(fromHead) || !IsHash(toHead))
            throw new ArgumentException("提交标识格式不合法。");
        return ExecuteAsync(workspace, "commit.files",
            ["diff", "--no-ext-diff", "--no-textconv", "--name-status", "-z", fromHead, toHead, "--", "."], cancellationToken);
    }

    private static async Task<Inspection> ExecuteAsync(string workspace, string view, IEnumerable<string> arguments, CancellationToken cancellationToken)
    {
        var folder = WorkspaceGuard.RequireTrustedDirectory(workspace);
        var git = AgentTools.Locate("git") ?? throw new FileNotFoundException("未检测到 Git。请先安装 Git for Windows。", "git.exe");
        await Slots.WaitAsync(cancellationToken);
        try
        {
            using var process = new Process();
            var start = new ProcessStartInfo(git)
            {
                WorkingDirectory = folder,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8
            };
            start.ArgumentList.Add("--no-pager");
            start.ArgumentList.Add("--literal-pathspecs");
            start.ArgumentList.Add("-c");
            start.ArgumentList.Add("core.fsmonitor=false");
            foreach (var arg in arguments) start.ArgumentList.Add(arg);
            start.Environment["GIT_OPTIONAL_LOCKS"] = "0";
            start.Environment["GIT_TERMINAL_PROMPT"] = "0";
            process.StartInfo = start;
            var watch = Stopwatch.StartNew();
            if (!process.Start()) throw new IOException("Git 子进程启动失败。 ");
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(12));
            // Drain both streams concurrently to prevent a blocked Git child on a full pipe.
            var outputTask = ReadBounded(process.StandardOutput, MaxOutputChars, timeout.Token);
            var errorTask = ReadBounded(process.StandardError, 5_000, timeout.Token);
            try
            {
                await process.WaitForExitAsync(timeout.Token);
                var (output, truncated) = await outputTask;
                var (errors, _) = await errorTask;
                watch.Stop();
                if (process.ExitCode != 0)
                    throw new InvalidOperationException("Git 只读操作失败（exit " + process.ExitCode + "）：" + errors);
                return new Inspection(view, "git --no-pager " + string.Join(' ', arguments),
                    output.Length == 0 ? "（无输出）" : output, truncated, process.ExitCode, watch.ElapsedMilliseconds);
            }
            catch (OperationCanceledException)
            {
                try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { }
                throw new TimeoutException("Git 查看超过 12 秒，已停止进程；请检查仓库大小或文件系统状态。");
            }
        }
        finally { Slots.Release(); }
    }

    private static async Task<(string Output, bool Truncated)> ReadBounded(StreamReader reader, int limit, CancellationToken ct)
    {
        var output = new StringBuilder(Math.Min(4096, limit));
        var buffer = new char[4096];
        var truncated = false;
        while (true)
        {
            var n = await reader.ReadAsync(buffer.AsMemory(), ct);
            if (n == 0) break;
            if (output.Length < limit)
            {
                var take = Math.Min(n, limit - output.Length);
                output.Append(buffer, 0, take);
                if (take < n) truncated = true;
            }
            else truncated = true;
        }
        return (output.ToString(), truncated);
    }
}
