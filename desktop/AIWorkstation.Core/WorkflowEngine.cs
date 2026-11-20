namespace AIWorkstation.Core;

public static class WorkflowEngine
{
    public static void Approve(WorkTask task, string stepId)
    {
        var step = Find(task, stepId);
        VerifyPrerequisites(task, step);
        if (step.Status != StepStatus.Pending) throw new InvalidOperationException("只有待开始阶段可以审批。");
        step.ApprovalGranted = true;
    }

    public static void Start(WorkTask task, string stepId)
    {
        var step = EnsureStartable(task, stepId);
        step.ApprovalGranted = false; // One-shot approval; it cannot be reused after a failure.
        step.Status = StepStatus.Running;
        step.StartedAt = DateTimeOffset.Now;
    }

    public static void Complete(WorkTask task, string stepId, string result)
    {
        var step = Find(task, stepId);
        if (step.Status != StepStatus.Running) throw new InvalidOperationException("请先启动当前阶段。");
        if (string.IsNullOrWhiteSpace(result)) throw new ArgumentException("完成阶段时需要填写实际结果。");
        step.Result = result.Trim();
        step.Status = StepStatus.Completed;
        step.CompletedAt = DateTimeOffset.Now;
    }

    public static void Fail(WorkTask task, string stepId, string reason)
    {
        var step = Find(task, stepId);
        if (step.Status != StepStatus.Running) throw new InvalidOperationException("只有运行中阶段可以标记失败。");
        step.Status = StepStatus.Failed;
        step.Result = string.IsNullOrWhiteSpace(reason) ? "人工标记失败" : reason.Trim();
        step.ApprovalGranted = false;
    }

    public static void Retry(WorkTask task, string stepId)
    {
        var step = Find(task, stepId);
        if (step.Status is not (StepStatus.Failed or StepStatus.Interrupted)) throw new InvalidOperationException("只有失败或中断的阶段可以重试。");
        step.Status = StepStatus.Pending;
        step.Result = "";
        step.GitBefore = null;
        step.GitAfter = null;
        step.StartedAt = null;
        step.CompletedAt = null;
        step.ApprovalGranted = false;
    }

    public static WorkflowStep EnsureStartable(WorkTask task, string stepId)
    {
        var step = Find(task, stepId);
        VerifyPrerequisites(task, step);
        if (step.Status != StepStatus.Pending) throw new InvalidOperationException("当前阶段不可重复启动。");
        if (step.RequiresApproval && !step.ApprovalGranted) throw new InvalidOperationException("请先批准当前阶段。");
        if (task.Steps.Any(x => x != step && x.Status == StepStatus.Running))
            throw new InvalidOperationException("当前任务已有执行中的阶段。");
        return step;
    }

    /// <summary>Called only on application startup; never resumes or retries an external CLI.</summary>
    public static int MarkInterrupted(WorkTask task)
    {
        var count = 0;
        foreach (var step in task.Steps.Where(x => x.Status == StepStatus.Running))
        {
            step.Status = StepStatus.Interrupted;
            step.ApprovalGranted = false;
            RequestTrace.Record(task, step, "stage.interrupted", "工作台重启；外部 CLI 状态未知，需人工核验后重试");
            count++;
        }
        return count;
    }

    public static WorkflowStep Find(WorkTask task, string stepId) =>
        task.Steps.FirstOrDefault(s => s.Id == stepId)
        ?? throw new InvalidOperationException("阶段不存在。");

    private static void VerifyPrerequisites(WorkTask task, WorkflowStep step)
    {
        var index = task.Steps.IndexOf(step);
        if (index < 0) throw new InvalidOperationException("阶段不属于此任务。");
        if (task.Steps.Take(index).Any(s => s.Status != StepStatus.Completed))
            throw new InvalidOperationException("请先完成此前的工作阶段。");
    }
}
