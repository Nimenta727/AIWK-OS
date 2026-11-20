using System.Text.Json;
using AIWorkstation.Core;

static void Assert(bool condition, string label)
{
    if (!condition) throw new Exception("FAILED: " + label);
    Console.WriteLine("PASS: " + label);
}
static bool ThrowsAny(Action action)
{
    try { action(); return false; }
    catch (Exception) { return true; }
}
static bool Throws(Action action)
{
    try { action(); return false; }
    catch (InvalidOperationException) { return true; }
    catch (ArgumentException) { return true; }
    catch (InvalidDataException) { return true; }
}

// Professional frontend bridge must never silently load an arbitrary remote site or token URL.
Assert(LocalFrontendEndpoint.TryParse("http://127.0.0.1:3773/", out var localT3) && localT3 is not null, "T3 local UI allowed");
Assert(LocalFrontendEndpoint.TryParse("http://localhost:18789/", out var localClaw) && localClaw is not null, "OpenClaw loopback allowed");
Assert(!LocalFrontendEndpoint.TryParse("https://example.com/", out _), "remote site rejected");
Assert(!LocalFrontendEndpoint.TryParse("http://localhost:3773/?token=secret", out _), "URL token rejected");
Assert(!LocalFrontendEndpoint.TryParse("file:///C:/Windows/system.ini", out _), "file scheme rejected");
Assert(!LocalFrontendEndpoint.TryParse("http://localhost.evil.com:3773/", out _), "lookalike hostname rejected");
Assert(!LocalFrontendEndpoint.TryParse("http://foo:pass@localhost:3773/", out _), "embedded credentials rejected");
Assert(LocalFrontendEndpoint.IsWithinOrigin(new Uri("http://127.0.0.1:3773/chat"), localT3!), "same-origin UI navigation allowed");
Assert(!LocalFrontendEndpoint.IsWithinOrigin(new Uri("http://127.0.0.1:3774/"), localT3!), "other port navigation rejected");
Assert(ThrowsAny(() => T3ServiceLauncher.StartLoopback(80)), "official CLI refuses privileged service port before launching");
Assert(ThrowsAny(() => T3ServiceLauncher.StartLoopback(65536)), "official CLI refuses invalid service port before launching");

