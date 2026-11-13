# VeilGate MVP — 目标与需求对齐 / Goals and Requirements Alignment

状态：**核心功能目标已对齐，已进入 pair system design。先完成已确认的网关 MVP；CaMeL／信息流扩展留待之后讨论。验收细则与具体设计仍需逐项明确，尚未完成本轮 MVP 验收。**

Status: **Core functional goals agreed; pair system design is underway. Complete the agreed gateway MVP first; defer CaMeL / information-flow extensions. Detailed acceptance conditions and design decisions still require clarification; this iteration has not passed MVP acceptance.**

版本：v0.6 · 2026-11-10

Version: v0.6 · 2026-11-10

本文只定义为什么做、为谁做、需要具备什么行为，以及怎样判断完成。架构、技术栈、接口、算法、部署方式和实现方案留到后续 pair system design。

This document defines why the project exists, whom it serves, the behavior it must provide, and how completion will be assessed. Architecture, technology choices, interfaces, algorithms, deployment approaches, and implementation decisions are reserved for subsequent pair system design.

本轮执行进展：通用工具发现与调用、有限参数授权、本地快照聚合和 HTTPS API 适配已实现并完成本地测试。真实模型端到端验收、外部 API 联调和容器隔离验证尚未完成。详见 [实现与验证记录](gateway-mvp-validation.md)。

Implementation progress: general tool discovery/invocation, finite argument authorization, local snapshot aggregation, and HTTPS API adaptation are implemented and locally tested. Real-model acceptance, external API integration, and container-isolation validation remain pending. See the [implementation and validation record](gateway-mvp-validation.md).

## 1. 一句话目标 / One-Sentence Goal

**产品定位：VeilGate 是面向 AI Agent 的工具访问与隐私治理网关。资源所有者集中配置访问与披露规则，多个 Agent 通过统一入口使用获准工具，获得允许返回的信息或结果。**

**Product positioning: VeilGate is a tool-access and privacy-governance gateway for AI agents. Resource owners centrally configure access and disclosure rules; multiple agents use approved tools through a common entry point and receive permitted information or results.**

**让用户可以指定本地或 API 来源的敏感内容，并让 AI Agent 在不向外部 LLM 披露这些受保护内容的前提下，完成约定范围内的有用任务。**

**Allow users to designate sensitive content from local or API sources, and enable an AI agent to complete useful tasks within an agreed scope without disclosing that protected content to an external LLM.**

“有用”和“受保护”必须同时成立：全部拒绝不是成功，完成任务但泄漏敏感内容也不是成功。

Both utility and protection are required: rejecting everything is not success, and completing a task while disclosing protected content is not success either.

## 2. 已明确的项目意图 / Established Project Intent

- 项目是通用的隐私资源保护能力，不限定为薪资、客户分析或其他单一业务。
- 用户指定敏感位置与内容；**本地文件和 API 返回内容都必须纳入本轮 MVP 验收。**
- **本轮必须由真实 Agent 完成端到端任务，并展示敏感内容没有进入实际模型请求。**
- 用户已接受案例 A/B 及其保护与披露边界：本地明细保密但允许批准的统计结果；API 响应保护敏感部分、保留批准的业务信息。
- 两例使用合成数据，分别验收；第一版不要求跨来源联合分析。
- 关注访问与披露是否符合用户设定的规则，不判断 Agent 的动机或任务偏离。行为监控是独立项目。
- 先对齐目标与需求，再共同设计，之后才实施。
- 实施过程同时用于培养用户的工程判断力，不能由助手独自完成所有设计选择。

- The project provides general-purpose protection for private resources, rather than targeting payroll, customer analytics, or another single business domain.
- Users designate sensitive locations and content. **Both local files and API responses are mandatory for acceptance in this MVP iteration.**
- **This iteration requires a real agent to complete end-to-end tasks, with evidence that protected content did not enter actual model requests.**
- The user has accepted scenarios A/B and their protection and disclosure boundaries: confidential local records with approved statistics, and protected sensitive portions of API responses with approved operational information retained.
- Both scenarios use synthetic data and are accepted separately; cross-source analysis is not required in the first version.
- The project focuses on whether access and disclosure comply with user-defined rules. Inferring agent intent or detecting task deviation belongs to a separate monitoring project.
- Goals and requirements are agreed first, followed by collaborative design and then implementation.
- The work also develops the user’s engineering judgment; the assistant must not make every design decision independently.

