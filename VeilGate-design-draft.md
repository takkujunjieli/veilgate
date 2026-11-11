# VeilGate — 隐私资源访问网关 / Privacy-Preserving Resource Access Gateway

设计草稿 v0.1 · 2026-10-21

Design Draft v0.1 · 2026-10-21

工作名：**VeilGate**。Veil 表示遮蔽敏感内容，Gate 表示受控访问入口；名称尚未做商标或重名核查。

Working name: **VeilGate**. “Veil” represents shielding sensitive content, while “Gate” represents a controlled access point. The name has not been checked for trademark conflicts or existing uses.

## 1. 项目定义 / Project Definition

**用户指定敏感资源，VeilGate 控制 AI Agent 对这些资源的访问、处理和内容披露。**

**Users designate sensitive resources; VeilGate controls how AI agents access and process those resources, and what information they may disclose.**

资源可以是本地文件、目录或指定 API 的返回内容。原始数据保留在可信环境中；LLM 通过受控接口获得允许披露的内容或计算结果。

Resources may be local files, directories, or responses from specified APIs. Raw data remains within a trusted environment; the LLM receives only content or computation results approved for disclosure through controlled interfaces.

项目是通用基础设施，不绑定某个业务。客户分析、内部文档、运营 API 等场景用于验证能力。

The project provides general-purpose infrastructure rather than targeting a single business use case. Scenarios such as customer analytics, internal documents, and operational APIs serve to validate its capabilities.

本项目负责执行明确的资源与隐私策略，不判断 Agent 的动机、不分析其行为是否偏离任务。Agent 行为监控作为独立项目考虑。

This project enforces explicit resource and privacy policies. It does not infer an agent’s motives or assess whether its behavior deviates from its task. Agent behavior monitoring is considered a separate project.

## 2. 用户配置什么 / User Configuration

| 配置 | 含义 | 示例 |
|---|---|---|
| 资源 | 哪些来源受保护 | 一个 CSV 文件、一个目录、一个固定 API 路由 |
| 敏感范围 | 保护整个资源还是部分字段 | 全文隔离；保护 `email`、`phone` |
| 使用权限 | 谁可以调用哪些处理操作 | 指定用户可以聚合，但不能导出明细 |
| 发布规则 | 哪些结果可以返回，返回给谁 | 仅向指定 Agent 返回批准的统计字段 |

| Configuration | Meaning | Example |
|---|---|---|
| Resources | Which sources are protected | A CSV file, a directory, or a fixed API route |
| Sensitivity scope | Whether protection applies to the entire resource or selected fields | Isolate all content; protect `email` and `phone` |
| Usage permissions | Who may invoke which processing operations | A designated user may aggregate data but may not export individual records |
| Release rules | Which results may be returned, and to whom | Return only approved statistical fields to a designated agent |

策略由资源所有者或管理员配置。LLM 不能修改策略，也不能自行声明用户角色、租户或权限。

Policies are configured by resource owners or administrators. The LLM cannot modify policies or assign itself user roles, tenant identities, or permissions.

## 3. 两种访问模式 / Two Access Modes

### A. 脱敏访问 / Redacted Access

适用于部分内容可以披露的资源。

For resources whose content may be partially disclosed.

1. 在可信环境内读取原始内容。
2. 按批准的输出字段构造结果，并对配置的敏感字段执行删除、遮盖或占位替换。
3. 校验输出，再返回给 Agent。

1. Read the original content within the trusted environment.
2. Construct the result using approved output fields, and remove, mask, or replace configured sensitive fields with placeholders.
3. Validate the output before returning it to the agent.

第一版以结构化数据为主。未知字段默认不发布；不能解析或不能匹配批准结构时拒绝返回。自动识别自由文本敏感信息只能作为补充，不能据此保证全部隐私都已消除。

The first version focuses on structured data. Unknown fields are withheld by default; responses are blocked if parsing fails or the content does not match the approved structure. Automated detection of sensitive information in free text is supplementary and cannot guarantee the removal of all private information.

### B. 隔离计算 / Opaque Processing

适用于原始内容整体保密，但允许有限计算的资源。

For resources whose raw content must remain confidential, but on which limited computation is permitted.

1. Agent 获得资源句柄和经过批准的操作说明，不获得原始内容。
2. Agent 提交操作名及参数。
3. 网关验证身份与策略，由可信执行器完成计算。
4. 结果通过发布检查后返回。

1. The agent receives a resource handle and approved operation descriptions, but no raw content.
2. The agent submits an operation name and parameters.
3. The gateway verifies identity and checks the policy; a trusted executor performs the computation.
4. Results are returned only after passing release checks.

