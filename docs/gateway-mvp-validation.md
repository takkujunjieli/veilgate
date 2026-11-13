# Gateway MVP — 实现与验证 / Implementation and Validation

本轮实现通用网关主线。真实 Agent 验收尚未完成：本次环境没有模型 API 凭据。有限测试不构成通用隐私保证。

This iteration implements the general gateway flow. Real-agent acceptance remains pending: no model API credentials are available in this environment. Finite tests do not establish universal privacy guarantees.

## 接口与职责 / Interfaces and responsibilities

- `GET /v1/tools`：按已认证身份返回获准工具描述与有限参数 schema，不返回路径、URL 或凭据。
- `POST /v1/tools/{id}/invoke`：请求为 `{"arguments": {...}}`。每个参数必填，值来自资源所有者批准的有限字符串集合；多余参数拒绝。
- `csv_read`：本地 CSV 字段投影。
- `csv_aggregate`：固定快照，按可信配置分组、计数与求和；支持配置指定的精确匹配筛选。金额最多两位小数，绝对值不超过 10^12；Decimal 运算。输出为 `group/count/total` 中批准的字段。
- `api_read`：调用可信配置指定的 HTTPS GET，禁止重定向，凭据由网关启动时从环境读取。定位指定记录数组，并重建批准的标量字段，支持嵌套字段路径。
- 共同执行身份、工具与参数授权、输出大小限制、固定错误与无原文审计。策略启动时加载，修改后重启生效；返回与审计包含策略版本。

Discovery exposes authorized descriptions and finite input schemas. Invocation authenticates, authorizes arguments, executes a trusted adapter, reconstructs approved output, and uses the existing bounded response/audit boundary. Credentials, source addresses and raw records are not tool arguments. API calls use fixed HTTPS GET targets without redirects. Local aggregates use hash-verified snapshots and Decimal arithmetic. Policies activate on process restart.

旧资源读取接口保留兼容，并复用 Gateway 服务层。MVP 使用 HTTP JSON，不实现 MCP；发现协议可以在后续适配到 MCP，而无需让协议决定授权。

The legacy resource endpoint remains compatible and uses the Gateway service layer. The MVP uses HTTP JSON, not MCP. A future protocol adapter can reuse authorization and execution behavior.

## 演示 / Demonstration

使用 `examples/gateway.toml`，将 `VEILGATE_DATA_ROOT` 设为 `examples/data` 的绝对真实路径，设置两个不同的高熵 token（`VEILGATE_DEMO_TOKEN`、`VEILGATE_SECOND_TOKEN`），再运行 `veilgate`。

Use `examples/gateway.toml`, set the absolute real data-root path and two distinct high-entropy tokens, then start `veilgate`.

请求 `regional_sales`，参数 `{"month":"2026-10"}`，预期 East：2 笔、250.00；West：2 笔、500.00。姓名、电话及逐笔金额均不返回。示例门槛 `min_group_rows=2` 仅用于演示可配置发布检查，不代表匿名化或客户隐私标准。

Invoke `regional_sales` with `{"month":"2026-10"}`. Expected results: East, 2 orders, 250.00; West, 2 orders, 500.00. Names, phones and individual amounts are withheld. The sample minimum group size of 2 exercises policy enforcement; it is not an anonymity or customer-privacy standard.

API 配置模板位于同一文件的注释中。替换为可信 HTTPS 服务后启用；本次测试使用合成上游响应，不声称外部业务 API 已接入。API 返回未知字段被丢弃，批准字段缺失或值为对象/数组时整体失败。批准字符串的完整值可以披露；不承诺识别误放在批准字段中的秘密。

The commented API template needs an operator-approved HTTPS source. Tests use synthetic upstream responses, not a live business integration. Unknown fields are omitted; missing approved fields or object/array values cause failure. Approved string values are released in full, with no semantic secret detection.

## 真实 Agent 入口 / Real-agent entry point

脚本依据 [OpenAI 官方工具调用文档](https://developers.openai.com/api/docs/guides/function-calling) 使用 Responses API。指定可用模型，不内置模型选择。每次请求在发送前将实际 JSON 请求体写入独占创建的 trace 文件并刷盘；不记录认证头。脚本最多调用模型 8 次，每次输出预算 2000 token。

The client follows the official Responses function-calling protocol. Every actual model request body is recorded and flushed before transmission, excluding authentication headers. The model is explicitly selected by the operator. The call budget is eight requests with up to 2000 output tokens each.

```bash
python scripts/agent_demo.py \
  --model YOUR_AVAILABLE_MODEL \
  --gateway http://127.0.0.1:8000 \
  --task 'Compare October 2026 regional order counts and sales totals; identify the highest region.' \
  --trace local/traces/local-agent.jsonl
```

运行前提供 `OPENAI_API_KEY` 与 `VEILGATE_AGENT_TOKEN`，并创建 trace 父目录。脚本只访问网关和模型。与网关使用同一宿主权限运行不能证明隔离；推荐独立容器，无受保护文件、网关配置或上游凭据挂载。

Provide `OPENAI_API_KEY` and `VEILGATE_AGENT_TOKEN` and create the trace parent directory. Same-host credentials and filesystem permissions do not prove isolation. Use the separate agent container for boundary validation.

```bash
# Set both gateway tokens and OPENAI_API_KEY in the operator environment first.
# Prepare local/traces writable by container UID 65532; mount only this directory to agent.
docker compose -f compose.demo.yaml up --build -d --wait veilgate
docker compose -f compose.demo.yaml run --build --rm agent \
  --gateway http://veilgate:8000 --model YOUR_AVAILABLE_MODEL \
  --task 'Compare October 2026 regional sales and identify the highest region.' \
  --trace /traces/local-agent.jsonl
```

检查全部 trace 请求中的输入、工具定义和历史；将批准信息与受保护测试值分开核对，并验证最终任务正确性。API 场景需配置并运行独立演示。仅搜索 canary 不足以证明没有泄露所有敏感内容；协议模拟测试不能替代真实模型或部署隔离验收。

Inspect all request bodies, including tool definitions and full history, against permitted and protected fixture content; verify task correctness separately. The API scenario requires its own configured run. Canary absence alone is not proof of complete privacy, and simulated protocol tests do not replace real-model or deployment-isolation acceptance.

## 验证状态 / Validation status

本轮本地验证：127 个测试通过（含模拟模型协议测试），语句与分支合并覆盖率 91.86%；Ruff lint/format、mypy 和 pip check 通过。Docker daemon 未运行，容器隔离演示尚未执行。真实 loopback HTTP smoke 已通过：旧资源发布与拒绝，以及新工具发现、快照聚合和越权参数拒绝。Compose 演示配置静态校验通过。未验证：真实模型调用、外部 HTTPS 业务服务、容器部署隔离与远程 CI。当前不承诺跨版本推断防护、差分隐私、自由文本语义检测或完整 CaMeL 信息流机制。

Final local check results are recorded below. Unverified: real model calls, external HTTPS business services, container isolation, and remote CI. Cross-version inference protection, differential privacy, semantic free-text detection, and full CaMeL information flow are outside the implemented scope.

Local checks: 127 tests passed, 91.86% combined statement/branch coverage; Ruff lint/format, mypy, and pip check passed. The Docker daemon was not running; container isolation has not been tested.

Both real loopback HTTP smoke runs passed: legacy resource publication/denial and tool discovery/snapshot aggregation/argument denial. The demo Compose configuration passed static validation; this does not establish container runtime behavior.