仓库中已有初步实现和历史验证记录。它们是后续评估的素材，不是本轮需求已确认的证据；本文不据此宣布任何验收项已通过，也不预设必须沿用或重写。

The repository contains an initial implementation and historical validation records. These are inputs for later assessment, not evidence that the requirements for this iteration have been agreed. This document declares no acceptance criterion passed and does not predetermine reuse or replacement.

## 3. 用户与要解决的问题 / Users and the Problem

**主要使用者：**希望让 Agent 使用私有资源完成任务、但不愿把原始敏感内容发送给外部模型的个人或团队。第一版不要求使用者具备传统安全专业知识。

**Primary users:** Individuals or teams who want an agent to use private resources for useful work without sending the original sensitive content to an external model. The first version should not require traditional security expertise from its users.

**资源管理者：**有权决定某份资源如何使用、什么内容允许披露的人。MVP 中可以与主要使用者是同一个人；并不因此把同等权限授予 Agent。

**Resource owner or administrator:** A person authorized to decide how a resource may be used and what may be disclosed. This may be the same person as the primary user in the MVP; that does not grant equivalent authority to the agent.

**核心痛点：**有权在本地使用数据，不代表愿意或有权把数据发给外部 LLM。仅拒绝访问又会使 Agent 无法完成原本有价值的工作。

**Core problem:** Permission to use data locally does not imply willingness or permission to send it to an external LLM. Simply denying access may prevent the agent from doing useful work.

## 4. 本轮功能目标 / Functional Objectives for This Iteration

2026-11-10 范围澄清：优先完成通用 Gateway 能力；案例 A/B 用于验证平台，不把具体业务发布阈值作为网关设计的前置条件。规则仍需由资源所有者明确配置，演示使用明确的测试规则；不将测试规则宣传为普遍隐私保证。详见决策记录 D006。

Scope clarification, 2026-11-10: prioritize general gateway capabilities. Scenarios A/B validate the platform; business-specific release thresholds are not prerequisites for gateway design. Resource owners must still configure explicit rules, and demonstrations use explicit test policies; test policies are not universal privacy guarantees. See decision D006.

以下目标以第 6 节已确认的两个案例为本轮必需范围。具体测试输入、预期结果和执行约束仍需补齐，不据此扩大支持的任务范围。

The two confirmed scenarios in Section 6 define the required scope of these objectives for this iteration. Concrete test inputs, expected results, and execution constraints still need to be specified; these objectives do not expand the supported task scope.

| ID | 中文目标 | English objective |
|---|---|---|
| G1 | 用户能明确指定受保护资源、敏感范围和允许披露的内容，理解配置后的效果。 | Users can designate protected resources, sensitivity scope, and permitted disclosures, and understand the resulting behavior. |
| G2 | Agent 能利用允许的信息或结果完成事先约定的正常任务。 | The agent can complete agreed legitimate tasks using permitted information or results. |
| G3 | 即使 Agent 提出违规请求，受保护内容也不会通过声明覆盖的路径被披露。 | Protected content is not disclosed through paths within the stated coverage, even when the agent submits prohibited requests. |
| G4 | 能提供可检查的证据，区分成功保护、合法拒绝、任务失败与保护失败。 | Inspectable evidence distinguishes successful protection, legitimate denial, task failure, and protection failure. |
| G5 | 用不同资源和场景验证通用性，而不要求第一版支持所有格式和所有任务。 | Generality is demonstrated across resources and scenarios without requiring support for every format or task. |
| G6 | 多个 Agent 复用集中规则；同类资源接入不重写核心治理逻辑；规则变更按明确的生效机制一致执行。 | Multiple agents reuse central rules; supported resources can be onboarded without rewriting core governance; policy changes apply consistently under defined activation semantics. |

“位置”回答保护什么来源；“敏感范围”回答保护全部内容还是指定部分；“允许披露”回答哪些信息可以给模型。三者都属于需求，不能只指定位置就默认其余含义。

A location identifies the source to protect; sensitivity scope determines whether all or only part of its content is protected; permitted disclosure defines what the model may receive. All three are requirements. Specifying a location alone does not resolve the others.

## 5. 用户可观察的需求 / User-Observable Requirements

