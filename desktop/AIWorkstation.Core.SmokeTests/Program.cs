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
    // V1.2: project explorer is read-only and stage evidence is explicitly non-attributive.
    Assert(ProjectWorkspaceService.ParsePorcelain(" M src/a.cs\0?? docs/new.md\0R  new.cs\0old.cs\0").Count == 3,
        "NUL porcelain parser supports modified, untracked and renamed entries");
    Assert(!ProjectWorkspaceService.IsSafeRelativePath("../secret")
        && !ProjectWorkspaceService.IsSafeRelativePath(".git/config")
        && !ProjectWorkspaceService.IsSafeRelativePath(".GIT/config")
        && !ProjectWorkspaceService.IsSafeRelativePath("C:/Windows/system.ini")
        && ProjectWorkspaceService.IsSafeRelativePath("src/nested/file.cs"),
        "project file paths exclude traversal, git internals and absolute paths");
    Assert(ThrowsAny(() => ProjectWorkspaceService.RequireSafeFile(workspace, "../outside.txt")),
        "file review rejects escaping the chosen workspace");
    var leftGit = new ProjectWorkspaceService.GitCheckpoint { Head = "1111111",
        Files = [new("src/a.cs", " M", "sha-one"), new("old.txt", "??", "old")] };
    var rightGit = new ProjectWorkspaceService.GitCheckpoint { Head = "2222222",
        Files = [new("src/a.cs", " M", "sha-two"), new("new.cs", "??", "new")] };
    var changeReport = ProjectWorkspaceService.Compare("step", "phase", leftGit, rightGit);
    Assert(changeReport.Files.Count == 3 && changeReport.HeadChanged && !changeReport.Partial,
        "stage change report captures changed fingerprints, new and cleared paths plus HEAD");
    Assert(changeReport.Notice.Contains("不能证明") && ProjectWorkspaceService.Compare("step", "phase", null, rightGit).Partial,
        "stage change reporting never attributes edits to model or invents missing evidence");
    Assert(ProjectWorkspaceService.ParseCommitPaths("M\0src/a.cs\0R100\0old.cs\0new.cs\0").SequenceEqual(["src/a.cs", "new.cs"]),
        "committed-file parser handles NUL output including renamed paths");
    Assert(ProjectWorkspaceService.ParseCommitRenames("R100\0old/src.cs\0new/src.cs\0M\0README.md\0").Single()
        == new ProjectWorkspaceService.ObservedRename("old/src.cs", "new/src.cs"),
        "explicit Git rename edges are parsed without path similarity guesses");
    if (AgentTools.Locate("git") is not null)
    {
        var repoDir = Path.Combine(workspace, "git-observation");
        Directory.CreateDirectory(repoDir);
        static void Git(string dir, params string[] argv)
        {
            var info = new System.Diagnostics.ProcessStartInfo("git") { WorkingDirectory = dir,
                RedirectStandardError = true, RedirectStandardOutput = true, UseShellExecute = false };
            foreach (var arg in argv) info.ArgumentList.Add(arg);
            using var proc = System.Diagnostics.Process.Start(info)!;
            var err = proc.StandardError.ReadToEnd();
            _ = proc.StandardOutput.ReadToEnd();
            proc.WaitForExit();
            if (proc.ExitCode != 0) throw new Exception("git fixture failure: " + err);
        }
        Git(repoDir, "init", "-q");
        Git(repoDir, "config", "user.email", "tests@aiws.invalid");
        Git(repoDir, "config", "user.name", "AIWS Tests");
        var observedFile = Path.Combine(repoDir, "hello.cs");
        File.WriteAllText(observedFile, "class A {}\n");
        Git(repoDir, "add", "hello.cs");
        Git(repoDir, "commit", "-q", "-m", "init");
        var clean = ProjectWorkspaceService.CaptureAsync(repoDir).GetAwaiter().GetResult();
        Assert(clean.Files.Count == 0 && !clean.Partial && clean.Head.Length >= 7,
            "clean Git baseline has real HEAD without phantom changes");
        File.WriteAllText(observedFile, "class A { int count = 1; }\n");
        File.WriteAllText(Path.Combine(repoDir, "added.ts"), "export const x = 1;\n");
        var changed = ProjectWorkspaceService.CaptureAsync(repoDir).GetAwaiter().GetResult();
        Assert(changed.Files.Any(x => x.Path == "hello.cs" && x.Status.Contains('M'))
            && changed.Files.Any(x => x.Path == "added.ts" && x.Status == "??"),
            "actual modified and untracked Git files are captured");
        var review = ProjectWorkspaceService.ReviewAsync(repoDir, "hello.cs").GetAwaiter().GetResult();
        Assert(review.Diff.Contains("+class A") && !review.IsPreview,
            "tracked file review returns actual local Git patch");
        var preview = ProjectWorkspaceService.ReviewAsync(repoDir, "added.ts").GetAwaiter().GetResult();
        Assert(preview.IsPreview && preview.Diff.Contains("export const x"),
            "new source files are previewed only when explicitly selected");
        var tree = ProjectWorkspaceService.InspectAsync(repoDir).GetAwaiter().GetResult();
        Assert(tree.Files.Any(x => x.Path == "hello.cs") && tree.Files.Any(x => x.Path == "added.ts")
            && !tree.Files.Any(x => x.Path.StartsWith(".git/")),
            "project explorer shows real files while skipping git internal metadata");
        Git(repoDir, "add", ".");
        Git(repoDir, "commit", "-q", "-m", "change tracked files");
        var committed = ProjectWorkspaceService.CaptureAsync(repoDir).GetAwaiter().GetResult();
        var committedReport = ProjectWorkspaceService.AnalyzeStageAsync(repoDir, "one", "stage", clean, committed).GetAwaiter().GetResult();
        Assert(committedReport.HeadChanged && committedReport.CommittedFiles.Contains("hello.cs")
            && committedReport.CommittedFiles.Contains("added.ts"),
            "committed paths are visible even after working tree becomes clean");
        // V1.7: structural directory changes are captured, compared and attributed to stage evidence only.
        Assert(clean.TreeCaptured && clean.Tree.Any(x => x.Path == "hello.cs" && !x.IsDirectory),
            "V1.7 baseline captures path inventory without source bodies");
        var worktask = WorkflowTemplates.DualAgent("structure test", repoDir);
        var examinedStage = worktask.Steps[0];
        examinedStage.GitBefore = clean;
        examinedStage.GitAfter = committed;
        var committedStructure = WorkspaceEvolutionService.InspectStageAsync(worktask, examinedStage).GetAwaiter().GetResult();
        Assert(committedStructure.HasBefore && committedStructure.HasAfter && !committedStructure.Partial
            && committedStructure.Entries.Any(x => x.Path == "added.ts" && x.Change == "added")
            && committedStructure.Entries.Any(x => x.Path == "hello.cs" && x.Change == "modified"),
            "committed Git changes remain visible in structural atlas after clean HEAD");
        var historyPatch = GitWorkspaceService.InspectHistoricalFileAsync(repoDir, clean.Head, committed.Head, "hello.cs")
            .GetAwaiter().GetResult();
        Assert(historyPatch.Output.Contains("+class A { int count") && historyPatch.ExitCode == 0,
            "committed file changes offer real read-only historical diff");
        var module = Path.Combine(repoDir, "src", "engine");
        Directory.CreateDirectory(module);
        File.WriteAllText(Path.Combine(module, "legacy.cs"), "class Old {}\n");
        Git(repoDir, "add", ".");
        Git(repoDir, "commit", "-q", "-m", "initialize engine module");
        var beforeStructure = ProjectWorkspaceService.CaptureAsync(repoDir).GetAwaiter().GetResult();
        File.Delete(Path.Combine(module, "legacy.cs"));
        Directory.Delete(module);
        var newModule = Path.Combine(repoDir, "src", "agents");
        Directory.CreateDirectory(newModule);
        File.WriteAllText(Path.Combine(newModule, "agent.cs"), "class Agent {}\n");
        var afterStructure = ProjectWorkspaceService.CaptureAsync(repoDir).GetAwaiter().GetResult();
        examinedStage.GitBefore = beforeStructure;
        examinedStage.GitAfter = afterStructure;
        var structure = WorkspaceEvolutionService.InspectStageAsync(worktask, examinedStage).GetAwaiter().GetResult();
        Assert(structure.Added == 1 && structure.Removed == 1 && structure.ChangedDirectories >= 2,
            "atlas detects module directory additions and deletions independently of Git file changes");
        Assert(structure.Entries.Any(x => x.Path == "src/agents/agent.cs" && x.Change == "added")
            && structure.Entries.Any(x => x.Path == "src/engine/legacy.cs" && x.Change == "removed"),
            "atlas file evidence supports expanding the before/after folder tree");
        var linked = WorkspaceEvolutionService.FindRelatedStagesAsync(worktask,"src/agents/agent.cs").GetAwaiter().GetResult();
        Assert(linked.Stages.Count == 1 && linked.Stages[0].StageId == examinedStage.Id,
            "clicking a changed file locates its observed stage without claiming model authorship");
        Assert(ThrowsAny(() => WorkspaceEvolutionService.FindRelatedStagesAsync(worktask, "../secret").GetAwaiter().GetResult()),
            "reverse stage lookup rejects traversal");
        var incomplete = new ProjectWorkspaceService.GitCheckpoint { Head = beforeStructure.Head };
        var partialStart = new ProjectWorkspaceService.GitCheckpoint { Head = beforeStructure.Head,
            TreeCaptured = true, TreePartial = true, Tree = [new("src", true)], Partial = true };
        var partialTree = WorkspaceEvolutionService.Compare(worktask, examinedStage, partialStart, afterStructure,
            ProjectWorkspaceService.Compare(examinedStage.Id, examinedStage.Title, partialStart, afterStructure));
        Assert(partialTree.Partial && partialTree.Entries.Any(x => x.Path == "src/agents/agent.cs" && x.Change == "unknown"),
            "truncated baseline cannot invent newly added files");
        var legacyStructure = WorkspaceEvolutionService.Compare(worktask, examinedStage, incomplete, afterStructure,
            ProjectWorkspaceService.Compare(examinedStage.Id, examinedStage.Title, incomplete, afterStructure));
        Assert(legacyStructure.Partial && !legacyStructure.HasBefore
            && legacyStructure.Entries.All(x => x.Change == "unknown"),
            "legacy checkpoints never fabricate added paths or a complete structural diff");
        repository.Save([worktask]);
        Assert(repository.Load()[0].Steps[0].GitAfter?.TreeCaptured == true,
            "new path inventory persists and is compatible with task JSON storage");
        var previewEvidence = ContextInspector.Preview(worktask, examinedStage);
        Assert(previewEvidence.Text.Contains("本阶段目标") && previewEvidence.ApproxTokens > 0
            && previewEvidence.Parts.Any(x => x.Kind == "instructions")
            && previewEvidence.Notice.Contains("本地"),
            "local context inspector exposes only known handoff text and estimated usage");
        Assert(ThrowsAny(() => GitWorkspaceService.InspectHistoricalFileAsync(repoDir,
            beforeStructure.Head, afterStructure.Head, "../escape.cs").GetAwaiter().GetResult()),
            "historical file diff blocks unsafe path");
        var changes = ProjectWorkspaceService.Compare("one", "stage", clean, changed);
        Assert(changes.Files.Count == 2 && !changes.Partial,
            "live stage comparison distinguishes two observed workspace changes");
        Assert(ThrowsAny(() => ProjectWorkspaceService.ReviewAsync(repoDir, "../outside.txt").GetAwaiter().GetResult()),
            "file patch endpoint refuses traversal before accessing Git");
        var sensitive = Path.Combine(repoDir, ".env.local");
        File.WriteAllText(sensitive, "secret=do-not-show");
        var blocked = ProjectWorkspaceService.ReviewAsync(repoDir, ".env.local").GetAwaiter().GetResult();
        Assert(!blocked.Diff.Contains("do-not-show") && !blocked.IsPreview,
            "sensitive untracked file contents are not previewed");
        var symlinkFile = Path.Combine(repoDir, "foreign.cs");
        try
        {
            File.CreateSymbolicLink(symlinkFile, observedFile);
            Assert(ThrowsAny(() => ProjectWorkspaceService.RequireSafeFile(repoDir, "foreign.cs")),
                "file-level symlinks cannot escape review protection");
        }
        catch (UnauthorizedAccessException) { Console.WriteLine("SKIP: file symlink requires privileges"); }
        catch (IOException) { Console.WriteLine("SKIP: file symlink creation unavailable"); }
    }
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
    // V1.3–V1.6: persisted events, safe DAG and stage-isolated execution model.
    var dag=WorkflowTemplates.ParallelReview("parallel-dag",workspace);
    WorkflowGraph.Validate(dag);
    Assert(dag.GraphMode && dag.Steps.Count==4 && WorkflowGraph.Ready(dag).Count==1,"DAG template starts with one prerequisite");
    WorkflowEngine.Start(dag,dag.Steps[0].Id);
    WorkflowEngine.Complete(dag,dag.Steps[0].Id,"scope reviewed");
    Assert(WorkflowGraph.Ready(dag).Count==2,"DAG branches become ready after planning");
    WorkflowEngine.Approve(dag,dag.Steps[1].Id);
    Assert(Throws(()=>WorkflowEngine.Start(dag,dag.Steps[1].Id))==false,"first branch can start");
    WorkflowEngine.Approve(dag,dag.Steps[2].Id);
    Assert(Throws(()=>WorkflowEngine.Start(dag,dag.Steps[2].Id)),"shared workspace prevents unsafe concurrent branches");
    dag.Steps[1].WorktreePath=workspace+"-isolated-one";
    dag.Steps[2].WorktreePath=workspace+"-isolated-two";
    WorkflowEngine.Start(dag,dag.Steps[2].Id);
    Assert(dag.Steps[2].Status==StepStatus.Running && dag.Steps[1].Status==StepStatus.Running,"independent worktrees permit concurrent DAG stages");
    Assert(Throws(()=>WorkflowEngine.Start(dag,dag.Steps[3].Id)),"join blocked until both branches complete");
    WorkflowEngine.Complete(dag,dag.Steps[1].Id,"implementation done");
    WorkflowEngine.Complete(dag,dag.Steps[2].Id,"review done");
    Assert(WorkflowGraph.Ready(dag).Single().Id==dag.Steps[3].Id,"DAG join unlocked after both dependencies finish");
    var compact=HandoffBuilder.Build(dag,dag.Steps[3]);
    Assert(compact.Contains("implementation done")&&compact.Contains("review done")&&!compact.Contains("scope reviewed"),"DAG context includes only direct dependencies");
    dag.Steps[0].DependsOn=[dag.Steps[3].Id];
    Assert(Throws(()=>WorkflowGraph.Validate(dag)),"DAG cycle rejected before persistence");
    dag.Steps[0].DependsOn=[];
    ExecutionLedger.Append(dag,dag.Steps[1],"git.worktree.observed",metadata:"local checkpoint");
    ExecutionLedger.Append(dag,dag.Steps[1],"provider.request.unknown",evidence:"unknown");
    Assert(ExecutionLedger.Timeline(dag).Count==2&&ExecutionLedger.Timeline(dag)[1].Evidence=="unknown","ledger distinguishes actual observation from unknown provider events");
    Assert(Throws(()=>ExecutionLedger.Append(dag,null,"too.much",metadata:new string('X',201))),"ledger rejects unbounded secret-bearing metadata");
    var dagFile=Path.Combine(workspace,"dag.json");
    var dagRepo=new TaskRepository(dagFile);
    dagRepo.Save([dag]);
    Assert(dagRepo.Load()[0].GraphMode && dagRepo.Load()[0].ExecutionRecords.Count==2,"DAG and evidence ledger persist in existing JSON format");
    using(var graphController=new WorkstationController(Path.Combine(workspace,"graph-controller")))
    {
        var project=Path.Combine(workspace,"graph-project");Directory.CreateDirectory(project);
        var graphTask=graphController.CreateTask("graph editing",project,"dag");
        graphController.AddStep(graphTask.Id,"extra review",AgentKind.Manual,[graphTask.Steps[1].Id]);
        Assert(graphTask.Steps.Count==5,"DAG editor adds a native persisted stage");
        Assert(Throws(()=>graphController.SetDependencies(graphTask.Id,graphTask.Steps[0].Id,[graphTask.Steps[4].Id])),"DAG editor refuses circular dependencies");
        Assert(graphTask.Steps[0].DependsOn.Count==0,"invalid DAG edit rolls back in memory");
    }
    if(AgentTools.Locate("git") is not null)
    {
        var source=Path.Combine(workspace,"isolation-repo");Directory.CreateDirectory(source);
        static void FixtureGit(string directory,params string[] args)
        {
            var p=new System.Diagnostics.ProcessStartInfo("git") {WorkingDirectory=directory,UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true};
            foreach(var a in args)p.ArgumentList.Add(a);
            using var process=System.Diagnostics.Process.Start(p)!;
            var stdout=process.StandardOutput.ReadToEnd();var stderr=process.StandardError.ReadToEnd();
            process.WaitForExit();if(process.ExitCode!=0)throw new Exception("git fixture failed: "+stderr+stdout);
        }
        FixtureGit(source,"init","-q");
        FixtureGit(source,"config","user.name","AIWS Tests");
        FixtureGit(source,"config","user.email","tests@aiws.invalid");
        File.WriteAllText(Path.Combine(source,"baseline.txt"),"stable base");
        FixtureGit(source,"add","baseline.txt");FixtureGit(source,"commit","-qm","baseline");
        var tid=Guid.NewGuid().ToString("N");var sid=Guid.NewGuid().ToString("N");
        var created=GitWorktreeService.CreateAsync(source,tid,sid).GetAwaiter().GetResult();
        Assert(Directory.Exists(created.Path)&&created.Head.Length>=7&&File.Exists(Path.Combine(created.Path,"baseline.txt")),"Git Worktree created from actual clean baseline");
        File.WriteAllText(Path.Combine(created.Path,"separate.txt"),"isolated change");
        Assert(!File.Exists(Path.Combine(source,"separate.txt")),"isolated change does not appear in main checkout");
        Assert(ThrowsAny(()=>GitWorktreeService.CreateAsync(source,tid,sid).GetAwaiter().GetResult()),"duplicate worktree creation is refused");
        Assert(ThrowsAny(()=>GitWorktreeService.CreateAsync(source,"../../bad",sid).GetAwaiter().GetResult()),"invalid task worktree id rejected");
    }
    Assert(!OperatingSystem.IsWindows() ? ThrowsAny(()=>ConPtyTerminal.StartPowerShell(workspace)) : true,
        "ConPTY rejects unsupported OS (real terminal requires Windows GUI acceptance)");

    // V1.7.2: deterministic AIWS-owned prompt-size guard, with no external model calls.
    var lean = WorkflowTemplates.Lean("simple change", workspace);
    Assert(lean.Steps.Count == 2 && lean.Steps.Count(x=>x.Agent!=AgentKind.Manual) == 1,
        "lean workflow avoids obligatory second model pass");
    var efficient = WorkflowTemplates.DualAgent("budget", workspace);
    var efficientStage = efficient.Steps[0];
    var baselineBudget = ContextBudgetPolicy.Assess(efficient, efficientStage);
    Assert(!baselineBudget.Blocked && baselineBudget.ApproxTokens>0 && !baselineBudget.Duplicate,
        "default preflight estimates only AIWS-owned draft without calling a provider");
    Assert(ThrowsAny(()=>ContextBudgetPolicy.Validate(499,600))
        && ThrowsAny(()=>ContextBudgetPolicy.Validate(8000,3000)),
        "invalid or inverted context thresholds are rejected");
    efficient.PromptWarningTokens=500;
    efficient.PromptStopTokens=650;
    efficientStage.Instructions=new string('界',1200);
    var over = ContextBudgetPolicy.Assess(efficient, efficientStage);
    Assert(over.Blocked && over.Warn && over.ApproxTokens>over.StopTokens,
        "large explicit stage instructions are surfaced and blocked, not silently truncated");
    Assert(ThrowsAny(()=>ContextBudgetPolicy.RequireAllowed(efficient,efficientStage)),
        "hard prompt-size preflight rejects launch before clipboard");
    efficientStage.Instructions="short instructions";
    var repeatDraft=HandoffBuilder.Prepare(efficient,efficientStage);
    efficientStage.LastPromptFingerprint=repeatDraft.Fingerprint;
    var again=ContextBudgetPolicy.Assess(efficient,efficientStage);
    Assert(again.Duplicate && ThrowsAny(()=>ContextBudgetPolicy.RequireAllowed(efficient,efficientStage)),
        "repeated identical prompt refuses unconfirmed relaunch");
    ContextBudgetPolicy.RequireAllowed(efficient,efficientStage,true);
    using(var budgetController=new WorkstationController(Path.Combine(workspace,"budget-store")))
    {
        var budgetTask=budgetController.CreateTask("budget persistence",workspace,"lean");
        Assert(budgetController.Preflight(budgetTask.Id,budgetTask.Steps[0].Id).ApproxTokens>0,
            "controller read-only preflight works before approval");
        budgetController.SetPromptBudget(budgetTask.Id,600,900);
        Assert(budgetTask.PromptWarningTokens==600 && budgetTask.PromptStopTokens==900,
            "local budget settings persist through the controller");
        Assert(ThrowsAny(()=>budgetController.SetPromptBudget(budgetTask.Id,900,600)),
            "invalid edit does not modify existing settings");
        budgetTask.Steps[0].Instructions=new string('中',1500);
        budgetController.Approve(budgetTask.Id,budgetTask.Steps[0].Id);
        var copied=false;var launched=false;
        Assert(ThrowsAny(()=>budgetController.Launch(budgetTask.Id,budgetTask.Steps[0].Id,
                _=>copied=true,(_,_)=>launched=true))
            && !copied && !launched && budgetTask.Steps[0].Status==StepStatus.Pending,
            "core refuses over-budget stage before clipboard or external CLI launch");
        budgetTask.Steps[0].Instructions="small and verifiable";
        budgetTask.Steps[0].LastPromptFingerprint=HandoffBuilder.Prepare(budgetTask,budgetTask.Steps[0]).Fingerprint;
        Assert(ThrowsAny(()=>budgetController.Launch(budgetTask.Id,budgetTask.Steps[0].Id,
                _=>copied=true,(_,_)=>launched=true)) && !copied && !launched,
            "core prevents accidental repeated launches without native confirmation");
    }
    using(var budgetReopen=new WorkstationController(Path.Combine(workspace,"budget-store")))
    {
        var saved=budgetReopen.Tasks.Single();
        Assert(saved.PromptWarningTokens==600 && saved.PromptStopTokens==900,
            "budget settings survive restart and JSON store validation");
    }

    // V1.8 Plan Studio: only explicitly recognized Markdown plans inside trusted workspaces.
    var planRoot=Path.Combine(workspace,"plan-studio-project");
    Directory.CreateDirectory(Path.Combine(planRoot,"docs","plans"));
    Directory.CreateDirectory(Path.Combine(planRoot,".claude","plans"));
    File.WriteAllText(Path.Combine(planRoot,"docs","ROADMAP.md"),"# 实施计划\n- [x] 分析\n- [ ] 构建\n");
    File.WriteAllText(Path.Combine(planRoot,"docs","plans","deployment.md"),"# 部署\n## 阶段一\n- [ ] 预检\n");
    File.WriteAllText(Path.Combine(planRoot,"docs","plans","secrets.md"),"PRIVATE");
    File.WriteAllText(Path.Combine(planRoot,"docs","notes.md"),"Not a plan");
    var planList=PlanWorkspaceService.List(planRoot);
    Assert(planList.Files.Count==2 && planList.Files.Any(x=>x.Path=="docs/ROADMAP.md")
        && planList.Files.Any(x=>x.Path=="docs/plans/deployment.md"),
        "plan discovery is bounded and limited to recognized Markdown plan locations");
    var planDoc=PlanWorkspaceService.ReadAsync(planRoot,"docs/ROADMAP.md").GetAwaiter().GetResult();
    Assert(planDoc.Text.Contains("[x]") && planDoc.Sha256.Length==64 && planDoc.Bytes>0,
        "plan document content and version evidence are read locally");
    File.WriteAllText(Path.Combine(planRoot,"docs","ROADMAP.md"),"# 实施计划\n- [x] 分析\n- [x] 构建\n");
    var planUpdated=PlanWorkspaceService.ReadAsync(planRoot,"docs/ROADMAP.md").GetAwaiter().GetResult();
    Assert(planUpdated.Sha256!=planDoc.Sha256,"plan file changes detected without model inference");
    Assert(!PlanWorkspaceService.IsAllowedPlanPath("../../secrets.md")
        && !PlanWorkspaceService.IsAllowedPlanPath("docs/notes.md")
        && !PlanWorkspaceService.IsAllowedPlanPath("docs/plans/secrets.md")
        && !PlanWorkspaceService.IsAllowedPlanPath("docs/routine/2026-11-20_log.md"),
        "plan reader refuses traversal, secret filenames and unrelated documents");
    Assert(ThrowsAny(()=>PlanWorkspaceService.ReadAsync(planRoot,"../../secrets.md").GetAwaiter().GetResult()),
        "plan reader does not access files outside workspace");
    File.WriteAllText(Path.Combine(planRoot,"docs","plans","oversize.md"),new string('x',262145));
    Assert(!PlanWorkspaceService.List(planRoot).Files.Any(x=>x.Name=="oversize.md")
        && ThrowsAny(()=>PlanWorkspaceService.ReadAsync(planRoot,"docs/plans/oversize.md").GetAwaiter().GetResult()),
        "oversized Markdown is rejected before materialization");
    try
    {
        File.CreateSymbolicLink(Path.Combine(planRoot,"docs","plans","linked.md"),
            Path.Combine(planRoot,"docs","ROADMAP.md"));
        Assert(!PlanWorkspaceService.List(planRoot).Files.Any(x=>x.Name=="linked.md")
            && ThrowsAny(()=>PlanWorkspaceService.ReadAsync(planRoot,"docs/plans/linked.md").GetAwaiter().GetResult()),
            "symlinked plan files are rejected");
    }
    catch (Exception ex) when (ex is UnauthorizedAccessException or System.PlatformNotSupportedException or IOException)
    {
        Console.WriteLine("SKIP: OS did not permit creating a symbolic-link fixture.");
    }

    // Unified control plane phases 1-3: durable task intent, deterministic context,
    // provider capabilities and switching without re-creating the user's work.
    var providers = ProviderAdapterRegistry.Describe(tool => tool == "codex");
    Assert(providers.Count == 3 && providers.Single(p => p.Id == "codex-cli").Available
        && !providers.Single(p => p.Id == "claude-cli").Available
        && providers.All(p => !p.SupportsUnattended && !p.CanObserveInternalRequests),
        "provider adapters disclose real capabilities without inventing unattended or internal request support");
    Assert(ThrowsAny(() => ProviderAdapterRegistry.IdFor((AgentKind)12345)),
        "invalid provider selection cannot silently fall back to Codex");
    var unifiedDir = Path.Combine(workspace,"unified-task-data");
    string savedTaskId;
    using (var control = new WorkstationController(unifiedDir))
    {
        var unified = control.CreateTask("跨 Agent 任务", planRoot, "lean");
        savedTaskId = unified.Id;
        Assert(unified.Unified.WorkItems.Count == unified.Steps.Count
            && unified.Unified.WorkItems.All(x=>x.Id==x.StageId),
            "unified work items are projections with stable stage IDs, not separate workflow authorities");
        control.SetTaskBrief(unified.Id,"重构项目组件","测试通过，Diff 可审查");
        var planFirst=control.LinkPlanAsync(unified.Id,"docs/ROADMAP.md").GetAwaiter().GetResult();
        var planDuplicate=control.LinkPlanAsync(unified.Id,"docs/ROADMAP.md").GetAwaiter().GetResult();
        Assert(planFirst && !planDuplicate && unified.Unified.Plans.Count==1,
            "verified plan revision is linked once without copying its contents");
        var firstStep=unified.Steps[0];
        control.Approve(unified.Id,firstStep.Id);
        control.SwitchAgent(unified.Id,firstStep.Id,AgentKind.ClaudeCode);
        Assert(firstStep.Agent==AgentKind.ClaudeCode && !firstStep.ApprovalGranted
            && unified.Unified.WorkItems.Single(x=>x.Id==firstStep.Id).Agent==AgentKind.ClaudeCode,
            "switching provider preserves the work item and revokes previous approval");
        var compiled=ContextCompiler.Compile(unified,firstStep);
        var sameDraft=HandoffBuilder.Prepare(unified,firstStep);
        Assert(compiled.AdapterId=="claude-cli" && compiled.Prompt.Contains("重构项目组件")
            && compiled.Prompt.Contains("验收条件") && compiled.Prompt.Contains("docs/ROADMAP.md")
            && compiled.Manifest.Any(x=>x.Kind=="plan-ref") && compiled.Prompt==sameDraft.Text
            && compiled.Fingerprint==sameDraft.Fingerprint,
            "context compiler builds one deterministic, source-labelled handoff for preflight and launch");
        Assert(!compiled.Prompt.Contains("# 实施计划") && compiled.Manifest.All(x=>x.ContentHash.Length==64),
            "handoff references plan hashes without reading and resending the whole Markdown plan");
        var summary=ContextCompiler.Summary(unified,firstStep);
        Assert(summary is not null && !summary.ToString()!.Contains("重构项目组件"),
            "safe handoff summary does not expose full prompt text");
        control.Approve(unified.Id,firstStep.Id);
        var copied=string.Empty;
        var invoked=false;
        control.Launch(unified.Id,firstStep.Id, text=>copied=text, (agent,root)=>
        {
            invoked=agent==AgentKind.ClaudeCode && root==planRoot;
        });
        Assert(invoked && copied==compiled.Prompt && firstStep.RunId.Length>0
            && unified.Unified.AgentRuns.Any(r=>r.Id==firstStep.RunId && r.Evidence=="local-intent"),
            "official CLI launch intent records adapter/run metadata without asserting a model request");
        Assert(ThrowsAny(()=>control.SwitchAgent(unified.Id,firstStep.Id,AgentKind.Codex)),
            "running provider cannot change and invalidate execution provenance");
        control.Complete(unified.Id,firstStep.Id,"实现并验证了核心工件");
        Assert(unified.Unified.Artifacts.Any(a=>a.Kind=="stage-result" && a.StageId==firstStep.Id
            && a.ContentHash==UnifiedTaskCore.HashText(firstStep.Result))
            && unified.Unified.AgentRuns.Single(r=>r.Id==firstStep.RunId).Status==StepStatus.Completed,
            "completed stage has immutable hashed artifact pointer and durable run status");
        var next=unified.Steps[1];
        var manualBundle=ContextCompiler.Compile(unified,next);
        Assert(manualBundle.Manifest.Any(x=>x.Kind=="stage-result" && x.Included)
            && manualBundle.Prompt.Contains("实现并验证了核心工件"),
            "handoff into manual review reuses confirmed work instead of cloning conversation history");
    }
    using (var reopened = new WorkstationController(unifiedDir))
    {
        var persisted=reopened.GetTask(savedTaskId);
        Assert(persisted.Unified.Goal=="重构项目组件" && persisted.Unified.Plans.Count==1
            && persisted.Unified.Artifacts.Count>=2 && persisted.Unified.AgentRuns.Count==1,
            "unified goal, plan revisions, artifacts and adapter run IDs survive restart");
        Assert(!File.ReadAllText(Path.Combine(unifiedDir,"tasks.json")).Contains("# 实施计划"),
            "local task database stores plan hashes rather than the imported plan body");
    }
    // Backward compatibility: an old JSON task lacking 'Unified' can still be read,
    // reconciled, saved and reloaded without changing existing IDs.
    var legacyPath=Path.Combine(workspace,"legacy-unified-migration.json");
    var legacyRepo=new TaskRepository(legacyPath);
    var legacy=WorkflowTemplates.Lean("旧版任务", planRoot);
    legacyRepo.Save([legacy]);
    var oldTree=System.Text.Json.Nodes.JsonNode.Parse(File.ReadAllText(legacyPath))!;
    oldTree.AsArray()[0]!.AsObject().Remove("Unified");
    File.WriteAllText(legacyPath,oldTree.ToJsonString());
    var upgraded=legacyRepo.Load().Single();
    Assert(upgraded.Unified.SchemaVersion==1 && upgraded.Unified.WorkItems.Select(x=>x.StageId)
            .SequenceEqual(legacy.Steps.Select(x=>x.Id)),
        "legacy JSON migrates to unified metadata while preserving pre-existing stage IDs");
    legacyRepo.Save([upgraded]);
    Assert(legacyRepo.Load().Single().Unified.WorkItems.Count==2,
        "migration remains valid under atomic backup and round-trip JSON validation");

    // Phases 4–6: restart-safe, zero-token scheduler, consolidated health evidence and privacy export.
    var schedulerData=Path.Combine(workspace,"scheduler-restart-data");
    var available=ProviderAdapterRegistry.Describe(name=>name=="codex");
    string scheduledTaskId, scheduledStageId, firstTicket;
    using(var ctrl=new WorkstationController(schedulerData))
    {
        var work=ctrl.CreateTask("SECRET_TASK_NAME",planRoot,"lean");
        scheduledTaskId=work.Id;
        scheduledStageId=work.Steps[0].Id;
        var firstPlan=AgentScheduler.Build(work,available);
        Assert(firstPlan.Stages[0].Status=="approval" && firstPlan.NextStageId==scheduledStageId
            && firstPlan.ReadyStages==0 && firstPlan.QueuedStages==0,
            "scheduler surfaces explicit approval without any hidden provider call");
        Assert(ThrowsAny(()=>ctrl.QueueStage(work.Id,scheduledStageId,available)),
            "scheduler refuses enqueue before an approved stage");
        ctrl.Approve(work.Id,scheduledStageId);
        var ready=AgentScheduler.Build(work,available);
        Assert(ready.Stages[0].Status=="ready" && ready.Stages[0].ApproxTokens>0,
            "scheduler derives readiness and estimates from persisted AIWS evidence");
        firstTicket=ctrl.QueueStage(work.Id,scheduledStageId,available);
        Assert(firstTicket.Length>10 && AgentScheduler.Build(work,available).Stages[0].Status=="queued"
            && work.Steps[0].Status==StepStatus.Pending,
            "queue persists only intent, never starts a CLI or modifies stage state");
        Assert(ThrowsAny(()=>ctrl.QueueStage(work.Id,scheduledStageId,available)),
            "duplicate dispatch ticket is rejected");
        Assert(ThrowsAny(()=>ctrl.SetRecommendedConcurrency(work.Id,6)),
            "recommended concurrency limit is bounded");
        ctrl.SetRecommendedConcurrency(work.Id,2);
        Assert(AgentScheduler.Build(work,available).MaxRecommendedActive==2,
            "scheduler concurrency policy updates local projections only");
        var redacted=ctrl.RedactedDiagnosticReport();
        Assert(redacted.Contains("unknownUsageStages",StringComparison.OrdinalIgnoreCase)
            && !redacted.Contains("SECRET_TASK_NAME") && !redacted.Contains(planRoot),
            "diagnostic export excludes task names, project paths and raw source content");
    }
    using(var reopened=new WorkstationController(schedulerData))
    {
        var work=reopened.GetTask(scheduledTaskId);
        Assert(work.Unified.DispatchRequests.Single(x=>x.Id==firstTicket).State=="queued"
            && work.Unified.MaxRecommendedActive==2,
            "scheduler tickets and concurrency preferences survive process restart");
        reopened.CancelQueuedStage(work.Id,firstTicket);
        Assert(work.Unified.DispatchRequests.Single(x=>x.Id==firstTicket).State=="cancelled",
            "operator can revoke a ticket without starting a model");
        var second=reopened.QueueStage(work.Id,scheduledStageId,available);
        Assert(second!=firstTicket,"requeued work obtains a fresh non-replayable ticket");
        reopened.SetTaskBrief(work.Id,"NEW_SECRET_GOAL","validated output");
        Assert(work.Unified.DispatchRequests.Single(x=>x.Id==second).State=="cancelled"
            && !work.Steps[0].ApprovalGranted,
            "editing task intent invalidates queued prompt fingerprints and approval");
        Assert(ThrowsAny(()=>reopened.QueueStage(work.Id,scheduledStageId,available)),
            "a changed goal cannot reuse an old write/launch approval");
        reopened.Approve(work.Id,scheduledStageId);
        var fresh=reopened.QueueStage(work.Id,scheduledStageId,available);
        var launched=0;
        reopened.Launch(work.Id,scheduledStageId,_=>{},(_agent,_root)=>launched++);
        Assert(launched==1 && work.Steps[0].Status==StepStatus.Running &&
            work.Unified.DispatchRequests.Single(x=>x.Id==fresh).State=="consumed",
            "explicitly approved CLI dispatch consumes queued intent exactly once");
        Assert(ThrowsAny(()=>reopened.Launch(work.Id,scheduledStageId,_=>{},(_agent,_root)=>launched++))
            && launched==1,"replay of running dispatch is blocked");
        var diagnostic=reopened.RedactedDiagnosticReport();
        Assert(!diagnostic.Contains("NEW_SECRET_GOAL") && !diagnostic.Contains("SECRET_TASK_NAME"),
            "health export never includes the live user goal or task title");
    }
    using(var reopened=new WorkstationController(schedulerData))
    {
        var work=reopened.GetTask(scheduledTaskId);
        Assert(work.Steps[0].Status==StepStatus.Interrupted
            && work.Unified.DispatchRequests.All(x=>x.State!="queued"),
            "restart marks incomplete execution interrupted; scheduler never replays it automatically");
    }
    Console.WriteLine("All native core smoke tests passed.");
}
finally
{
    // Git for Windows stores object files with the ReadOnly attribute. Remove only that
    // attribute from test fixture files; otherwise Directory.Delete(recursive:true)
    // throws UnauthorizedAccessException even when all assertions passed.
    if (OperatingSystem.IsWindows() && Directory.Exists(workspace))
    {
        foreach (var path in Directory.EnumerateFiles(workspace, "*", SearchOption.AllDirectories))
        {
            var attributes = File.GetAttributes(path);
            if ((attributes & FileAttributes.ReadOnly) != 0 && (attributes & FileAttributes.ReparsePoint) == 0)
                File.SetAttributes(path, attributes & ~FileAttributes.ReadOnly);
        }
    }
    Directory.Delete(workspace, true);
}
