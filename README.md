# VeilGate

为 AI Agent 提供受策略约束的私有资源访问。**用户指定资源，网关决定谁可以执行什么操作，以及哪些字段可以返回。**

当前实现包括本地 CSV、固定快照聚合、HTTPS API 适配、工具发现与调用、参数授权和输出白名单发布。设计愿景见 [设计草稿](VeilGate-design-draft.md)，实际保证以本文及 [威胁模型](docs/threat-model.md) 为准。

## 当前能力

- 使用资源 ID 访问预先注册的 CSV，不接受客户端传入路径。
- 通过高熵 Bearer token 映射到服务器配置的身份；每次请求重新授权。
- `read_redacted` 按输出白名单重建 JSON，未批准字段直接删除。
- 新增未知源字段不会自动发布；缺少批准字段、重复列名、行宽不一致、无效 UTF-8 等情况拒绝整个结果。
- POSIX 文件描述符相对读取，拒绝路径穿越、符号链接、硬链接及非普通文件。
- 文件、行数、列数、输出、请求体及并发限制。
- 固定错误码、服务器生成的请求 ID、无原文审计记录、响应禁止缓存。
- 审计写入失败时，不向客户端发布成功结果。

新增通用工具入口与演示配置见 [网关 MVP 实现与验证](docs/gateway-mvp-validation.md) 和 [examples/gateway.toml](examples/gateway.toml)。真实模型端到端验收仍待执行。

当前**不包含**任意代码执行、自由文本 PII 检测、MCP 或行为监控。删除敏感列不是匿名化，也不能识别被错误放入批准列的秘密。

## 本地运行

要求：Python 3.12、Linux 或 macOS。本地模式用于开发；Agent 如果与服务共享文件系统权限，仍能绕过网关。生产部署要求见下文。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation .

export VEILGATE_CONFIG="$PWD/examples/policy.toml"
export VEILGATE_DATA_ROOT="$(python -c 'from pathlib import Path; print(Path("examples/data").resolve())')"
export VEILGATE_DEMO_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
veilgate
```

示例数据全部为合成数据。不要把真实文件、生产配置或凭据提交到仓库；开发私有文件可放在已忽略的 `local/` 中。

服务默认只监听 `127.0.0.1:8000`。使用受支持的 `veilgate` 入口，避免额外服务器日志记录请求 URL 或未处理异常。

同一 shell 环境或由可信客户端注入 token：

```bash
curl --fail --silent \
  -H "Authorization: Bearer $VEILGATE_DEMO_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{}' http://127.0.0.1:8000/v1/resources/customers/read
