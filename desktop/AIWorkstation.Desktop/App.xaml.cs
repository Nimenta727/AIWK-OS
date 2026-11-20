using System.Windows;
namespace AIWorkstation.Desktop;
public partial class App : Application
{
    private void App_Startup(object sender, StartupEventArgs e)
    {
        try
        {
            MainWindow = new ModularWorkstationWindow();
            MainWindow.Show();
        }
        catch (Exception ex)
        {
            MessageBox.Show("无法安全启动 AI Workstation；未覆盖任务数据库。\n" + ex.Message,
                "启动失败", MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(-1);
        }
    }
}
