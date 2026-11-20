using Microsoft.Win32.SafeHandles;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

namespace AIWorkstation.Core;

/// <summary>
/// Explicitly user-owned Windows PowerShell terminal backed by native ConPTY.
/// No model/agent may invoke this class through a tool endpoint; output and input are never persisted.
/// Requires Windows 10 1809+ and the Windows console pseudoconsole API.
/// </summary>
public sealed class ConPtyTerminal : IDisposable
{
    private const int ExtStartupInfo = 0x00080000;
    private const int PseudoConsoleAttribute = 0x00020016;
    private const uint StillActive = 259;
    private readonly FileStream _writer;
    private readonly FileStream _reader;
    private readonly IntPtr _pseudoConsole;
    private readonly IntPtr _process;
    private readonly object _writeLock = new();
    private volatile bool _closed;
    private readonly Task _readTask;
    public string Id { get; } = Guid.NewGuid().ToString("N");
    public event Action<string>? Output;
    public event Action<uint>? Exited;

    [StructLayout(LayoutKind.Sequential)] private struct Coord { public short X, Y; public Coord(short x,short y){X=x;Y=y;} }
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] private struct StartupInfo
    {
        public int cb; public string? lpReserved; public string? lpDesktop; public string? lpTitle;
        public int dwX,dwY,dwXSize,dwYSize,dwXCountChars,dwYCountChars,dwFillAttribute,dwFlags;
        public short wShowWindow,cbReserved2;
        public IntPtr lpReserved2,hStdInput,hStdOutput,hStdError;
    }
    [StructLayout(LayoutKind.Sequential)] private struct StartupInfoEx { public StartupInfo StartupInfo; public IntPtr lpAttributeList; }
    [StructLayout(LayoutKind.Sequential)] private struct ProcessInformation { public IntPtr hProcess,hThread; public uint dwProcessId,dwThreadId; }
    [DllImport("kernel32.dll",SetLastError=true)] private static extern bool CreatePipe(out SafeFileHandle read,out SafeFileHandle write,IntPtr attributes,int size);
    [DllImport("kernel32.dll",SetLastError=true)] private static extern int CreatePseudoConsole(Coord size,SafeFileHandle input,SafeFileHandle output,uint flags,out IntPtr hpc);
    [DllImport("kernel32.dll")] private static extern void ClosePseudoConsole(IntPtr hpc);
    [DllImport("kernel32.dll")] private static extern int ResizePseudoConsole(IntPtr hpc,Coord size);
    [DllImport("kernel32.dll",SetLastError=true)] private static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,int flags,ref IntPtr size);
    [DllImport("kernel32.dll",SetLastError=true)] private static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,IntPtr attribute,IntPtr value,IntPtr size,IntPtr previous,IntPtr returned);
    [DllImport("kernel32.dll")] private static extern void DeleteProcThreadAttributeList(IntPtr list);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true,EntryPoint="CreateProcessW")]
    [return:MarshalAs(UnmanagedType.Bool)] private static extern bool CreateProcess(string? app,StringBuilder command,IntPtr processAttributes,IntPtr threadAttributes,
        [MarshalAs(UnmanagedType.Bool)] bool inherit,uint flags,IntPtr environment,string currentDirectory,ref StartupInfoEx startup,out ProcessInformation result);
    [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] private static extern bool TerminateProcess(IntPtr h,uint code);
    [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] private static extern bool GetExitCodeProcess(IntPtr h,out uint code);
    [DllImport("kernel32.dll",SetLastError=true)] [return:MarshalAs(UnmanagedType.Bool)] private static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll",SetLastError=true)] private static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);

    public static ConPtyTerminal StartPowerShell(string workspace,short columns=100,short rows=30)
    {
        if(!OperatingSystem.IsWindows())throw new PlatformNotSupportedException("ConPTY 仅适用于 Windows。");
        var directory=WorkspaceGuard.RequireTrustedDirectory(workspace);
        var windows=Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        var executable=Path.Combine(windows,"System32","WindowsPowerShell","v1.0","powershell.exe");
        if(!File.Exists(executable))throw new FileNotFoundException("找不到系统 PowerShell。",executable);
        return new ConPtyTerminal(executable,directory,columns,rows);
    }
    private ConPtyTerminal(string executable,string directory,short cols,short rows)
    {
        if(!CreatePipe(out var inputRead,out var inputWrite,IntPtr.Zero,0))throw new Win32Exception(Marshal.GetLastWin32Error());
        if(!CreatePipe(out var outputRead,out var outputWrite,IntPtr.Zero,0))
        {inputRead.Dispose();inputWrite.Dispose();throw new Win32Exception(Marshal.GetLastWin32Error());}
        IntPtr pseudo=IntPtr.Zero,attributes=IntPtr.Zero,ptyPtr=IntPtr.Zero;
        IntPtr child=IntPtr.Zero;
        var attributesReady=false;
        try
        {
            var hr=CreatePseudoConsole(new Coord(cols,rows),inputRead,outputWrite,0,out pseudo);
            if(hr!=0)Marshal.ThrowExceptionForHR(hr);
            inputRead.Dispose();outputWrite.Dispose();
            IntPtr size=IntPtr.Zero;
            InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref size);
            attributes=Marshal.AllocHGlobal(size);
            if(!InitializeProcThreadAttributeList(attributes,1,0,ref size))throw new Win32Exception(Marshal.GetLastWin32Error());
            attributesReady=true;
            ptyPtr=Marshal.AllocHGlobal(IntPtr.Size);
            Marshal.WriteIntPtr(ptyPtr,pseudo);
            if(!UpdateProcThreadAttribute(attributes,0,(IntPtr)PseudoConsoleAttribute,ptyPtr,(IntPtr)IntPtr.Size,IntPtr.Zero,IntPtr.Zero))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            var startup=new StartupInfoEx{ StartupInfo=new StartupInfo{cb=Marshal.SizeOf<StartupInfoEx>()},lpAttributeList=attributes};
            var cmdline=new StringBuilder("\""+executable+"\" -NoLogo -NoProfile");
            if(!CreateProcess(executable,cmdline,IntPtr.Zero,IntPtr.Zero,false,ExtStartupInfo,IntPtr.Zero,directory,ref startup,out var pi))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            child=pi.hProcess;
            CloseHandle(pi.hThread);
            _process=child;
            _pseudoConsole=pseudo;
            _writer=new FileStream(inputWrite,FileAccess.Write,4096,false);
            _reader=new FileStream(outputRead,FileAccess.Read,4096,false);
            _readTask=Task.Run(ReadLoop);
            _=Task.Run(()=> { WaitForSingleObject(_process,0xffffffff); if(!_closed && GetExitCodeProcess(_process,out var exit))Exited?.Invoke(exit); });
        }
        catch
        {
            inputRead.Dispose();inputWrite.Dispose();outputRead.Dispose();outputWrite.Dispose();
            if(child!=IntPtr.Zero) {TerminateProcess(child,1);CloseHandle(child);}
            if(pseudo!=IntPtr.Zero)ClosePseudoConsole(pseudo);
            throw;
        }
        finally
        {
            if(attributes!=IntPtr.Zero) {if(attributesReady)DeleteProcThreadAttributeList(attributes);Marshal.FreeHGlobal(attributes);}
            if(ptyPtr!=IntPtr.Zero)Marshal.FreeHGlobal(ptyPtr);
        }
    }
    private void ReadLoop()
    {
        var bytes=new byte[4096];
        var chars=new char[8192];
        var decoder=Encoding.UTF8.GetDecoder();
        try
        {
            while(!_closed)
            {
                var n=_reader.Read(bytes,0,bytes.Length);
                if(n<=0)break;
                var count=decoder.GetChars(bytes,0,n,chars,0,false);
                if(count>0)Output?.Invoke(new string(chars,0,count));
            }
        }
        catch(Exception e) when(e is IOException or ObjectDisposedException) { }
    }
    public void Write(string input)
    {
        if(_closed)throw new InvalidOperationException("终端已关闭。");
        if(input.Length is < 1 or > 4096)throw new ArgumentException("终端输入长度无效。");
        var bytes=Encoding.UTF8.GetBytes(input);
        lock(_writeLock) { if(_closed)throw new InvalidOperationException("终端已关闭。");_writer.Write(bytes,0,bytes.Length);_writer.Flush(); }
    }
    public void Resize(int columns,int rows)
    {
        if(_closed)throw new InvalidOperationException("终端已关闭。");
        if(columns is < 20 or > 300 || rows is < 5 or > 120)throw new ArgumentException("终端尺寸无效。");
        var hr=ResizePseudoConsole(_pseudoConsole,new Coord((short)columns,(short)rows));
        if(hr!=0)Marshal.ThrowExceptionForHR(hr);
    }
    public void Dispose()
    {
        if(_closed)return;
        _closed=true;
        // A user-approved terminal is never left running invisibly after this window closes.
        try { if(GetExitCodeProcess(_process,out var status)&&status==StillActive)TerminateProcess(_process,1); }catch{ }
        _writer.Dispose(); _reader.Dispose();
        ClosePseudoConsole(_pseudoConsole);
        CloseHandle(_process);
    }
}
