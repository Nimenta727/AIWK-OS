using System.Windows;

namespace AIWorkstation.Desktop;

public partial class App : Application
{
    private void App_Startup(object sender, StartupEventArgs e)
    {
        try
        {
            MainWindow = new MainWindow();
            MainWindow.Show();
        }
        catch (Exception ex)
        {
            MessageBox.Show("工作台无法安全启动，未修改任务数据库。\n" + ex.Message,
                "Windows AI Workstation 启动失败", MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(-1);
        }
    }
}
