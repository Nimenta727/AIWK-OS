using System.IO;
using System.Net.Http;
using System.Windows;
using System.Windows.Media;
using AIWorkstation.Core;
using Microsoft.Web.WebView2.Core;

namespace AIWorkstation.Desktop;

/// <summary>
/// Hosts an original, locally running upstream UI rather than recreating its components.
/// No model auth token or AIWS execution API is forwarded to the embedded site.
/// </summary>
public partial class ProfessionalShellWindow : Window
{
    private const string T3Key = "t3";
    private const string ClawKey = "openclaw";
    private string _selected = T3Key;
    private readonly Dictionary<string, string> _savedEndpoints = new();
    private readonly HttpClient _healthClient = new(new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false })
    {
        Timeout = TimeSpan.FromSeconds(2)
    };
    private readonly string _configPath;
    private Uri? _trustedEndpoint;
    private bool _webViewInitialized;
    private MainWindow? _nativeWindow;

    public ProfessionalShellWindow()
    {
        InitializeComponent();
        _configPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "WindowsAIWorkstation", "frontend-endpoints.txt");
        ReadEndpoints();
        SetTab(T3Key);
        Closed += (_, _) => _healthClient.Dispose();
    }

    private void ReadEndpoints()
    {
        try
        {
            if (!File.Exists(_configPath)) return;
            foreach (var line in File.ReadAllLines(_configPath))
            {
                var index = line.IndexOf('=');
                if (index < 1) continue;
                var key = line[..index];
                var value = line[(index + 1)..];
                if (key is T3Key or ClawKey && LocalFrontendEndpoint.TryParse(value, out _))
                    _savedEndpoints[key] = value;
            }
        }
        catch (IOException) { /* An invalid or locked settings file is nonfatal. */ }
        catch (UnauthorizedAccessException) { /* Same behavior: no secrets to recover. */ }
    }

    private void SaveEndpoints()
    {
        // Store URLs only: never store query parameters, credentials or provider tokens.
        var safe = _savedEndpoints.Where(kv => LocalFrontendEndpoint.TryParse(kv.Value, out _))
            .Select(kv => kv.Key + "=" + kv.Value);
        var dir = Path.GetDirectoryName(_configPath)!;
        Directory.CreateDirectory(dir);
        File.WriteAllLines(_configPath, safe);
    }

    private void SetTab(string key)
    {
        _selected = key;
        _trustedEndpoint = null;
        if (_webViewInitialized && UpstreamWebView.CoreWebView2 is { } browser)
            browser.Navigate("about:blank");
        UpstreamWebView.Visibility = Visibility.Collapsed;
        WelcomePanel.Visibility = Visibility.Visible;
        QuickStartT3Button.Visibility = key == T3Key ? Visibility.Visible : Visibility.Collapsed;
        EndpointInput.Text = _savedEndpoints.GetValueOrDefault(key)
            ?? (key == T3Key ? LocalFrontendEndpoint.T3Default : LocalFrontendEndpoint.OpenClawDefault);
        T3Tab.Background = key == T3Key ? new SolidColorBrush(Color.FromRgb(245, 235, 229)) : Brushes.Transparent;
        OpenClawTab.Background = key == ClawKey ? new SolidColorBrush(Color.FromRgb(245, 235, 229)) : Brushes.Transparent;
        T3Tab.FontWeight = key == T3Key ? FontWeights.SemiBold : FontWeights.Normal;
        OpenClawTab.FontWeight = key == ClawKey ? FontWeights.SemiBold : FontWeights.Normal;
        StatusText.Text = key == T3Key
            ? "T3 Code · 等待连接本机原版前端" : "OpenClaw · 等待连接本机原版控制台";
    }

    private void T3Tab_Click(object sender, RoutedEventArgs e) => SetTab(T3Key);
    private void OpenClawTab_Click(object sender, RoutedEventArgs e) => SetTab(ClawKey);

    private async void Connect_Click(object sender, RoutedEventArgs e)
    {
        if (!TryGetSelectedEndpoint(out var url) || url is null) return;
        await ConnectToUriAsync(url, _selected);
    }

    private bool TryGetSelectedEndpoint(out Uri? url)
    {
        if (LocalFrontendEndpoint.TryParse(EndpointInput.Text, out url) && url is not null)
            return true;
        StatusText.Text = "地址无效：只允许 http(s)://localhost / 127.0.0.1 / [::1]，不允许账号、Token 或查询参数。";
        return false;
    }

    private async Task<bool> IsServiceResponsiveAsync(Uri url)
    {
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Get, url);
            using var response = await _healthClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
            return true; // Unauthorized is still a response from a running local service.
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException)
        {
            return false;
        }
    }

    private async void QuickStartT3_Click(object sender, RoutedEventArgs e)
    {
        if (_selected != T3Key || !TryGetSelectedEndpoint(out var url) || url is null) return;
        // The official CLI is started only on an explicitly validated local HTTP endpoint.
        // HTTPS may be used to connect manually but is not something this launcher configures.
        if (url.Scheme != Uri.UriSchemeHttp || url.AbsolutePath != "/" ||
            url.Host is not ("127.0.0.1" or "localhost"))
        {
            StatusText.Text = "一键启动只支持本机 HTTP 根地址；其他地址请使用手动连接。";
            return;
        }
        QuickStartT3Button.IsEnabled = false;
        try
        {
            if (!await IsServiceResponsiveAsync(url))
            {
                T3ServiceLauncher.StartLoopback(url.Port);
                StatusText.Text = "已启动官方 T3 CLI，正在等待本机服务…";
                bool ready = false;
                for (int attempt = 0; attempt < 15; attempt++)
                {
                    await Task.Delay(800);
                    if (_selected != T3Key) return;
                    if (await IsServiceResponsiveAsync(url)) { ready = true; break; }
                }
                if (!ready)
                {
                    StatusText.Text = "已请求启动官方 T3，但本机端口尚未响应。检查 T3 终端输出或手动填写实际地址。";
                    return;
                }
            }
            if (_selected == T3Key) await ConnectToUriAsync(url, T3Key);
        }
        catch (Exception ex) when (ex is IOException or System.ComponentModel.Win32Exception or ArgumentException)
        {
            StatusText.Text = "未能启动官方 T3 服务：" + ex.Message;
        }
        finally
        {
            QuickStartT3Button.IsEnabled = true;
        }
    }

    private async Task ConnectToUriAsync(Uri url, string tabAtStart)
    {
        StatusText.Text = "检查本机服务连接…";
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Get, url);
            using var response = await _healthClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
            // A tab change during the async probe invalidates this connect request.
            if (tabAtStart != _selected) return;
            // 401/403 are still evidence of a running service; no redirect is followed.
            StatusText.Text = $"本机服务响应 {(int)response.StatusCode}，正在加载原版前端…";
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException)
        {
            StatusText.Text = "本机服务未就绪。请先启动官方 T3 Code / OpenClaw 服务器，再核对端口。";
            return;
        }
        if (tabAtStart != _selected) return;
        try
        {
            if (!_webViewInitialized)
            {
                var profileDir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "WindowsAIWorkstation", "WebView2-ProfessionalUI");
                Directory.CreateDirectory(profileDir);
                var env = await CoreWebView2Environment.CreateAsync(userDataFolder: profileDir);
                await UpstreamWebView.EnsureCoreWebView2Async(env);
                var browser = UpstreamWebView.CoreWebView2;
                browser.Settings.IsWebMessageEnabled = false;
                browser.Settings.AreDevToolsEnabled = false;
                browser.Settings.AreDefaultContextMenusEnabled = true;
                browser.NavigationStarting += (_, args) =>
                {
                    if (args.Uri == "about:blank") return;
                    if (!Uri.TryCreate(args.Uri, UriKind.Absolute, out var target) ||
                        _trustedEndpoint is null || !LocalFrontendEndpoint.IsWithinOrigin(target, _trustedEndpoint))
                    {
                        args.Cancel = true;
                        StatusText.Text = "已拦截外部跳转。请使用系统浏览器完成需要的官方登录步骤。";
                    }
                };
                browser.NewWindowRequested += (_, args) =>
                {
                    args.Handled = true;
                    StatusText.Text = "网页尝试打开新窗口；请在官方系统浏览器完成该步骤。";
                };
                _webViewInitialized = true;
            }
            if (tabAtStart != _selected) return;
            _trustedEndpoint = url;
            _savedEndpoints[_selected] = url.GetLeftPart(UriPartial.Path);
            try { SaveEndpoints(); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                StatusText.Text = "原版前端连接成功，但本地地址设置无法保存。";
            }
            UpstreamWebView.Visibility = Visibility.Visible;
            WelcomePanel.Visibility = Visibility.Collapsed;
            UpstreamWebView.CoreWebView2.Navigate(url.AbsoluteUri);
            StatusText.Text = "已连接原版 " + (_selected == T3Key ? "T3 Code" : "OpenClaw") + " 本机界面；执行状态由其官方服务管理。";
        }
        catch (Exception ex)
        {
            UpstreamWebView.Visibility = Visibility.Collapsed;
            WelcomePanel.Visibility = Visibility.Visible;
            StatusText.Text = "WebView2 初始化失败：" + ex.Message;
        }
    }

    private void OpenNative_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            if (_nativeWindow is null || !_nativeWindow.IsLoaded)
            {
                _nativeWindow = new MainWindow { Owner = this };
                _nativeWindow.Closed += (_, _) => _nativeWindow = null;
                _nativeWindow.Show();
            }
            else
            {
                _nativeWindow.Activate();
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show("AIWS 原生任务窗口无法安全打开：\n" + ex.Message,
                "打开工作台失败", MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
}
