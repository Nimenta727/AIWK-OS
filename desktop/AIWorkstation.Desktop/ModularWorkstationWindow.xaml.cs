using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Windows;
using AIWorkstation.Core;
using Microsoft.Win32;
using Microsoft.Web.WebView2.Core;

namespace AIWorkstation.Desktop;

/// <summary>
/// AIWS-owned, offline React UI inside a native WPF executable. No upstream
/// website/server is embedded. The only bridge is a narrow allowlisted protocol.
/// </summary>
public partial class ModularWorkstationWindow : Window
{
    private const string TrustedHost = "aiws.local";
    private readonly WorkstationController _controller;
    private ConPtyTerminal? _terminal;
    private static readonly JsonSerializerOptions WireOptions = new(JsonSerializerDefaults.Web)
    {
        Converters = { new JsonStringEnumConverter() }
    };

    public ModularWorkstationWindow()
    {
        InitializeComponent();
        var appRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WindowsAIWorkstation");
        _controller = new WorkstationController(appRoot);
        Closed += (_, _) => { _terminal?.Dispose(); _controller.Dispose(); };
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        try
        {
            var assetDir = Path.Combine(AppContext.BaseDirectory, "ui-dist");
            if (!File.Exists(Path.Combine(assetDir, "index.html")))
                throw new FileNotFoundException("本地 UI 文件缺失。请通过 scripts/Build-NativeDesktop.ps1 重新打包完整目录。", assetDir);
            var userData = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WindowsAIWorkstation", "WebView2");
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder:userData);
            await FrontendView.EnsureCoreWebView2Async(environment);
            var core = FrontendView.CoreWebView2;
            core.Settings.AreDevToolsEnabled = false;
            core.Settings.AreDefaultContextMenusEnabled = false;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.AreHostObjectsAllowed = false;
            core.Settings.IsWebMessageEnabled = true;
            core.SetVirtualHostNameToFolderMapping(TrustedHost, assetDir, CoreWebView2HostResourceAccessKind.DenyCors);
            core.NavigationStarting += (_, args) =>
            {
                if (!IsTrustedOrigin(args.Uri)) args.Cancel = true;
            };
            core.NewWindowRequested += (_, args) => args.Handled = true;
            core.PermissionRequested += (_, args) => args.State = CoreWebView2PermissionState.Deny;
            core.WebMessageReceived += OnWebMessage;
            FrontendView.Visibility = Visibility.Visible;
            LoadingMessage.Visibility = Visibility.Collapsed;
            core.Navigate("https://aiws.local/index.html");
        }
        catch (Exception ex)
        {
            LoadingMessage.Text = "本地前端启动失败：" + ex.Message;
            MessageBox.Show("无法加载 AIWS 本地前端。\n" + ex.Message, "Windows AI Workstation", MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }

    internal static bool IsTrustedOrigin(string source)
    {
        if (!Uri.TryCreate(source, UriKind.Absolute, out var uri)) return false;
        return uri.Scheme == Uri.UriSchemeHttps && uri.Host.Equals(TrustedHost, StringComparison.OrdinalIgnoreCase)
            && uri.IsDefaultPort && uri.UserInfo.Length == 0;
    }

    private async void OnWebMessage(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        if (!IsTrustedOrigin(e.Source)) return;
        int id = 0;
        try
        {
            var json = e.TryGetWebMessageAsString();
            if (json.Length > 16_384) throw new InvalidDataException("请求过长。");
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object) throw new InvalidDataException("请求格式不正确。");
            if (!root.TryGetProperty("id", out var idField) || !idField.TryGetInt32(out id) || id < 1) return;
            var action = ReadField(root, "action");
            var payload = root.TryGetProperty("payload", out var node) && node.ValueKind == JsonValueKind.Object
                ? node : default;
            object? result = action switch
            {
                "state" => Snapshot(),
                "workspaces.pick" => PickDirectory(),
                "tasks.create" => CreateTask(payload),
                "steps.approve" => await StepActionAsync(payload, "approve"),
                "steps.complete" => await StepActionAsync(payload, "complete"),
                "steps.retry" => await StepActionAsync(payload, "retry"),
                "steps.startManual" => await StepActionAsync(payload, "startManual"),
                "steps.launch" => await StepActionAsync(payload, "launch"),
                "steps.preflight" => _controller.Preflight(ReadField(payload,"taskId"), ReadField(payload,"stepId")),
                "tasks.setPromptBudget" => SetPromptBudget(payload),
                "steps.add" => AddStep(payload),
                "steps.dependencies" => UpdateDependencies(payload),
                "worktrees.create" => await CreateWorktree(payload),
                "ledger.timeline" => ExecutionLedger.Timeline(_controller.GetTask(ReadField(payload,"taskId"))),
                "plans.list" => PlanWorkspaceService.List(PlanWorkspace(payload)),
                "plans.read" => await PlanWorkspaceService.ReadAsync(PlanWorkspace(payload), ReadField(payload,"path")),
                "atlas.flow" => CallFlowBuilder.Build(_controller.GetTask(ReadField(payload,"taskId"))),
                "atlas.context" => ContextInspector.Preview(
                    _controller.GetTask(ReadField(payload,"taskId")),
                    WorkflowEngine.Find(_controller.GetTask(ReadField(payload,"taskId")), ReadField(payload,"stepId"))),
                "atlas.structure" => await AtlasStructure(payload),
                "atlas.fileStages" => await AtlasRelatedStages(payload),
                "atlas.fileDiff" => await AtlasFileDiff(payload),
                "terminal.start" => OpenTerminal(payload),
                "terminal.write" => WriteTerminal(payload),
                "terminal.resize" => ResizeTerminal(payload),
                "terminal.close" => CloseTerminal(payload),
                "tools.gitInspect" => await GitWorkspaceService.InspectAsync(
                    ResolveWorkspace(payload), ReadField(payload, "view")),
                "tools.capabilities" => WindowsToolPolicy.Describe(),
                "project.overview" => await ProjectWorkspaceService.InspectAsync(ResolveWorkspace(payload)),
                "project.review" => await ProjectWorkspaceService.ReviewAsync(
                    ResolveWorkspace(payload), ReadField(payload, "path")),
                "project.stageChanges" => await StageChangeDetails(payload),
                "tools.openShell" => OpenUserShell(payload),
                _ => throw new InvalidOperationException("不允许的工作台操作。")
            };
            Reply(id, true, result, null);
        }
        catch (Exception ex)
        {
            if (id > 0) Reply(id, false, null, ex.Message);
        }
        await Task.CompletedTask;
    }

