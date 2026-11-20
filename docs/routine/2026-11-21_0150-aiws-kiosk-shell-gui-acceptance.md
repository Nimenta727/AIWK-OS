# 2026-11-21 01:50 — AIWS shell becomes default guest GUI with actual click acceptance

## 变更
- Debian Live 客户机 LightDM 默认进入 AIWS Xsession；Openbox 仅为窗口管理，Chromium Kiosk 全屏打开 AIWS 工作台，无 XFCE 面板、传统文件管理器或应用启动器。
- 新增 aiws-session、xsessions/aiws.desktop、kiosk 参数及 packages openbox/xdotool/chromedriver/python3-selenium。保留系统内部 Linux 文件系统与维护入口，但 GUI 操作以 AIWS 为主。
- 修改客户机启动 smoke：除 LightDM/Openbox/HTTP/MCP，必须经 guest 用户 xdotool 确认可见 Chromium 窗口，Selenium 真正点击文件管理、读取客体文件、创建并执行持久 DAG，再确认本地模型缺省禁用。任何一步失败不会输出 PASS。
- 新增客体内 aiws_gui_smoke.py，构建脚本为 shell 赋可执行权限。
- 修改文件：os/debian/config/includes.chroot/etc/lightdm/lightdm.conf.d/50-aiws-autologin.conf，usr/share/xsessions/aiws.desktop，usr/local/bin/aiws-session，usr/local/bin/aiws-open-workbench，usr/local/bin/aiws-boot-smoke，usr/local/lib/aiws/aiws_gui_smoke.py，os/debian/profiles/smoke.list.chroot，os/debian/build.sh，本 routine。

## 验证及限制
提交后须实际执行 GitHub ISO/QEMU CI；只有串口明确通过新校验才能认定 GUI 验收成功。Selenium headless 验证 React 点击行为，独立确认 kiosk 可见窗口，并抓取 QEMU framebuffer。NixOS adapter 还未切换 shell；这仍是无网络一次性自动登录 guest 实验配置，绝不用于用户主机、联网共享系统或宿主提权。

## 下一步
依据真实 GUI 启动日志修复失败；集成 NixOS 可构建镜像、模型 guest 服务和评测数据；扩展 DAG 协议与审批审计，所有 AI 权限限于客户机。
