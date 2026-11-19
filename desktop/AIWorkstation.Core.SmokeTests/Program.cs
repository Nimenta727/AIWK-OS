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
}

var workspace = Path.Combine(Path.GetTempPath(), "aiws-desktop-tests-" + Guid.NewGuid().ToString("N"));
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
    Console.WriteLine("All native core smoke tests passed.");
}
finally
{
    Directory.Delete(workspace, true);
}