    private object Snapshot() => new
    {
        Version = "1.7.2-context-budget-preflight",
        Tasks = _controller.Tasks,
        Agents = new Dictionary<string, bool>
        {
            ["Claude Code"] = AgentTools.Locate("claude") is not null,
            ["Codex CLI"] = AgentTools.Locate("codex") is not null
        },
        Limitations = new [] {
            "进程启动只代表本地事件，不代表真实模型请求。",
            "模型用量必须来自经过验证的官方结构化日志。",
            "Windows CLI 继承当前用户权限；工作目录检查不是沙箱。"
        }
    };

    private object SetPromptBudget(JsonElement payload)
    {
        var taskId = ReadField(payload,"taskId");
        if (!payload.TryGetProperty("warningTokens",out var warn) || !warn.TryGetInt32(out var warningTokens)
            || !payload.TryGetProperty("stopTokens",out var stop) || !stop.TryGetInt32(out var stopTokens))
            throw new ArgumentException("预算必须是整数。");
        _controller.SetPromptBudget(taskId, warningTokens, stopTokens);
        return new { success = true };
    }

    private object? PickDirectory()
    {
        var dialog = new OpenFolderDialog { Title = "选择受信任的 AIWS 项目目录" };
        return dialog.ShowDialog(this) == true ? new { path = dialog.FolderName } : new { path = "" };
    }

    private object CreateTask(JsonElement payload) => _controller.CreateTask(
        ReadField(payload, "title"), ReadField(payload, "workspace"), ReadField(payload, "template"));

