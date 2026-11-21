# 2026-11-22 08:30 — O4：构建通道隔离，以及观察台布局紧凑化

## 改动
- 新增 `aiws_egress_proxy.py`（域名白名单 HTTPS 代理）、镜像文件（sysusers/tmpfiles、nftables 规则、两个 systemd 单元及启用符号链接、sudoers、白名单）、`os/builder/aiws_builder_selftest.py` 与 `os/builder/README.md`；`build.sh` 安装并设置权限；两个软件包清单补齐 `nftables`/`acl`/`sudo`。
- 监督器新增 `UserIsolation`（专用用户 + ACL + sudo 信号 + 防火墙标记）与 `isolation` 配置（默认 none）。
- 前端：观察台改为 6 列密集网格（“需要你”与审计结论在最上，其余并排；收件箱两列、默认 6 条可展开；更小的内边距与行距）；构建卡片显示隔离状态与已安装的 CLI。
- 测试：`test_egress_proxy.py`（15）、`test_builder_isolation.py`（11）、`test_builder_infra.py`（18，含网络命名空间里的真实内核行为测试）。

## 发现并修复
- 代理：Python 的 `is_global` 会把组播地址（如 224.0.0.1）当成公网地址放行，已改为严格的公网单播判断，并排除 IPv4 映射的 IPv6、NAT64、6to4、Teredo。
- 观察台：收件箱待批准很多时会无限拉长并撑出空白，已限制并两列排布。

## 验证
- 见观察台方案第 15 节。真实内核行为只在容器的网络命名空间里验证；**真实客体、ACL、systemd 顺序、真实 CLI 均未验证**。

## 下一步
O5（小模型框架省资源：按需启动/空闲卸载、约束输出、基准）与 O6（真实 CLI 录制与计费核对）；在 CI 里增加 QEMU 客体运行 `aiws-builder-selftest` 的任务。