| ID | 中文需求 | English requirement |
|---|---|---|
| R1 | 用户可以表达整份内容保密或部分内容保密，系统不会默默扩大可披露范围。 | Users can designate entire content or selected portions as confidential; the system must not silently broaden permitted disclosure. |
| R2 | 允许使用资源与允许把内容交给模型是两个独立的授权问题。 | Permission to use a resource and permission to disclose its content to a model are distinct authorization questions. |
| R3 | 受保护内容确实不出现在发往外部模型的请求中；不能只检查最终回答是否出现秘密。 | Protected content must be absent from requests sent to the external model; checking only the final answer is insufficient. |
| R4 | 对整体保密的内容，可以明确允许特定派生结果；不因此默认允许任何摘要或计算结果。 | Specific derived results may be approved for wholly confidential content; this does not implicitly approve every summary or computation result. |
| R5 | Agent 的说辞、角色声明或忽略规则的请求不能改变资源所有者的授权决定。 | Agent claims, asserted roles, or requests to ignore rules cannot change the resource owner’s authorization decisions. |
| R6 | 无法确定是否允许披露时，不发布有争议的内容，并给出不泄漏秘密的结果说明。 | When disclosure cannot be established as permitted, disputed content is withheld and a non-sensitive explanation is provided. |
| R7 | 源内容变化、处理失败或异常信息不能导致敏感内容意外发布。 | Source changes, processing failures, or error information must not cause accidental disclosure of protected content. |
| R8 | 对已支持的任务，结果应正确且有用；不能通过编造结果来掩盖拒绝或失败。 | Results for supported tasks must be correct and useful; fabricated results must not conceal denials or failures. |
| R9 | 第一版主要依靠明确的用户指定来确定保护范围，不承诺自动发现所有隐私。 | The first version primarily relies on explicit user designation of what to protect; it does not promise automatic discovery of all private information. |

本轮资源来源、代表任务和披露边界已确认，见第 6 节。具体支持的数据形态和验收细则仍需明确。以上是行为要求，不指定实现方法。

Resource sources, representative tasks, and disclosure boundaries are confirmed in Section 6. Specific supported data forms and detailed acceptance conditions still need to be defined. These are behavioral requirements, not implementation prescriptions.

## 6. 已确认的验收场景 / Confirmed Acceptance Scenarios

用户已接受以下两个互补场景及其披露边界，作为本轮 MVP 的功能验收目标。两例均使用合成数据和真实 Agent，检验同一项通用隐私保护能力，不将产品限定为订单分析工具。确认案例不等于已经通过验收，也不代表已选择实现方案。

The user has accepted the following two complementary scenarios and their disclosure boundaries as functional acceptance goals for this MVP. Both use synthetic data and a real agent to exercise the same general-purpose privacy capability; they do not define the product as an order analytics tool. Acceptance of the scenarios does not mean validation has passed or an implementation approach has been selected.

### A. 本地文件：明细保密，允许统计结果 / Local File: Confidential Records, Approved Statistics

**用户任务：**“根据这份本地订单文件，比较上个月各地区的订单量和销售总额，指出销售总额最高的地区。”

**User task:** “Using this local order file, compare last month’s order counts and total sales by region, and identify the region with the highest total sales.”

| 项目 / Item | 已确认需求 / Confirmed requirement |
|---|---|
| 来源 / Source | 本地订单文件，含客户姓名、联系方式、地区、日期和订单金额。 / A local order file containing customer names, contact details, regions, dates, and order amounts. |
| 保护范围 / Protected content | 所有逐笔明细，包括客户身份、联系方式和单笔订单金额；模型不得收到原始文件或明细样例。 / All individual records, including customer identity, contact details, and individual order amounts; the model must not receive the raw file or sample records. |
| 允许披露 / Permitted disclosure | 资源所有者批准的固定月份、地区分组下的地区名称、订单数和销售总额。 / Region names, order counts, and total sales for the fixed month and regional groups approved by the resource owner. |
| 成功结果 / Successful outcome | Agent 正确比较这些汇总指标并指出最高地区；实际模型请求只包含允许的信息。 / The agent correctly compares these aggregate metrics and identifies the leading region; actual model requests contain only permitted information. |
| 必须拒绝 / Required denial | 请求逐笔导出、客户联系方式、单笔金额，或批准范围外的进一步细分；不能通过换一种表述获得同样的禁止内容。 / Requests for individual records, customer contact details, individual amounts, or further breakdowns outside the approved scope; rephrasing must not permit the same prohibited disclosure. |

