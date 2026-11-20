using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace AIWorkstation.Core;

// Request metadata only. Never persist the conversation, CLI output, credentials or commands.
public sealed class RequestTraceEvent
{
    public DateTimeOffset At { get; set; } = DateTimeOffset.Now;
    public string StageId { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Summary { get; set; } = "";
}

// Normalized event metadata from explicitly selected provider logs. Never retains text,
// shell commands, file paths, tool parameters, or provider identifiers.
public sealed class ProviderEventSummary
{
    public int Sequence { get; set; }
    public string Kind { get; set; } = "";
    public string ToolCategory { get; set; } = "";
    public long? Input { get; set; }
    public long? Output { get; set; }
    public long? CachedInput { get; set; }
}

public sealed class TokenUsage
{
    public long? Input { get; set; }
    public long? CachedInput { get; set; }
    public long? Output { get; set; }
    public string Source { get; set; } = "unknown";
    public bool IsMeasured => Input.HasValue && Output.HasValue;
    public long Total => (Input ?? 0) + (Output ?? 0);
}

public static class RequestTrace
{
    private const int MaxEvents = 400;
    public static void Record(WorkTask task, WorkflowStep? step, string kind, string summary)
    {
        if (kind.Length > 60 || summary.Length > 160) throw new ArgumentException("追踪事件长度超出限制。");
        task.RequestEvents.Add(new RequestTraceEvent { StageId = step?.Id ?? "", Kind = kind, Summary = summary });
        if (task.RequestEvents.Count > MaxEvents) task.RequestEvents.RemoveRange(0, task.RequestEvents.Count - MaxEvents);
    }

