namespace AIWorkstation.Core;

/// <summary>
/// AIWS-owned application use cases. No provider-specific UI, web RPC or credentials.
/// The caller is responsible for the native confirmation before an external CLI is launched.
/// </summary>
public sealed class WorkstationController : IDisposable
{
    private readonly WorkspaceLease _lease;
    private readonly TaskRepository _repository;
    private readonly List<WorkTask> _tasks;
    private bool _healthy = true;

    public WorkstationController(string dataDirectory)
    {
        var root = Path.GetFullPath(dataDirectory);
        Directory.CreateDirectory(root);
        _lease = WorkspaceLease.Acquire(root);
        try
        {
            _repository = new TaskRepository(Path.Combine(root, "tasks.json"));
            _tasks = _repository.Load(); // Do not silently reset damaged task data.
            if (_tasks.Sum(WorkflowEngine.MarkInterrupted) > 0)
                Save(); // Persist interrupted state before exposing commands.
        }
        catch
        {
            _lease.Dispose();
            throw;
        }
    }

    public IReadOnlyList<WorkTask> Tasks => _tasks;
    public WorkTask GetTask(string taskId) => _tasks.FirstOrDefault(t => t.Id == taskId)
        ?? throw new ArgumentException("任务不存在。", nameof(taskId));

    public WorkTask CreateTask(string title, string workspace, string template)
    {
        EnsureHealthy();
        var safeTitle = title?.Trim() ?? "";
        if (safeTitle.Length is < 1 or > 120) throw new ArgumentException("任务标题须为 1–120 字符。", nameof(title));
        var folder = WorkspaceGuard.RequireTrustedDirectory(workspace);
        WorkTask task = template switch
        {
            "research" => WorkflowTemplates.Research(safeTitle, folder),
            "dual" => WorkflowTemplates.DualAgent(safeTitle, folder),
            _ => throw new ArgumentException("未知工作流模板。", nameof(template))
        };
        _tasks.Add(task);
        try { Save(); }
        catch { _tasks.Remove(task); throw; }
        return task;
    }

    public void Approve(string taskId, string stepId)
        => Change(taskId, task => WorkflowEngine.Approve(task, stepId));

    public void Complete(string taskId, string stepId, string result)
    {
        ArgumentNullException.ThrowIfNull(result);
        if (result.Length > 12_000) throw new ArgumentException("阶段结果不能超过 12,000 字符。", nameof(result));
        Change(taskId, task =>
        {
            var step = WorkflowEngine.Find(task, stepId);
            WorkflowEngine.Complete(task, stepId, result);
            RequestTrace.Record(task, step, "stage.completed", "阶段结果已由用户确认并保存；模型调用次数未知");
        });
    }

    public void StartManual(string taskId, string stepId)
        => Change(taskId, task =>
        {
            var step = WorkflowEngine.EnsureStartable(task, stepId);
            if (step.Agent != AgentKind.Manual) throw new InvalidOperationException("此阶段不是人工执行器。");
            WorkflowEngine.Start(task, stepId);
            RequestTrace.Record(task, step, "manual.started", "用户手动开始人工阶段；未启动模型");
        });

    public void Retry(string taskId, string stepId)
        => Change(taskId, task => WorkflowEngine.Retry(task, stepId));

    public void Launch(string taskId, string stepId, Action<string> copyPrompt, Action<AgentKind, string> startCli)
    {
        EnsureHealthy();
        var task = GetTask(taskId);
        var step = WorkflowEngine.EnsureStartable(task, stepId);
        if (step.Agent == AgentKind.Manual)
            throw new InvalidOperationException("人工阶段不能启动模型 CLI。");
        var folder = WorkspaceGuard.RequireTrustedDirectory(task.Workspace);
        var draft = HandoffBuilder.Prepare(task, step);
        StageLaunchCoordinator.PrepareAndStart(task, step, draft, copyPrompt, Save);
        try
        {
            startCli(step.Agent, folder); // Official installed program, not an embedded API.
        }
        catch (Exception ex)
        {
            try
            {
                WorkflowEngine.Fail(task, step.Id, "本机 CLI 启动失败；未确认任何模型请求。");
                RequestTrace.Record(task, step, "cli.failed", "外部进程启动失败，实际模型调用仍未知");
                Save();
            }
            catch { _healthy = false; }
            throw new IOException("阶段已保存为失败状态（若任务库写入失败则进入只读保护）。" + ex.Message, ex);
        }
    }

    private void Change(string taskId, Action<WorkTask> act)
    {
        EnsureHealthy();
        var task = GetTask(taskId);
        // Snapshot before mutation: persistence failure cannot leave a phantom status in memory.
        var stepSnapshots = task.Steps.Select(s => (s, s.Status, s.ApprovalGranted, s.Result, s.StartedAt, s.CompletedAt)).ToList();
        var oldEvents = task.RequestEvents.ToList();
        try { act(task); Save(); }
        catch
        {
            foreach (var (s,status,approved,result,start,completed) in stepSnapshots)
            {
                s.Status = status; s.ApprovalGranted = approved; s.Result = result;
                s.StartedAt = start; s.CompletedAt = completed;
            }
            task.RequestEvents.Clear();
            task.RequestEvents.AddRange(oldEvents);
            throw;
        }
    }

    private void Save()
    {
        EnsureHealthy();
        try { _repository.Save(_tasks); }
        catch { _healthy = false; throw; }
    }

    private void EnsureHealthy()
    {
        if (!_healthy) throw new InvalidOperationException("任务库上次写入失败；当前只读。请检查备份并重新启动。");
    }
    public void Dispose() => _lease.Dispose();
}
