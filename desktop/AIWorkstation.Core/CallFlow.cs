using System.Text.Json;

namespace AIWorkstation.Core;

// This graph is a projection of local workflow facts and user-imported usage.
// In particular, an interactive CLI launch is NOT evidence of a provider model request.
public enum FlowState { Planned, Recorded, Imported, Unknown, Attention }
public enum FlowPhase { Routing, Context, Launcher, Provider, Handoff }

public sealed record CallFlowNode(
    string Id,
    string StepId,
    FlowPhase Phase,
    string Title,
    string Subtitle,
    FlowState State,
    string Detail,
    string Evidence,
    string UsageText,
    string DurationText,
    DateTimeOffset? RecordedAt = null);

public sealed record CallFlowLane(
    string StepId, string Header, string Agent, string State, IReadOnlyList<CallFlowNode> Nodes,
    IReadOnlyList<ProviderEventSummary> ImportedEvents);

public sealed class CallFlowSnapshot
{
    public IReadOnlyList<CallFlowLane> Lanes { get; init; } = [];
    public int ImportedStages { get; init; }
    public int UnknownUsageStages { get; init; }
    public long ImportedInput { get; init; }
    public long ImportedOutput { get; init; }
    public long ImportedCachedInput { get; init; }
    public int DuplicatePreparations { get; init; }
    public int? ImportedToolEvents { get; init; }
    public int TotalStages => Lanes.Count;
    public long ImportedTokens => ImportedInput + ImportedOutput;
    public IEnumerable<CallFlowNode> Nodes => Lanes.SelectMany(x => x.Nodes);

    // Redacted export intentionally omits task name, workspace, instructions, results,
    // original CLI logs, prompt hashes, and event summaries.
    public string ToRedactedJson() => JsonSerializer.Serialize(new
    {
        schema = "aiws.callflow.v1",
        accuracy = "Local events and explicitly imported provider usage; no internal CLI traffic interception",
        totals = new { ImportedStages, UnknownUsageStages, ImportedInput, ImportedOutput, ImportedCachedInput, DuplicatePreparations, ImportedToolEvents },
        lanes = Lanes.Select((lane, index) => new
        {
            stage = index + 1,
            lane.Agent,
            state = lane.State,
            events = lane.ImportedEvents.Select(evt => new
            {
                evt.Sequence,
                evt.Kind,
                evt.ToolCategory,
                evt.Input,
                evt.Output,
                evt.CachedInput
            }),
            nodes = lane.Nodes.Select(node => new
            {
                phase = node.Phase.ToString(),
                status = node.State.ToString(),
                at = node.RecordedAt,
                usage = node.UsageText,
                duration = node.DurationText
            })
        })
    }, new JsonSerializerOptions { WriteIndented = true });
}

