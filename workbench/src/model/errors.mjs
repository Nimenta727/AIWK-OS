/** Service error messages arrive in English. In the Chinese UI they are translated here; anything not in the table is shown as
 *  an explicit "English original" instead of silently mixing languages. A Python test checks that every message raised by the
 *  user-facing modules is listed (see os/verify/test_error_translations.py), so new messages cannot slip through untranslated. */

/** [english exact text, chinese] */
const EXACT = [
  // HTTP layer and the UI's own fallbacks
  ['Invalid response from guest service', '服务返回了无法识别的内容'], ['Guest service request failed', '服务请求失败'], ['Session unavailable', '会话不可用（服务可能正在重启）'],
  ['A valid session id is required', '需要有效的会话编号'], ['Invalid CSRF', '请求令牌无效（页面会自动刷新后重试）'], ['Invalid host', '主机头无效'],
  ['Invalid length', '内容长度无效'], ['Invalid origin', '请求来源无效'], ['JSON required', '需要 JSON 格式的请求'], ['Missing asset', '缺少资源文件'],
  ['Not a previewable file type or too large', '不是可预览的文件类型，或文件过大'], ['Not found', '未找到'],
  ['One bounded guest-workspace path required', '需要一个位于工作区内的路径'], ['React workbench assets missing', '工作台界面文件缺失'],
  ['Request too large or empty', '请求为空或过大'], ['Unknown job', '未知的任务'], ['after must be an integer', 'after 必须是整数'],
  ['Agent queue full', '代理队列已满，请稍后再试'], ['Dedicated workspace required', '需要先指定专用工作区'], ['Expected JSON object', '需要 JSON 对象'],
  ['Expected instruction', '需要填写指令'], ['Expected instruction and agent', '需要指令和代理'], ['Expected mandateId and prompt', '需要授权编号和任务描述'],
  ['Expected the application id only', '只能提供应用编号'], ['Expected title, goal and stages', '需要标题、目标和步骤'], ['Expected tool and arguments', '需要工具和参数'],
  ['Expected {text, kind} or {forget}', '需要 {text, kind} 或 {forget}'], ['Invalid asset', '资源无效'], ['Missing head', '缺少内容'], ['Missing required tool arguments', '缺少必需的工具参数'],
  ['Model toggle accepts no body fields', '模型开关不接受任何字段'], ['No arguments allowed', '不允许带参数'], ['No arguments allowed for approval', '批准操作不允许带参数'],
  ['No arguments allowed for dispatch', '派发操作不允许带参数'], ['Outside assets', '资源超出范围'], ['The builder is disabled (enable it in ~/.config/aiws/builder.json)', '构建通道未启用（在 ~/.config/aiws/builder.json 中启用）'],
  ['Too many system operations; wait a moment', '系统操作太频繁，请稍等'], ['Tool arguments must be strings', '工具参数必须是字符串'], ['Tool is not exposed to the workbench', '该工具未向工作台开放'],
  ['Unexpected fields for this system operation', '这个系统操作包含不被接受的字段'], ['Unknown external agent', '未知的外部代理'], ['Unknown tool arguments', '未知的工具参数'],
  ['AIWS Code is not installed in this image (see os/ide/README.md)', '本镜像未安装 AIWS Code（见 os/ide/README.md）'],
  ['External handoff is not permitted for this request or configuration', '此请求或当前配置不允许转交外部模型'], ['External handoff is not permitted for this request', '此请求不允许转交外部模型'],
  // system controls
  ['Confirmation required', '需要确认'], ['Invalid input method name', '输入法名称无效'], ['Invalid network name', '网络名称无效'], ['Invalid output or mode', '显示器或分辨率无效'],
  ['That network was not seen in the last scan', '最近一次扫描没有发现这个网络'], ['That output/mode is not offered by the display', '显示器不支持这个输出或分辨率'],
  ['Unknown power action', '未知的电源操作'], ['Wi-Fi password must be 8–63 printable characters', 'Wi-Fi 密码必须是 8–63 个可打印字符'],
  // change review
  ['Git did not answer', 'Git 没有响应'], ['Git is not installed', '未安装 Git'], ['No diff available', '没有可用的差异'], ['Not a folder', '不是文件夹'],
  ['Not a git project (nothing to compare against)', '不是 Git 项目（没有可比较的内容）'], ['Unreadable file', '文件无法读取'],
  // capabilities / skills / memory
  ['Memory is full; forget something first', '记忆已满，请先删除一些'], ['No such memory', '没有这条记忆'], ['Skill name must be lowercase letters, digits, . _ -', 'Skill 名称只能用小写字母、数字和 . _ -'],
  ['Skill needs a --- front matter block', 'Skill 需要以 --- 开头的头部信息'], ['That looks like a secret; secrets are never stored in memory', '这看起来像密钥；密钥不会存入记忆'],
  ['Too many required tools', '声明依赖的工具太多'], ['Unknown kind', '未知的类型'], ['Unknown memory kind', '未知的记忆类型'], ['hash does not match the pinned manifest', '哈希与固定清单不一致'], ['too large', '内容过大'],
  // applications and launcher
  ['This entry cannot be launched from outside the workbench', '这个条目不能从工作台外部启动'], ['Unknown application', '未知的应用'],
  ['The desktop launcher is not available (is the graphical workbench running?)', '桌面启动器不可用（图形工作台在运行吗？）'], ['The user has not approved this launch', '你还没有批准这次启动'],
  ['This execution has already launched', '这次执行已经启动过了'], ['Invalid identifiers', '编号无效'], ['Expected taskId, stageKey and id', '需要 taskId、stageKey 和 id'],
  ['Stage arguments differ from the request', '步骤参数与请求不一致'], ['Not the exact persisted running launch stage', '不是已记录的、正在运行的启动步骤'],
  // builder mandate
  ['An unrestricted shell can never be granted; use a specific pattern such as Bash(npm test)', '不能授予不受限的 shell；请使用具体模式，例如 Bash(npm test)'],
  ['Invalid needApprovalFor categories', '“需批准的操作”类别无效'], ['Invalid tool entry', '工具条目无效'], ['Mandate record was modified after it was granted', '授权记录在授予后被改动过'],
  ['Tool pattern contains a forbidden command or shell syntax', '工具模式包含被禁止的命令或 shell 语法'], ['Unknown mandate', '未知的授权'], ['Unknown mandate fields', '授权包含未知字段'],
  ['Unknown run', '未知的运行'], ['Unknown run field', '运行包含未知字段'], ['allowedTools needs 1-16 entries', '允许的工具需要 1–16 项'],
  ['permissionMode may not bypass permission prompts', '权限模式不能绕过权限确认'], ['projectDir may not contain symlinks', '项目文件夹不能包含符号链接'],
  ['projectDir may not use protected or parent folders', '项目文件夹不能使用受保护目录或上级目录'], ['projectDir must be a relative workspace folder', '项目文件夹必须是工作区内的相对路径'],
  ['projectDir must be an existing sub-folder of the workspace', '项目文件夹必须是工作区中已存在的子文件夹'], ['provider must be claude, codex or deepseek', '云端模型只能是 claude、codex 或 deepseek'],
  ['model, thinking, effort and planApproval are only for the deepseek provider', 'model、thinking、effort、planApproval 只适用于 deepseek'],
  ['model is not one of the supported DeepSeek models', '不是受支持的 DeepSeek 模型'], ['effort must be low, high or max', '推理强度只能是 low、high 或 max'],
  ['thinking and planApproval must be true or false', 'thinking 和 planApproval 必须是 true 或 false'],
  // DeepSeek key and runner
  ['execWithoutIsolation must be true or false', 'execWithoutIsolation 必须是 true 或 false'],
  ['No DeepSeek API key is configured', '还没有配置 DeepSeek API 密钥'], ['Could not start the runner', '无法启动云端运行器'], ['Expected {key} or {clear: true}', '需要 {key} 或 {clear: true}'],
  ['The key file must be a regular file, not a link', '密钥文件必须是普通文件，不能是链接'], ['The key file must belong to this user', '密钥文件必须属于当前用户'],
  ['The key file must not be readable by others (use mode 600)', '密钥文件不能被其他用户读取（请用权限 600）'], ['The key file is too large', '密钥文件过大'],
  ['The key file does not contain a valid key', '密钥文件里不是有效的密钥'], ['That does not look like an API key', '这看起来不像 API 密钥'],
  ['The key cannot be stored inside the workspace', '密钥不能存放在工作区内'], ['The config directory must not be a link', '配置目录不能是链接'],
  ['requireMetering must be true or false', 'requireMetering 必须是 true 或 false'], ['tokenBudget needs input and output limits', 'token 预算需要同时给出输入和输出上限'],
  // router
  ['Instruction must contain 1-1000 characters', '指令需要 1–1000 个字符'], ['Unknown agent', '未知的代理'], ['externalEnabled must be true or false', 'externalEnabled 必须是 true 或 false'],
  ['providers must map claude/codex to booleans', 'providers 必须把 claude/codex 映射为布尔值'], ['Route config is not valid JSON', '路由配置不是有效的 JSON'], ['Route config contains unknown keys', '路由配置包含未知项'],
  // supervisor
  ['A build is already running; only one run at a time', '已有构建在运行；同一时间只能运行一个'], ['Nothing is waiting for approval', '没有等待批准的事项'], ['That run is not active', '该运行已不在进行'],
  ['The builder firewall is not active (marker missing): refusing to run the builder', '构建防火墙未生效（缺少标记）：拒绝运行构建'], ['The mandate\'s token budget is used up', '这份授权的 token 预算已用完'],
  ['The project folder contains a symlink', '项目文件夹里有符号链接'], ['The project folder no longer exists inside the workspace', '项目文件夹已不在工作区内'],
  ['The task text may not start with \'-\'', '任务描述不能以 “-” 开头'], ['The task text must contain 1-4000 characters', '任务描述需要 1–4000 个字符'],
  ['Refusing to build a permission-bypassing command line', '拒绝生成会绕过权限的命令行'], ['Builder config is not valid JSON', '构建配置不是有效的 JSON'], ['Builder config has unknown keys', '构建配置包含未知项'],
  // task plans
  ['DAG contains a cycle', '任务依赖图里有循环'], ['Dependency references invalid', '依赖引用无效'], ['Duplicate stage key', '步骤编号重复'], ['Each stage requires key, label, tool, arguments, dependsOn', '每个步骤都需要 key、label、tool、arguments、dependsOn'],
  ['Guest-write stage requires explicit approval', '会改动文件的步骤需要你明确批准'], ['Invalid dependencies', '依赖无效'], ['Invalid stage key', '步骤编号无效'], ['Missing/unknown tool arguments', '工具参数缺失或未知'],
  ['Only guest-scoped allowlisted tools may be planned', '计划里只能使用白名单内、限定在客户机的工具'], ['Only pending guest-write stages require approval', '只有待处理的写入步骤才需要批准'], ['Plan requires 1-32 stages', '计划需要 1–32 个步骤'],
  ['Stage already queued/running/completed; cannot double dispatch', '步骤已在排队/运行/完成，不能重复派发'], ['Stage label required', '步骤需要名称'], ['Task goal too long', '任务目标太长'], ['Task title required', '任务需要标题'],
  ['Tool arguments must be bounded string values', '工具参数必须是长度受限的字符串'], ['Unknown stage', '未知的步骤'], ['Unknown task ID', '未知的任务编号'], ['Expected queued stage', '步骤应处于排队状态'], ['Expected running stage', '步骤应处于运行状态'],
];

