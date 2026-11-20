namespace AIWorkstation.Core;

public enum AgentKind { ClaudeCode, Codex, Manual }
public enum StepStatus { Pending, Running, Completed, Failed, Interrupted }

public sealed class WorkflowStep
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string Title { get; set; } = "新阶段";
    public AgentKind Agent { get; set; } = AgentKind.ClaudeCode;
    public StepStatus Status { get; set; } = StepStatus.Pending;
    public bool RequiresApproval { get; set; } = true;
    public bool ApprovalGranted { get; set; }
    public string Instructions { get; set; } = "";
    public string Result { get; set; } = "";
    public TokenUsage Usage { get; set; } = new();
    public string ImportFingerprint { get; set; } = "";
    // Null means not reported; zero is a measured count from a structured log.
    public int? ImportedToolEvents { get; set; }
    public int? ImportedUsageEvents { get; set; }
    public List<ProviderEventSummary> ProviderEvents { get; set; } = [];
    public string LastPromptFingerprint { get; set; } = "";
    public List<string> DependsOn { get; set; } = [];
    public string WorktreePath { get; set; } = "";
    public string WorktreeBaseline { get; set; } = "";
    public string RunId { get; set; } = "";
    public ProjectWorkspaceService.GitCheckpoint? GitBefore { get; set; }
    public ProjectWorkspaceService.GitCheckpoint? GitAfter { get; set; }
    public DateTimeOffset? StartedAt { get; set; }
    public DateTimeOffset? CompletedAt { get; set; }
}

public sealed class WorkTask
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string Title { get; set; } = "未命名任务";
    public string Workspace { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.Now;
    public bool GraphMode { get; set; }
    public List<WorkflowStep> Steps { get; set; } = [];
    public List<ExecutionRecord> ExecutionRecords { get; set; } = [];
    public string WorkspaceFor(WorkflowStep step) => string.IsNullOrWhiteSpace(step.WorktreePath) ? Workspace : step.WorktreePath;
    public List<RequestTraceEvent> RequestEvents { get; set; } = [];
    public int CompletedCount => Steps.Count(x => x.Status == StepStatus.Completed);
}

public static class AgentLabel
{
    public static string Name(AgentKind agent) => agent switch
    {
        AgentKind.ClaudeCode => "Claude Code",
        AgentKind.Codex => "Codex CLI",
        _ => "人工处理"
    };
    public static string State(StepStatus state) => state switch
    {
        StepStatus.Pending => "待开始",
        StepStatus.Running => "执行中",
        StepStatus.Completed => "已完成",
        StepStatus.Interrupted => "执行中断 · 需人工核验",
        _ => "失败 · 可重试"
    };
}

public static class WorkflowTemplates
{
    public static WorkTask DualAgent(string name, string workspace) => new()
    {
        Title = name,
        Workspace = workspace,
        Steps =
        [
            new() { Title = "方案与边界分析", Agent = AgentKind.ClaudeCode, Instructions = "梳理现有仓库架构，提出可验证的实施方案与风险点。不要直接修改文件。", RequiresApproval = false },
            new() { Title = "代码实现与测试", Agent = AgentKind.Codex, Instructions = "遵照已确认的方案修改项目，执行可用测试，整理文件差异与已知风险。", RequiresApproval = true },
            new() { Title = "独立复核与交付", Agent = AgentKind.ClaudeCode, Instructions = "核对变更和测试证据，记录存在的问题。GitHub 修改后在 docs/routine 生成包含时间、变更和下一步规划的开发日志。", RequiresApproval = false }
        ]
    };

    public static WorkTask ParallelReview(string name, string workspace)
    {
        var plan = new WorkflowStep { Title = "目标与范围分析", Agent = AgentKind.ClaudeCode,
            Instructions = "梳理现有架构和风险，输出简明可验证的实施方案。", RequiresApproval = false };
        var build = new WorkflowStep { Title = "实现与测试", Agent = AgentKind.Codex,
            Instructions = "按方案实施并验证；所有写操作只在明确的工作区进行。", DependsOn = [plan.Id] };
        var audit = new WorkflowStep { Title = "独立审查", Agent = AgentKind.ClaudeCode,
            Instructions = "独立审查代码、安全边界与测试；不要假装看到不可观察的模型调用。", DependsOn = [plan.Id] };
        var ship = new WorkflowStep { Title = "整合验收", Agent = AgentKind.Manual,
            Instructions = "核实两个分支的产物，决定是否合并与提交。", DependsOn = [build.Id, audit.Id] };
        return new WorkTask { Title = name, Workspace = workspace, GraphMode = true, Steps = [plan,build,audit,ship] };
    }

    public static WorkTask Research(string name, string workspace) => new()
    {
        Title = name,
        Workspace = workspace,
        Steps =
        [
            new() { Title = "研究规划", Agent = AgentKind.ClaudeCode, Instructions = "列出研究问题、资料来源和事实核验计划。", RequiresApproval = false },
            new() { Title = "交叉验证", Agent = AgentKind.Codex, Instructions = "验证数据、复查结论、汇总不确定性。", RequiresApproval = false },
            new() { Title = "报告整合", Agent = AgentKind.Manual, Instructions = "检查出处和结论后确认最终文稿。", RequiresApproval = true }
        ]
    };
}
