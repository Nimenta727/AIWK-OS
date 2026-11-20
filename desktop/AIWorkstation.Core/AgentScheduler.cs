namespace AIWorkstation.Core;

/// <summary>
/// Deterministic, zero-token, restart-safe planning for an AIWS-owned DAG.
/// A dispatch ticket grants NO shell, provider, filesystem, or network authority.
/// Official interactive CLIs may only be launched by a separate explicit native confirmation.
/// </summary>
public static class AgentScheduler
{
    public sealed record DispatchSlot(
        string StageId, string Title, string AdapterId, string Agent, string Status,
        string Reason, int DependencyCount, int ApproxTokens, bool CanQueue,
        bool NeedsApproval, bool IsQueued, string? TicketId, AgentKind? RecommendedAgent);

    public sealed record DispatchPlan(
        string TaskId, string Mode, int MaxRecommendedActive, int ActiveStages,
        int CompletedStages, int ReadyStages, int QueuedStages,
        string? NextStageId, string EvidenceNotice, IReadOnlyList<DispatchSlot> Stages);

    public static DispatchPlan Build(WorkTask task, IReadOnlyList<ProviderCapability> providers)
    {
        ArgumentNullException.ThrowIfNull(task);
        ArgumentNullException.ThrowIfNull(providers);
        WorkflowGraph.Validate(task);
        var map = providers.ToDictionary(x => x.Agent);
        var active = task.Steps.Count(x => x.Status == StepStatus.Running);
        var slots = new List<DispatchSlot>();
        var stageIndex = task.Steps.Select((s,i)=>(s.Id,i)).ToDictionary(x=>x.Id,x=>x.i);
        foreach (var step in task.Steps)
        {
            AgentKind? recommendedAgent = null;
            var queued = task.Unified.DispatchRequests.LastOrDefault(x => x.StageId == step.Id && x.State == "queued");
            var status = "ready";
            var reason = "阶段就绪：仍需用户主动批准外部启动";
            var approx = 0;
            var needsApproval = step.RequiresApproval && !step.ApprovalGranted;
            if (step.Status != StepStatus.Pending)
            {
                status = step.Status switch
                {
                    StepStatus.Completed => "completed", StepStatus.Running => "running",
                    StepStatus.Interrupted => "interrupted", _ => "failed"
                };
                reason = status == "interrupted" ? "执行状态不明；需先人工核对外部副作用" : "该阶段当前不可调度";
            }
            else if (task.GraphMode && step.DependsOn.Any(id=>task.Steps.Single(x=>x.Id==id).Status!=StepStatus.Completed)
                || !task.GraphMode && task.Steps.Take(stageIndex[step.Id]).Any(x=>x.Status!=StepStatus.Completed))
            {
                status = "waiting"; reason = "等待前置阶段的已确认产物";
            }
            else if (active >= task.Unified.MaxRecommendedActive)
            {
                status = "capacity"; reason = "建议的并行容量已满；可等待当前阶段完成";
            }
            else if (active > 0 && (!task.GraphMode || string.IsNullOrWhiteSpace(step.WorktreePath) ||
                task.Steps.Any(x => x.Status == StepStatus.Running && (string.IsNullOrWhiteSpace(x.WorktreePath) ||
                    string.Equals(x.WorktreePath,step.WorktreePath,OperatingSystem.IsWindows()?StringComparison.OrdinalIgnoreCase:StringComparison.Ordinal)))))
            {
                status = "isolation"; reason = "当前并行执行需要独立且不同的 Git Worktree";
            }
            else if (!map.TryGetValue(step.Agent, out var provider) || !provider.Available)
            {
                status = "unavailable"; reason = "当前执行器未安装或不可用，用户可在阶段检查器中切换";
                if(step.Agent != AgentKind.Manual)
                    recommendedAgent=providers.FirstOrDefault(x=>x.Available && (x.Agent is AgentKind.ClaudeCode or AgentKind.Codex))?.Agent;
            }
            else if (step.Agent != AgentKind.Manual)
            {
                try
                {
                    var budget = ContextBudgetPolicy.Assess(task, step);
                    approx = budget.ApproxTokens;
                    if (budget.Blocked) {status="budget";reason="本地交接草稿超过估算预算上限";}
                }
                catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
                { status="budget";reason="交接预算无法评估，请检查任务数据"; }
            }
            if (status == "ready" && needsApproval)
            { status = "approval"; reason = "需要一次性阶段审批"; }
            if (status == "ready" && queued is not null)
            { status = "queued"; reason = "已加入本地调度队列；不会自动调用模型"; }
            slots.Add(new DispatchSlot(step.Id,step.Title,ProviderAdapterRegistry.IdFor(step.Agent),AgentLabel.Name(step.Agent),
                status,reason,step.DependsOn.Count,approx,status == "ready", needsApproval,
                queued is not null,queued?.Id,recommendedAgent));
        }
        var next = slots.FirstOrDefault(x=>x.Status is "ready" or "queued" or "approval");
        return new DispatchPlan(task.Id,"human-supervised",task.Unified.MaxRecommendedActive,active,
            slots.Count(x=>x.Status=="completed"),slots.Count(x=>x.Status=="ready"),
            slots.Count(x=>x.Status=="queued"),next?.StageId,
            "调度计划仅来自 AIWS 已保存的状态与本地预算。排队不启动 CLI、不调用模型，也不能证明模型内部请求。",
            slots);
    }

