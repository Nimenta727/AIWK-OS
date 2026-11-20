using System.Diagnostics;
using System.Text;

namespace AIWorkstation.Core;

/// <summary>Explicitly approved per-stage Git worktree, never a Windows OS sandbox.</summary>
public static class GitWorktreeService
{
    public sealed record CreatedWorktree(string Path,string Head,string Branch);
    private static readonly SemaphoreSlim MutationLock=new(1,1);

    private static async Task<string> Git(string root,IReadOnlyList<string> argv,CancellationToken ct)
    {
        var git=AgentTools.Locate("git") ?? throw new FileNotFoundException("Git for Windows 未安装。");
        var psi=new ProcessStartInfo(git){WorkingDirectory=root,UseShellExecute=false,RedirectStandardOutput=true,
            RedirectStandardError=true,CreateNoWindow=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};
        psi.ArgumentList.Add("--no-pager");
        psi.ArgumentList.Add("-c"); psi.ArgumentList.Add("core.fsmonitor=false");
        psi.ArgumentList.Add("-c"); psi.ArgumentList.Add("core.hooksPath=.aiws-disabled-hooks");
        foreach(var a in argv) psi.ArgumentList.Add(a);
        psi.Environment["GIT_TERMINAL_PROMPT"]="0";
        psi.Environment["GIT_LFS_SKIP_SMUDGE"]="1";
        using var p=new Process{StartInfo=psi};
        if(!p.Start())throw new IOException("Git 子进程无法启动。");
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TimeSpan.FromSeconds(25));
        var o=p.StandardOutput.ReadToEndAsync(timeout.Token);
        var e=p.StandardError.ReadToEndAsync(timeout.Token);
        try
        {
            await p.WaitForExitAsync(timeout.Token).ConfigureAwait(false);
            var stdout=await o.ConfigureAwait(false);
            var stderr=await e.ConfigureAwait(false);
            if(stdout.Length>16000 || stderr.Length>16000)throw new IOException("Git 输出超过安全限制。");
            if(p.ExitCode!=0)throw new InvalidOperationException("Git worktree 操作失败："+stderr.Trim());
            return stdout.Trim();
        }
        catch(OperationCanceledException)
        {
            try {if(!p.HasExited)p.Kill(entireProcessTree:true);}catch(InvalidOperationException){}
            throw new TimeoutException("Git worktree 超时，可能留下部分创建的工作区，请检查现场。");
        }
    }

    public static async Task<CreatedWorktree> CreateAsync(string source,string taskId,string stageId,CancellationToken cancellationToken=default)
    {
        static bool SafeId(string id) => id.Length==32 && id.All(c=>c is >= '0' and <= '9' or >= 'a' and <= 'f');
        if(!SafeId(taskId)||!SafeId(stageId))throw new ArgumentException("Worktree ID 必须由本地任务生成。");
        var root=WorkspaceGuard.RequireTrustedDirectory(source);
        await MutationLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var top=await Git(root,["rev-parse","--show-toplevel"],cancellationToken).ConfigureAwait(false);
            if(!PathEquals(root,top))throw new InvalidOperationException("工作区必须是 Git 仓库根目录。");
            var dirty=await Git(root,["status","--porcelain=v1","--untracked-files=normal"],cancellationToken).ConfigureAwait(false);
            if(dirty.Length!=0)throw new InvalidOperationException("创建隔离 Worktree 前请先保存或提交主仓库的未提交修改。");
            var head=await Git(root,["rev-parse","--verify","HEAD"],cancellationToken).ConfigureAwait(false);
            var parent=Path.GetDirectoryName(Path.TrimEndingDirectorySeparator(root))!;
            var destination=Path.Combine(parent,".aiws-worktrees",taskId[..12]+"-"+stageId[..12]);
            if(Directory.Exists(destination)||File.Exists(destination))throw new IOException("Worktree 目标路径已存在，拒绝覆盖。");
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            _ = WorkspaceGuard.RequireTrustedDirectory(Path.GetDirectoryName(destination)!); // Reject linked parent before Git writes.
            var branch="aiws/"+taskId[..12]+"/"+stageId[..12];
            await Git(root,["worktree","add","-b",branch,destination,head],cancellationToken).ConfigureAwait(false);
            return new CreatedWorktree(WorkspaceGuard.RequireTrustedDirectory(destination),head,branch);
        }
        finally {MutationLock.Release();}
    }
    private static bool PathEquals(string a,string b)=>string.Equals(Path.TrimEndingDirectorySeparator(Path.GetFullPath(a)),
        Path.TrimEndingDirectorySeparator(Path.GetFullPath(b)),OperatingSystem.IsWindows()?StringComparison.OrdinalIgnoreCase:StringComparison.Ordinal);
}
