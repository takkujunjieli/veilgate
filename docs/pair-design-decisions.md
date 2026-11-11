# VeilGate — Pair Design 决策记录 / Pair Design Decision Log

本文只记录共同设计中的决定与未决问题，不表示对应功能已实现或通过验证。

This document records collaborative design decisions and open questions. It does not imply that the corresponding functionality has been implemented or validated.

## D001：原始内容的信任边界 / Trust Boundary for Raw Content

状态：**用户已选择 B：在资源返回给 Agent 前限制内容。**

Status: **The user selected option B: restrict content before returning it to the agent.**

### 已确定的约束 / Agreed Constraints

- 原始敏感内容在 VeilGate 的可信处理范围内使用，不交给 Agent 程序及其外部 LLM。
- VeilGate 不具备或调用 LLM 能力，包括不把原文交给另一个模型做脱敏判断或总结。
- Agent 可以提出处理请求，但只能获得批准的信息或派生结果。
- 这一边界不改变原始文件存储方或上游 API 本身的数据可见性。
- 工具开放方式已在 D003 中确定；具体接口、发布条件和部署隔离仍需细化。

- Raw sensitive content is used within VeilGate’s trusted processing scope, not given to the agent program or its external LLM.
- VeilGate neither contains nor invokes an LLM, including sending raw content to another model for redaction decisions or summarization.
- The agent may request processing but receives only approved information or derived results.
- This boundary does not change the visibility of the original file storage or upstream API provider.
- The tool exposure approach is agreed in D003; concrete interfaces, release conditions, and deployment isolation still require refinement.

### 用户的理由 / User’s Rationale

Agent 能调度 LLM 并组织后续操作，若它同时持有原始数据，其一次错误就可能扩大为敏感内容披露。因此希望把原始数据限制在 VeilGate 内。

The agent can orchestrate LLM calls and subsequent actions. If it also holds raw data, a single mistake may cause sensitive disclosure. The user therefore wants raw data confined to VeilGate.

### 需要保留的限制 / Important Limitations

- 将原始数据移出 Agent 的可见范围，不会消除 VeilGate 自身的失败风险。处理和发布规则仍需验证。
- VeilGate 没有 LLM，不代表它不能计算、筛选或转换数据；但无法自动满足所有需要理解敏感原文的语义任务。
- 若后续允许执行模型提出的表达式或代码，这些内容仍是不可信请求；它们产生的结果不能自动视为允许披露。

- Removing raw data from the agent’s view does not eliminate failures within VeilGate. Processing and release rules still need validation.
- Having no LLM does not prevent VeilGate from computing, filtering, or transforming data, but it cannot automatically support every semantic task requiring understanding of confidential source content.
- If model-proposed expressions or code are allowed later, they remain untrusted requests; their outputs are not automatically approved for disclosure.

## D002：先完成网关 MVP，暂缓 CaMeL 扩展 / Complete the Gateway MVP Before CaMeL Extensions

日期：2026-11-10。状态：**用户已确认先完成既定网关 MVP；上一轮讨论中第 9 点的 CaMeL／信息流扩展留待之后讨论。**

Date: 2026-11-10. Status: **The user confirmed completing the agreed gateway MVP first and deferring the CaMeL / information-flow extension discussed in point 9 of the preceding conversation.**

VeilGate 定位为面向 AI Agent 的工具访问与隐私治理网关。资源所有者集中配置访问与披露规则，多个 Agent 通过统一入口使用获准工具，获得允许返回的信息或结果。网关执行通用治理；已接入的可信工具可以负责业务计算。注册工具本身不构成对其可信性的证明。

VeilGate is a tool-access and privacy-governance gateway for AI agents. Resource owners centrally configure access and disclosure rules; multiple agents use approved tools through a common entry point and receive only permitted information or results. The gateway enforces shared governance; integrated trusted tools may perform business computation. Registration alone does not establish a tool's trustworthiness.

本轮保留本地文件与 API 两类来源、案例 A/B、真实 Agent 演示及全过程模型请求检查。VeilGate 不调用 LLM，Agent 及其模型不能接触受保护原文。原始数据源和经明确授权的可信处理工具属于需要审查的信任范围，不能把“只有 VeilGate 可见”理解为原始数据源也不可见。

This iteration retains both local files and APIs, scenarios A/B, real-agent demonstrations, and inspection of model requests throughout each task. VeilGate does not invoke an LLM, and the agent and its model must not receive protected raw content. Original sources and explicitly authorized trusted processing tools are part of the trust scope to review; “visible only to VeilGate” does not exclude the original source itself.

本轮不增加 CaMeL 式 Agent 执行运行时、通用变量依赖与隐式控制流跟踪，也不把独立 monitor 项目并入 MVP。不继承 CaMeL 的安全结论。批准汇总的具体发布条件仍是现有案例 A 必须解决的需求，不能随信息流扩展一起推迟。

This iteration does not add a CaMeL-style agent execution runtime, general variable-dependency or implicit-control-flow tracking, or the separate monitor project. It does not inherit CaMeL's security conclusions. Release conditions for approved aggregates remain necessary for scenario A and are not deferred with the information-flow extension.