    public static string Queue(WorkTask task, string stepId, IReadOnlyList<ProviderCapability> providers)
    {
        var stage = WorkflowEngine.Find(task,stepId);
        var proposed = Build(task,providers).Stages.Single(x=>x.StageId==stepId);
        if (proposed.Status != "ready") throw new InvalidOperationException("阶段当前不可排队："+proposed.Reason);
        WorkflowEngine.EnsureStartable(task, stepId);
        if (task.Unified.DispatchRequests.Count >= 120)
            throw new InvalidOperationException("调度票据达到容量限制，请先归档旧任务。");
        var fingerprint = stage.Agent == AgentKind.Manual ? UnifiedTaskCore.HashText("manual:"+stepId)
            : ContextCompiler.Compile(task,stage).Fingerprint;
        var ticket = new DispatchRequest {StageId=stage.Id,AdapterId=ProviderAdapterRegistry.IdFor(stage.Agent),
            HandoffFingerprint=fingerprint};
        task.Unified.DispatchRequests.Add(ticket);
        return ticket.Id;
    }

    public static void Cancel(WorkTask task, string ticketId)
    {
        var ticket=task.Unified.DispatchRequests.SingleOrDefault(x=>x.Id==ticketId && x.State=="queued")
            ?? throw new InvalidOperationException("待执行票据不存在或已结束。");
        ticket.State="cancelled";
        ticket.UpdatedAt=DateTimeOffset.UtcNow;
    }

    public static void CancelForStage(WorkTask task,string stepId)
    {
        foreach(var ticket in task.Unified.DispatchRequests.Where(x=>x.StageId==stepId && x.State=="queued"))
        { ticket.State="cancelled";ticket.UpdatedAt=DateTimeOffset.UtcNow; }
    }

    public static void ConsumeIfQueued(WorkTask task,WorkflowStep step)
    {
        foreach(var ticket in task.Unified.DispatchRequests.Where(x=>x.StageId==step.Id && x.State=="queued"))
        {
            // A changed goal, provider or prompt cannot reuse a stale handoff approval/queue entry.
            var expected=step.Agent==AgentKind.Manual ? UnifiedTaskCore.HashText("manual:"+step.Id)
                : ContextCompiler.Compile(task,step).Fingerprint;
            if (ticket.AdapterId != ProviderAdapterRegistry.IdFor(step.Agent) || ticket.HandoffFingerprint != expected)
            { ticket.State="cancelled"; }
            else { ticket.State="consumed"; }
            ticket.UpdatedAt=DateTimeOffset.UtcNow;
        }
    }
}

public sealed class DispatchRequest
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string StageId { get; set; } = "";
    public string AdapterId { get; set; } = "";
    public string HandoffFingerprint { get; set; } = "";
    public string State { get; set; } = "queued"; // queued | consumed | cancelled
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
}
