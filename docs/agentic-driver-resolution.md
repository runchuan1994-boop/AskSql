# Agentic 驱动缺失自动修复方案

> 状态: 设计文档
> 负责人: 
> 创建日期: 2026-08-22

## 1. 问题描述

### 1.1 现象

用户通过 AI Agent 连接数据库时，如果主服务环境缺少对应的 Python 数据库驱动（如 `psycopg2`），连接测试会直接失败，Agent 只能告知用户"缺少驱动，请手动安装"。

用户体验问题：
- 用户需要手动操作服务器安装依赖
- 中断了 AI 驱动的自动化流程
- 违背了"agentic"的理念 — Agent 应该能自主发现并解决问题

### 1.2 根因分析

当前 Agent 虽然已经有 `install_driver` 工具，但**没有形成可靠的问题解决闭环**。具体有三层原因：

| 层面 | 问题 | 影响 |
|------|------|------|
| **提示词层** | 系统提示只是"告知可以装驱动"，没有明确的诊断-修复策略 | Agent 看到错误后不会主动调用工具，倾向于直接放弃 |
| **工具层** | 错误信息是自然语言字符串，没有结构化分类 | Agent 需要自己猜错误类型，猜不准就不会调用正确的工具 |
| **流程层** | 缺少明确的"诊断 → 修复 → 验证 → 重试"循环策略 | Agent 是线性执行的，遇到问题不知道该循环尝试 |

### 1.3 现有基础

- ✅ 沙盒系统已实现（Docker + 可配置 runtime: runc/runsc）
- ✅ `install_driver` 工具已存在（在沙盒中 pip install）
- ✅ `test_connection_sandbox` 工具已存在（在沙盒中测试连接）
- ✅ `DatasourceConnectorAgent` 已独立为子 Agent

---

## 2. 解决方案：三层加固的 Agentic 驱动修复循环

### 2.1 核心思路

把"驱动缺失"从一个"用户自己解决的问题"，变成"Agent 自主诊断、自主修复、自主验证"的闭环：

```
连接失败
  ↓
诊断错误类型（结构化错误输出）
  ↓
┌──────── 修复循环 ────────┐
│                          │
│  选择修复策略            │
│  执行修复动作            │
│  验证是否成功            │
│     ↓ 成功              │
│  退出循环                │
│     ↓ 失败              │
│  下一个修复策略          │
│  （最多尝试 N 次）       │
└──────────────────────────┘
  ↓
全部策略都失败 → 向用户汇报 + 给出手动解决方案
```

### 2.2 第一层：结构化错误分类

**目标**：让 Agent 一眼就知道是什么错误、该用什么工具修。

**方案**：改造 `test_connection_sandbox` 工具，返回结构化的错误信息，而不是纯文本。

输出格式：
```json
{
  "success": false,
  "error_type": "driver_missing",
  "error_message": "No module named 'psycopg2'",
  "missing_module": "psycopg2",
  "suggested_fixes": [
    {"tool": "install_driver", "package": "psycopg2-binary"},
    {"tool": "install_driver", "package": "psycopg2"}
  ],
  "db_type": "postgresql"
}
```

错误类型枚举：
- `driver_missing` — 缺少数据库驱动模块
- `authentication_failed` — 用户名/密码错误
- `connection_refused` — 主机/端口不通
- `database_not_found` — 数据库不存在
- `network_timeout` — 网络超时
- `unknown` — 其他错误

### 2.3 第二层：模型生成修复策略（非硬编码）

**目标**：修复策略由 LLM 实时生成，而不是硬编码的策略表。
结构化错误信息为模型提供诊断上下文，但具体怎么修由模型自主决策。

**设计原则**：
- ✅ 灵活：模型可以处理未预料到的错误类型
- ✅ 智能：模型能组合多种工具解决复杂问题
- ✅ 可扩展：加新数据库/新驱动不需要改代码
- ⚠️ 风险：可能重复尝试、可能死循环 → 需要护栏机制（见 2.4）

**系统提示中的引导方式**：

不给出"必须按顺序执行"的硬策略表，而是给出：

1. **错误类型标签** — 帮助模型快速理解问题性质
2. **参考驱动列表** — 仅作参考，模型可以自由选择或尝试其他包
3. **可用工具说明** — 模型知道自己有哪些能力
4. **思考框架** — 引导模型按"诊断 → 生成方案 → 执行 → 验证"的流程思考

参考驱动列表（仅作建议，非硬性规定）：

