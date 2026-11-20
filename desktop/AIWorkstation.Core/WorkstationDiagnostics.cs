using System.Text.Json;

namespace AIWorkstation.Core;

/// <summary>Evidence-based local health projection with a redacted, explicit export.</summary>
public static class WorkstationDiagnostics
{
    public sealed record Health(
        string Version, DateTimeOffset InspectedAt, int Tasks, int RunningStages,
        int InterruptedStages, int PendingApprovals, int QueuedStages,
        int ImportedUsageStages, int UnknownUsageStages, bool BackupAvailable,
        string SecurityNotice, string ReleaseNotice);

    public static Health Inspect(IReadOnlyList<WorkTask> tasks,bool backupAvailable)
    {
        ArgumentNullException.ThrowIfNull(tasks);
        var stages=tasks.SelectMany(x=>x.Steps).ToArray();
        return new Health("1.8-orchestration-preview",DateTimeOffset.UtcNow,tasks.Count,
            stages.Count(s=>s.Status==StepStatus.Running),
            stages.Count(s=>s.Status==StepStatus.Interrupted),
            stages.Count(s=>s.Status==StepStatus.Pending && s.RequiresApproval && !s.ApprovalGranted),
            tasks.Sum(t=>t.Unified.DispatchRequests.Count(d=>d.State=="queued")),
            stages.Count(s=>s.Agent!=AgentKind.Manual && s.Usage.IsMeasured),
            stages.Count(s=>s.Agent!=AgentKind.Manual && !s.Usage.IsMeasured),
            backupAvailable,
            "工作台以当前 Windows 用户运行；Worktree/路径验证不是系统沙箱；自动计划不授予模型任何执行权限。",
            "Windows CI 成功不等于 Hyper-V GUI 验收、代码签名或独立安全审计完成。");
    }

    public static string CreateRedactedReport(IReadOnlyList<WorkTask> tasks,bool backupAvailable)
    {
        // Never export workspace paths, prompts, task titles, stage results, commands, file trees or raw events.
        var status=Inspect(tasks,backupAvailable);
        var report=new
        {
            schemaVersion=1,
            generatedAt=status.InspectedAt,
            counts=new {status.Tasks,status.RunningStages,status.InterruptedStages,status.PendingApprovals,
                status.QueuedStages,status.ImportedUsageStages,status.UnknownUsageStages},
            backupAvailable=status.BackupAvailable,
            evidence="AIWS local counts. Unknown provider requests and tokens cannot be reconstructed.",
            security=status.SecurityNotice,
            release=status.ReleaseNotice
        };
        return JsonSerializer.Serialize(report,new JsonSerializerOptions {WriteIndented=true});
    }
}