此案例要求第一版具有“原始内容不进入模型，也能完成约定计算”的能力。只删除姓名和邮箱、然后把全部订单金额交给模型，不算通过。

This scenario requires the first version to support the agreed computation without placing raw content in the model context. Removing names and emails while sending every individual order amount to the model does not satisfy it.

本案例仅允许明确批准的汇总，不承诺任意统计查询都安全。若批准分组可能暴露个人信息，需要先调整发布要求；详细条件将在验收任务定稿前明确。

Only explicitly approved aggregates are permitted; this does not claim that arbitrary statistical queries are safe. If an approved group could expose personal information, release requirements must first be revised. Detailed conditions will be specified before acceptance tasks are finalized.

### B. API 响应：保护敏感部分，保留业务可用信息 / API Response: Protect Sensitive Portions, Preserve Useful Information

**用户任务：**“查看订单服务，列出本周预计发货、但目前仍未发货的订单，给出订单编号、当前状态和预计发货日期。”

**User task:** “Check the order service and list orders scheduled to ship this week that have not yet shipped, including the order reference, current status, and expected shipping date.”

| 项目 / Item | 已确认需求 / Confirmed requirement |
|---|---|
| 来源 / Source | API 返回的订单数据，包含业务状态和客户姓名、电话、地址及内部备注。 / Order data returned by an API, containing operational status alongside customer names, phone numbers, addresses, and internal notes. |
| 保护范围 / Protected content | 客户姓名、电话、地址、内部备注，不因其出现在不同层级或错误信息中而变为可披露。 / Customer names, phone numbers, addresses, and internal notes, even when they appear at different nesting levels or in error information. |
| 允许披露 / Permitted disclosure | 明确批准的订单编号、状态和预计发货日期；订单编号在此案例中明确允许，不代表其他场景也允许。 / Explicitly approved order references, statuses, and expected shipping dates; order references are specifically permitted here, not universally. |
| 成功结果 / Successful outcome | Agent 根据允许的信息正确筛选和列出订单；实际模型请求不含上述受保护内容。 / The agent correctly selects and lists orders using permitted information; actual model requests contain none of the protected content above. |
| 必须拒绝或安全失败 / Required denial or safe failure | 请求补充客户电话、地址或备注时不披露；上游返回异常或无法确定新增内容是否可披露时，不泄漏也不编造正常结果。 / Do not disclose customer phone numbers, addresses, or notes when requested; upstream failures or uncertainty about newly added content must not cause leakage or fabricated successful results. |

“本周”及“上个月”会在验收案例中使用固定参考日期，避免时间变化使预期结果漂移。两个案例需分别验收；第一版不默认要求跨本地文件和 API 联合分析。

“This week” and “last month” will use fixed reference dates in acceptance cases so expected outcomes do not drift over time. Each scenario is accepted separately; joining local-file and API data is not proposed as a first-version requirement.

两例的共同拒绝规则：Agent 要求忽略隐私限制或以排查问题为由索要原文时，不能扩大披露范围。这里验收的是违规请求后的可观察结果，不要求判断 Agent 的意图。

Shared denial requirement: requests to ignore privacy restrictions or obtain raw content for debugging must not broaden disclosure. Acceptance concerns observable outcomes of prohibited requests, not inference of agent intent.

## 7. 验收原则与证据 / Acceptance Principles and Evidence

必需任务和禁止披露的信息已在第 6 节确认。下一步需明确具体测试输入、预期结果及剩余验收条件。尚未执行本轮实验，不填写虚构的提升比例或安全结论。

Required tasks and prohibited disclosures are confirmed in Section 6. Concrete test inputs, expected outcomes, and remaining acceptance conditions must be specified next. No experiments have been run for this iteration, so no improvement percentages or safety conclusions are asserted.

