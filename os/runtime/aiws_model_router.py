"""AIWS model router: decides WHERE a request is handled. It never executes anything.

Layers
  L0  deterministic rules (this file): local model, external official CLI, or ask the user.
  L1  outcome of the local model: ok / refused / invalid / unavailable.
  L2  external official CLI (Claude Code / Codex): only a user-consented HANDOFF FILE is produced.
      This module opens no sockets, starts no process and calls no model.

Safety invariants (tests pin each one)
  * A policy refusal is FINAL. It is never "escalated" to a stronger model.
  * Requests matching a forbidden category are never externally routable.
  * External routing is OFF by default and needs explicit configuration.
  * An escalation is only a proposal; the user approves the handoff file stage.
  * Handoff files hold the instruction and workspace file NAMES only: no contents, no secrets.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil

MAX_INSTRUCTION = 1000
MAX_KEYWORDS = 16
MAX_HANDOFF_FILES = 24
PROVIDERS = {"claude": "claude", "codex": "codex"}   # provider id -> official CLI executable name

DEFAULT_CONFIG = {"externalEnabled": False, "providers": {"claude": True, "codex": True},
                  "extraLocalKeywords": [], "extraExternalKeywords": []}

class RouterError(ValueError):
    pass

# --- L0 vocabulary -------------------------------------------------------------------------
# Forbidden categories: the local model must refuse these and they may never leave the guest.
# NOTE on "audit": only ATTEMPTS TO SUPPRESS auditing count (disable/erase/hide the audit log ...). The bare word used to flag a request for a
# security audit, or to design a system with an audit log, as an attempt to evade auditing.
# NOTE on "root": only phrases about root PRIVILEGES count (as root, root access, root 权限 ...). The bare word used to match "root cause"
# and "project root", so a debugging question ("find the root cause of the leak") was treated as restricted.
FORBIDDEN = {
    "network": r"https?://|ftp://|\bping\b|\bcurl\b|\bwget\b|联网|上网|go online|\bfetch\b|从.{0,40}拉取|pull the file|\bscp\b|\bssh\b|"
               r"\b\d{1,3}(\.\d{1,3}){3}\b|\b[a-z0-9-]+\.(com|org|net|io|cn|edu|gov|dev|app)\b|连上|连接到|connect(ion)? to|search the web|browse the (web|internet)|web search|搜索网络|网上搜",
    "download_control": r"(暂停|继续|取消|重新开始|停止|限速).{0,60}下载|下载.{0,40}(暂停|继续|取消|限速|重启)|让.{0,40}接着下|(pause|resume|restart|cancel|stop|throttle|keep)\b.{0,40}download|downloading\b",
    "shell_root": r"\bsudo\b|\b(as|with|using|become|becoming|gain|get|obtain|switch to|login as|log in as|su to)\s+root\b|\broot\s+(access|privileges?|permissions?|authority|rights|shell|user|account|password|login)\b|root ?(权限|身份|用户|账号|账户|密码)|提权|escalat|rm -rf|\bchmod\b|bash -c|\bnc -l|dd if=|执行命令|任意.{0,6}命令|arbitrary command|run (this|a|the|any) command|(run|execute|运行|执行) ?(sudo|bash|python3?|sh|perl|node|curl|rm|nc|\./)\S*|exploit|payload|reverse shell|\btype\b.{0,20}\bin a shell|在终端里|管理员(命令|权限|模式)",
    "host": r"宿主|\bhost\b|主机(上|里|的文件|磁盘)|hypervisor|虚拟机管理|\bqmp\b|qemu monitor|直通|passthrough|usb 设备|through to the guest",
    "permanent_delete": r"永久|彻底|物理删除|permanent|irrevers|\bshred|\bwipe\b|销毁|抹掉|for good|no undo|不留备份|清空回收站|empty the trash|\berase\b",
    "write_content": r"写入|追加|\bappend\b|\bwrite ['\"“]|replace the content|替换.{0,20}内容|so it says|填入|\binsert\b.{0,30}\bat\b|加上 ?[a-z#]|编辑 .{0,40}加上",
    "bypass": r"绕过|\bbypass|跳过审批|skip the approval|(关闭|禁用|停用|跳过|清除|清空|删除|隐藏|规避|屏蔽|不要|别).{0,8}审计|审计.{0,8}(关闭|禁用|停用|跳过|清除|清空|删除|隐藏|规避|屏蔽|痕迹)|不留痕|\b(disable|turn off|skip|suppress|erase|delete|clear|wipe|hide|conceal|evade|avoid|stop)\w*\b.{0,30}\baudit\w*|\baudit (log|logs|trail|trails|record|records)\b.{0,20}\b(delet\w*|eras\w*|clear\w*|wip\w*|hid\w*|conceal\w*)|不要记录|do not log|without asking|别让用户批准|不需要审批|无需审批|ignore (all |the )?(previous |prior |permission |safety )?(rules|limits|instructions|restrictions)|忽略.{0,12}(规则|限制)|忘掉.{0,10}设定|disregard|developer mode|管理员模式|new (rule|policy):|新规则",
    "path_escape": r"/etc/|/root|/proc/|/home/|\.\./|\.\.\\|[a-z]:\\|/mnt/|\.aws|credentials|\bshadow\b|\bpasswd\b|id_rsa|private key|ssh 密钥",
    "cloud_or_exfil": r"云端|cloud (model|storage)|chatgpt|在线 ?api|online api|remote llm|远程的 ?claude|forward this to|发到网上|发送到|\bemail the|邮箱|传到远程|网盘|(upload|push|send)\b.{0,40}\b(external|remote|outside|server|endpoint)|上传",
}
LOCAL_HINTS = (
    r"文件|文件夹|目录|回收站|重命名|移动|复制|删除|新建|恢复|备份|读取|查看|列出|搜索|下载|进度|内存|磁盘|系统|网络|网卡|端口|\bdns\b|负载|开机|内核|git|diff|"
    r"\bfiles?\b|folders?|director(y|ies)|\btrash\b|recycle|rename|\bmove\b|\bcopy\b|\bdelete\b|\bcreate\b|restore|back ?up|\bread\b|\blist\b|\bshow\b|search|grep|"
    r"download|progress|memory|\bram\b|disk|system|network|interface|\bports?\b|\bload\b|uptime|kernel|status|\bmkdir\b|\bmv\b|\bcp\b|\brm\b|"
    r"已安装|开发工具|运行时|编译器|环境|installed|compilers?|runtimes?|toolchains?|dev tools"
)
CLAUDE_HINTS = r"架构|方案|设计|规划|分析|研究|解释|architecture|design|research|planning|analy[sz]e|explain (why|how)|review (the |my )?code"
CODEX_HINTS = r"实现|编写|开发(一个|个|新|功能|程序|应用|模块)|重构|修复|调试|优化|测试|写(一个|个)?(函数|程序|代码|脚本|模块|类)|implement|refactor|debug|fix (the |this )?bug|optimi[sz]e|write (a |an )?(function|program|script|class|module|test)|unit tests?"

FILENAME = re.compile(r"[\w./\\-]+\.[A-Za-z0-9]{1,8}\b")

def _words_only(text):
    """File names are data, not task words: `design.pdf` must not look like a design task."""
    return FILENAME.sub(" ", text)

def _hits(pattern, text):
    return len(re.findall(pattern, _words_only(text), flags=re.IGNORECASE))

def forbidden_categories(text):
    return sorted(name for name, pattern in FORBIDDEN.items() if re.search(pattern, text, flags=re.IGNORECASE))

# --- configuration -------------------------------------------------------------------------
def load_config(path=None):
    """Strict, bounded, symlink-refusing config; unknown keys are rejected (fail closed to defaults)."""
    path = Path(path) if path is not None else Path.home() / ".config/aiws/routes.json"
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path.is_symlink():
        raise RouterError("Route config must not be a symlink")
    if not path.exists():
        return config
    if not path.is_file() or path.stat().st_size > 4096:
        raise RouterError("Route config must be a regular file up to 4 KiB")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RouterError("Route config is not valid JSON") from exc
    if not isinstance(data, dict) or set(data) - set(DEFAULT_CONFIG):
        raise RouterError("Route config contains unknown keys")
    if "externalEnabled" in data:
        if not isinstance(data["externalEnabled"], bool):
            raise RouterError("externalEnabled must be true or false")
        config["externalEnabled"] = data["externalEnabled"]
    if "providers" in data:
        value = data["providers"]
        if not isinstance(value, dict) or set(value) - set(PROVIDERS) or any(not isinstance(v, bool) for v in value.values()):
            raise RouterError("providers must map claude/codex to booleans")
        config["providers"].update(value)
    for key in ("extraLocalKeywords", "extraExternalKeywords"):
        if key in data:
            words = data[key]
            if (not isinstance(words, list) or len(words) > MAX_KEYWORDS or
                    any(not isinstance(w, str) or not 1 <= len(w) <= 32 for w in words)):
                raise RouterError(key + " must be up to 16 short strings")
            config[key] = [w.casefold() for w in words]
    return config

# --- decision ------------------------------------------------------------------------------
def _providers(config, which):
    return {name: {"enabled": bool(config["providers"].get(name)), "installed": which(exe) is not None}
            for name, exe in PROVIDERS.items()}

def classify(instruction, config=None, which=shutil.which):
    if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= MAX_INSTRUCTION:
        raise RouterError("Instruction must contain 1-1000 characters")
    config = load_config() if config is None else config
    text = instruction.strip()
    folded = text.casefold()
    forbidden = forbidden_categories(text)
    local = _hits(LOCAL_HINTS, text) + sum(1 for w in config["extraLocalKeywords"] if w in folded)
    claude = _hits(CLAUDE_HINTS, text) + sum(1 for w in config["extraExternalKeywords"] if w in folded)
    codex = _hits(CODEX_HINTS, text)
    external_score = (claude + codex) * 2
    decision = {
        "instructionSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "forbidden": forbidden, "externalAllowed": not forbidden,
        "externalEnabled": config["externalEnabled"], "providers": _providers(config, which),
        "scores": {"local": local, "claude": claude, "codex": codex},
        "requiresConsent": False, "sendsDataAutomatically": False, "agent": "local",
    }
    if forbidden:
        # The local model decides (and is trained to refuse). Nothing here may go external.
        decision.update(route="local", rule="L0-forbidden",
                        reason={"zh": "请求涉及受限操作，只交给本地模型判断；不会转交外部模型。",
                                "en": "Restricted request: handled by the local model only; never sent to an external model."})
        return decision
    if external_score > local and external_score > 0:
        agent = "dual" if claude and codex else ("claude" if claude >= codex else "codex")
        decision["agent"] = agent
        decision["requiresConsent"] = True
        if config["externalEnabled"] and any(p["enabled"] for p in decision["providers"].values()):
            decision.update(route="external", rule="L0-external",
                            reason={"zh": "这是代码编写/设计类任务，建议使用官方 CLI；需要你确认并生成交接文件。",
                                    "en": "Code authoring/design task: an official CLI is recommended; needs your consent and a handoff file."})
        else:
            decision.update(route="manual", rule="L0-external-disabled",
                            reason={"zh": "任务超出本地小模型的范围，但外部模型未启用：请手动选择，或在 routes.json 中启用。",
                                    "en": "Beyond the local model, but external routing is disabled: choose manually or enable it in routes.json."})
        return decision
    decision.update(route="local", rule="L0-local" if local else "L0-default",
                    reason={"zh": "文件、系统与下载信息类任务，在本机离线处理。" if local else "无法确定类型，先交给本地模型；它无法处理时再询问你。",
                            "en": "File, system and download-info task: handled offline on this machine." if local
                                  else "Type unclear: try the local model first; you are asked if it cannot help."})
    return decision

def after_local(decision, outcome):
    """L1: what to do once the local model answered. Refusals are final."""
    if outcome not in ("ok", "refused", "invalid", "unavailable"):
        raise RouterError("Unknown local outcome")
    if outcome == "ok":
        return {"escalate": False, "final": False, "action": "use-local-result"}
    if outcome == "refused":
        return {"escalate": False, "final": True, "action": "show-refusal",
                "reason": {"zh": "拒绝是最终结论：不会为绕过限制而转交其他模型。",
                           "en": "A refusal is final: it is never forwarded to another model to get around the limits."}}
    can_go_out = (decision["externalAllowed"] and decision["externalEnabled"]
                  and any(p["enabled"] for p in decision["providers"].values()))
    if can_go_out:
        agent = decision["agent"] if decision["agent"] in ("claude", "codex", "dual") else "claude"
        return {"escalate": True, "final": False, "agent": agent, "requiresConsent": True,
                "action": "propose-handoff",
                "reason": {"zh": "本地模型这次没能给出有效方案；可以生成交接文件，由你确认后用官方 CLI 处理。",
                           "en": "The local model could not produce a valid plan; you may generate a handoff file for an official CLI after consenting."}}
    return {"escalate": False, "final": False, "action": "ask-user",
            "reason": {"zh": "本地模型没能处理这个请求；请换一种说法或手动操作。",
                       "en": "The local model could not handle this request; rephrase it or act manually."}}

# --- handoff (the only way anything is prepared for an external CLI) ------------------------
def build_handoff(instruction, agent, decision, file_names):
    if agent not in ("claude", "codex", "dual"):
        raise RouterError("Unknown agent")
    if not decision.get("externalAllowed") or not decision.get("externalEnabled"):
        raise RouterError("External handoff is not permitted for this request")
    names = []
    for name in file_names[:MAX_HANDOFF_FILES]:
        if isinstance(name, str) and 0 < len(name) <= 96 and not any(ord(c) < 32 for c in name):
            names.append(name)
    digest = hashlib.sha256((instruction.strip() + "\0" + agent).encode("utf-8")).hexdigest()
    ident = digest[:12]
    lines = ["# AIWS handoff request", "",
             "Generated offline by the AIWS router. Review it before use. It contains the instruction and",
             "workspace file NAMES only: no file contents, no credentials, no host information.", "",
             "Suggested agent: " + agent, "", "## Instruction", "", instruction.strip(), "",
             "## Workspace file names (names only)", ""] + ["- " + n for n in names] + [
             "", "## How to use", "",
             "Open this file yourself in the official Claude Code or Codex CLI. AIWS never launches an",
             "external CLI and sends nothing automatically.", ""]
    text = "\n".join(lines)
    return {"id": ident, "path": "handoff/" + ident + ".md", "text": text,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "dataShared": {"instruction": True, "fileNames": len(names), "fileContents": False, "credentials": False}}

def handoff_stages(handoff, folder_exists):
    """Approval-gated DAG stages that write the handoff file into the workspace."""
    stages, previous = [], None
    if not folder_exists:
        stages.append({"key": "folder", "label": "Create handoff folder", "tool": "file.mkdir",
                       "arguments": {"path": "handoff"}, "dependsOn": []})
        previous = "folder"
    stages.append({"key": "write", "label": "Write handoff file (review before sharing)", "tool": "file.replace",
                   "arguments": {"path": handoff["path"], "text": handoff["text"], "expectedSha256": ""},
                   "dependsOn": [previous] if previous else []})
    return stages