继续遵守 pair system design：逐项比较方案、讨论取舍、记录决定后实施。本次范围决定不表示具体接口、计算方式或运行环境已经选定，也不表示 MVP 已完成。

Continue pair system design: compare alternatives, discuss trade-offs, and record each decision before implementing it. This scope decision does not select concrete interfaces, computation mechanisms, or deployment environments, and does not imply that the MVP is complete.

## D003：受限工具接口与可复用计算 / Constrained Tool Interfaces and Reusable Computation

日期：2026-11-10。状态：**用户已确认采用此设计。具体接口和聚合发布条件尚未定稿。**

Date: 2026-11-10. Status: **The user approved this design. Concrete interfaces and aggregate release conditions are not yet finalized.**

### 已确定的职责 / Agreed Responsibilities

| 职责 / Responsibility | 决定 / Decision |
|---|---|
| Agent 接口 / Agent interface | 提供已注册、参数受限的工具；MVP 不向 Agent 开放任意查询表达式或生成代码执行。 / Expose registered tools with constrained parameters; the MVP does not expose arbitrary query expressions or generated-code execution to agents. |
| 资源所有者 / Resource owner | 配置资源、调用权限、允许的参数范围及结果披露规则。 / Configure resources, caller permissions, permitted parameter ranges, and result-disclosure rules. |
| 网关 / Gateway | 验证身份、工具权限和参数授权；在结果满足发布规则后才向 Agent 返回。参数结构合法不等于获得授权。 / Verify identity, tool permissions, and argument authorization; return results only when release rules are satisfied. Structurally valid arguments are not necessarily authorized. |
| 可信工具与计算组件 / Trusted tools and computation components | 已有 API 保留其业务实现；本地计算复用筛选、分组、计数、求和等组件，由可信配置限定组合。 / Existing APIs retain their business implementation; local computation reuses filtering, grouping, counting, and summation components whose composition is constrained by trusted configuration. |

例如，Agent 可以调用月度地区统计工具，但不能自行改为按客户分组。工具内部可以复用通用聚合组件；接入同类资源应复用这些组件与共同治理逻辑，而不为每个 Agent 重写隐私处理。示例名称与参数格式不构成最终接口契约。

For example, an agent may invoke a monthly regional summary tool but cannot independently change the grouping to customers. The tool may reuse general aggregation components internally; similar resources should reuse these components and shared governance rather than reimplement privacy processing for each agent. Example names and argument formats are not final interface contracts.

### 取舍与验证方向 / Trade-offs and Validation Direction

选择受限工具接口，是为了让调用权限、参数范围和输出边界可明确验证。代价是新增计算需求可能需要新增或调整工具配置，超出已有组件能力时仍需开发。通用性来自内部复用，不要求 Agent 获得任意组合权限。

Constrained tool interfaces make caller permissions, argument ranges, and output boundaries explicit and testable. New computation needs may require new or revised tool configuration, and capabilities beyond existing components still require development. Generality comes from internal reuse, without requiring arbitrary agent-controlled composition.

后续测试应覆盖批准调用的正确结果、未经授权的参数与分组被拒绝、错误路径不返回原文，以及多个 Agent 复用相同规则。工具 schema、提示词描述或工具注册本身都不能替代运行时授权与发布检查。

Subsequent tests should cover correct approved results, denial of unauthorized arguments and groupings, error paths that do not return raw content, and shared rules across agents. Tool schemas, prompt descriptions, and registration do not replace runtime authorization and release checks.

## D004：聚合报告整体发布或整体拒绝 / All-or-Nothing Aggregate Report Release

日期：2026-11-10。状态：**用户选择 A：任一分组不满足发布条件，拒绝整份报告。** 此决定适用于案例 A 的聚合报告，不意味着 API 案例 B 的全部处理方式已确定。

Date: 2026-11-10. Status: **The user selected A: reject the entire report if any group fails the release conditions.** This applies to scenario A's aggregate report; it does not determine all processing behavior for API scenario B.

用户理由：恶意调用者可能反复探测边界情况。整体拒绝可减少部分结果被组合利用的机会，也避免把不完整报告当作完整地区比较。代价是一个不满足条件的分组会阻止其他合格分组的结果发布。

User rationale: malicious callers may repeatedly probe edge cases. Whole-report denial reduces opportunities to combine partial results and avoids presenting an incomplete report as a complete regional comparison. The cost is that one failing group prevents release of otherwise eligible groups.

实现时必须先完成全部分组的发布检查，再返回报告；失败时不返回部分分组、部分总额或从这些结果计算的排名。测试应覆盖失败分组位于处理顺序末尾的情况，确保此前计算出的合格结果没有提前发出。

The implementation must check release conditions for all groups before returning the report. On failure, it must not return partial groups, partial totals, or rankings derived from them. Tests should include a failing group processed last to ensure previously computed eligible results were not emitted early.