第一版仅允许注册的操作，例如指定字段的计数、聚合，以及经过审核的内部分析函数。注册函数在可信环境中执行，实现代码不进入 LLM 上下文。

The first version permits only registered operations, such as counts and aggregations over designated fields, and reviewed internal analysis functions. Registered functions execute within the trusted environment; their implementation code does not enter the LLM context.

每个操作必须同时定义输入约束和输出发布规则；“函数可以运行”不自动意味着“它的全部返回值可以公开”。

Each operation must define both input constraints and output release rules. Permission to execute a function does not automatically permit disclosure of everything it returns.

## 4. 核心架构 / Core Architecture

```text
资源所有者 / 管理员
        │ 配置资源、权限和发布规则
        ▼
  资源注册表 + 策略配置
        │
AI Agent / 工具客户端
        │ 资源 ID、操作、参数；身份来自可信会话
        ▼
┌──────────── VeilGate：可信边界 ────────────┐
│ 入口与身份验证 → 策略校验                  │
│                       ↓                  │
│                 资源适配器                │
│             ↙             ↘              │
│        本地文件          固定 API         │
│             ↘             ↙              │
│           脱敏处理 / 受控执行器            │
│                       ↓                  │
│                 结果发布检查              │
│                       ↓                  │
│              安全结果 / 标准拒绝           │
│                                          │
│ 审计：记录决策元数据，不记录原始敏感内容     │
└──────────────────────────────────────────┘
        │ 仅允许发布的内容
        ▼
AI Agent / LLM 上下文
```

```text
Resource owner / administrator
        | Configures resources, permissions, and release rules
        v
Resource registry + policy configuration
        |
AI agent / tool client
        | Resource ID, operation, parameters;
        | identity comes from a trusted session
        v
+------------ VeilGate: trusted boundary ------------+
| Entry point and authentication -> Policy checks    |
|                              |                    |
|                              v                    |
|                      Resource adapters             |
|                       /           \               |
|                 Local files     Fixed APIs         |
|                       \           /               |
|                 Redaction / controlled executor    |
|                              |                    |
|                              v                    |
|                      Result release checks         |
|                              |                    |
|                              v                    |
|                 Safe result / standard denial      |
|                                                   |
| Audit: decision metadata, no raw sensitive content |
+---------------------------------------------------+
        | Only content approved for release
        v
AI agent / LLM context
```

| 模块 | 最小职责 |
|---|---|
| 资源注册表 | 将资源 ID 映射到私有路径或 API 配置；只暴露批准的描述 |
| 文件适配器 | 在配置的文件范围内读取；阻止路径穿越及符号链接越界 |
| API 适配器 | 调用固定上游，管理凭据，验证响应结构；限制参数与重定向 |
| 策略引擎 | 校验真实身份、资源、操作、字段和参数；默认拒绝 |
| 受控执行器 | 运行注册操作；限制文件访问、网络、运行时间和资源消耗 |
| 结果发布器 | 按输出契约重建结果，执行字段保护、聚合约束和大小限制 |
| 审计模块 | 记录资源 ID、操作、策略版本、决策及原因，不保存原文 |

| Module | Minimum responsibilities |
|---|---|
| Resource registry | Map resource IDs to private paths or API configurations; expose only approved descriptions |
| File adapter | Read within configured file boundaries; block path traversal and symlink escapes |
| API adapter | Call fixed upstream endpoints, manage credentials, validate response structure, and restrict parameters and redirects |
| Policy engine | Check authenticated identity, resources, operations, fields, and parameters; deny by default |
| Controlled executor | Run registered operations; restrict file access, networking, execution time, and resource consumption |
| Result release component | Reconstruct results according to output contracts; enforce field protection, aggregation constraints, and size limits |
| Audit module | Record resource IDs, operations, policy versions, decisions, and reasons without storing original content |

## 5. 初步接口 / Preliminary Interfaces

以下是设计接口，不代表已经实现。

The following are proposed interfaces; their inclusion here does not imply that they have been implemented.

```text
list_resources()
describe_resource(resource_id)
read_redacted(resource_id, approved_options)
execute(resource_id, operation, parameters)
```

- `list_resources` 只显示当前身份可见的资源。
- `describe_resource` 只返回批准的名称、模式和可用操作，不泄漏真实路径、凭据或数据样例。
- `read_redacted` 只对允许脱敏访问的资源开放。
- `execute` 只接受注册操作与受限参数，不接受任意 SQL、Python 或任意上游 URL。
- 身份信息通过网关会话传递，不由上述模型参数提供。
- 资源句柄不是授权凭据；每次调用都重新校验访问权，并绑定主体与资源版本。

