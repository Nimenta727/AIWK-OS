using AIWorkstation.Core;

static void Assert(bool condition, string label)
{
    if (!condition) throw new Exception("FAILED: " + label);
    Console.WriteLine("PASS: " + label);
}
static bool Throws(Action action)
{
    try { action(); return false; }
    catch (InvalidOperationException) { return true; }
    catch (ArgumentException) { return true; }
    catch (InvalidDataException) { return true; }
}

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
    Console.WriteLine("All native core smoke tests passed.");
}
finally
{
    Directory.Delete(workspace, true);
}