此选择不消除反复查询的风险：成功与拒绝本身可透露条件是否满足；变化的数据版本或重叠查询的结果也可能被作差。具体发布门槛及计量单位、拒绝响应的细节、数据版本和重复查询约束仍需共同确定。不得将整体拒绝等同于推断攻击防护证明。

This choice does not eliminate repeated-query risks: success or denial can reveal whether conditions hold, and results from changing data versions or overlapping queries can be differenced. Release thresholds and counting units, denial-response details, data versions, and repeated-query constraints still require joint decisions. Whole-report denial is not a proof against inference attacks.

## D005：本地月度报告采用固定快照 / Fixed Snapshots for Local Monthly Reports

日期：2026-11-10。状态：**用户选择 A：本地月度报告先使用固定、经批准的数据快照。缓存与实际读取方式留待具体场景讨论。**

Date: 2026-11-10. Status: **The user selected A: use a fixed, approved data snapshot for local monthly reports. Caching and physical read mechanisms are deferred until concrete scenarios are discussed.**

快照限定的是数据版本，不等于必须使用缓存。同一报告在相同快照、参数和规则版本下应产生一致的业务结果；读取缓存或重新读取该快照都可以满足这一语义，但不得在源文件更新后静默改用最新数据。快照如何标识、保存及验证完整性尚未选定。

A snapshot fixes the data version; it does not require caching. The same report under the same snapshot, arguments, and policy version should produce consistent business results. Reading a cache or rereading that snapshot can both satisfy this semantic requirement, but source updates must not silently switch the report to newer data. Snapshot identification, storage, and integrity verification mechanisms remain undecided.

本决定仅针对案例 A，不自动要求案例 B 的 API 订单状态采用快照。新快照的批准发布及新旧结果组合的风险需单独讨论；固定快照本身不证明所有统计推断都被阻止。身份和授权仍须逐次检查，不能因复用数据或结果而跳过。

This decision applies only to scenario A and does not automatically require snapshot-based API order status in scenario B. Approval of new snapshots and risks from combining old and new results need separate discussion; a fixed snapshot does not prove protection against all statistical inference. Identity and authorization must still be checked on every call, even when data or results are reused.

后续验证应覆盖：重复查询的业务结果一致、源数据变化不会静默改变已批准报告，以及规则或权限变更后仍按当前生效规则授权。此处记录预期行为，不表示快照能力已实现。

Future validation should cover consistent business results across repeated calls, source changes not silently changing an approved report, and authorization under currently effective rules after policy or permission changes. These are expected behaviors, not claims of an implemented snapshot capability.

## D006：优先建设通用网关能力 / Prioritize General Gateway Capabilities

日期：2026-11-10。状态：**用户明确当前没有具体业务，先完成 Gateway 的基本功能，再在相关系统设计问题上结合研究进行创新与拓展。**

Date: 2026-11-10. Status: **The user clarified that there is no concrete business domain yet: complete the gateway's basic capabilities first, then use relevant research to inform innovation and extensions in system design.**

不再以订单条数、客户数或业务发布阈值的选择作为通用网关设计的前置条件。网关负责表达并强制执行资源所有者明确配置的规则，不代替所有者制定普遍适用的业务隐私标准。示例验收仍需明确规则与预期结果，但这些属于测试配置，不成为产品内置的业务定义。

Choices about order counts, customer counts, or business release thresholds are no longer prerequisites for general gateway design. The gateway represents and enforces rules explicitly configured by resource owners; it does not define universal business privacy standards on their behalf. Demonstrations still need explicit rules and expected outcomes, but these are test configurations rather than built-in business definitions.

近期设计与实现围绕工具注册、统一调用、身份与参数授权、本地及 API 适配、结果披露、错误处理和审计展开。继续验证多个 Agent 复用规则、同类资源接入无需重写核心治理，以及真实模型请求中没有受保护原文。

Near-term design and implementation focus on tool registration, unified invocation, identity and argument authorization, local and API adapters, result disclosure, error handling, and auditing. Validation continues to cover shared rules across agents, onboarding supported resources without rewriting core governance, and absence of protected raw content from actual model requests.

D004 的整体拒绝和 D005 的固定快照保留为当前本地聚合演示的决定，不扩展为所有工具的统一业务要求。原有两个验收案例保留为平台能力的验证载体；具体业务条件不继续作为逐项提问的主线。

D004's whole-report denial and D005's fixed snapshot remain decisions for the current local aggregation demonstration, not universal business requirements for every tool. The two existing acceptance scenarios remain vehicles for validating platform capabilities; detailed business conditions are no longer the main sequence of design questions.

继续采用 pair system design，但重点转向职责与接口、信任边界、策略执行位置和可扩展性等工程取舍。研究扩展需分别说明来源、相对基础实现的变化、可测试假设及成本；D002 暂缓完整 CaMeL 扩展的决定不变。

Continue pair system design, focusing on engineering trade-offs such as responsibilities and interfaces, trust boundaries, policy enforcement placement, and extensibility. Research extensions must identify their sources, changes relative to the baseline, testable hypotheses, and costs. D002's deferral of a full CaMeL extension remains in effect.