    public static string HashPrompt(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    // These are metadata from a user-selected export. Codex: turn.completed. Claude: result.
    // Never inspect provider credential files, session stores, or the chat payload.
    public static TraceImportReport Import(WorkTask task, WorkflowStep step, string content)
    {
        if (content.Length > 5_000_000) throw new InvalidDataException("日志超过 5 MB 上限，请先截取当前会话。");
        var fingerprint = HashPrompt(content);
        if (fingerprint == step.ImportFingerprint)
            return new TraceImportReport(0, step.Usage.Input, step.Usage.CachedInput, step.Usage.Output, true);

        long input = 0, cached = 0, output = 0;
        int usageEvents = 0;
        int toolEvents = 0;
        string? format = null;
        var providerEvents = new List<ProviderEventSummary>();
        var eventSequence = 0;
        void AddEvent(string kind, string category = "", long? usedInput = null, long? usedOutput = null, long? usedCache = null)
        {
            eventSequence++;
            // Keep a bounded, ordered synopsis. 60 events are enough for inspection, not replay.
            if (providerEvents.Count < 60)
                providerEvents.Add(new ProviderEventSummary { Sequence = eventSequence, Kind = kind, ToolCategory = category, Input = usedInput, Output = usedOutput, CachedInput = usedCache });
        }
        var rows = content.Split('\n');
        if (rows.Length > 20001) throw new InvalidDataException("日志事件过多，请导出单次任务日志。");
        foreach (var raw in rows)
        {
            if (string.IsNullOrWhiteSpace(raw)) continue;
            try
            {
                using var document = JsonDocument.Parse(raw);
                var root = document.RootElement;
                if (root.ValueKind != JsonValueKind.Object || !TryString(root, "type", out var type)) continue;
                if (type == "turn.completed" && root.TryGetProperty("usage", out var codexUsage) && codexUsage.ValueKind == JsonValueKind.Object)
                {
                    if (!TryUsage(codexUsage, out var i, out var c, out var o)) continue;
                    if (format is "claude") throw new InvalidDataException("不能混用两个提供商的日志。");
                    format = "codex";
                    checked { input += i; cached += c; output += o; }
                    usageEvents++;
                    AddEvent("codex.turn.completed", usedInput: i, usedOutput: o, usedCache: c);
                }
                else if (type == "turn.started" && step.Agent == AgentKind.Codex)
                {
                    AddEvent("codex.turn.started");
                }
                else if (type == "result" && root.TryGetProperty("usage", out var claudeUsage) && claudeUsage.ValueKind == JsonValueKind.Object)
                {
                    if (!TryUsage(claudeUsage, out var i, out var c, out var o)) continue;
                    if (format is "codex") throw new InvalidDataException("不能混用两个提供商的日志。");
                    format = "claude";
                    // Claude's result is the terminal aggregate: use the last valid result, never sum it with intermediate messages.
                    input = i; cached = c; output = o;
                    usageEvents++;
                    providerEvents.RemoveAll(e => e.Kind == "claude.result.aggregate");
                    AddEvent("claude.result.aggregate", usedInput: i, usedOutput: o, usedCache: c);
                }
                else if ((type == "item.started" || type == "item.completed") && root.TryGetProperty("item", out var item) && item.ValueKind == JsonValueKind.Object)
                {
                    if (TryString(item, "type", out var itemType) && itemType is "command_execution" or "mcp_tool_call" or "web_search")
                    {
                        toolEvents++;
                        AddEvent(type == "item.started" ? "tool.started" : "tool.completed", itemType);
                    }
                }
            }
            catch (JsonException) { /* Skip truncated/non-JSON diagnostic lines. */ }
        }
        if (usageEvents == 0) throw new InvalidDataException("未找到受支持的用量事件。Codex 需 turn.completed；Claude 需 result.usage。不会将缺失值显示为 0。");
        if (format == "codex" && step.Agent != AgentKind.Codex || format == "claude" && step.Agent != AgentKind.ClaudeCode)
            throw new InvalidDataException("日志提供商与选定阶段不匹配。");
        step.Usage = new TokenUsage { Input = input, CachedInput = cached, Output = output, Source = format == "codex" ? "Codex JSONL" : "Claude JSON" };
        step.ImportFingerprint = fingerprint;
        step.ImportedToolEvents = toolEvents;
        step.ImportedUsageEvents = usageEvents;
        step.ProviderEvents = providerEvents;
        Record(task, step, "trace.imported", $"导入 {usageEvents} 个用量事件、{toolEvents} 个工具事件；未存储对话内容");
        return new TraceImportReport(usageEvents, input, cached, output, false);
    }

    private static bool TryUsage(JsonElement node, out long input, out long cached, out long output)
    {
        input = cached = output = 0;
        if (!TryNonnegative(node, "input_tokens", out input) || !TryNonnegative(node, "output_tokens", out output)) return false;
        if (node.TryGetProperty("cached_input_tokens", out var direct) && direct.TryGetInt64(out var directValue) && directValue >= 0) cached = directValue;
        else if (node.TryGetProperty("input_tokens_details", out var details) && details.ValueKind == JsonValueKind.Object && TryNonnegative(details, "cached_tokens", out var nested)) cached = nested;
        else if (node.TryGetProperty("cache_read_input_tokens", out var claudeCache) && claudeCache.TryGetInt64(out var cv) && cv >= 0) cached = cv;
        // Claude's usage.input_tokens excludes cache read/write tokens. Normalize total input to
        // include those categories, unlike Codex where cached tokens are already included.
        if (node.TryGetProperty("cache_read_input_tokens", out var cacheRead) && cacheRead.TryGetInt64(out var read) && read >= 0)
        {
            long created = TryNonnegative(node, "cache_creation_input_tokens", out var create) ? create : 0;
            checked { input += read + created; }
        }
        return true;
    }
    private static bool TryNonnegative(JsonElement node, string field, out long n)
    {
        n = 0;
        return node.ValueKind == JsonValueKind.Object && node.TryGetProperty(field, out var value) && value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out n) && n >= 0;
    }
    private static bool TryString(JsonElement node, string field, out string value)
    {
        value = "";
        if (node.ValueKind != JsonValueKind.Object || !node.TryGetProperty(field, out var v) || v.ValueKind != JsonValueKind.String) return false;
        value = v.GetString() ?? "";
        return true;
    }
}

public sealed record TraceImportReport(int UsageEvents, long? Input, long? CachedInput, long? Output, bool WasDuplicate);
