using System.Security.Cryptography;
using System.Text;

namespace AIWorkstation.Core;

/// <summary>Bounded, evidence-labelled local task events. No secrets, prompts or terminal output.</summary>
public sealed class ExecutionRecord
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string StageId { get; set; } = "";
    public string RunId { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Source { get; set; } = "aiws.local";
    public string Evidence { get; set; } = "observed";
    public DateTimeOffset At { get; set; } = DateTimeOffset.UtcNow;
    public string Metadata { get; set; } = "";
}

public static class ExecutionLedger
{
    public const int Limit = 2_000;
    public static ExecutionRecord Append(WorkTask task, WorkflowStep? step, string kind,
        string evidence = "observed", string metadata = "")
    {
        if (kind.Length is < 1 or > 70 || metadata.Length > 200 || evidence is not ("observed" or "imported" or "inferred" or "unknown"))
            throw new ArgumentException("执行证据参数不合法。只记录有限的非敏感元数据。");
        task.ExecutionRecords ??= [];
        var record = new ExecutionRecord {StageId=step?.Id ?? "",RunId=step?.RunId ?? "",Kind=kind,Evidence=evidence,Metadata=metadata};
        task.ExecutionRecords.Add(record);
        if(task.ExecutionRecords.Count>Limit) task.ExecutionRecords.RemoveRange(0,task.ExecutionRecords.Count-Limit);
        return record;
    }
    public static IReadOnlyList<ExecutionRecord> Timeline(WorkTask task) => (task.ExecutionRecords ?? [])
        .OrderBy(x => x.At).ThenBy(x=>x.Id, StringComparer.Ordinal).ToArray();
}