public static class CallFlowBuilder
{
    public static CallFlowSnapshot Build(WorkTask task)
    {
        ArgumentNullException.ThrowIfNull(task);
        var lanes = new List<CallFlowLane>();
        var known = task.Steps.Where(x => x.Usage.IsMeasured).ToArray();
        var duplicateEvents = task.RequestEvents.Count(x => x.Kind == "prompt.reused");
        foreach (var (step, index) in task.Steps.Select((step, index) => (step, index)))
        {
            var stepEvents = task.RequestEvents.Where(e => e.StageId == step.Id).ToArray();
            RequestTraceEvent? Last(string kind) => stepEvents.LastOrDefault(x => x.Kind == kind);
            RequestTraceEvent? LastOf(params string[] kinds) => stepEvents.LastOrDefault(x => kinds.Contains(x.Kind));
            var draft = HandoffBuilder.Prepare(task, step);
            var nodes = new List<CallFlowNode>();
            var stageState = AgentLabel.State(step.Status);

            nodes.Add(new CallFlowNode(
                $"{step.Id}:route", step.Id, FlowPhase.Routing, "分配执行器", AgentLabel.Name(step.Agent),
                FlowState.Planned,
                $"阶段 {index + 1}/{task.Steps.Count}：由工作流模板或用户选择 {AgentLabel.Name(step.Agent)}。这是本地计划，不表示已经调用模型。",
                "本地工作流配置 · 无额外模型请求", "不消耗模型 Token", "未发生模型请求"));

            var preparedEvent = LastOf("prompt.prepared", "prompt.reused");
            var duplicated = preparedEvent?.Kind == "prompt.reused";
            nodes.Add(new CallFlowNode(
                $"{step.Id}:context", step.Id, FlowPhase.Context, "构建上下文",
                duplicated ? "检测到相同交接" : $"约 {draft.ApproxTokens:N0} Token · 预估",
                duplicated ? FlowState.Attention : preparedEvent != null ? FlowState.Recorded : FlowState.Planned,
                $"本地生成交接内容：{draft.SentCharacters:N0} 字符，较未裁剪的上下文减少约 {draft.SavedCharacters:N0} 字符。仅保留最近两个已完成阶段结果，当前阶段指令不裁剪。" +
                (duplicated ? " 检测到重复复制，但不能推断模型被重复调用。" : ""),
                preparedEvent == null ? "预览计算 · 尚未复制或发送" : $"本地事件 {preparedEvent.Kind} · {preparedEvent.At:yyyy-MM-dd HH:mm:ss}",
                $"≈ {draft.ApproxTokens:N0} 预估 Token（非计费值）", "本地处理 · 未统计耗时", preparedEvent?.At));

            var launch = LastOf("cli.launched", "cli.launch_failed");
            var hasStart = Last("stage.started") != null;
            var isManual = step.Agent == AgentKind.Manual;
            FlowState launcherState;
            string launcherCaption;
            string launcherEvidence;
            if (isManual)
            {
                launcherState = hasStart ? FlowState.Recorded : FlowState.Planned;
                launcherCaption = "人工处理（不调用 CLI）";
                launcherEvidence = hasStart ? "本地人工阶段开始记录" : "尚未开始人工阶段";
            }
            else if (launch?.Kind == "cli.launched")
            {
                launcherState = FlowState.Recorded;
                launcherCaption = "已启动外部 CLI";
                launcherEvidence = $"本地进程启动事件 · {launch.At:yyyy-MM-dd HH:mm:ss}";
            }
            else if (launch?.Kind == "cli.launch_failed")
            {
                launcherState = FlowState.Attention;
                launcherCaption = "启动失败";
                launcherEvidence = "本地失败事件；没有证明模型请求被发送";
            }
            else
            {
                launcherState = hasStart ? FlowState.Unknown : FlowState.Planned;
                launcherCaption = hasStart ? "标记已开始 · CLI 未核验" : "等待用户启动";
                launcherEvidence = hasStart ? "仅有 stage.started；旧版本无法确认进程启动" : "没有 CLI 启动事件";
            }
            nodes.Add(new CallFlowNode(
                $"{step.Id}:cli", step.Id, FlowPhase.Launcher, isManual ? "人工阶段" : "启动官方 CLI", launcherCaption,
                launcherState,
                isManual ? "这个阶段由用户处理。" : "启动官方交互式程序是本机动作。当前工作台没有拦截 CLI 内部的请求、响应或隐藏上下文。",
                launcherEvidence, "模型 Token 未在此处计量", "进程启动 ≠ 模型调用耗时", launch?.At));

            var usageKnown = step.Usage.IsMeasured;
            nodes.Add(new CallFlowNode(
                $"{step.Id}:provider", step.Id, FlowPhase.Provider, "模型 / 工具事件",
                usageKnown ? $"已导入 {step.Usage.Total:N0} Token" : "内部调用未观测",
                usageKnown ? FlowState.Imported : FlowState.Unknown,
                usageKnown
                    ? $"用户导入的结构化统计（来源未验真）：输入 {step.Usage.Input:N0}、输出 {step.Usage.Output:N0}、缓存输入 {step.Usage.CachedInput?.ToString("N0") ?? "未知"}。" +
                      (step.ImportedToolEvents.HasValue ? $" 识别到 {step.ImportedToolEvents:N0} 条工具事件（不是去重后的工具调用次数）。" : " 工具调用次数未知。")
                    : "尚无这个阶段的官方结构化用量。无法从外部交互式 CLI 推断模型轮数、输入/输出 Token 或工具调用；显示未知而不是零。",
                usageKnown ? $"用户导入的结构化格式：{step.Usage.Source} · {step.ImportedUsageEvents?.ToString() ?? "未知"} 条用量事件（未验证日志真实性）" : "未导入可验证的官方用量事件",
                usageKnown ? $"实测合计 {step.Usage.Total:N0} Token" : "未知（非 0）", "模型耗时未知"));

            var endedEvent = LastOf("stage.completed", "stage.changed");
            var finished = step.Status == StepStatus.Completed;
            var duration = step.StartedAt.HasValue && step.CompletedAt.HasValue && step.CompletedAt >= step.StartedAt
                ? $"阶段历时 {FormatDuration(step.CompletedAt.Value - step.StartedAt.Value)}（非模型耗时）"
                : "阶段历时未知";
            nodes.Add(new CallFlowNode(
                $"{step.Id}:handoff", step.Id, FlowPhase.Handoff, "结果与交接",
                finished ? "用户已核实完成" : step.Status == StepStatus.Failed ? "已失败" : step.Status == StepStatus.Interrupted ? "执行中断，需核验" : "等待结果回填",
                finished ? FlowState.Recorded : step.Status is StepStatus.Failed or StepStatus.Interrupted ? FlowState.Attention : FlowState.Planned,
                finished ? "本地记录了用户确认的阶段结果，下一阶段会按精简上下文规则使用它。此事件不是官方模型完成信号。" :
                "本阶段未确认完成。若工作台重启导致中断，应先核实外部 CLI 的实际结果，再决定是否重新执行。",
                endedEvent == null ? "暂无阶段结束事件" : $"本地事件 {endedEvent.Kind} · {endedEvent.At:yyyy-MM-dd HH:mm:ss}",
                "不额外调用模型", duration, endedEvent?.At));
            lanes.Add(new CallFlowLane(step.Id, $"{index + 1:D2}  ·  {step.Title}", AgentLabel.Name(step.Agent), stageState, nodes,
                (step.ProviderEvents ?? []).Take(60).ToArray()));
        }
        return new CallFlowSnapshot
        {
            Lanes = lanes,
            ImportedStages = known.Length,
            UnknownUsageStages = task.Steps.Count(x => x.Agent != AgentKind.Manual && !x.Usage.IsMeasured),
            ImportedInput = known.Sum(x => x.Usage.Input ?? 0),
            ImportedOutput = known.Sum(x => x.Usage.Output ?? 0),
            ImportedCachedInput = known.Sum(x => x.Usage.CachedInput ?? 0),
            DuplicatePreparations = duplicateEvents,
            ImportedToolEvents = task.Steps.Where(x => x.ImportedToolEvents.HasValue).Select(x => x.ImportedToolEvents!.Value).Any()
                ? task.Steps.Sum(x => x.ImportedToolEvents ?? 0)
                : task.Steps.Any(x => x.ImportedToolEvents.HasValue) ? 0 : null
        };
    }

    private static string FormatDuration(TimeSpan duration)
        => duration.TotalHours >= 1 ? $"{duration.TotalHours:F1} 小时" : duration.TotalMinutes >= 1 ? $"{duration.TotalMinutes:F1} 分钟" : $"{duration.TotalSeconds:F0} 秒";
}
