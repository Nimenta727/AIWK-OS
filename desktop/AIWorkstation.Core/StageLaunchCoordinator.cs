namespace AIWorkstation.Core;

/// <summary>
/// Enforces a pre-execution prepare/commit boundary. If clipboard or persistence fails,
/// no external CLI has been launched and the in-memory stage returns to Pending.
/// </summary>
public static class StageLaunchCoordinator
{
    public static void PrepareAndStart(WorkTask task, WorkflowStep step, PreparedHandoff draft,
        Action<string> copyToClipboard, Action persist)
    {
        ArgumentNullException.ThrowIfNull(copyToClipboard);
        ArgumentNullException.ThrowIfNull(persist);
        WorkflowEngine.EnsureStartable(task, step.Id);
        copyToClipboard(draft.Text); // Fallible UI operation happens BEFORE mutating execution status.
        var oldApproval = step.ApprovalGranted;
        var oldStartedAt = step.StartedAt;
        var oldFingerprint = step.LastPromptFingerprint;
        var oldEvents = task.RequestEvents.ToArray();
        try
        {
            var duplicate = draft.Fingerprint == oldFingerprint;
            step.LastPromptFingerprint = draft.Fingerprint;
            RequestTrace.Record(task, step, duplicate ? "prompt.reused" : "prompt.prepared",
                duplicate ? "重复复制交接内容（未自动请求模型）" : "交接提示词已复制（未自动请求模型）");
            WorkflowEngine.Start(task, step.Id);
            RequestTrace.Record(task, step, "stage.started", "阶段已记录启动意图，外部模型调用仍未知");
            persist();
        }
        catch
        {
            // Never leave a phantom Running step in memory if persistence failed.
            step.Status = StepStatus.Pending;
            step.ApprovalGranted = oldApproval;
            step.StartedAt = oldStartedAt;
            step.LastPromptFingerprint = oldFingerprint;
            task.RequestEvents.Clear();
            task.RequestEvents.AddRange(oldEvents);
            throw;
        }
    }
}
