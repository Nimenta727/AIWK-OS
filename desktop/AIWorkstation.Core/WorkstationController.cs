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
            var interrupted=0;
            foreach (var task in _tasks)
            {
                var count=WorkflowEngine.MarkInterrupted(task);
                if(count>0) ExecutionLedger.Append(task,null,"workflow.interrupted",metadata:$"stages={count}");
                interrupted+=count;
            }
            if (interrupted > 0) Save(); // Persist interrupted state before exposing commands.
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
            "lean" => WorkflowTemplates.Lean(safeTitle, folder),
            "dag" => WorkflowTemplates.ParallelReview(safeTitle, folder),
            "dual" => WorkflowTemplates.DualAgent(safeTitle, folder),
            _ => throw new ArgumentException("未知工作流模板。", nameof(template))
        };
        _tasks.Add(task);
        ExecutionLedger.Append(task,null,"task.created");
        try { Save(); }
        catch { _tasks.Remove(task); throw; }
        return task;
    }

    public ContextBudgetPolicy.Assessment Preflight(string taskId, string stepId)
    {
        var task = GetTask(taskId);
        return ContextBudgetPolicy.Assess(task, WorkflowEngine.Find(task, stepId));
    }

    public void SetPromptBudget(string taskId, int warningTokens, int stopTokens)
    {
        ContextBudgetPolicy.Validate(warningTokens, stopTokens);
        Change(taskId, task =>
        {
            task.PromptWarningTokens = warningTokens;
            task.PromptStopTokens = stopTokens;
            ExecutionLedger.Append(task, null, "context.budget.updated",
                metadata: $"warning={warningTokens}; stop={stopTokens}; estimates-only");
        });
    }

    public void Approve(string taskId, string stepId)
        => Change(taskId, task => { WorkflowEngine.Approve(task, stepId);
            ExecutionLedger.Append(task,WorkflowEngine.Find(task,stepId),"stage.approved"); });

    public void AddStep(string taskId, string title, AgentKind agent, IReadOnlyList<string> dependencies)
        => Change(taskId, task =>
        {
            if (!task.GraphMode || task.Steps.Any(x=>x.Status!=StepStatus.Pending))
                throw new InvalidOperationException("只允许在未启动的 DAG 中添加阶段。");
            if (title.Trim().Length is < 1 or > 100 || dependencies.Count>50)
                throw new ArgumentException("阶段标题或依赖数量无效。");
            var step = new WorkflowStep { Title=title.Trim(), Agent=agent, DependsOn=dependencies.ToList(),
                Instructions="检查依赖阶段产物，并记录本阶段实际结果。" };
            task.Steps.Add(step);
            WorkflowGraph.Validate(task);
            ExecutionLedger.Append(task,step,"workflow.step.added");
        });

    public void SetDependencies(string taskId, string stepId, IReadOnlyList<string> dependencies)
        => Change(taskId, task =>
        {
            if(!task.GraphMode || task.Steps.Any(s=>s.Status!=StepStatus.Pending))
                throw new InvalidOperationException("运行后的 DAG 结构不可修改；请另建任务。");
            var step=WorkflowEngine.Find(task,stepId);
            step.DependsOn=dependencies.ToList();
            WorkflowGraph.Validate(task);
            ExecutionLedger.Append(task,step,"workflow.dependencies.updated");
        });

    public async Task<string> CreateStageWorktreeAsync(string taskId,string stepId)
    {
        var task=GetTask(taskId);
        var step=WorkflowEngine.Find(task,stepId);
        if(step.Status!=StepStatus.Pending || !string.IsNullOrWhiteSpace(step.WorktreePath))
            throw new InvalidOperationException("只允许为未开始的阶段创建一次独立 Worktree。");
        var created=await GitWorktreeService.CreateAsync(task.Workspace,task.Id,step.Id).ConfigureAwait(false);
        try
        {
            Change(taskId, t=>
            {
                var s=WorkflowEngine.Find(t,stepId);
                s.WorktreePath=created.Path;
                s.WorktreeBaseline=created.Head;
                ExecutionLedger.Append(t,s,"git.worktree.created",metadata:"local git worktree");
            });
        }
        catch
        {
            // Do not silently delete potentially modified worktrees. Explicit user reconciliation is required.
            throw new IOException("Worktree 已创建，但任务库保存失败。保留现场："+created.Path);
        }
        return created.Path;
    }

    public async Task CompleteWithGitAsync(string taskId, string stepId, string result)
    {
        var task = GetTask(taskId);
        var step = WorkflowEngine.Find(task, stepId); // Refuse an unknown stage before performing I/O.
        var after = await ProjectWorkspaceService.CaptureAsync(task.WorkspaceFor(step));
        Complete(taskId, stepId, result, after);
    }

    public void Complete(string taskId, string stepId, string result, ProjectWorkspaceService.GitCheckpoint? after = null)
    {
        ArgumentNullException.ThrowIfNull(result);
        if (result.Length > 12_000) throw new ArgumentException("阶段结果不能超过 12,000 字符。", nameof(result));
        Change(taskId, task =>
        {
            var step = WorkflowEngine.Find(task, stepId);
            WorkflowEngine.Complete(task, stepId, result);
            step.GitAfter = after;
            RequestTrace.Record(task, step, "stage.completed", "阶段结果已由用户确认并保存；模型调用次数未知");
            ExecutionLedger.Append(task,step,"stage.completed",metadata:after is null?"no git checkpoint":"git checkpoint");
        });
    }

    public async Task StartManualWithGitAsync(string taskId, string stepId)
    {
        var task = GetTask(taskId);
        WorkflowEngine.EnsureStartable(task, stepId);
        var before = await ProjectWorkspaceService.CaptureAsync(task.WorkspaceFor(WorkflowEngine.Find(task,stepId)));
        StartManual(taskId, stepId, before);
    }

    public void StartManual(string taskId, string stepId, ProjectWorkspaceService.GitCheckpoint? before = null)
        => Change(taskId, task =>
        {
            var step = WorkflowEngine.EnsureStartable(task, stepId);
            if (step.Agent != AgentKind.Manual) throw new InvalidOperationException("此阶段不是人工执行器。");
            step.GitBefore = before;
            step.GitAfter = null;
            WorkflowEngine.Start(task, stepId);
            RequestTrace.Record(task, step, "manual.started", "用户手动开始人工阶段；未启动模型");
            ExecutionLedger.Append(task,step,"stage.started",metadata:"manual");
        });

    public void Retry(string taskId, string stepId)
        => Change(taskId, task => {var step=WorkflowEngine.Find(task,stepId);
            WorkflowEngine.Retry(task,stepId);ExecutionLedger.Append(task,step,"stage.retry.armed");});

    public async Task LaunchWithGitAsync(string taskId, string stepId, Action<string> copyPrompt, Action<AgentKind, string> startCli, bool confirmDuplicate = false)
    {
        var task = GetTask(taskId);
        var ready = WorkflowEngine.EnsureStartable(task, stepId);
        ContextBudgetPolicy.RequireAllowed(task, ready, confirmDuplicate); // Before any file scan or clipboard write.
        var before = await ProjectWorkspaceService.CaptureAsync(task.WorkspaceFor(ready));
        Launch(taskId, stepId, copyPrompt, startCli, before, confirmDuplicate);
    }

    public void Launch(string taskId, string stepId, Action<string> copyPrompt, Action<AgentKind, string> startCli,
        ProjectWorkspaceService.GitCheckpoint? before = null, bool confirmDuplicate = false)
    {
        EnsureHealthy();
        var task = GetTask(taskId);
        var step = WorkflowEngine.EnsureStartable(task, stepId);
        if (step.Agent == AgentKind.Manual)
            throw new InvalidOperationException("人工阶段不能启动模型 CLI。");
        ContextBudgetPolicy.RequireAllowed(task, step, confirmDuplicate);
        var folder = WorkspaceGuard.RequireTrustedDirectory(task.WorkspaceFor(step));
        var draft = HandoffBuilder.Prepare(task, step);
        var oldBefore = step.GitBefore;
        var oldAfter = step.GitAfter;
        step.GitBefore = before;
        step.GitAfter = null;
        try { StageLaunchCoordinator.PrepareAndStart(task, step, draft, copyPrompt, Save); }
        catch { step.GitBefore = oldBefore; step.GitAfter = oldAfter; throw; }
        try
        {
            ExecutionLedger.Append(task,step,"cli.launch.intent",evidence:"unknown");
            Save();
            startCli(step.Agent, folder); // Official installed program, not an embedded API.
        }
        catch (Exception ex)
        {
            try
            {
                WorkflowEngine.Fail(task, step.Id, "本机 CLI 启动失败；未确认任何模型请求。");
                RequestTrace.Record(task, step, "cli.failed", "外部进程启动失败，实际模型调用仍未知");
                ExecutionLedger.Append(task,step,"cli.launch.failed",metadata:"local process launch failed");
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
        var stepSnapshots = task.Steps.Select(s => (s, s.Status, s.ApprovalGranted, s.Result, s.StartedAt, s.CompletedAt, s.GitBefore, s.GitAfter)).ToList();
        var oldEvents = task.RequestEvents.ToList();
        var oldLedger = task.ExecutionRecords.ToList();
        var oldDependencies=task.Steps.Select(x=>(x,x.DependsOn.ToList(),x.WorktreePath,x.WorktreeBaseline,x.RunId)).ToArray();
        var oldStepCount=task.Steps.Count;
        var oldWarningTokens = task.PromptWarningTokens;
        var oldStopTokens = task.PromptStopTokens;
        try { act(task); Save(); }
        catch
        {
            task.PromptWarningTokens = oldWarningTokens;
            task.PromptStopTokens = oldStopTokens;
            foreach (var (s,status,approved,result,start,completed,before,after) in stepSnapshots)
            {
                s.Status = status; s.ApprovalGranted = approved; s.Result = result;
                s.StartedAt = start; s.CompletedAt = completed; s.GitBefore = before; s.GitAfter = after;
            }
            foreach(var (s,deps,path,baseline,runId) in oldDependencies)
            { s.DependsOn=deps; s.WorktreePath=path; s.WorktreeBaseline=baseline; s.RunId=runId; }
            if(task.Steps.Count>oldStepCount) task.Steps.RemoveRange(oldStepCount,task.Steps.Count-oldStepCount);
            task.ExecutionRecords.Clear(); task.ExecutionRecords.AddRange(oldLedger);
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