| 维度 / Dimension | 候选验收要求 / Proposed acceptance requirement |
|---|---|
| 正常任务 / Legitimate tasks | 所有双方确认的必需场景得到正确结果；不要求支持任意用户问题。 / Every mutually agreed required scenario produces the correct result; arbitrary user questions need not be supported. |
| 隐私保护 / Privacy protection | 约定测试中，不允许存在已知且未修复的禁止内容披露。有限测试通过不等于普遍安全证明。 / No known, unresolved disclosure of prohibited content is accepted in the agreed tests. Passing a finite suite is not a universal security proof. |
| 实际模型输入 / Actual model input | 已确认必需：两类来源均需真实 Agent 端到端演示，覆盖任务全过程发给模型的实际内容，确认保护发生在发送前；只展示最终回答或某一轮请求不够。 / Confirmed requirement: both source types need real-agent end-to-end demonstrations, covering actual model-bound content throughout the task to verify protection before transmission; the final answer or a single request alone is insufficient. |
| 违规请求 / Prohibited requests | 不能把模型自行拒绝算作保护机制有效的证据；必须验证违规请求实际到达保护边界后的结果。 / A model’s voluntary refusal is not evidence that protection works; assess prohibited requests that actually reach the protection boundary. |
| 误拒绝 / False rejection | 单独记录允许任务被拒绝的情况，不将一律拒绝当作高安全性。 / Record rejected legitimate tasks separately; blanket denial is not treated as strong security. |
| 异常路径 / Failure paths | 对选定的内容变化与处理错误，既不泄漏，也不伪装成功。 / Selected source changes and processing failures neither disclose protected content nor masquerade as success. |
| 开销 / Overhead | 记录额外耗时与使用成本；是否设置硬性上限，待使用场景和预算确认。 / Record added latency and usage cost; hard limits depend on the agreed usage scenario and budget. |
| 可复现性 / Reproducibility | 另一个开发者可以使用合成数据复现演示、失败案例和结果。 / Another developer can reproduce demonstrations, failure cases, and results using synthetic data. |

验收报告应区分“已验证”“未验证”和“明确不覆盖”。隐私错误与普通任务错误分别报告，不合并成一个平均分数。

The acceptance report must distinguish verified behavior, unverified behavior, and explicit exclusions. Privacy failures and ordinary task errors are reported separately rather than merged into one average score.

## 8. 第一版不承诺什么 / What the First Version Does Not Promise

- 通用 Agent 行为监控、动机识别或完整的 prompt injection 检测。
- 任意数据格式、任意任务、任意内部代码都能安全交给 Agent 使用。
- 自动识别所有敏感信息，或证明所有派生结果都无法用于隐私推断。
- 对用户手动粘贴到其他应用的数据、所有系统流量、已失陷的宿主环境提供全面保护。
- 在未明确覆盖条件与证据前声称不可绕过、生产就绪或满足某项合规认证。

- General-purpose agent behavior monitoring, intent inference, or complete prompt-injection detection.
- Safe agent use of every data format, every task, or arbitrary proprietary code.
- Automatic recognition of all sensitive information, or proof that no derived result can support private inference.
- Comprehensive protection for data manually pasted into other applications, all system traffic, or a compromised host environment.
- Claims of unbypassability, production readiness, or compliance certification without defined coverage conditions and evidence.

支持的使用环境必须能满足保护承诺；不能在已知存在直读旁路的演示中宣称完成隐私隔离。如何满足这一要求留到系统设计讨论。

The supported usage environment must make the protection commitments achievable. A demonstration with a known direct-access bypass cannot be presented as completed privacy isolation. How to meet this requirement is reserved for system design.

## 9. 学习与协作约定 / Learning and Collaboration Agreement

**培养目标：**能从需求出发识别约束，区分安全保证与假设，比较方案，解释取舍，设计能推翻错误假设的验证，并根据证据修正判断。

**Learning objective:** Learn to derive constraints from requirements, distinguish guarantees from assumptions, compare alternatives, explain trade-offs, design checks that can falsify mistaken assumptions, and revise judgments based on evidence.

后续每个重要设计决策采用以下节奏：

For each significant design decision, follow this sequence:

1. 助手提出具体问题、已有约束和必要概念，不先替用户作结论。
2. 给出少量可比较方案及其优缺点，不把某个选项包装成唯一合理答案。
3. 用户选择方案，并说明理由、关键假设、可能失败的情况，以及会怎样验证。
4. 助手评审推理，指出遗漏与风险，再给出自己的建议和理由。
5. 双方记录决定、接受的代价与需要重新考虑的条件；对齐后再进入实现。

1. The assistant presents the concrete question, established constraints, and necessary concepts without deciding for the user first.
2. Present a small set of comparable alternatives with advantages and disadvantages, without framing one as the only reasonable answer.
3. The user chooses and explains the reasoning, key assumptions, possible failures, and how the choice would be validated.
4. The assistant reviews the reasoning, identifies omissions and risks, and then gives a recommendation with its rationale.
5. Record the agreed decision, accepted costs, and conditions for revisiting it; implementation follows agreement.

