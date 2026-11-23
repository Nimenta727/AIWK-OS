# 模型权重：自己下载，怎么放进系统 / Model weights: download them yourself

**发布的 ISO 里没有任何模型权重。** 没有权重时，系统其余部分都能用（工作台、计划审核、云端构建、文件与日志的确定性工具、`log.digest`/`log.lines`），只是没有**本地助手**和**本地路由**。想要它们，按下面做。

> **诚实声明**：下面的第 1 步（下载与校验）和第 5 步里的命令，本身都在仓库代码里并有测试；但"把权重放进**这个发布的镜像**并在客户机里跑起来"这一整套步骤**没有在镜像里端到端验证过**。每一步我都写明了依赖什么、哪里可能不对。

## 0. 先决条件

| 项 | 要求 | 说明 |
|---|---|---|
| 虚拟机内存 | **≥ 16 GiB**（实测运行需约 11 GiB，再加系统和权重文件本身） | 默认 6 GiB 放不下，启动脚本会拒绝（退出码 75）。运行脚本时 `AIWS_VM_MEM=16384`；用 virt-manager / VirtualBox 等就在界面里设内存 |
| 速度 | CPU 上每步 10–40 秒，读一份日志要几分钟 | 实测 4 核：生成 3–4 token/s，预填约 44 token/s |
| 磁盘 | 主机上约 6 GB 放权重文件 | |
| 虚拟机里的网络 | **默认没有**（`-nic none`） | 所以权重要经一块只读的盘带进去，见第 3 步 |

**宿主显卡路径**：仓库里有宿主侧（`os/host/aiws_host_model.py`）和 virtio 通道（`os/runtime/aiws_model_channel.py`）的代码并有测试，但**这个镜像和 `run-qemu-offline.sh` 里还没有接线**（没有 virtio-serial 参数，客户机里也没有对应的服务单元），所以它**现在不是可用的发布路径**。

## 1. 在你的电脑上下载并校验

产品模型是 **Qwen3.5-9B，Q4_K_M 量化**（Apache-2.0；模型卡、GGUF 元数据与仓库 LICENSE 全文均核对过）。

| 项 | 值 |
|---|---|
| 文件 | `Qwen3.5-9B-Q4_K_M.gguf` |
| 来源 | `https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf`（第三方量化；原模型 `Qwen/Qwen3.5-9B`） |
| 大小 | 5,680,522,464 字节 |
| SHA-256 | `03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8` |

```bash
mkdir weights && cd weights
curl -L -C - -o Qwen3.5-9B-Q4_K_M.gguf \
  https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf
sha256sum Qwen3.5-9B-Q4_K_M.gguf        # 必须等于上表的哈希；不等就重新下载，不要继续
```

第三方量化可能附带自己的条件；发行或再分发之前请自己确认（上表是我核对时的状态，不是法律意见）。

## 2. 把文件装进一块虚拟盘（Linux / macOS / WSL，不需要 root）

```bash
cd ..                                   # weights 文件夹的上一级
truncate -s 6200M models.img
mkfs.ext4 -L AIWS-MODELS -d weights models.img      # 需要 e2fsprogs ≥ 1.43；-d 会把 weights/ 里的文件放进镜像
```

## 3. 带着这块盘启动虚拟机

```bash
AIWS_VM_MEM=16384 AIWS_EXTRA_DISK=$PWD/models.img \
AIWS_WORK_DISK=$PWD/work.qcow2 \                    # 可选但建议：独立工作盘（见 docs/AIWS_DUAL_DISK.md）
  ./os/host/run-qemu-offline.sh path/to/aiws-os-0.3.0-preview.1-amd64.iso
```

`AIWS_EXTRA_DISK` 以**只读**方式挂进去，不会被自动挂载。分卷下载的 ISO 先按发布页的 `REASSEMBLE.txt` 合并并校验。

## 4. 在客户机里取出权重（第 4 步和第 5 步需要一个终端）

客户机是全屏工作台，没有桌面环境。终端的两个入口（**我没有在镜像里验证过哪个可用**）：工作台里的 AIWS Code 自带终端；或 `Ctrl+Alt+F2` 切到文字控制台，用 `user` / `live` 登录。

```bash
sudo mount -o ro LABEL=AIWS-MODELS /mnt          # 如果 sudo 不可用，就是镜像里没给这个用户提权：这一步会卡住
mkdir -p ~/.local/share/aiws/projects
cp /mnt/Qwen3.5-9B-Q4_K_M.gguf ~/.local/share/aiws/projects/
```

**注意内存**：Live 系统的家目录在内存里。这一步复制进来占 5.7 GB，下面的导入还会再复制一份，所以导入完成后**必须删掉这份源文件**（第 5 步最后一行），否则内存会被占满。

## 5. 导入、校验、启用

```bash
python3 /usr/local/lib/aiws/aiws_model_registry.py \
  --import-guest Qwen3.5-9B-Q4_K_M.gguf \
  --sha256 03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8 \
  --accept-source-license                         # 重算哈希要一两分钟；哈希不符、文件不是 GGUF、超过 12 GiB 都会被拒绝
rm ~/.local/share/aiws/projects/Qwen3.5-9B-Q4_K_M.gguf     # 释放 5.7 GB 内存
```

`--accept-source-license` 表示你已看过上面的许可说明。成功会打印 `{"verified": true, ...}`。

然后在工作台：侧边栏 **系统 → 本地模型开关**，点"申请启用模型"并批准。模型随后加载（常驻），**本地助手**页顶上的徽章从"模型已关闭"变成"模型就绪"。

## 6. 局限（请知道）

- **Live 会话不持久**：重启后家目录清空，权重要**重新导入**（约几分钟）。想省事，把系统装到盘上，或把权重放在持久的工作盘上并自行调整路径（后者我没有做）。
- 内存不足时启动脚本拒绝启动而不是被内核杀掉；真遇到，请加内存而不是跳过检查（`AIWS_MODEL_SKIP_RAM_CHECK=1` 只给确有交换空间的机器）。
- 想换别的模型：登记表只认 `Qwen/Qwen3.5-9B`，其他模型会被拒绝；评测、路由提示词和读日志的数字都只对这个模型成立。
- 导入命令的底层是 `aiws_model_registry.py`：权重只能来自客户机里的工作区文件、必须给出精确的 SHA-256、必须确认许可，不会联网、不会访问宿主目录。

## 7. 出了问题

| 现象 | 原因 / 办法 |
|---|---|
| 启动脚本报 `Not enough free memory`，退出码 75 | 虚拟机内存不足，按第 0 步加到 ≥ 16 GiB |
| `Expected artifact hash does not match` | 下载不完整或被改：回到第 1 步重下并校验 |
| `Disable the guest model service before switching weights` | 模型正在运行：先在"本地模型开关"里关闭再导入 |
| 本地助手徽章一直是"模型未运行" | 看服务日志 `journalctl --user -u aiws-local-model`；常见是内存不足或权重未通过校验 |
| 本地助手能启动但很慢 | CPU 推理的正常速度（见第 0 步）；有显卡通道之后才会快，目前未接线 |
