using System.Text.Json;
using System.Text.Json.Serialization;

namespace AIWorkstation.Core;

public sealed class TaskRepository
{
    private readonly string _file;
    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter() }
    };

    public TaskRepository(string file) => _file = Path.GetFullPath(file);

    public List<WorkTask> Load()
    {
        if (!File.Exists(_file)) return [];
        return JsonSerializer.Deserialize<List<WorkTask>>(File.ReadAllText(_file), Options)
            ?? throw new InvalidDataException("任务数据库不可读取，请先备份原文件。");
    }

    public void Save(IReadOnlyCollection<WorkTask> tasks)
    {
        var folder = Path.GetDirectoryName(_file)!;
        Directory.CreateDirectory(folder);
        var temp = _file + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllText(temp, JsonSerializer.Serialize(tasks, Options));
            if (File.Exists(_file)) File.Copy(_file, _file + ".bak", true);
            File.Move(temp, _file, true);
        }
        finally
        {
            if (File.Exists(temp)) File.Delete(temp);
        }
    }
}
