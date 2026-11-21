# 2026-11-21 19:05 — P1/P2：CSRF 根因修复、去桌面外壳、系统控制面板

## 改动
- **Invalid CSRF**：令牌在服务每次启动时重新生成，前端只在页面加载取一次，服务重启后所有按钮都会报错；各处还各自拼请求头。现在所有写请求统一走 `api.ts`：自动带令牌、缺失时先取、遇到 403 `Invalid CSRF` 刷新后重试一次，调用方自带的旧令牌会被覆盖。`OsWorkbench` 订阅令牌变化。
- **去桌面外壳**：`aiws-session` 不再启动 `xfce4-panel`，只留一个无边框的 Openbox；窗口一律无标题栏并最大化；浏览器 `--start-fullscreen --app`；Alt+Tab 切换、Alt+F4 关闭、Super+Home 回到工作台（`aiws-focus-workbench`）。软件包去掉 `xfce4`、`xfce4-appfinder`、`xfce4-notifyd`、`xfce4-panel`，加入 `x11-xserver-utils`。`desktopInstalled` 改看 openbox。
- **系统控制**（原来由桌面面板承担）：新增 `aiws_system.py` 与工作台「系统」页面：显示分辨率（只接受显示器宣告的模式）、输入法（fcitx5-remote）、Wi-Fi（密码走 stdin，不进 argv）、电源（必须带确认令牌）。命令全部固定 argv，请求值只做校验后的参数。
- **启动**：新增 binary hook 把 isolinux/grub 菜单改为自动继续（30/3 秒），内核参数加 `video=1920x1080`；启动自检里 `json.load` 空输入的追踪信息被静默（探测本来就会重试）。

## 文件
`workbench/src/os/{api.ts,OsWorkbench.tsx,SystemControls.tsx,shell.css}`、`workbench/tests/api.test.mjs`、`os/runtime/{aiws_system.py,aiws_workbench.py,MODULES}`、`os/debian/build.sh`、`os/debian/config/{hooks/normal/9010-aiws-boot-menu.hook.binary,package-lists,includes.chroot/...}`、`os/debian/profiles/smoke.list.chroot`、`os/verify/{test_system_controls.py,test_config.py}`

## 验证
- 前端 `tsc`、`npm test`（含 4 项新的 CSRF 重试测试）、`vite build` 通过；Python 全量 428 项通过。
- 测试中发现并修复：输入法名/显示器名允许以 `-` 开头（选项注入面），改为必须以字母数字开头。
- **未验证**：真实镜像里的 Openbox 无边框行为、全屏启动、菜单超时 hook 是否匹配 live-build 生成的文件、`video=1920x1080` 在 QEMU 的实际效果、`xrandr/nmcli/fcitx5-remote` 在客体里的真实输出格式、输入法能否打出中文（需要启动后实测）。启动自检脚本改动未在真实镜像里重跑。

## 已知问题
- 去掉面板后没有通知气泡；审批等提示只在工作台内显示。
- 用其他程序（终端等）全屏打开后，需要 Alt+Tab / Super+Home 回来；「应用」页还没有提示这一点。

## 下一步
P3 观察台可视化重做（保留清晰的，删装饰）→ P4 文件两层视图 → P5 插件功能内建与工具检索 → P6 双盘、宿主模型通道。