判断标准是推理质量和需求满足程度，不是是否猜中助手的答案。安全关键约束可以有必须遵守的底线，其余取舍允许存在多种合理选择。用户可以要求提示、示例或更小的问题，不需要先掌握全部安全知识。

Assessment is based on reasoning quality and satisfaction of requirements, not on guessing the assistant’s answer. Security-critical constraints may impose mandatory requirements; other trade-offs can have several reasonable solutions. The user may request hints, examples, or smaller questions without first mastering all of security engineering.

## 10. 对齐记录与待确认项 / Alignment Record and Open Questions

| ID | 待确认问题 / Question | 当前状态 / Status |
|---|---|---|
| Q1 | 本轮是否必须同时支持本地资源与 API 返回内容，还是允许分阶段验收？ / Must this iteration support both local resources and API responses, or may acceptance be phased? | **已确认：两种来源均为本轮必需。** / **Confirmed: both sources are required in this iteration.** |
| Q2 | 本轮是否必须完成真实 Agent 的端到端演示，还是先验收独立保护能力？ / Is a real-agent end-to-end demonstration required now, or is standalone protection sufficient for this iteration? | **已确认：真实 Agent 完成任务，并展示敏感内容未进入模型请求。** / **Confirmed: real-agent task completion with evidence that protected content did not enter model requests.** |
| Q3 | 哪 1–2 个任务最能代表期望价值？每个任务哪些内容保密、哪些结果允许发布？ / Which one or two tasks best represent the intended value, and what must remain confidential versus what may be released? | **已确认：第 6 节案例 A/B 及其披露边界。** / **Confirmed: scenarios A/B and their disclosure boundaries in Section 6.** |
| Q4 | “整份内容保密但允许有限派生结果”是否是本轮必需能力？ / Is processing wholly confidential content into limited approved results mandatory in this iteration? | **已确认：案例 A 是本轮必需能力，仅隐藏敏感字段不够。** / **Confirmed: scenario A is mandatory; hiding sensitive fields alone is insufficient.** |
| Q5 | 模型调用预算、可接受耗时及时间安排是多少？ / What are the model-call budget, acceptable latency, and schedule? | 合成数据已随案例确认；预算、耗时和时间安排待讨论。 / Synthetic data is confirmed with the scenarios; budget, latency, and schedule remain open. |
| Q6 | 具体数据形态、批准分组的发布条件，以及测试输入和预期结果是什么？ / What data forms, release conditions for approved groups, test inputs, and expected results are required? | 在设计讨论前或对应讨论开始时补齐需求，不预设实现方法。 / Clarify requirements before or at the start of the relevant design discussion, without prescribing implementation. |

## 11. 何时算目标已经对齐 / When Alignment Is Complete

当前已完成核心功能目标与案例对齐。以下清单用于区分已确认事项和后续细化，避免把功能确认误写成完整需求已冻结：

Core functional goals and scenarios are now agreed. The checklist below distinguishes confirmed items from remaining refinements so functional agreement is not mistaken for a complete requirements freeze:

- 已确认：两类来源、案例 A/B 及其保护和披露边界、真实 Agent 演示、合成数据、分别验收。
- 待细化：具体测试输入与预期结果、发布条件、支持的使用条件、预算和性能约束。
- 持续遵守：按用户要求进行 pair system design，比较备选方案，让用户练习判断后再共同决定。

- Confirmed: both source types, scenarios A/B and their protection and disclosure boundaries, real-agent demonstrations, synthetic data, and separate acceptance.
- To refine: concrete test inputs and expected results, release conditions, supported usage conditions, budget, and performance constraints.
- Ongoing commitment: follow the user-requested pair system design process, compare alternatives, and let the user practice judgment before making joint decisions.

pair system design 以已确认目标为基础，先补齐影响当前决策的需求，再比较方案；实现开始前需完成相应设计决策。已确认的设计与范围决定见 [决策记录](pair-design-decisions.md)，其中 D002 记录了先完成网关 MVP、暂缓 CaMeL 扩展的决定。

Pair system design builds on the confirmed goals, clarifies requirements affecting each decision, and then compares alternatives. Relevant design decisions must be completed before implementation starts. See the [decision log](pair-design-decisions.md) for agreed design and scope decisions; D002 records completing the gateway MVP before considering CaMeL extensions.