    private async Task<object> AtlasStructure(JsonElement payload)
    {
        var task = _controller.GetTask(ReadField(payload, "taskId"));
        var step = WorkflowEngine.Find(task, ReadField(payload, "stepId"));
        return await WorkspaceEvolutionService.InspectStageAsync(task, step);
    }

    private async Task<object> AtlasRelatedStages(JsonElement payload)
    {
        var task = _controller.GetTask(ReadField(payload, "taskId"));
        return await WorkspaceEvolutionService.FindRelatedStagesAsync(task, ReadField(payload, "path"));
    }

    private async Task<object> AtlasFileDiff(JsonElement payload)
    {
        var task = _controller.GetTask(ReadField(payload, "taskId"));
        var step = WorkflowEngine.Find(task, ReadField(payload, "stepId"));
        var path = ReadField(payload, "path");
        var workspace = task.WorkspaceFor(step);
        var current = await ProjectWorkspaceService.ReviewAsync(workspace, path);
        if (ProjectWorkspaceService.IsSensitiveName(path) || current.IsPreview ||
            !current.Diff.StartsWith("当前工作区无该文件的未提交 Git Diff", StringComparison.Ordinal))
            return current;
        var before = step.GitBefore?.Head;
        var after = (step.Status == StepStatus.Running
            ? (await ProjectWorkspaceService.CaptureAsync(workspace)).Head : step.GitAfter?.Head);
        if (string.IsNullOrWhiteSpace(before) || string.IsNullOrWhiteSpace(after) || before == after)
            return current;
        try
        {
            var historical = await GitWorkspaceService.InspectHistoricalFileAsync(workspace, before, after, path);
            if (historical.Output == "（无输出）") return current;
            return new ProjectWorkspaceService.FileReview(path, current.Status, historical.Output,
                historical.Truncated, false,
                "已提交 HEAD 前后对比。仅展示本地 Git 证据，不推断哪个 Agent 是作者。");
        }
        catch (Exception ex) when (ex is IOException or InvalidOperationException or TimeoutException or ArgumentException)
        {
            return current with {Note = current.Note + " 历史提交差异暂不可用。"};
        }
    }

    private async Task<object> StageChangeDetails(JsonElement payload)
    {
        var task = _controller.GetTask(ReadField(payload, "taskId"));
        var stage = WorkflowEngine.Find(task, ReadField(payload, "stepId"));
        // A running stage is compared to a fresh read-only snapshot, never treated as complete.
        var workspace = task.WorkspaceFor(stage);
        var current = stage.Status == StepStatus.Running
            ? await ProjectWorkspaceService.CaptureAsync(workspace) : stage.GitAfter;
        return await ProjectWorkspaceService.AnalyzeStageAsync(workspace, stage.Id, stage.Title,
            stage.GitBefore, current, stage.StartedAt, stage.CompletedAt);
    }