- `list_resources` lists only resources visible to the current identity.
- `describe_resource` returns only approved names, modes, and available operations, without exposing actual paths, credentials, or data samples.
- `read_redacted` is available only for resources that permit redacted access.
- `execute` accepts only registered operations and constrained parameters, not arbitrary SQL, Python, or upstream URLs.
- Identity is conveyed through the gateway session, not through the model-supplied parameters above.
- Resource handles are not authorization credentials. Every call rechecks access rights and is bound to the principal and resource version.

示例 / Example:

```json
{
  "resource_id": "orders",
  "operation": "aggregate",
  "parameters": {
    "group_by": ["region"],
    "metrics": [{"field": "amount", "function": "sum"}]
  }
}
```

输出包含批准的结果及必要的发布说明，例如哪些分组因规则被抑制；不能以原始异常、调试输出或堆栈替代标准响应。

Outputs include approved results and any necessary release notes, such as which groups were suppressed by policy. Raw exceptions, debug output, or stack traces must not replace standard responses.

## 6. 安全边界与承诺 / Security Boundaries and Commitments

### 信任假设 / Trust Assumptions

- 信任宿主环境、网关、策略管理员和已审核的执行代码。
- 不信任模型提交的操作、参数，以及资源内容中可能携带的指令。
- 上游 API 是原始数据来源；网关控制从上游返回后向 Agent 披露的信息，不改变上游本身的数据可见性。

- The host environment, gateway, policy administrators, and reviewed execution code are trusted.
- Model-submitted operations and parameters, as well as instructions that may be embedded in resource content, are untrusted.
- Upstream APIs are sources of raw data. The gateway controls disclosure to the agent after receiving upstream responses; it does not change what the upstream service itself can see.

### 必须成立的部署条件 / Required Deployment Conditions

Agent 无法通过其他工具直接读取受保护文件或使用上游凭据。文件权限、挂载和凭据分配必须实际隔离这些访问路径；仅在提示词中要求“使用网关”不构成保护。

The agent must not be able to read protected files directly or use upstream credentials through other tools. File permissions, mounts, and credential allocation must enforce isolation of these access paths. Merely instructing the agent to “use the gateway” in a prompt is not a security control.

API 访问限制在适配器中；处理器默认不能访问网络。文件路径需要安全解析与打开，防止读取过程中绕过配置范围。

API access is confined to the adapters; processing components have no network access by default. File paths must be resolved and opened safely to prevent reads from escaping the configured boundaries.

### 第一版目标 / First-Version Goals

- 未授权主体不能访问资源。
- 整体隔离资源的原始内容不返回给 LLM。
- 字段保护资源只发布输出契约允许的信息。
- 请求、错误、日志及执行输出不能形成额外的原文返回通道。
- 策略失败、解析失败或输出校验失败时，拒绝发布。

- Unauthorized principals cannot access resources.
- Raw content from fully isolated resources is not returned to the LLM.
- Resources with field-level protection release only information permitted by their output contracts.
- Requests, errors, logs, and execution outputs must not create additional channels for returning raw content.
- Failures in policy enforcement, parsing, or output validation block release.

### 明确的限制 / Explicit Limitations

- 保护范围是已注册资源通过网关的访问；不自动保护用户粘贴到其他聊天窗口的内容，也不覆盖所有系统网络流量。
- 不声称抵御宿主机失陷、管理员恶意行为或全部侧信道。
- 脱敏不等于匿名化；聚合结果可能造成推断泄漏。最小群体阈值和查询限制不提供差分隐私保证。
- 不承诺隐藏函数实现后无法通过输入输出推测其行为。

- Protection covers access to registered resources through the gateway. It does not automatically protect content pasted into other chat windows or cover all network traffic on the system.
- The design does not claim protection against host compromise, malicious administrators, or all side channels.
- Redaction is not anonymization; aggregate results may enable inference. Minimum group thresholds and query restrictions do not provide differential privacy guarantees.
- Hiding a function’s implementation does not guarantee that its behavior cannot be inferred from inputs and outputs.

## 7. MVP 范围 / MVP Scope

| 纳入第一版 | 后续扩展 |
|---|---|
| 本地 CSV / JSON 文件 | PDF、Office 文档、任意自然语言文件 |
| 配置目录内的指定结构化文件 | 自动发现与分类所有文件 |
| 固定 HTTP API 的 JSON 响应 | 任意 API、流式响应、通用流量代理 |
| 字段白名单与删除 / 遮盖 | 自由文本语义识别、复杂可逆脱敏 |
| 计数、分组聚合等注册操作 | 任意 SQL / Python 执行 |
| 简单身份与资源权限 | 企业 SSO 和复杂组织权限 |
| 标准工具接口与审计 | 多 Agent 集成与管理界面 |