```

返回：

```json
{"resource_id":"customers","policy_version":"example-v1","fields":["region","amount"],"rows":[{"region":"East","amount":"100"},{"region":"West","amount":"200"}]}
```

发送 `{"fields":["email"]}` 返回 `403 fields_not_allowed`。可以请求批准字段的子集；不能传入身份、路径、角色或其他操作参数。

token 由可信 Agent 宿主保存并注入 HTTP 头，不能放入模型提示词或工具参数。调用示例使用 shell 仅方便本地演示，不应在共享终端开启命令跟踪。

## 策略配置

参考 [examples/policy.toml](examples/policy.toml)。

- `schema_version`：当前必须是整数 `1`。
- `policy_version`：运维分配的版本标识，每次变更应更新。
- `data_root`：绝对路径；路径的每一级都不能是符号链接。
- `principals`：身份与 token 环境变量的映射。token 需要至少 32 个 URL-safe 字符，推荐 `secrets.token_urlsafe(32)`，每个身份使用不同 token。
- `resources`：相对路径、身份白名单、发布字段白名单和唯一支持的操作。
- `VEILGATE_DATA_ROOT`：可信部署环境可覆盖数据根目录。

配置启动时验证并加载，未知键、重复标识、无效授权引用、缺失或弱格式凭据均导致启动失败。策略和凭据的更新/吊销通过修改配置或环境并重启进程生效。禁止热改内存策略；当前没有管理 API。

白名单表示允许公开这些列的**完整值**，不是对内容做语义判断。原始列顺序可以变化；批准列被删除会导致拒绝。不会截断后返回部分成功结果。

## HTTP 契约

| 接口 | 认证 | 用途 |
|---|---|---|
| `GET /healthz` | 无 | 进程存活 |
| `GET /readyz` | 无 | 已完成配置、凭据和根目录初始化；不逐文件探测 |
| `POST /v1/resources/{resource_id}/read` | Bearer | 返回批准的 CSV 字段（兼容接口） |
| `GET /v1/tools` | Bearer | 发现获准工具及其有限参数 schema |
| `POST /v1/tools/{tool_id}/invoke` | Bearer | 统一调用已注册工具 |

请求体必须是 JSON 对象（最多 4096 字节），旧资源接口只允许可选的 `fields` 数组；工具调用接口只允许 `arguments` 对象。不接受查询参数、压缩请求、重复 JSON 键或自动重定向。API 不提供文档路由或资源目录枚举。

错误形如 `{"error":{"code":"invalid_request"}}`，响应头中的 `X-Request-ID` 用于关联审计；客户端不能指定或覆盖它。

| 状态码 | 示例错误码 |
|---|---|
| 400 | `invalid_request` |
| 401 | `unauthorized` |
| 403 | `fields_not_allowed` |
| 404 | `resource_unavailable`（不存在和无权访问相同） |
| 409 | `source_changed` |
| 413 | `request_too_large` / `source_limit_exceeded` / `output_limit_exceeded` |
| 415 | `unsupported_media_type` |
| 422 | `invalid_source` / `source_unavailable` |
| 500 | `internal_error` |
| 503 | `busy` / `audit_unavailable` |
| 504 | `request_timeout` |

响应为 JSON 字符串值，不自动推断数字类型。非 UTF-8、过长 CSV 单元格等解析错误会拒绝整个文件。未来类型化 schema 需要单独的版本设计。

## 验证

测试针对安装后的包执行，避免源码路径掩盖打包问题。修改源码后先重新安装：

```bash
python -m pip install --no-deps --no-build-isolation .
ruff check src tests
ruff format --check src tests
mypy src
pytest --cov=veilgate --cov-report=term-missing
python -m pip check
pip-audit --no-deps --disable-pip -r requirements.lock
python scripts/smoke_http.py
```

最后两项分别需要漏洞数据库网络访问和本地监听端口权限。单元与集成测试使用合成数据，不调用模型或外部数据服务。测试覆盖率门槛不是安全保证。

CI 定义包括 Linux/macOS 检查及容器启动测试；只有实际运行通过后才能声称远程 CI 已验证。

## 部署

```bash
export VEILGATE_DEMO_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose up --build --wait
```

示例容器以非 root 身份运行，文件和配置只读挂载，根文件系统只读，去掉 capabilities，禁止提权，并限制内存、CPU、进程数。仅发布到宿主机 loopback。数据挂载必须对容器 UID `65532` 可读，且对 Agent 不可访问；不要把容器数据目录同时挂载给 Agent。

这是一份开发/私有试点部署配置，**不是公开互联网生产部署方案**。公开上线前必须完成 [发布检查](docs/release-checklist.md)，包括 TLS、边缘流量限制、独立权限验证、审计保留、凭据轮换和安全评审。容器配置没有自动阻止全部出站网络；需由部署环境另设网络规则。

## 项目结构

```text
src/veilgate/
  gateway.py     工具发现、参数授权、适配执行与结果发布
  config.py      严格、带版本的配置模型
  auth.py        凭据与真实身份映射
  policy.py      资源授权及发布字段授权
  files.py       安全文件读取适配器
  publisher.py   CSV 验证与输出白名单重建
  audit.py       固定结构审计
  app.py         HTTP/错误/请求限制边界
  cli.py         服务启动入口
tests/           身份、策略、文件边界、发布和异常测试
```

资源授权与发布逻辑不依赖 HTTP；本地与 API 工具复用统一调用流程。当前故意保持单服务，不提前引入数据库、队列或微服务。

## 依赖与升级

`requirements.lock`、`requirements-dev.lock` 和 `requirements-build.lock` 固定直接与传递依赖，并包含包哈希。使用 Python 3.12 更新：

```bash
pip-compile --allow-unsafe --strip-extras --generate-hashes -o requirements.lock requirements.in
pip-compile --allow-unsafe --strip-extras --generate-hashes -o requirements-dev.lock requirements-dev.in
pip-compile --allow-unsafe --strip-extras --generate-hashes -o requirements-build.lock requirements-build.in
```

更新后重新安装并运行完整检查。`pyproject.toml` 声明兼容范围；部署使用锁文件。容器基础镜像仍使用版本系列标签，发布时应固定审核过的 digest。仓库尚未选择开源许可证，不应假定已授予外部分发许可。