var safeBase = OperatingSystem.IsWindows() ? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) : Path.GetTempPath();
var workspace = Path.Combine(safeBase, "aiws-desktop-tests-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(workspace);
try
{
    var task = WorkflowTemplates.DualAgent("验证工作台", workspace);
    Assert(task.Steps.Count == 3, "workflow contains 3 executable stages");
    Assert(task.Steps[1].RequiresApproval, "implementation requires approval");
    Assert(Throws(() => WorkflowEngine.Start(task, task.Steps[1].Id)), "no out-of-order stage start");
    WorkflowEngine.Start(task, task.Steps[0].Id);
    Assert(Throws(() => WorkflowEngine.Complete(task, task.Steps[0].Id, " ")), "result cannot be blank");
    WorkflowEngine.Complete(task, task.Steps[0].Id, "分析通过");
    Assert(Throws(() => WorkflowEngine.Start(task, task.Steps[1].Id)), "approval gate enforced");
    WorkflowEngine.Approve(task, task.Steps[1].Id);
    WorkflowEngine.Start(task, task.Steps[1].Id);
    WorkflowEngine.Fail(task, task.Steps[1].Id, "人为失败");
    Assert(!task.Steps[1].ApprovalGranted, "failure invalidates approval");
    WorkflowEngine.Retry(task, task.Steps[1].Id);
    Assert(Throws(() => WorkflowEngine.Start(task, task.Steps[1].Id)), "retry requires new approval");
    WorkflowEngine.Approve(task, task.Steps[1].Id);
    WorkflowEngine.Start(task, task.Steps[1].Id);
    WorkflowEngine.Complete(task, task.Steps[1].Id, "实现完成");
    var brief = HandoffBuilder.Build(task, task.Steps[2]);
    Assert(brief.Contains("分析通过") && brief.Contains("实现完成"), "handoff passes prior results");
    Assert(brief.Contains("docs/routine"), "handoff carries development logging rule");
    Assert(task.CompletedCount == 2, "progress computed");
    var file = Path.Combine(workspace, "tasks.json");
    var repository = new TaskRepository(file);
    repository.Save([task]);
    var loaded = repository.Load();
    Assert(loaded.Count == 1 && loaded[0].Steps[1].Status == StepStatus.Completed, "persisted state survives reload");
    repository.Save(loaded);
    Assert(File.Exists(file + ".bak"), "save maintains a backup");
    Assert(Throws(() => WorkspaceGuard.RequireTrustedDirectory(Path.GetPathRoot(workspace)!)), "reject drive root");
    Assert(WorkspaceGuard.RequireTrustedDirectory(workspace) == workspace, "trusted existing workspace accepted");
    Assert(AgentTools.Locate("claude") == null || AgentTools.Locate("claude") is string, "agent locator operates without shell");
    // Request trace / usage import: only structured metadata; repeated imports must never double-count.
    var first = task.Steps[0];
    var before = new string('A', 3000);
    first.Result = before;
    var draft = HandoffBuilder.Prepare(task, task.Steps[1]);
    Assert(draft.Text.Contains("已省略其余内容") && !draft.Text.Contains(before), "handoff prunes verbose history");
    Assert(draft.Text.Contains("docs/routine"), "handoff preserves project policy");
    Assert(draft.ApproxTokens > 0 && draft.SavedCharacters > 0, "estimates are labelled and context reduced");
    RequestTrace.Record(task, task.Steps[1], "stage.started", "人工启动");
    var codexLog = "{\"type\":\"thread.started\"}\n" +
        "{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":100,\"output_tokens\":30,\"cached_input_tokens\":25}}\n" +
        "{\"type\":\"item.started\",\"item\":{\"type\":\"command_execution\",\"command\":\"SECRET_PRIVATE_COMMAND\"}}\n" +
        "{\"type\":\"item.completed\",\"item\":{\"type\":\"command_execution\",\"command\":\"SECRET_PRIVATE_COMMAND\"}}\n" +
        "{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":50,\"output_tokens\":20,\"cached_input_tokens\":10}}\n";
    var report = RequestTrace.Import(task, task.Steps[1], codexLog);
    Assert(report.UsageEvents == 2 && report.Input == 150 && report.CachedInput == 35 && report.Output == 50, "Codex usage aggregated across turns");
    Assert(RequestTrace.Import(task, task.Steps[1], codexLog).WasDuplicate, "duplicate import does not count twice");
    Assert(Throws(() => RequestTrace.Import(task, first, codexLog)), "mismatched provider is rejected");
    var claudeLog = "{\"type\":\"assistant\",\"message\":{\"usage\":{\"input_tokens\":1000}}}\n" +
        "{\"type\":\"result\",\"usage\":{\"input_tokens\":80,\"output_tokens\":15,\"cache_read_input_tokens\":20,\"cache_creation_input_tokens\":10}}\n";
    var claudeReport = RequestTrace.Import(task, first, claudeLog);
    Assert(claudeReport.Input == 110 && claudeReport.CachedInput == 20 && claudeReport.Output == 15, "Claude cache token categories normalized");
    Assert(task.RequestEvents.Count >= 3, "trace persists workflow metadata");
    repository.Save([task]);
    var traced = repository.Load()[0];
    Assert(traced.Steps[0].Usage.IsMeasured && traced.Steps[1].Usage.IsMeasured && traced.RequestEvents.Count > 0, "usage and trace persist without raw JSONL");
    Assert(!File.ReadAllText(file).Contains("thread.started"), "raw provider log is not persisted");
    // V1.1: read-only developer tools never accept a shell command or arbitrary Git argv.
    Assert(GitWorkspaceService.SupportedViews.Contains("diff") && !GitWorkspaceService.SupportedViews.Contains("push"),
        "Git inspector exposes a fixed read-only view allowlist");
    Assert(ThrowsAny(() => GitWorkspaceService.InspectAsync(workspace, "push").GetAwaiter().GetResult()),
        "Git inspector rejects arbitrary git push command");
    Assert(ThrowsAny(() => GitWorkspaceService.InspectAsync(workspace, "status; whoami").GetAwaiter().GetResult()),
        "Git inspector rejects shell injection via view parameter");
    var capabilities = WindowsToolPolicy.Describe();
    Assert(capabilities.Count == 4 && capabilities.All(x => !string.IsNullOrWhiteSpace(x.Detail)),
        "Windows capability inventory is explicit and documented");
    Assert(capabilities.Single(x => x.Id == "shell.user").RequiresUserConfirmation,
        "interactive PowerShell is user initiated, not an autonomous agent tool");
    if (AgentTools.Locate("git") is not null)
    {
        var gitWorkspace = Path.Combine(workspace, "git-workspace");
        Directory.CreateDirectory(gitWorkspace);
        var gitProgram = AgentTools.Locate("git")!;
        using var init = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(gitProgram)
        {
            WorkingDirectory = gitWorkspace,
            ArgumentList = { "init", "-q" },
            UseShellExecute = false,
            CreateNoWindow = true
        })!;
        init.WaitForExit();
        Assert(init.ExitCode == 0, "fixture Git repository initializes");
        File.WriteAllText(Path.Combine(gitWorkspace, "review-me.txt"), "local fixture");
        var status = GitWorkspaceService.InspectAsync(gitWorkspace, "status").GetAwaiter().GetResult();
        Assert(status.ExitCode == 0 && status.Output.Contains("review-me.txt"),
            "Git inspector returns real read-only worktree status");
        var summary = GitWorkspaceService.InspectAsync(gitWorkspace, "summary").GetAwaiter().GetResult();
        Assert(summary.ExitCode == 0 && summary.View == "summary", "Git summary is read-only and completes");
    }
    // V0.6 evidence-based request flow: a process launch must not become a fabricated model request.
    var graph = CallFlowBuilder.Build(task);
    Assert(graph.Lanes.Count == 3 && graph.Nodes.Count() == 15, "request flow builds five linked phases per stage");
    Assert(graph.UnknownUsageStages == 1 && graph.ImportedStages == 2, "unknown model usage remains unknown rather than zero");
    Assert(graph.ImportedTokens == 325 && graph.ImportedCachedInput == 55, "imported input/output and cache totals have independent accounting");
    Assert(graph.Lanes[1].ImportedEvents.Count == 4 && graph.ImportedToolEvents == 2, "Codex turn and tool metadata recorded in ordered evidence chain");
    Assert(graph.Lanes[1].ImportedEvents[1].ToolCategory == "command_execution", "tool category retained without the command itself");
    var codexNodes = graph.Lanes[1].Nodes;
    Assert(codexNodes.Select(n => n.Phase).SequenceEqual(new[] { FlowPhase.Routing, FlowPhase.Context, FlowPhase.Launcher, FlowPhase.Provider, FlowPhase.Handoff }), "node order reflects actual workflow lifecycle");
    Assert(codexNodes[2].State == FlowState.Unknown && codexNodes[3].State == FlowState.Imported,
        "stage.started does not imply CLI launch, imported metrics retain provenance");
    Assert(codexNodes[3].Detail.Contains("工具调用次数未知") || codexNodes[3].Detail.Contains("工具事件"), "tool provenance is explicitly explained");
    RequestTrace.Record(task, task.Steps[1], "cli.launched", "子进程已打开");
    RequestTrace.Record(task, task.Steps[1], "prompt.reused", "复制相同提示词");
    graph = CallFlowBuilder.Build(task);
    Assert(graph.Lanes[1].Nodes[2].State == FlowState.Recorded, "CLI launch is represented as local evidence only");
    Assert(graph.Lanes[1].Nodes[1].State == FlowState.Attention && graph.DuplicatePreparations == 1,
        "repeated context is visible without asserting duplicate model cost");
    var json = graph.ToRedactedJson();
    Assert(json.Contains("aiws.callflow.v1") && json.Contains("ImportedStages"), "redacted JSON carries trace schema and metrics");
    Assert(!json.Contains(task.Title) && !json.Contains(task.Workspace) && !json.Contains(before) && !json.Contains("子进程已打开") && !json.Contains("SECRET_PRIVATE_COMMAND"),
        "trace export excludes prompts, files, response bodies and free-text event logs");
    repository.Save([task]);
    var reloadGraph = CallFlowBuilder.Build(repository.Load()[0]);
    Assert(reloadGraph.Lanes[1].Nodes[2].State == FlowState.Recorded && reloadGraph.ImportedTokens == graph.ImportedTokens && reloadGraph.Lanes[1].ImportedEvents.Count == 4,
        "request flow survives local restart without storing original provider logs");
    // V0.7: single writer lease rejects duplicate application instances.
    var leaseDirectory = Path.Combine(workspace, "lease");
    using (WorkspaceLease.Acquire(leaseDirectory))
        Assert(ThrowsAny(() => WorkspaceLease.Acquire(leaseDirectory)), "exclusive workspace lease prevents concurrent writers");
    using (WorkspaceLease.Acquire(leaseDirectory))
        Assert(true, "workspace lease is released after disposal");

    // Atomic persistence: do not overwrite an invalid primary or silently use .bak.
    var recoveryFile = Path.Combine(workspace, "recovery.json");
    var recoveryRepo = new TaskRepository(recoveryFile);
    recoveryRepo.Save([WorkflowTemplates.Research("snapshot one", workspace)]);
    recoveryRepo.Save([WorkflowTemplates.Research("snapshot two", workspace)]);
    Assert(recoveryRepo.HasBackup && recoveryRepo.Load()[0].Title == "snapshot two", "validated primary and backup exist");
    File.WriteAllText(recoveryFile, "{invalid json");
    Assert(Throws(() => recoveryRepo.Load()), "corrupted primary is not treated as an empty database");
    Assert(Throws(() => recoveryRepo.Save([])), "save refuses to clobber corrupted primary and backup");
    var badPath = recoveryRepo.RestoreBackup();
    Assert(File.Exists(badPath) && File.ReadAllText(badPath).Contains("invalid json"), "explicit recovery preserves corrupt evidence");
    Assert(recoveryRepo.Load()[0].Title == "snapshot one" && recoveryRepo.HasBackup, "explicit recovery restores validated previous snapshot");
    File.Delete(recoveryFile);
    Assert(Throws(() => recoveryRepo.Load()) && Throws(() => recoveryRepo.Save([])), "missing primary plus backup refuses silent fresh start");
    recoveryRepo.RestoreBackup();

    var corruptIdsFile = Path.Combine(workspace, "duplicates.json");
    var duplicate = WorkflowTemplates.Research("dupe", workspace);
    File.WriteAllText(corruptIdsFile, JsonSerializer.Serialize(new[] { duplicate, duplicate })); // valid JSON, invalid domain identities
    Assert(Throws(() => new TaskRepository(corruptIdsFile).Load()), "duplicate task identities rejected on load");

    // Clipboard or disk failure must not create a phantom active stage.
    var gatedTask = WorkflowTemplates.DualAgent("guarded", workspace);
    var stage = gatedTask.Steps[0];
    var plan = HandoffBuilder.Prepare(gatedTask, stage);
    Assert(ThrowsAny(() => StageLaunchCoordinator.PrepareAndStart(gatedTask, stage, plan,
        _ => throw new IOException("clipboard busy"), () => { })) && stage.Status == StepStatus.Pending,
        "clipboard failure leaves stage Pending");
    Assert(ThrowsAny(() => StageLaunchCoordinator.PrepareAndStart(gatedTask, stage, plan,
        _ => { }, () => throw new IOException("disk full"))) && stage.Status == StepStatus.Pending
        && gatedTask.RequestEvents.Count == 0 && stage.LastPromptFingerprint == "",
        "durability failure rolls back in-memory running state and transient events");
    StageLaunchCoordinator.PrepareAndStart(gatedTask, stage, plan, _ => { }, () => { });
    Assert(stage.Status == StepStatus.Running && gatedTask.RequestEvents.Any(e => e.Kind == "stage.started"),
        "durable launch intent is distinct from an actual model request");
    Assert(WorkflowEngine.MarkInterrupted(gatedTask) == 1 && stage.Status == StepStatus.Interrupted,
        "startup recovery marks running stage Interrupted without automatic retry");
    Assert(Throws(() => WorkflowEngine.Start(gatedTask, stage.Id)), "interrupted stage cannot be restarted implicitly");
    WorkflowEngine.Retry(gatedTask, stage.Id);
    Assert(stage.Status == StepStatus.Pending && !stage.ApprovalGranted, "interrupted stage requires explicit retry");

    var gateTask = WorkflowTemplates.DualAgent("approval", workspace);
    WorkflowEngine.Start(gateTask, gateTask.Steps[0].Id);
    WorkflowEngine.Complete(gateTask, gateTask.Steps[0].Id, "ok");
    WorkflowEngine.Approve(gateTask, gateTask.Steps[1].Id);
    WorkflowEngine.Start(gateTask, gateTask.Steps[1].Id);
    Assert(!gateTask.Steps[1].ApprovalGranted, "one-shot approval is consumed on start");

    var impossibleUsage = "{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":100,\"output_tokens\":20,\"cached_input_tokens\":300}}";
    Assert(Throws(() => RequestTrace.Import(gateTask, gateTask.Steps[1], impossibleUsage)),
        "invalid cached-token > input-token telemetry rejected");
    var hugeUsage = "{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":9223372036854775807,\"output_tokens\":1}}";
    Assert(Throws(() => RequestTrace.Import(gateTask, gateTask.Steps[1], hugeUsage)),
        "unreasonable token magnitudes are rejected without false totals");
    if (OperatingSystem.IsWindows())
        Assert(Throws(() => WorkspaceGuard.RequireTrustedDirectory(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile))),
            "entire user home is not allowed as a workspace");
    // On operating systems where symlink creation is permitted, validate traversal protection.
    var symlink = Path.Combine(workspace, "linked-workspace");
    try
    {
        Directory.CreateSymbolicLink(symlink, workspace);
        Assert(Throws(() => WorkspaceGuard.RequireTrustedDirectory(symlink)), "workspace reparse links are rejected");
        Directory.Delete(symlink);
    }
    catch (UnauthorizedAccessException) { Console.WriteLine("SKIP: symlink creation needs privileges"); }
    catch (IOException) { Console.WriteLine("SKIP: symlink creation unavailable"); }

    // V1.0 source-recomposition: bridge-independent controller tests.
    var bridgeRoot = Path.Combine(workspace, "bridge-root");
    var projectRoot = Path.Combine(workspace, "bridge-project");
    Directory.CreateDirectory(projectRoot);
    string controllerTaskId;
    using (var ctl = new WorkstationController(bridgeRoot))
    {
        var created = ctl.CreateTask("AIWS use case", projectRoot, "dual");
        controllerTaskId = created.Id;
        Assert(ctl.Tasks.Count == 1, "AIWS controller creates a real durable task");
        Assert(Throws(() => ctl.Approve(controllerTaskId, created.Steps[1].Id)), "controller respects prerequisite ordering");
        Assert(ThrowsAny(() => ctl.Launch(controllerTaskId, created.Steps[0].Id,
            _ => { }, (_, _) => throw new IOException("simulated external CLI failure"))), "external launch failure surfaces to UI");
        Assert(created.Steps[0].Status == StepStatus.Failed && created.RequestEvents.Any(e => e.Kind == "cli.failed"),
            "failed CLI launch never masquerades as successful provider request");
    }
    using (var reopened = new WorkstationController(bridgeRoot))
        Assert(reopened.GetTask(controllerTaskId).Steps[0].Status == StepStatus.Failed,
            "controller persisted failure survives restart");
    using (var manualControl = new WorkstationController(Path.Combine(workspace, "manual-test-store")))
    {
        var manualTask = manualControl.CreateTask("research", projectRoot, "research");
        WorkflowEngine.Start(manualTask, manualTask.Steps[0].Id);
        WorkflowEngine.Complete(manualTask, manualTask.Steps[0].Id, "plan");
        WorkflowEngine.Start(manualTask, manualTask.Steps[1].Id);
        WorkflowEngine.Complete(manualTask, manualTask.Steps[1].Id, "review");
        Assert(Throws(() => manualControl.StartManual(manualTask.Id, manualTask.Steps[2].Id)), "manual phase approval required");
        manualControl.Approve(manualTask.Id, manualTask.Steps[2].Id);
        manualControl.StartManual(manualTask.Id, manualTask.Steps[2].Id);
        Assert(manualTask.Steps[2].Status == StepStatus.Running && manualTask.RequestEvents.Any(e => e.Kind == "manual.started"), "manual stage starts without a model call");
    }
    Console.WriteLine("All native core smoke tests passed.");
}
finally
{
    Directory.Delete(workspace, true);
}
