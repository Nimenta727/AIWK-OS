using System.Security.Cryptography;
using System.Text;

namespace AIWorkstation.Core;

/// <summary>
/// AIWS owns the durable task, not the provider. This is an additive, versioned
/// projection of the existing WorkflowStep state, not a second scheduler.
/// No plan text, model credentials, terminal output, or source file bodies are stored here.
/// </summary>
public sealed class UnifiedTaskState
{
    public int SchemaVersion { get; set; } = 1;
    public string Goal { get; set; } = "";
    public string AcceptanceCriteria { get; set; } = "";
    public List<PlanRevision> Plans { get; set; } = [];
    public List<UnifiedWorkItem> WorkItems { get; set; } = [];
    public List<TaskArtifactRef> Artifacts { get; set; } = [];
    public List<AgentRunRecord> AgentRuns { get; set; } = [];
    public int MaxRecommendedActive { get; set; } = 1; // Scheduler planning only; not an OS lock.
    public List<DispatchRequest> DispatchRequests { get; set; } = [];
}

public sealed class PlanRevision
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string RelativePath { get; set; } = "";
    public string Sha256 { get; set; } = "";
    public DateTimeOffset LinkedAt { get; set; } = DateTimeOffset.UtcNow;
}

public sealed class UnifiedWorkItem
{
    // The existing stage ID is the stable work-item ID. No duplicate authority.
    public string Id { get; set; } = "";
    public string StageId { get; set; } = "";
    public string Title { get; set; } = "";
    public StepStatus Status { get; set; }
    public AgentKind Agent { get; set; }
    public List<string> DependsOn { get; set; } = [];
}

public sealed class TaskArtifactRef
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string Kind { get; set; } = ""; // plan | stage-result
    public string StageId { get; set; } = "";
    public string Reference { get; set; } = ""; // AIWS stage or workspace-relative path
    public string ContentHash { get; set; } = "";
    public DateTimeOffset RecordedAt { get; set; } = DateTimeOffset.UtcNow;
}

public sealed class AgentRunRecord
{
    public string Id { get; set; } = ""; // WorkflowStep.RunId (one attempt)
    public string StageId { get; set; } = "";
    public AgentKind Agent { get; set; }
    public string AdapterId { get; set; } = "";
    public StepStatus Status { get; set; }
    public DateTimeOffset? StartedAt { get; set; }
    public DateTimeOffset? CompletedAt { get; set; }
    public string Evidence { get; set; } = "local-intent"; // Never proof of a remote request.
}

public static class UnifiedTaskCore
{
    public const int SchemaVersion = 1;
    public const int MaxPlanRevisions = 80;
    public const int MaxArtifactRefs = 500;
    public const int MaxRunRecords = 500;

