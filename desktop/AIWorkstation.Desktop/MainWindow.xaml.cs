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
    private CallFlowSnapshot? _traceSnapshot;
    private string? _selectedTraceNodeId;

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
        StepInspectorPanel.Visibility = page == "trace" ? Visibility.Collapsed : Visibility.Visible;
        TraceInspectorPanel.Visibility = page == "trace" ? Visibility.Visible : Visibility.Collapsed;
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
        _selectedTraceNodeId = null;
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
        var plannedDraft = HandoffBuilder.Prepare(_activeTask, _activeStep);
        if (plannedDraft.Fingerprint == _activeStep.LastPromptFingerprint &&
            _activeTask.RequestEvents.Any(evt => evt.StageId == _activeStep.Id && evt.Kind == "cli.launched"))
        {
            var repeat = MessageBox.Show("当前交接指令与上次复制的内容相同。\n\n再次启动 Agent 可能产生重复的模型消耗。确定仍要继续吗？",
                "重复上下文提醒", MessageBoxButton.YesNo, MessageBoxImage.Warning);
            if (repeat != MessageBoxResult.Yes)
            {
                RequestTrace.Record(_activeTask, _activeStep, "launch.cancelled", "用户取消重复启动；未启动外部 CLI");
                Save();
                return;
            }
            RequestTrace.Record(_activeTask, _activeStep, "prompt.duplicate_warning", "用户确认使用相同交接指令（是否重复模型调用未知）");
        }
        if (plannedDraft.ApproxTokens > 3500)
        {
            var longContext = MessageBox.Show($"交接内容约 {plannedDraft.ApproxTokens:N0} 预估 Token（并非真实计费值），可能较长。\n\n是否继续启动？",
                "上下文预算提醒", MessageBoxButton.YesNo, MessageBoxImage.Information);
            if (longContext != MessageBoxResult.Yes) return;
        }
        WorkflowEngine.Start(_activeTask, _activeStep.Id);
        RequestTrace.Record(_activeTask, _activeStep, "stage.started", "本地阶段开始；尚未证明模型收到请求");
        Save();
        RefreshWorkflow();
        CopyDraft(_activeTask, _activeStep);
        if (_activeStep.Agent != AgentKind.Manual)
        {
            try
            {
                AgentTools.LaunchInteractive(_activeStep.Agent, _activeTask.Workspace);
                RequestTrace.Record(_activeTask, _activeStep, "cli.launched", "外部交互式 CLI 进程已启动；模型请求未观测");
                Save();
            }
            catch (Exception ex)
            {
                RequestTrace.Record(_activeTask, _activeStep, "cli.launch_failed", "外部 CLI 启动异常；未确认模型调用");
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
            _traceSnapshot = null;
            TraceChainSummary.Text = "尚无任务 · 先创建一个工作流";
            UsageSummary.Text = "实际用量未知";
            UsageDetail.Text = "没有工作流与官方用量日志。";
            TraceQualitySummary.Text = "无已确认的模型请求";
            ContextSummary.Text = "没有待处理的交接内容。";
            TraceFlowLanes.ItemsSource = null;
            TraceEventsList.ItemsSource = null;
            PromptPreview.Text = "";
            RenderTraceNodeDetails(null);
            return;
        }
        _traceSnapshot = CallFlowBuilder.Build(_activeTask);
        TraceChainSummary.Text = "用户任务  →  " + string.Join("  →  ", _activeTask.Steps.Select(s => AgentLabel.Name(s.Agent)));
        UsageSummary.Text = _traceSnapshot.ImportedStages == 0
            ? "实际 Token：未知"
            : $"{_traceSnapshot.ImportedTokens:N0} 已导入 Token";
        UsageDetail.Text = _traceSnapshot.ImportedStages == 0
            ? "未从官方 CLI 的结构化日志导入用量；这不代表实际使用了 0 Token。"
            : $"输入 {_traceSnapshot.ImportedInput:N0} · 输出 {_traceSnapshot.ImportedOutput:N0} · 缓存输入 {_traceSnapshot.ImportedCachedInput:N0}（属于输入的一部分，不重复相加）。";
        TraceQualitySummary.Text = $"已导入 {_traceSnapshot.ImportedStages}/{_activeTask.Steps.Count(s => s.Agent != AgentKind.Manual)} 个模型阶段 · " +
            $"{_traceSnapshot.UnknownUsageStages} 阶段用量未知 · {_traceSnapshot.DuplicatePreparations} 次重复上下文提醒";
        ContextSummary.Text = _activeStep == null ? "请选择一个阶段以分析交接上下文。" : DescribeDraft(HandoffBuilder.Prepare(_activeTask, _activeStep));
        TraceEventsList.ItemsSource = _activeTask.RequestEvents.AsEnumerable().Reverse().Select(e => new TraceRow(e)).ToList();
        var nodes = _traceSnapshot.Nodes.ToArray();
        if (_selectedTraceNodeId == null || !nodes.Any(n => n.Id == _selectedTraceNodeId))
            _selectedTraceNodeId = nodes.FirstOrDefault()?.Id;
        TraceFlowLanes.ItemsSource = _traceSnapshot.Lanes.Select(lane => new TraceLaneRow(lane, _selectedTraceNodeId)).ToList();
        RenderTraceNodeDetails(nodes.FirstOrDefault(n => n.Id == _selectedTraceNodeId));
    }

    private void TraceNode_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (sender is not Button { Tag: string id } || _activeTask == null || _traceSnapshot == null) return;
        var node = _traceSnapshot.Nodes.FirstOrDefault(n => n.Id == id);
        if (node == null) return;
        _selectedTraceNodeId = node.Id;
        _activeStep = WorkflowEngine.Find(_activeTask, node.StepId);
        RenderStepEditor();
        RefreshTrace();
        Info("查看节点证据：" + node.Title + "（不触发 AI 调用）");
    });

    private void TraceToStep_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeTask == null || _traceSnapshot == null || _selectedTraceNodeId == null) return;
        var node = _traceSnapshot.Nodes.FirstOrDefault(n => n.Id == _selectedTraceNodeId);
        if (node == null) return;
        _activeStep = WorkflowEngine.Find(_activeTask, node.StepId);
        RenderStepEditor();
        ShowPage("flow");
    });

    private void RenderTraceNodeDetails(CallFlowNode? node)
    {
        TraceNodeName.Text = node?.Title ?? "请选择节点";
        TraceNodeState.Text = node == null ? "暂无证据" : TraceNodeRow.StateLabelFor(node.State);
        TraceNodeDescription.Text = node?.Detail ?? "从可视化调用链中选择一个节点，查看本地事件或官方导入数据。";
        TraceNodeEvidence.Text = node?.Evidence ?? "未记录";
        TraceNodeTokens.Text = node?.UsageText ?? "未知（非零值）";
        TraceNodeTiming.Text = node == null ? "未知" :
            (node.RecordedAt.HasValue ? $"记录时间 {node.RecordedAt:yyyy-MM-dd HH:mm:ss}\n" : "") + node.DurationText;
    }

    private void RefreshTrace_Click(object sender, RoutedEventArgs e) => RefreshTrace();
    private void ExportTrace_Click(object sender, RoutedEventArgs e) => Guard(() =>
    {
        if (_activeTask == null) throw new InvalidOperationException("请先选择一个任务。");
        var snapshot = CallFlowBuilder.Build(_activeTask);
        var dialog = new SaveFileDialog
        {
            Title = "导出脱敏调用链元数据（不含任务内容、工作区或 CLI 日志）",
            Filter = "JSON 文件|*.json",
            DefaultExt = ".json",
            FileName = "aiws-callflow-redacted.json"
        };
        if (dialog.ShowDialog() != true) return;
        File.WriteAllText(dialog.FileName, snapshot.ToRedactedJson());
        Info("已导出脱敏调用链；不包含任务名称、用户提示词或文件路径。");
    });

    private sealed class TraceLaneRow
    {
        public TraceLaneRow(CallFlowLane lane, string? selected)
        {
            Header = lane.Header;
            Agent = lane.Agent;
            State = lane.State;
            Nodes = lane.Nodes.Select((node, i) => new TraceNodeRow(node, i < lane.Nodes.Count - 1, node.Id == selected)).ToArray();
            ImportedEvents = lane.ImportedEvents.Select(x => new ImportedEventRow(x)).ToArray();
            ImportedVisibility = ImportedEvents.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
        }
        public string Header { get; }
        public string Agent { get; }
        public string State { get; }
        public IReadOnlyList<TraceNodeRow> Nodes { get; }
        public IReadOnlyList<ImportedEventRow> ImportedEvents { get; }
        public Visibility ImportedVisibility { get; }
    }

    private sealed class ImportedEventRow(ProviderEventSummary item)
    {
        public string Title => item.Kind switch
        {
            "codex.turn.started" => $"{item.Sequence:D2} · Codex 回合开始",
            "codex.turn.completed" => $"{item.Sequence:D2} · Codex 回合用量",
            "claude.result.aggregate" => $"{item.Sequence:D2} · Claude 最终汇总",
            "tool.started" => $"{item.Sequence:D2} · 工具启动",
            "tool.completed" => $"{item.Sequence:D2} · 工具结束",
            _ => $"{item.Sequence:D2} · 导入事件"
        };
        public string Metric => item.Input.HasValue
            ? $"输入 {item.Input:N0} · 输出 {item.Output:N0} · 缓存 {item.CachedInput:N0}"
            : item.ToolCategory.Length > 0 ? item.ToolCategory switch
            {
                "command_execution" => "命令工具 · 不保存参数",
                "mcp_tool_call" => "MCP 工具 · 不保存参数",
                "web_search" => "网页搜索 · 不保存查询",
                _ => "工具元数据"
            } : "无用量字段（非零值）";
    }

    private sealed class TraceNodeRow
    {
        private readonly CallFlowNode _node;
        public TraceNodeRow(CallFlowNode node, bool hasNext, bool selected)
        {
            _node = node;
            ArrowVisibility = hasNext ? Visibility.Visible : Visibility.Collapsed;
            Surface = selected ? new SolidColorBrush(Color.FromRgb(250, 236, 226)) : node.State switch
            {
                FlowState.Imported => new SolidColorBrush(Color.FromRgb(239, 247, 241)),
                FlowState.Recorded => new SolidColorBrush(Color.FromRgb(252, 246, 239)),
                FlowState.Attention => new SolidColorBrush(Color.FromRgb(255, 244, 233)),
                _ => new SolidColorBrush(Color.FromRgb(250, 249, 247))
            };
            Stroke = selected ? new SolidColorBrush(Color.FromRgb(177, 106, 75)) :
                node.State == FlowState.Imported ? new SolidColorBrush(Color.FromRgb(180, 211, 189)) :
                new SolidColorBrush(Color.FromRgb(233, 226, 218));
            LabelBrush = node.State switch
            {
                FlowState.Imported => new SolidColorBrush(Color.FromRgb(52, 118, 91)),
                FlowState.Recorded => new SolidColorBrush(Color.FromRgb(166, 98, 68)),
                FlowState.Attention => new SolidColorBrush(Color.FromRgb(169, 104, 41)),
                _ => new SolidColorBrush(Color.FromRgb(119, 115, 110))
            };
        }
        public string Id => _node.Id;
        public string Title => _node.Title;
        public string Subtitle => _node.Subtitle;
        public string StateLabel => StateLabelFor(_node.State);
        public string PhaseLabel => _node.Phase switch
        {
            FlowPhase.Routing => "01 / ROUTE",
            FlowPhase.Context => "02 / CONTEXT",
            FlowPhase.Launcher => "03 / LAUNCH",
            FlowPhase.Provider => "04 / PROVIDER",
            _ => "05 / HANDOFF"
        };
        public Brush Surface { get; }
        public Brush Stroke { get; }
        public Brush LabelBrush { get; }
        public Visibility ArrowVisibility { get; }
        public static string StateLabelFor(FlowState state) => state switch
        {
            FlowState.Planned => "计划 / 待执行",
            FlowState.Recorded => "已记录本地事件",
            FlowState.Imported => "已导入的统计",
            FlowState.Attention => "需要关注",
            _ => "真实调用未知"
        };
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
