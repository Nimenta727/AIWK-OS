namespace AIWorkstation.Core;

/// <summary>
/// Prevents two Windows workbench windows from writing the same local tasks.json.
/// This is an OS-enforced file-share lease; a crashed process releases it automatically.
/// </summary>
public sealed class WorkspaceLease : IDisposable
{
    private readonly FileStream _stream;
    private WorkspaceLease(FileStream stream) => _stream = stream;

    public static WorkspaceLease Acquire(string dataDirectory)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(dataDirectory);
        var path = Path.GetFullPath(dataDirectory);
        Directory.CreateDirectory(path);
        try
        {
            var stream = new FileStream(Path.Combine(path, "aiws.instance.lock"), FileMode.OpenOrCreate,
                FileAccess.ReadWrite, FileShare.None);
            return new WorkspaceLease(stream);
        }
        catch (IOException ex)
        {
            throw new IOException("此工作区已被另一个 AI Workstation 实例占用。请先关闭之前的窗口，避免任务数据被互相覆盖。", ex);
        }
    }

    public void Dispose() => _stream.Dispose();
}