| Included in the first version | Future extensions |
|---|---|
| Local CSV / JSON files | PDFs, Office documents, and arbitrary natural-language files |
| Designated structured files within configured directories | Automatic discovery and classification of all files |
| JSON responses from fixed HTTP APIs | Arbitrary APIs, streaming responses, and a general-purpose traffic proxy |
| Field allowlists and removal / masking | Semantic detection in free text and advanced reversible redaction |
| Registered operations such as counts and grouped aggregations | Arbitrary SQL / Python execution |
| Basic identity and resource permissions | Enterprise SSO and complex organizational permissions |
| Standard tool interfaces and auditing | Multi-agent integrations and an administration UI |

开发顺序 / Development sequence:

1. 完成本地结构化文件的资源注册、策略校验与脱敏读取。
2. 增加隔离计算及独立的结果发布检查。
3. 增加固定 API 适配器，复用相同的策略与发布流程。
4. 接入一个 LLM Agent，完成跨场景演示和安全验证。

1. Implement resource registration, policy checks, and redacted reads for local structured files.
2. Add opaque processing and independent result release checks.
3. Add fixed API adapters that reuse the same policy and release flow.
4. Integrate an LLM agent and complete demonstrations across scenarios and security validation.

不先训练语义分类器；先确保明确配置的规则确实得到执行。

Prioritize reliable enforcement of explicitly configured rules before training a semantic classifier.

## 8. 验证与交付 / Validation and Deliverables

### 安全验证 / Security Validation

- 未授权资源访问、伪造身份、跨用户句柄使用。
- 路径越界、符号链接越界、未批准 API 地址与重定向。
- 未知字段、嵌套敏感字段、错误格式和上游结构变化。
- 原文出现在异常、日志、调试输出或内部函数返回值中的情况。
- 禁止操作、过大结果、小群体聚合和重叠查询推断案例。

- Unauthorized resource access, identity spoofing, and cross-user handle use.
- Path escapes, symlink escapes, and unapproved API addresses and redirects.
- Unknown fields, nested sensitive fields, malformed content, and upstream schema changes.
- Raw content appearing in exceptions, logs, debug output, or internal function return values.
- Prohibited operations, oversized results, small-group aggregations, and inference from overlapping queries.

先直接调用网关验证规则，再测试 LLM 完整流程，区分网关强制保护与模型自行拒绝。

First validate rules through direct gateway calls, then test the complete LLM workflow. Distinguish protection enforced by the gateway from refusals made by the model itself.

### 实用性验证 / Utility Validation

使用合成数据验证至少三个场景：本地表格分析、API 响应字段保护、内部函数调用。分别报告任务正确率、合法请求误拒绝率、违规信息发布率和延迟开销，并公开指标口径及失败案例。

Use synthetic data to validate at least three scenarios: local tabular data analysis, field protection in API responses, and internal function calls. Report task correctness, the false rejection rate for legitimate requests, the rate of policy-violating information releases, and latency overhead. Publish metric definitions and failure cases.

### 最小交付物 / Minimum Deliverables

- 可运行的网关与示例配置。
- 一个 Agent 接入示例。
- 三类场景的合成数据与演示。
- 策略和资源边界测试、对抗测试及结果报告。
- 明确说明保证范围与限制的 README。

- A runnable gateway with example configurations.
- An example agent integration.
- Synthetic data and demonstrations for the three scenario types.
- Policy and resource-boundary tests, adversarial tests, and a results report.
- A README that clearly states the scope of guarantees and limitations.

## 9. 后续需要确定的设计选择 / Design Decisions Still to Be Made

1. 首个接入协议：普通 HTTP 工具接口，或 MCP；核心策略逻辑保持独立。
2. 第一版支持的精确字段路径、数据类型和聚合操作。
3. 注册操作的隔离实现，以及 Agent 进程与数据目录的权限划分。
4. 允许发布的聚合结果、筛选组合和跨请求限制。

1. Initial integration protocol: a conventional HTTP tool interface or MCP, with core policy logic kept independent.
2. The precise field paths, data types, and aggregation operations supported in the first version.
3. The isolation mechanism for registered operations, and the permission separation between the agent process and data directories.
4. Permitted aggregate releases, filter combinations, and cross-request restrictions.

这些是下一轮设计决策，不阻碍当前确定项目边界。

These decisions belong to the next design iteration and do not prevent defining the project’s boundaries now.