| 数据库类型 | 常见驱动包（参考） |
|-----------|-------------------|
| postgresql | psycopg2-binary, psycopg2 |
| mysql | mysql-connector-python, pymysql, mysqlclient |
| sqlite | 内置，无需安装 |
| oracle | oracledb, cx_Oracle |
| sqlserver | pyodbc, pymssql |

### 2.4 第三层：护栏机制（防止循环和重复）

**为什么需要护栏**：
即使有历史消息记录，LLM 仍然可能：
- 重复尝试同一个已经失败的修复方案
- 陷入"测试 → 失败 → 同样的修复 → 测试 → 失败"的死循环
- 在多个错误类型之间来回跳，没有进展

**护栏 1：已尝试方案追踪（代码层）**

Agent 内部维护一个 `attempted_fixes` 集合，记录已经尝试过的修复动作。
每次调用工具前检查：
- 这个方案是不是已经试过了？
- 试过就跳过，生成新的方案

追踪粒度：
- `install_driver(package)` → 追踪 package 名，同一个包不装两次
- `test_connection_sandbox` → 允许重复（因为每轮修复后都要验证）

**护栏 2：最大迭代次数（代码层 + 提示层）**

- 代码层：`max_iterations = 6` 硬限制，超过直接退出
- 提示层：明确告诉模型"整个连接流程最多尝试 3 次修复 + 3 次验证"

**护栏 3：每轮差异检查（提示层）**

系统提示要求：
```
每次尝试新的修复方案时，必须满足：
1. 和之前所有尝试过的方案都不同
2. 明确说明："这次尝试的是 XXX，和上次的 YYY 不同在于 ZZZ"
3. 如果想不出新的方案，直接向用户汇报，不要硬凑
```

**护栏 4：进展单调性检查（提示层）**

要求模型每轮都要评估：
- 相比上一轮，错误信息有没有变化？
- 是在变好（比如从"找不到驱动"变成"认证失败"），还是原地踏步？
- 如果连续两轮错误信息完全一样，说明修复没生效，应该换思路

### 2.5 执行环境自选择（Agentic）

**目标**：不由代码硬编码"哪个工具在沙盒里跑、哪个在主进程跑"，而是让 Agent 自己判断每个操作应该在什么环境中执行。

**核心理念**：给模型两套工具 + 充分的环境信息，让模型自己做决策。

#### 两套并行工具

Agent 同时拥有两套功能相似但执行环境不同的工具：

| 功能 | 主进程工具 | 沙盒工具 |
|------|-----------|---------|
| 测试连接 | `test_connection` | `test_connection_sandbox` |
| 执行 SQL | `execute_sql` | （沙盒 executor） |
| 安装驱动 | ❌ 不提供 | `install_driver` |
| 创建数据源 | `create_datasource` | ❌ 不提供 |
| 导入 Schema | `import_schema` | ❌ 不提供（需要写文件） |

#### 环境选择框架（系统提示中给出）

不直接告诉模型"用哪个"，而是告诉模型**每种环境的特性和适用场景**，让模型自己选：

```
你有两种执行环境可用：

【主进程环境】
- 工具: test_connection, create_datasource, import_schema 等
- 特点: 速度快、能持久化数据、能写文件
- 限制: 驱动是固定的，不能动态安装；出错会影响主服务
- 适合: 创建数据源、导入schema、需要持久化结果的操作

【沙盒环境】
- 工具: test_connection_sandbox, install_driver, SQL 执行
- 特点: 隔离安全、可以动态 pip install 驱动
- 限制: 不持久化（用完销毁）、启动稍慢
- 适合: 测试驱动是否可用、验证连接、需要临时装驱动的场景

选择原则（你自己判断，不是硬性规定）：
1. 需要动态安装/测试驱动 → 用沙盒
2. 需要持久化结果（创建数据源、导入schema）→ 用主进程
3. 不确定的时候 → 先在沙盒里验证，验证成功了再在主进程做正式操作
4. 主进程里因为缺驱动失败了 → 可以换到沙盒里试试
```

#### 典型决策路径

模型可能会自发形成这样的最优路径：

```
用户请求连接 PostgreSQL 数据库
  ↓
Agent 决定: 先在主进程创建数据源（需要持久化）→ create_datasource
  ↓
Agent 决定: 测试连接（先试主进程，因为快）→ test_connection
  ↓
失败了: 缺少 psycopg2 驱动
  ↓
Agent 决定: 换到沙盒环境试试，因为可以装驱动 → install_driver
  ↓
驱动安装成功
  ↓
Agent 决定: 在沙盒里验证连接是否通 → test_connection_sandbox
  ↓
沙盒连接成功
  ↓
Agent 向用户汇报：沙盒验证通过，但主服务还缺驱动，
建议管理员安装后可完整使用（schema导入/SQL查询等）
```

