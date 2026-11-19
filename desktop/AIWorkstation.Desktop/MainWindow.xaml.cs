using System.Collections.ObjectModel;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using AIWorkstation.Core;
using Microsoft.Win32;

namespace AIWorkstation.Desktop;

public partial class MainWindow : Window
{
    private readonly TaskRepository _repository;
    private readonly List<WorkTask> _tasks;
    private WorkTask? _activeTask;
    private WorkflowStep? _activeStep;
    private string _page = "home";
    private bool _loading;
    private bool _databaseHealthy = true;

    public MainWindow()
    {
        InitializeComponent();
        var appRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WindowsAIWorkstation");
        _repository = new TaskRepository(Path.Combine(appRoot, "tasks.json"));
        try { _tasks = _repository.Load(); }
        catch (Exception ex)
        {
            _tasks = [];
            _databaseHealthy = false;
            MessageBox.Show("本地任务库读取失败。为保护原数据，不会覆盖数据库。\n" + ex.Message,
                "读取数据异常", MessageBoxButton.OK, MessageBoxImage.Warning);
        }
        var root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "AIWorkstation", "projects");
        Directory.CreateDirectory(root);
        NewTaskWorkspace.Text = root;
        UpdateTaskList();
        RefreshTools();
        ShowPage("home");
    }

    private void Save()
    {
        if (!_databaseHealthy) throw new InvalidOperationException("任务库损坏，已进入只读保护状态。请先备份并修复 tasks.json。");
        _repository.Save(_tasks);
        UpdateTaskList();
    }

    private void UpdateTaskList()
    {
        _loading = true;
        var selectedId = _activeTask?.Id;
        TasksList.ItemsSource = _tasks.OrderByDescending(x => x.CreatedAt).Select(t => new TaskItem(t)).ToList();
        if (selectedId != null)
            TasksList.SelectedItem = TasksList.Items.Cast<TaskItem>().FirstOrDefault(x => x.Task.Id == selectedId);
        _loading = false;
    }

    private void ShowPage(string page)
    {
        _page = page;
        HomeView.Visibility = page == "home" ? Visibility.Visible : Visibility.Collapsed;
        FlowView.Visibility = page == "flow" ? Visibility.Visible : Visibility.Collapsed;
        ToolsView.Visibility = page == "tools" ? Visibility.Visible : Visibility.Collapsed;
        TraceView.Visibility = page == "trace" ? Visibility.Visible : Visibility.Collapsed;
        if (page == "trace") RefreshTrace();
        TopHeading.Text = page switch { "flow" => "可视化工作流", "tools" => "Agent 与集成", "trace" => "请求追踪", _ => "工作台概览" };
        NavHome.Background = page == "home" ? (Brush)FindResource("SoftAccent") : Brushes.Transparent;
        NavFlow.Background = page == "flow" ? (Brush)FindResource("SoftAccent") : Brushes.Transparent;
        NavTools.Background = page == "tools" ? (Brush)FindResource("SoftAccent") : Brushes.Transparent;
        NavTrace.Background = page == "trace" ? (Brush)FindResource("SoftAccent") : Brushes.Transparent;
    }

    private void HomeNav_Click(object sender, RoutedEventArgs e) => ShowPage("home");
    private void FlowNav_Click(object sender, RoutedEventArgs e)
    {
        if (_activeTask == null)
        {
            if (_tasks.Count == 0) { Info("请先在概览页创建一个任务。"); ShowPage("home"); return; }
            OpenTask(_tasks.OrderByDescending(x => x.CreatedAt).First());
        }
        ShowPage("flow");
    }
    private void TraceNav_Click(object sender, RoutedEventArgs e) => ShowPage("trace");
    private void ToolsNav_Click(object sender, RoutedEventArgs e) { RefreshTools(); ShowPage("tools"); }

    private void TasksList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_loading || TasksList.SelectedItem is not TaskItem item) return;
        OpenTask(item.Task);
        ShowPage("flow");
    }

    private void PickFolder_Click(object sender, RoutedEventArgs e)
    {
        var dlg = new OpenFolderDialog { Title = "选择已信任的 Agent 工作目录" };
        if (dlg.ShowDialog() == true) NewTaskWorkspace.Text = dlg.FolderName;
    }

    private void CreateTask_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        var name = NewTaskTitle.Text.Trim();
        if (name.Length == 0 || name.Length > 160) throw new ArgumentException("任务标题长度需要在 1–160 字符之间。");
        var workspace = WorkspaceGuard.RequireTrustedDirectory(NewTaskWorkspace.Text);
        var task = NewTaskTemplate.SelectedIndex == 1
            ? WorkflowTemplates.Research(name, workspace)
            : WorkflowTemplates.DualAgent(name, workspace);
        RequestTrace.Record(task, null, "task.created", "创建本地任务（不调用模型）");
        _tasks.Add(task);
        _activeTask = task;
        _activeStep = task.Steps.FirstOrDefault();
        Save();
        RefreshWorkflow();
        ShowPage("flow");
        Info("流程已创建，数据保存在本机用户目录。");
    });

    private void OpenTask(WorkTask task)
    {
        _activeTask = task;
        _activeStep = task.Steps.FirstOrDefault();
        RefreshWorkflow();
    }

    private void RefreshWorkflow()
    {
        if (_activeTask == null) return;
        ActiveTaskTitle.Text = _activeTask.Title;
        ActiveTaskPath.Text = _activeTask.Workspace;
        ProgressText.Text = $"{_activeTask.CompletedCount} / {_activeTask.Steps.Count} 已完成";
        StepsCanvas.ItemsSource = _activeTask.Steps.Select((s, i) => new FlowRow(s, i)).ToList();
        RenderStepEditor();
        if (_page == "trace") RefreshTrace();
    }

    private void SelectStep_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeTask == null || sender is not Button { Tag: string id }) return;
        _activeStep = WorkflowEngine.Find(_activeTask, id);
        RenderStepEditor();
        Info("已选中：" + _activeStep.Title);
    });

    private void RenderStepEditor()
    {
        if (_activeStep == null) return;
        StepTitleBox.Text = _activeStep.Title;
        StepInstructionsBox.Text = _activeStep.Instructions;
        StepAgentCombo.SelectedIndex = (int)_activeStep.Agent;
        NeedsApprovalCheck.IsChecked = _activeStep.RequiresApproval;
        StepResultBox.Text = _activeStep.Result;
    }

    private void AddStep_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeTask == null) throw new InvalidOperationException("请先创建工作流。");
        var step = new WorkflowStep { Title = "新建执行阶段", Instructions = "请在检查器中编辑此阶段目标。" };
        _activeTask.Steps.Add(step);
        _activeStep = step;
        Save();
        RefreshWorkflow();
    });

    private void SaveStep_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeStep == null) throw new InvalidOperationException("请先选择阶段。");
        if (_activeStep.Status is StepStatus.Running or StepStatus.Completed)
            throw new InvalidOperationException("运行中或完成的阶段不能修改计划。");
        var title = StepTitleBox.Text.Trim();
        if (title.Length == 0 || title.Length > 120) throw new ArgumentException("阶段标题长度无效。");
        _activeStep.Title = title;
        _activeStep.Instructions = StepInstructionsBox.Text.Trim();
        _activeStep.Agent = (AgentKind)Math.Max(0, StepAgentCombo.SelectedIndex);
        _activeStep.RequiresApproval = NeedsApprovalCheck.IsChecked == true;
        _activeStep.ApprovalGranted = false; // editing invalidates any previous approval
        RequestTrace.Record(_activeTask!, _activeStep, "step.edited", "节点修改；撤销此前审批");
        Save();
        RefreshWorkflow();
        Info("已保存阶段修改，并撤销旧审批。");
    });

    private void MoveUp_Click(object sender, RoutedEventArgs e) => MoveStep(-1);
    private void MoveDown_Click(object sender, RoutedEventArgs e) => MoveStep(1);
    private void MoveStep(int amount) => Guard(() =>
    {
        if (_activeTask == null || _activeStep == null) return;
        if (_activeTask.Steps.Any(s => s.Status != StepStatus.Pending))
            throw new InvalidOperationException("流程一旦执行，不能重新排序。");
        var index = _activeTask.Steps.IndexOf(_activeStep);
        var target = index + amount;
        if (target < 0 || target >= _activeTask.Steps.Count) return;
        _activeTask.Steps.RemoveAt(index);
        _activeTask.Steps.Insert(target, _activeStep);
        foreach (var step in _activeTask.Steps) step.ApprovalGranted = false;
        Save();
        RefreshWorkflow();
    });

    private void CopyPrompt_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeTask == null || _activeStep == null) throw new InvalidOperationException("请先选择阶段。");
        CopyDraft(_activeTask, _activeStep);
        Info("已复制精简交接指令；未自动发送模型。可在请求追踪页查看预估值。");
    });

    private void ApproveStep_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeTask == null || _activeStep == null) throw new InvalidOperationException("请先选择阶段。");
        var confirmation = MessageBox.Show($"允许开始阶段「{_activeStep.Title}」？\n执行器：{AgentLabel.Name(_activeStep.Agent)}\n工作区：{_activeTask.Workspace}\n\n本批准仅针对当前阶段，不授予管理员权限。",
            "确认当前审批", MessageBoxButton.YesNo, MessageBoxImage.Question);
        if (confirmation != MessageBoxResult.Yes) return;
        WorkflowEngine.Approve(_activeTask, _activeStep.Id);
        RequestTrace.Record(_activeTask, _activeStep, "stage.approved", "用户确认阶段执行权限");
        Save();
        Info("当前阶段已批准。实际命令仍需要手动启动。");
    });

    private void StartAgent_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeTask == null || _activeStep == null) throw new InvalidOperationException("请先选择阶段。");
        // Preflight before marking Running. No credentials are read or stored.
        WorkspaceGuard.RequireTrustedDirectory(_activeTask.Workspace);
        if (_activeStep.Agent != AgentKind.Manual && AgentTools.Locate(_activeStep.Agent == AgentKind.ClaudeCode ? "claude" : "codex") == null)
            throw new FileNotFoundException("当前 Agent 未安装。请在「Agent 与集成」中查看状态。");
        WorkflowEngine.Start(_activeTask, _activeStep.Id);
        RequestTrace.Record(_activeTask, _activeStep, "stage.started", "开始阶段；待官方 CLI 接受指令");
        Save();
        RefreshWorkflow();
        CopyDraft(_activeTask, _activeStep);
        if (_activeStep.Agent != AgentKind.Manual)
        {
            try { AgentTools.LaunchInteractive(_activeStep.Agent, _activeTask.Workspace); }
            catch (Exception ex)
            {
                WorkflowEngine.Fail(_activeTask, _activeStep.Id, "启动失败：" + ex.Message);
                Save();
                RefreshWorkflow();
                throw;
            }
            Info("官方 Agent 已启动；交接指令已复制，请粘贴到终端。完成后回填实际结果。");
        }
        else Info("人工阶段已开始；请完成后回填实际结果。");
    });

    private void CompleteStep_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeTask == null || _activeStep == null) throw new InvalidOperationException("请先选择阶段。");
        WorkflowEngine.Complete(_activeTask, _activeStep.Id, StepResultBox.Text);
        RequestTrace.Record(_activeTask, _activeStep, "stage.completed", "用户核实并回填阶段结果");
        Save();
        RefreshWorkflow();
        Info("阶段已完成，结果将作为下一阶段的待核实上下文。");
    });

    private void FailOrRetryStep_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeTask == null || _activeStep == null) throw new InvalidOperationException("请先选择阶段。");
        if (_activeStep.Status == StepStatus.Failed) WorkflowEngine.Retry(_activeTask, _activeStep.Id);
        else WorkflowEngine.Fail(_activeTask, _activeStep.Id, StepResultBox.Text);
        RequestTrace.Record(_activeTask, _activeStep, "stage.changed", "失败或重试状态已更新");
        Save();
        RefreshWorkflow();
        Info("阶段状态已更新。");
    });

    private void CopyDraft(WorkTask task, WorkflowStep step)
    {
        var draft = HandoffBuilder.Prepare(task, step);
        bool duplicate = draft.Fingerprint == step.LastPromptFingerprint;
        Clipboard.SetText(draft.Text);
        step.LastPromptFingerprint = draft.Fingerprint;
        RequestTrace.Record(task, step, duplicate ? "prompt.reused" : "prompt.prepared", duplicate
            ? "重复复制相同交接内容；未再次自动调用模型"
            : $"精简交接请求约 {draft.ApproxTokens} Token（仅字符估算，不是实际用量）");
        Save();
    }

    private void RefreshTrace()
    {
        if (_activeTask == null)
        {
            UsageSummary.Text = "暂无任务";
            UsageDetail.Text = "先创建并打开一个工作流。";
            ContextSummary.Text = "没有待处理的交接内容。";
            TraceEventsList.ItemsSource = null;
            PromptPreview.Text = "";
            return;
        }
        var known = _activeTask.Steps.Where(x => x.Usage.IsMeasured).ToArray();
        UsageSummary.Text = known.Length == 0 ? "尚未导入真实 Token 用量" : $"{known.Sum(x => x.Usage.Total):N0} 已报告 Token（{known.Length} 个阶段）";
        UsageDetail.Text = known.Length == 0
            ? "交互式 Claude/Codex 的内部调用不可直接观测。请选择官方导出的 JSONL/JSON 用量日志；实际值未知。"
            : $"已报告输入 {known.Sum(x => x.Usage.Input ?? 0):N0} · 输出 {known.Sum(x => x.Usage.Output ?? 0):N0} · 缓存输入 {known.Sum(x => x.Usage.CachedInput ?? 0):N0}。尚未导入 { _activeTask.Steps.Count - known.Length} 个阶段；各提供商缓存口径不同，数据并非费用账单。";
        ContextSummary.Text = _activeStep == null ? "选择某个阶段以分析交接提示。" : DescribeDraft(HandoffBuilder.Prepare(_activeTask, _activeStep));
        TraceEventsList.ItemsSource = _activeTask.RequestEvents.AsEnumerable().Reverse().Select(e => new TraceRow(e)).ToList();
    }

    private static string DescribeDraft(PreparedHandoff draft) =>
        $"发送前预估约 {draft.ApproxTokens:N0} Token（按字符粗估）；共 {draft.SentCharacters:N0} 字符，压缩/省略约 {draft.SavedCharacters:N0} 字符。CLI 后续系统提示、工具与隐藏推理 Token 不计入。";

    private void PreviewPrompt_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeTask == null || _activeStep == null) throw new InvalidOperationException("请先打开一个任务并选择阶段。");
        var draft = HandoffBuilder.Prepare(_activeTask, _activeStep);
        PromptPreview.Text = draft.Text;
        ContextSummary.Text = DescribeDraft(draft);
    });

    private void ImportTrace_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeTask == null || _activeStep == null) throw new InvalidOperationException("请先打开工作流并选择阶段。");
        if (_activeStep.Agent == AgentKind.Manual) throw new InvalidOperationException("人工阶段没有官方模型用量。");
        var chooser = new OpenFileDialog { Title = "手动选择本次阶段官方导出的用量日志", Filter = "JSON / JSONL|*.json;*.jsonl|全部文件|*.*", CheckFileExists = true };
        if (chooser.ShowDialog() != true) return;
        var file = new FileInfo(chooser.FileName);
        if (file.Length > 5_000_000) throw new InvalidDataException("日志超过 5 MB，请缩小范围。");
        var report = RequestTrace.Import(_activeTask, _activeStep, File.ReadAllText(file.FullName));
        if (!report.WasDuplicate) Save();
        RefreshTrace();
        Info(report.WasDuplicate ? "此日志已导入过，未重复统计。" : $"导入 {report.UsageEvents} 个用量事件。仅保存匿名指标。");
    });

    private sealed class TraceRow(RequestTraceEvent row)
    {
        public string Title => $"{row.At:MM-dd HH:mm:ss}   {row.Kind}";
        public string Detail => row.Summary;
    }

    private void RefreshTools_Click(object sender, RoutedEventArgs e) => RefreshTools();
    private void RefreshTools()
    {
        ClaudeHealth.Text = AgentTools.Locate("claude") is string claudeLocation ? "已检测 · " + claudeLocation : "未检测到 CLI · 需要官方安装与登录";
        CodexHealth.Text = AgentTools.Locate("codex") is string codexLocation ? "已检测 · " + codexLocation : "未检测到 CLI · 需要官方安装与登录";
    }
    private void LaunchT3_Click(object sender, RoutedEventArgs e) => Guard(() => AgentTools.LaunchCompanion("t3"));
    private void LaunchOpenClaw_Click(object sender, RoutedEventArgs e) => Guard(() => AgentTools.LaunchCompanion("openclaw"));

    private void Guard(Action action)
    {
        try { action(); }
        catch (Exception ex)
        {
            Info("操作失败 · " + ex.Message);
            MessageBox.Show(ex.Message, "Windows AI Workstation", MessageBoxButton.OK, MessageBoxImage.Warning);
        }
    }
    private void Info(string message) => StatusLine.Text = DateTime.Now.ToString("HH:mm") + " · " + message;

    private sealed class TaskItem
    {
        public TaskItem(WorkTask task) => Task = task;
        public WorkTask Task { get; }
        public string Title => Task.Title;
        public string Subtitle => $"{Task.CompletedCount}/{Task.Steps.Count} 阶段 · {Task.CreatedAt:MM-dd HH:mm}";
    }
    private sealed class FlowRow(WorkflowStep step, int index)
    {
        public string Id => step.Id;
        public string Number => (index + 1).ToString("00");
        public string Title => step.Title;
        public string Agent => AgentLabel.Name(step.Agent) + (step.RequiresApproval ? "  ·  审批后运行" : "  ·  无需审批");
        public string Status => AgentLabel.State(step.Status);
    }
}