    private async Task<object> StepActionAsync(JsonElement payload, string action)
    {
        var taskId = ReadField(payload, "taskId");
        var stepId = ReadField(payload, "stepId");
        switch (action)
        {
            case "approve": _controller.Approve(taskId, stepId); break;
            case "complete": await _controller.CompleteWithGitAsync(taskId, stepId, ReadField(payload,"result")); break;
            case "retry": _controller.Retry(taskId, stepId); break;
            case "startManual": await _controller.StartManualWithGitAsync(taskId, stepId); break;
            case "launch":
                var task = _controller.GetTask(taskId);
                var step = WorkflowEngine.EnsureStartable(task, stepId);
                var check = _controller.Preflight(taskId, stepId);
                if (check.Blocked)
                    throw new InvalidOperationException(check.Note + $"（估算 {check.ApproxTokens} / 上限 {check.StopTokens} Token）");
                if (check.Duplicate && MessageBox.Show(this,
                        "本阶段交接内容与上一次完全相同。重复启动可能重复消耗 Token。\n\n" +
                        "请先确认原 CLI 没有在运行、这次重试确有必要。仍要再次启动吗？",
                        "重复提示词拦截",MessageBoxButton.YesNo,MessageBoxImage.Warning)!=MessageBoxResult.Yes)
                    throw new OperationCanceledException("已取消重复调用。");
                if (MessageBox.Show(this,
                        $"本地交接草稿预估 {check.ApproxTokens:N0} Token，提醒阈值 {check.WarningTokens:N0}，拦截阈值 {check.StopTokens:N0}。\n" +
                        (check.Warn ? "注意：已触发上下文规模提醒或重复提示词检查。\n" : "") +
                        $"\n将以当前 Windows 用户身份启动 {AgentLabel.Name(step.Agent)}，目录：\n{task.WorkspaceFor(step)}\n\n" +
                        "AIWS 只复制交接草稿，不自动发出模型请求；真实 CLI 内部 Token 用量未知。\n确认继续？",
                        "交接预算与 CLI 启动确认", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
                    throw new OperationCanceledException("已取消外部程序启动。");
                await _controller.LaunchWithGitAsync(taskId, stepId,
                    text => Clipboard.SetText(text),
                    (agent,dir) => AgentTools.LaunchInteractive(agent,dir), confirmDuplicate: check.Duplicate);
                break;
        }
        return new { success = true };
    }

    private object OpenUserShell(JsonElement payload)
    {
        var task = _controller.GetTask(ReadField(payload, "taskId"));
        if (MessageBox.Show(this,
                "将在以下受信任目录中打开独立的 Windows PowerShell：\n" + task.Workspace +
                "\n\n此终端由你本人操作，不是 Agent 自动执行工具；它继承当前 Windows 用户权限。确认打开？",
                "启动交互终端", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
            throw new OperationCanceledException("已取消打开终端。");
        WindowsToolPolicy.OpenUserPowerShell(task.Workspace);
        return new { success = true };
    }

    // Plan center may inspect the trusted task root or a previously created stage Worktree.
    // It cannot select arbitrary filesystem paths through WebView messages.
    private string PlanWorkspace(JsonElement payload)
    {
        var task = _controller.GetTask(ReadField(payload,"taskId"));
        if (payload.ValueKind == JsonValueKind.Object &&
            payload.TryGetProperty("stepId", out var field) && field.ValueKind == JsonValueKind.String &&
            !string.IsNullOrWhiteSpace(field.GetString()))
        {
            var stage=WorkflowEngine.Find(task,field.GetString()!);
            if (string.IsNullOrWhiteSpace(stage.WorktreePath))
                throw new InvalidOperationException("所选阶段没有独立 Worktree。");
            return WorkspaceGuard.RequireTrustedDirectory(stage.WorktreePath);
        }
        return WorkspaceGuard.RequireTrustedDirectory(task.Workspace);
    }

    private string ResolveWorkspace(JsonElement payload)
    {
        var task=_controller.GetTask(ReadField(payload,"taskId"));
        return payload.ValueKind==JsonValueKind.Object && payload.TryGetProperty("stepId",out var field) && field.ValueKind==JsonValueKind.String
            ? task.WorkspaceFor(WorkflowEngine.Find(task,field.GetString()??"")) : task.Workspace;
    }

    private static List<string> ReadDependencies(JsonElement payload)
    {
        if(!payload.TryGetProperty("dependsOn",out var value) || value.ValueKind!=JsonValueKind.Array)
            throw new ArgumentException("缺少依赖列表。");
        if(value.GetArrayLength()>100)throw new ArgumentException("依赖列表过长。");
        return value.EnumerateArray().Select(x=>x.ValueKind==JsonValueKind.String?x.GetString()??"":
            throw new ArgumentException("依赖标识必须是字符串。")).ToList();
    }
    private object AddStep(JsonElement payload)
    {
        var agent=ReadField(payload,"agent");
        if(!Enum.TryParse<AgentKind>(agent,false,out var parsed) || !Enum.IsDefined(parsed))
            throw new ArgumentException("未知 Agent 类型。");
        _controller.AddStep(ReadField(payload,"taskId"),ReadField(payload,"title"),parsed,ReadDependencies(payload));
        return new {success=true};
    }
    private object UpdateDependencies(JsonElement payload)
    {
        _controller.SetDependencies(ReadField(payload,"taskId"),ReadField(payload,"stepId"),ReadDependencies(payload));
        return new {success=true};
    }
    private async Task<object> CreateWorktree(JsonElement payload)
    {
        var task=_controller.GetTask(ReadField(payload,"taskId"));
        var stage=WorkflowEngine.Find(task,ReadField(payload,"stepId"));
        if(MessageBox.Show(this,
            "将创建独立 Git Worktree 和新的本地分支：\n"+task.Workspace+"\n阶段："+stage.Title+
            "\n\n不会修改或清理你的主仓库，但 Git 是同一 Windows 用户权限，不是 OS 沙箱。确认？",
            "创建隔离 Worktree",MessageBoxButton.YesNo,MessageBoxImage.Question)!=MessageBoxResult.Yes)
            throw new OperationCanceledException("已取消 Worktree 操作。");
        return new {path=await _controller.CreateStageWorktreeAsync(task.Id,stage.Id)};
    }
    private object OpenTerminal(JsonElement payload)
    {
        var workspace=ResolveWorkspace(payload);
        if(_terminal is not null)throw new InvalidOperationException("已有终端会话；请先关闭。");
        if(MessageBox.Show(this,"将在已验证目录中打开应用内 Windows PowerShell：\n"+workspace+
            "\n\n这是你直接控制的交互终端，可以执行系统命令。Agent 无法通过工具接口直接输入。确认？",
            "启动 ConPTY 终端",MessageBoxButton.YesNo,MessageBoxImage.Warning)!=MessageBoxResult.Yes)
            throw new OperationCanceledException("终端启动已取消。");
        var pty=ConPtyTerminal.StartPowerShell(workspace);
        pty.Output+=text=>Dispatcher.BeginInvoke(new Action(()=>SendEvent("terminal.output",new {sessionId=pty.Id,text})));
        pty.Exited+=code=>Dispatcher.BeginInvoke(new Action(()=>SendEvent("terminal.exited",new {sessionId=pty.Id,code})));
        _terminal=pty;
        return new {sessionId=pty.Id};
    }
    private object WriteTerminal(JsonElement payload)
    {
        var pty=RequireTerminal(payload);
        pty.Write(ReadField(payload,"text"));
        return new {success=true};
    }
    private object ResizeTerminal(JsonElement payload)
    {
        var pty=RequireTerminal(payload);
        if(!payload.TryGetProperty("columns",out var columns)||!columns.TryGetInt32(out var c)
            ||!payload.TryGetProperty("rows",out var rows)||!rows.TryGetInt32(out var r))
            throw new ArgumentException("终端尺寸无效。");
        pty.Resize(c,r);return new {success=true};
    }
    private object CloseTerminal(JsonElement payload)
    {
        var pty=RequireTerminal(payload);
        _terminal=null;
        pty.Dispose();
        return new {success=true};
    }
    private ConPtyTerminal RequireTerminal(JsonElement payload)
    {
        if(_terminal is null || _terminal.Id!=ReadField(payload,"sessionId"))
            throw new InvalidOperationException("终端会话不存在或已关闭。");
        return _terminal;
    }
    private void SendEvent(string kind,object data)
    {
        if(FrontendView.CoreWebView2 is not { } host)return;
        host.PostWebMessageAsJson(JsonSerializer.Serialize(new {eventName=kind,data},WireOptions));
    }

    private static string ReadField(JsonElement root, string key)
    {
        if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty(key, out var field) || field.ValueKind != JsonValueKind.String)
            throw new ArgumentException("缺少字段：" + key);
        return field.GetString() ?? "";
    }

    private void Reply(int id, bool ok, object? data, string? error)
    {
        if (FrontendView.CoreWebView2 is not { } web) return;
        var json = JsonSerializer.Serialize(new { id, ok, data, error }, WireOptions);
        web.PostWebMessageAsJson(json);
    }
}