整个过程中，**每一步"在哪个环境执行"的决策都是模型自己做的**，代码不做硬性路由。

### 2.7 第五层：Reflective 修复循环

**目标**：让 Agent 形成"诊断 → 生成策略 → 执行 → 验证 → 反思 → 再诊断"的循环。

推荐的思考框架（在系统提示中给出，不强制）：

```
连接测试失败时，建议按以下思路处理：

1. 【诊断】分析 error_type 和 error_message，理解根本原因
2. 【生成方案】想出 2-3 种可能的修复方案，按成功概率排序
3. 【筛选】排除已经尝试过的方案
4. 【执行】选择最可能成功的方案执行
5. 【验证】调用 test_connection_sandbox 验证
6. 【反思】
   - 成功了？ → 继续后续流程
   - 失败了？ → 错误有变化吗？新的错误类型是什么？
   - 还有新方案吗？ → 回到步骤 4
   - 没新方案了？ → 向用户汇报
```

---

## 3. 详细设计

### 3.1 工具改造

#### test_connection_sandbox 改造

**输入**：不变（db_url）

**输出**：增加结构化错误信息

```python
def test_connection_sandbox(state, db_url):
    # 执行测试...

    if 成功:
        return {"success": True, ...}

    # 失败时，结构化分类
    error_type = _classify_error(error_message)
    suggestions = _get_fix_suggestions(error_type, db_type)

    return {
        "success": False,
        "error_type": error_type,
        "error_message": error_message,
        "suggested_fixes": suggestions,
        # 同时保留人类可读的描述
        "human_readable": f"连接失败（{error_type}）：{error_message}",
    }
```

#### 错误分类函数 `_classify_error`

基于关键词匹配的轻量级分类器：

```python
def _classify_error(error_msg: str) -> str:
    error_lower = error_msg.lower()

    # 驱动缺失
    if any(k in error_lower for k in [
        "no module named", "modulenotfounderror",
        "driver not found", "cannot load driver",
        "module not found",
    ]):
        return "driver_missing"

    # 认证失败
    if any(k in error_lower for k in [
        "password authentication", "access denied",
        "authentication failed", "invalid password",
    ]):
        return "authentication_failed"

    # 连接拒绝
    if any(k in error_lower for k in [
        "connection refused", "errno 61", "could not connect",
        "connection could not be established",
    ]):
        return "connection_refused"

    # 数据库不存在
    if any(k in error_lower for k in [
        "database \".*\" does not exist", "unknown database",
        "database not found",
    ]):
        return "database_not_found"

    # 超时
    if any(k in error_lower for k in [
        "timeout", "timed out", "operation timed out",
    ]):
        return "network_timeout"

    return "unknown"
```

### 3.2 系统提示改造

在 `CONNECT_DS_SYSTEM_PROMPT` 中加入完整的错误处理策略章节。

关键变化：
- 从"如果失败告诉用户" → "如果失败，主动诊断并尝试修复"
- 结构化错误信息帮助模型快速定位问题
- 给出"诊断 → 生成方案 → 执行 → 验证 → 反思"的思考框架（引导，不强制）
- 提供常见驱动包列表作为参考（建议，非硬性规定）
- 明确护栏规则（必须遵守，防止循环）

### 3.3 护栏机制实现

四层护栏，从代码层硬限制到提示层引导：

#### 护栏 1：已尝试方案追踪（代码层）

**实现方式**：在 `DatasourceConnectorAgent` 中维护 `attempted_fixes: set[str]` 集合。

每次工具调用前：
- 如果是 `install_driver`，检查 `package` 是否已在 `attempted_fixes` 中
- 如果已尝试过，**代码层直接拦截**，返回"此方案已尝试过，请换一个"的提示
- 如果没试过，执行并加入集合

**追踪粒度**：
- `install_driver:package_name` — 按包名去重
- `test_connection_sandbox` — 允许重复（每轮修复后都要验证）

#### 护栏 2：最大迭代次数（代码层 + 提示层）

- **代码层**：`max_iterations = 8` 硬限制，超过直接返回失败
- **提示层**：明确告知模型最多有多少次尝试机会，让它自己合理分配