    public static string HashText(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    /// <summary>Backfills old task JSON in memory. The next validated repository save persists it.</summary>
    public static void Reconcile(WorkTask task)
    {
        task.Unified ??= new UnifiedTaskState();
        var state = task.Unified;
        if (string.IsNullOrWhiteSpace(state.Goal)) state.Goal = task.Title;
        state.WorkItems ??= [];
        state.Plans ??= [];
        state.AgentRuns ??= [];
        state.Artifacts ??= [];
        state.DispatchRequests ??= [];
        foreach (var step in task.Steps)
        {
            var item = state.WorkItems.FirstOrDefault(x => x.StageId == step.Id);
            if (item is null)
            {
                item = new UnifiedWorkItem { Id = step.Id, StageId = step.Id };
                state.WorkItems.Add(item);
            }
            item.Title = step.Title;
            item.Agent = step.Agent;
            item.Status = step.Status;
            item.DependsOn = step.DependsOn.ToList();
            if (!string.IsNullOrWhiteSpace(step.RunId))
            {
                var run = state.AgentRuns.FirstOrDefault(x => x.Id == step.RunId);
                if (run is null)
                {
                    run = new AgentRunRecord { Id = step.RunId, StageId = step.Id,
                        AdapterId = ProviderAdapterRegistry.IdFor(step.Agent), Evidence = "local-intent" };
                    state.AgentRuns.Add(run);
                }
                run.Agent = step.Agent;
                run.Status = step.Status;
                run.StartedAt = step.StartedAt;
                run.CompletedAt = step.CompletedAt;
            }
            if (step.Status == StepStatus.Completed && !string.IsNullOrWhiteSpace(step.Result))
            {
                var hash = HashText(step.Result);
                // No duplicated result text: stage record is the authority, artifact is an immutable pointer.
                if (!state.Artifacts.Any(x => x.Kind == "stage-result" && x.StageId == step.Id && x.ContentHash == hash))
                    state.Artifacts.Add(new TaskArtifactRef { Kind = "stage-result", StageId = step.Id,
                        Reference = "stage:" + step.Id, ContentHash = hash });
            }
        }
        state.WorkItems.RemoveAll(item => task.Steps.All(step => step.Id != item.StageId));
        Validate(task);
    }

    public static bool AttachPlan(WorkTask task, PlanWorkspaceService.PlanDocument document)
    {
        ArgumentNullException.ThrowIfNull(document);
        Reconcile(task);
        if (!PlanWorkspaceService.IsAllowedPlanPath(document.Path) || document.Sha256.Length != 64)
            throw new InvalidDataException("计划路径或哈希无效。");
        if (task.Unified.Plans.Any(x => x.RelativePath == document.Path && x.Sha256 == document.Sha256))
            return false;
        if (task.Unified.Plans.Count >= MaxPlanRevisions || task.Unified.Artifacts.Count >= MaxArtifactRefs)
            throw new InvalidOperationException("计划版本或工件已达容量上限，请先归档旧项目。");
        var revision = new PlanRevision { RelativePath = document.Path, Sha256 = document.Sha256 };
        task.Unified.Plans.Add(revision);
        task.Unified.Artifacts.Add(new TaskArtifactRef { Kind = "plan", Reference = document.Path,
            ContentHash = document.Sha256 });
        Validate(task);
        return true;
    }

    public static void Validate(WorkTask task)
    {
        var state = task.Unified ?? throw new InvalidDataException("统一任务数据缺失。");
        if (state.SchemaVersion != SchemaVersion || state.Goal is null || state.Goal.Length > 6000 ||
            state.AcceptanceCriteria is null || state.AcceptanceCriteria.Length > 6000 ||
            state.Plans is null || state.WorkItems is null || state.Artifacts is null || state.AgentRuns is null ||
            state.Plans.Count > MaxPlanRevisions || state.Artifacts.Count > MaxArtifactRefs ||
            state.AgentRuns.Count > MaxRunRecords || state.WorkItems.Count > 200 ||
            state.MaxRecommendedActive is < 1 or > 4 || state.DispatchRequests is null || state.DispatchRequests.Count > 120)
            throw new InvalidDataException("统一任务字段或 schema 版本无效。");
        var stageIds = task.Steps.Select(s => s.Id).ToHashSet(StringComparer.Ordinal);
        if (state.WorkItems.Count != task.Steps.Count ||
            state.WorkItems.Any(x => x is null || x.Id != x.StageId || !stageIds.Contains(x.StageId) ||
                x.DependsOn is null || x.DependsOn.Count > 200 || x.Title is null) ||
            state.WorkItems.Select(x => x.Id).Distinct(StringComparer.Ordinal).Count() != state.WorkItems.Count)
            throw new InvalidDataException("工作项与工作流阶段不一致。");
        if (state.Plans.Any(x => x is null || string.IsNullOrWhiteSpace(x.Id) ||
            !PlanWorkspaceService.IsAllowedPlanPath(x.RelativePath) || !IsHexHash(x.Sha256)) ||
            state.Plans.Select(x => x.Id).Distinct(StringComparer.Ordinal).Count() != state.Plans.Count)
            throw new InvalidDataException("计划版本来源无效。");
        if (state.Artifacts.Any(x => x is null || string.IsNullOrWhiteSpace(x.Id) || !IsHexHash(x.ContentHash) ||
            x.Kind is not ("plan" or "stage-result") ||
            (x.Kind == "plan" && !PlanWorkspaceService.IsAllowedPlanPath(x.Reference)) ||
            (x.Kind == "stage-result" && (!stageIds.Contains(x.StageId) || x.Reference != "stage:" + x.StageId))) ||
            state.Artifacts.Select(x => x.Id).Distinct(StringComparer.Ordinal).Count() != state.Artifacts.Count)
            throw new InvalidDataException("任务工件指针无效。");
        if (state.DispatchRequests.Any(x=> x is null || string.IsNullOrWhiteSpace(x.Id) ||
            !stageIds.Contains(x.StageId) || x.AdapterId is not ("claude-cli" or "codex-cli" or "manual") ||
            !IsHexHash(x.HandoffFingerprint) || x.State is not ("queued" or "consumed" or "cancelled")) ||
            state.DispatchRequests.Select(x=>x.Id).Distinct(StringComparer.Ordinal).Count()!=state.DispatchRequests.Count ||
            state.DispatchRequests.Where(x=>x.State=="queued").GroupBy(x=>x.StageId).Any(x=>x.Count()>1))
            throw new InvalidDataException("调度票据损坏、重复或超出允许范围。");
        if (state.AgentRuns.Any(x => x is null || string.IsNullOrWhiteSpace(x.Id) ||
            !stageIds.Contains(x.StageId) || x.AdapterId != ProviderAdapterRegistry.IdFor(x.Agent) ||
            x.Evidence != "local-intent") ||
            state.AgentRuns.Select(x => x.Id).Distinct(StringComparer.Ordinal).Count() != state.AgentRuns.Count)
            throw new InvalidDataException("Agent 运行尝试记录无效。");
    }

    private static bool IsHexHash(string? hash) => hash is { Length: 64 } && hash.All(c => char.IsAsciiHexDigit(c));
}