/** [regex, chinese with $1.. placeholders] for messages that embed a value */
const PATTERNS = [
  [/^Not installed in this image: (.*)$/, '本镜像未安装：$1'], [/^Not a launchable application: (.*)$/, '不是可启动的应用：$1'], [/^Launch refused: (.*)$/, '启动被拒绝：$1'],
  [/^Memory must be 1.\d* ?characters?$|^Memory must be 1–(\d+) characters$/, '记忆需要 1–$1 个字符'], [/^Skill is larger than (\d+) bytes$/, 'Skill 超过 $1 字节'],
  [/^Command failed: (.*)$/, '命令执行失败：$1'], [/^(.+) is not available in this image$/, '本镜像没有 $1'],
  [/^The (.+) approval cannot be switched off$/, '“$1”这项批准无法关闭'], [/^(.+) must be an integer between (\d+) and (\d+)$/, '$1 必须是 $2 到 $3 之间的整数'],
  [/^The mandate is (.+)$/, '这份授权的状态是 $1，不能运行'], [/^The official (.+) CLI is not installed on this machine$/, '这台机器上没有安装官方的 $1 命令行工具'],
  [/^Could not start the CLI: (.*)$/, '无法启动命令行工具：$1'], [/^Prerequisite has not completed: (.*)$/, '前置步骤尚未完成：$1'],
  [/^(.+) failed \(exit (.+)\)$/, '$1 执行失败（退出码 $2）'], [/^(.+) failed: (.*)$/, '$1 执行失败：$2'], [/^(.+) is required for the isolated builder$/, '隔离构建需要 $1'],
  [/^Git (.*)$/, 'Git：$1'], [/^allowedTools needs 1-(\d+) entries$/, '允许的工具需要 1–$1 项'],
];

const map = new Map(EXACT);

/** The Chinese text for a service message, or null when it is not in the table. */
export function translateError(text) {
  const t = String(text ?? '').trim();
  if (map.has(t)) return map.get(t);
  for (const [rx, zh] of PATTERNS) {
    const m = t.match(rx);
    if (m) return zh.replace(/\$(\d)/g, (_, i) => m[Number(i)] ?? '');
  }
  return null;
}

/** What to show. English UI: the original. Chinese UI: the translation, or a clearly labelled English original. */
export function localizeError(text, english) {
  const t = String(text ?? '');
  if (english) return t;
  return translateError(t) ?? '（服务返回的英文原文）' + t;
}

export const TABLE_SIZE = EXACT.length + PATTERNS.length;