#### 护栏 3：差异检查（提示层）

系统提示中明确要求：

```
每次尝试修复前，先回答两个问题：
1. 这个方案之前试过吗？试过就换一个。
2. 和上一次尝试相比，有什么本质不同？

如果想不出新的、不同的方案，直接向用户说明情况，不要硬凑。
```

#### 护栏 4：进展监控（提示层）

要求模型每轮评估进展：

```
每次测试失败后，对比和上一次失败的错误：
- 错误类型变了吗？（比如从 driver_missing 变成 authentication_failed = 有进展）
- 还是同一个错误、完全没变化？（= 修复没生效，换思路）
- 如果连续 2 次是同一个错误类型，说明当前方向不对，要彻底换思路
```

### 3.4 迭代控制

为了避免 Agent 陷入无限循环，设置以下限制：
- 每个数据源连接流程最多 **8 次迭代**（给修复循环留充分空间，但有硬顶）
- 驱动安装最多尝试 **3 个不同的包**（由护栏 1 强制）
- 如果连续 2 次同一个错误类型没有进展，模型应该主动放弃并向用户汇报

---

## 4. 与现有系统的集成

### 4.1 对沙盒系统的依赖

| 依赖 | 状态 |
|------|------|
| SandboxManager | ✅ 已实现 |
| SandboxExecutor | ✅ 已实现 |
| install_driver 工具 | ✅ 已实现，需验证 |
| test_connection_sandbox 工具 | ✅ 已实现，需改造结构化输出 |

### 4.2 对 DatasourceConnectorAgent 的改造

| 改动点 | 说明 |
|--------|------|
| 系统提示重写 | 加入错误诊断-修复策略 |
| 迭代次数 | 4 → 6（给修复循环留空间） |
| 工具列表 | 不变（已经有 install_driver 和 test_connection_sandbox） |

### 4.3 前端 SSE 事件

新增事件（用于前端展示修复过程）：
- `ds_installing_driver` — 正在安装驱动
- `ds_driver_installed` — 驱动安装成功
- `ds_driver_install_failed` — 驱动安装失败
- `ds_retrying_connection` — 重试连接测试

---

## 5. 测试计划

### 5.1 单元测试

1. **错误分类测试**：验证 `_classify_error` 对各种错误消息的分类准确性
2. **修复建议测试**：验证不同错误类型返回正确的修复建议
3. **Agent 策略执行测试**：mock LLM 响应，验证 Agent 按策略顺序执行

### 5.2 集成测试

1. **驱动缺失自动修复**：模拟缺驱动 → Agent 自动安装 → 重试成功
2. **多驱动候选尝试**：第一个驱动失败 → 试第二个 → 成功
3. **驱动全部失败**：所有驱动都装不上 → Agent 正确上报
4. **非驱动类错误**：认证失败 / 网络不通 → Agent 不瞎装驱动

### 5.3 端到端测试

1. 完整的 PostgreSQL 连接流程（真数据库，真缺驱动）
2. 验证 Agent 自主完成识别-安装-验证全流程

---

## 6. 后续迭代方向

### V2：更智能的诊断

- 用 LLM 做错误诊断（而不是关键词匹配），处理更复杂的错误
- 根据用户提供的连接信息预判可能需要什么驱动，提前安装

### V3：主服务驱动自动安装

- 目前驱动只装在沙盒里，schema 导入等主进程操作还是缺驱动
- V2 可以考虑：沙盒验证驱动可用后，Agent 引导/协助管理员在主服务安装
- 或者：schema 导入也迁到沙盒里做

### V4：驱动缓存

- 安装过的驱动缓存到沙盒镜像层/volume
- 下次不用重新装，加速连接测试

---

## 7. 风险与权衡

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Agent 可能在非驱动错误时也乱装驱动 | 浪费时间 + 资源 | 严格的错误分类 + 策略表限制 |
| 驱动安装时间长（pip install 慢） | 用户等待久 | 预装常见驱动到沙盒镜像 |
| 安装多个驱动包增加沙盒体积 | 沙盒变重 | 每个沙盒只装需要的驱动 |
| 沙盒网络需要开启才能 pip install | 安全风险 | 默认关闭网络，仅安装驱动时临时开启（V2） |

---

## 8. 实施优先级

- **P0（必须）**：结构化错误输出 + 强化系统提示 + 驱动候选列表
- **P1（应该）**：错误分类函数 + 修复建议生成
- **P2（可以）**：驱动缓存 + 更智能的 LLM 诊断
