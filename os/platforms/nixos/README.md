# NixOS image adapter — experimental / NixOS 系统重构适配器

目标：通过 NixOS 模块把 AIWS 共享 React 工作台、客户机工具、Agent 任务队列、XFCE/LightDM 与 systemd 用户服务声明成一个镜像，而不是另外造一套 GUI 或特定 Debian 工具。

**尚未完成 NixOS 构建或 VM 启动验证。** 当前 flake 使用 nixos-26.05 分支，未提交 flake.lock，也没有 npm lockfile；因此不能宣称可重复构建。真实 ISO 构建必须安装 Nix 和 Node.js，并先构建共享 UI：

    cd desktop/AIWorkstation.Frontend
    npm install --no-audit --no-fund
    npm run build
    cd ../..
    AIWS_UI_DIST="$PWD/desktop/AIWorkstation.Frontend/dist" nix build --impure .#aiws-iso

如成功，生成的 ISO 位于 result/iso/。AIWS_UI_DIST 通过 builtins.path 注入到 Nix，属于过渡方案。未来将引入固定 npm/Nix 锁文件和完整构建衍生包。未传 UI dist 时，boot probe 必须拒绝报告通过。

注意：本 profile 为离线一次性 VM，会自动登录 aiws 用户；联网/共享用户前需要改为受保护的登录与隔离策略。不提供客体以外 root、宿主共享挂载和 Hypervisor 控制。

参考 NixOS 官方文档：https://nixos.org/manual/nixos/stable/
