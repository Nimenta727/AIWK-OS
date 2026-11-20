using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace AIWorkstation.Core;

/// <summary>
/// Local task persistence. Writes are staged on the same volume, flushed, and atomically
/// renamed; the previous complete version is retained in .bak. Recovery is never silent.
/// </summary>
public sealed class TaskRepository
{
    private readonly string _file;
    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        MaxDepth = 48,
        Converters = { new JsonStringEnumConverter() }
    };

    public TaskRepository(string file) => _file = Path.GetFullPath(file);
    public string BackupPath => _file + ".bak";
    public bool HasBackup => File.Exists(BackupPath);

    public List<WorkTask> Load()
    {
        if (!File.Exists(_file))
        {
            if (HasBackup) throw new InvalidDataException("主任务库缺失，但仍存在备份。请确认后显式恢复，避免覆盖历史任务。");
            return [];
        }
        return ReadValidated(_file);
    }

    private static List<WorkTask> ReadValidated(string path)
    {
        try
        {
            var tasks = JsonSerializer.Deserialize<List<WorkTask>>(File.ReadAllText(path, Encoding.UTF8), Options)
                ?? throw new InvalidDataException("任务库根节点不是任务列表。");
            if (tasks.Count > 10_000) throw new InvalidDataException("任务数量超出安全上限。");
            var taskIds = new HashSet<string>(StringComparer.Ordinal);
            foreach (var task in tasks)
            {
                if (task is null || string.IsNullOrWhiteSpace(task.Id) || !taskIds.Add(task.Id) || task.Steps is null || task.RequestEvents is null)
                    throw new InvalidDataException("任务库含有缺失或重复的任务标识，已拒绝加载。");
                if (task.Steps.Count > 200 || task.RequestEvents.Count > 10_000)
                    throw new InvalidDataException("任务阶段或事件数量超过安全上限。");
                if (task.ExecutionRecords is null || task.ExecutionRecords.Count > ExecutionLedger.Limit)
                    throw new InvalidDataException("执行事件记录无效或超过容量限制。");
                var eventIds = new HashSet<string>(StringComparer.Ordinal);
                foreach (var ev in task.ExecutionRecords)
                    if (ev is null || string.IsNullOrWhiteSpace(ev.Id) || !eventIds.Add(ev.Id))
                        throw new InvalidDataException("执行事件 ID 缺失或重复。");
                var stageIds = new HashSet<string>(StringComparer.Ordinal);
                foreach (var step in task.Steps)
                {
                    if (step is null || string.IsNullOrWhiteSpace(step.Id) || !stageIds.Add(step.Id) || step.Usage is null)
                        throw new InvalidDataException("任务库含有缺失或重复的阶段标识，已拒绝加载。");
                    if ((step.GitBefore?.Files?.Count ?? 0) > 800 || (step.GitAfter?.Files?.Count ?? 0) > 800)
                        throw new InvalidDataException("Git 检查点条目超过安全上限。");
                    if ((step.GitBefore?.Tree?.Count ?? 0) > 2500 || (step.GitAfter?.Tree?.Count ?? 0) > 2500)
                        throw new InvalidDataException("结构检查点条目超过 2500 的采集上限。");
                    if ((step.GitBefore?.Tree?.Any(x => x is null || !ProjectWorkspaceService.IsSafeRelativePath(x.Path)) ?? false)
                        || (step.GitAfter?.Tree?.Any(x => x is null || !ProjectWorkspaceService.IsSafeRelativePath(x.Path)) ?? false))
                        throw new InvalidDataException("结构检查点包含无效相对路径。");
                    if (step.DependsOn is null || step.RunId is null || step.WorktreePath is null)
                        throw new InvalidDataException("阶段新字段无效。");
                    if (!Enum.IsDefined(step.Agent) || !Enum.IsDefined(step.Status))
                        throw new InvalidDataException("任务库含有未知的 Agent 或阶段状态。");
                }
                WorkflowGraph.Validate(task);
            }
            return tasks;
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException("任务 JSON 已损坏，原文件未覆盖。可检查 .bak 备份后手动恢复。", ex);
        }
    }

    public void Save(IReadOnlyCollection<WorkTask> tasks)
    {
        ArgumentNullException.ThrowIfNull(tasks);
        if (!File.Exists(_file) && HasBackup)
            throw new InvalidDataException("主任务库缺失且存在备份。请先执行显式恢复操作。");
        var folder = Path.GetDirectoryName(_file)!;
        Directory.CreateDirectory(folder);
        var temp = _file + "." + Guid.NewGuid().ToString("N") + ".tmp";
        var backupTemp = BackupPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            var json = JsonSerializer.Serialize(tasks, Options);
            WriteDurably(temp, json);
            _ = ReadValidated(temp); // Refuse to replace a good database with invalid serialized state.
            if (File.Exists(_file))
            {
                _ = ReadValidated(_file); // Corrupt primary is never silently overwritten.
                File.Copy(_file, backupTemp);
                _ = ReadValidated(backupTemp);
                File.Move(backupTemp, BackupPath, true);
            }
            File.Move(temp, _file, true); // Same-directory replacement, not in-place truncation.
        }
        finally
        {
            if (File.Exists(temp)) File.Delete(temp);
            if (File.Exists(backupTemp)) File.Delete(backupTemp);
        }
    }

    /// <summary>
    /// Explicit user-approved recovery only. Preserves the bad primary as a unique forensic file.
    /// Never overwrites the backup as part of the restore operation.
    /// </summary>
    public string RestoreBackup()
    {
        if (!HasBackup) throw new FileNotFoundException("没有可恢复的 .bak 文件。", BackupPath);
        _ = ReadValidated(BackupPath);
        var temp = _file + "." + Guid.NewGuid().ToString("N") + ".restore.tmp";
        var preserved = _file + ".corrupt-" + DateTimeOffset.UtcNow.ToString("yyyyMMddTHHmmssfff") + "-" + Guid.NewGuid().ToString("N") + ".json";
        try
        {
            File.Copy(BackupPath, temp);
            _ = ReadValidated(temp);
            if (File.Exists(_file)) File.Copy(_file, preserved);
            File.Move(temp, _file, true);
            return File.Exists(preserved) ? preserved : "";
        }
        finally
        {
            if (File.Exists(temp)) File.Delete(temp);
        }
    }

    private static void WriteDurably(string file, string contents)
    {
        using var stream = new FileStream(file, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        using var writer = new StreamWriter(stream, new UTF8Encoding(false), bufferSize: 4096, leaveOpen: true);
        writer.Write(contents);
        writer.Flush();
        stream.Flush(flushToDisk: true);
    }
}
