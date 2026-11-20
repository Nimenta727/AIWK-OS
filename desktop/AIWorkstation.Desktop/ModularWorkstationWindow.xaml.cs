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
    private static readonly JsonSerializerOptions WireOptions = new(JsonSerializerDefaults.Web)
    {
        Converters = { new JsonStringEnumConverter() }
    };

    public ModularWorkstationWindow()
    {
        InitializeComponent();
        var appRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WindowsAIWorkstation");
        _controller = new WorkstationController(appRoot);
        Closed += (_, _) => _controller.Dispose();
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
                "steps.approve" => StepAction(payload, "approve"),
                "steps.complete" => StepAction(payload, "complete"),
                "steps.retry" => StepAction(payload, "retry"),
                "steps.startManual" => StepAction(payload, "startManual"),
                "steps.launch" => StepAction(payload, "launch"),
                "tools.gitInspect" => await GitWorkspaceService.InspectAsync(
                    _controller.GetTask(ReadField(payload, "taskId")).Workspace, ReadField(payload, "view")),
                "tools.capabilities" => WindowsToolPolicy.Describe(),
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
        Version = "1.1.0-developer-tools",
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

    private object? PickDirectory()
    {
        var dialog = new OpenFolderDialog { Title = "选择受信任的 AIWS 项目目录" };
        return dialog.ShowDialog(this) == true ? new { path = dialog.FolderName } : new { path = "" };
    }

    private object CreateTask(JsonElement payload) => _controller.CreateTask(
        ReadField(payload, "title"), ReadField(payload, "workspace"), ReadField(payload, "template"));

    private object StepAction(JsonElement payload, string action)
    {
        var taskId = ReadField(payload, "taskId");
        var stepId = ReadField(payload, "stepId");
        switch (action)
        {
            case "approve": _controller.Approve(taskId, stepId); break;
            case "complete": _controller.Complete(taskId, stepId, ReadField(payload,"result")); break;
            case "retry": _controller.Retry(taskId, stepId); break;
            case "startManual": _controller.StartManual(taskId, stepId); break;
            case "launch":
                var task = _controller.GetTask(taskId);
                var step = WorkflowEngine.EnsureStartable(task, stepId);
                if (MessageBox.Show(this,
                        $"将以当前 Windows 用户身份启动 {AgentLabel.Name(step.Agent)}，目录：\n{task.Workspace}\n\nAIWS 会将交接提示词复制到剪贴板，但不会自动发送给模型。\n确认继续？",
                        "确认执行官方 Agent", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
                    throw new OperationCanceledException("已取消外部程序启动。");
                _controller.Launch(taskId, stepId,
                    text => Clipboard.SetText(text),
                    (agent,dir) => AgentTools.LaunchInteractive(agent,dir));
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
