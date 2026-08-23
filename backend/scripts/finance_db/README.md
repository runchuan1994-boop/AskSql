# 金融测试数据库 (Finance Test DB)

使用 PostgreSQL + Faker 生成的零售银行风格测试数据库，用于 nl2sql 项目的测试和验证。

## 快速开始

```bash
# 一键初始化（启动 docker + 建表 + 生成数据）
bash backend/scripts/finance_db/init.sh
```

## 连接信息

| 项 | 值 |
|----|----|
| 主机 | localhost |
| 端口 | 5432 |
| 数据库 | finance_db |
| 用户 | nl2sql |
| 密码 | nl2sql123 |
| URL | `postgresql://nl2sql:nl2sql123@localhost:5432/finance_db` |

连接命令：
```bash
docker compose exec -it postgres psql -U nl2sql -d finance_db
```

## 数据库结构 (9 张表)

```
                    ┌──────────────┐
                    │   branches   │  分支机构 (20)
                    └──────┬───────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
    ┌────────────┐  ┌────────────┐  ┌───────────────┐
    │ employees  │  │  accounts  │  │     ...       │
    │  (200)     │  │  (8,000)   │  └───────────────┘
    └────────────┘  └──────┬─────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ transactions │  交易记录 (~80,000)
                    └──────────────┘

    ┌──────────────┐
    │  customers   │  客户 (5,000)
    └──────┬───────┘
           ├──────────────┬──────────────┬──────────────┐
           ▼              ▼              ▼              ▼
    ┌──────────┐   ┌──────────┐   ┌─────────────┐   ┌───────────────┐
    │ accounts │   │  loans   │   │credit_cards │   │  investment_  │
    │ (8,000)  │   │ (1,200)  │   │  (3,000)    │   │  portfolios   │
    └─────┬────┘   └────┬─────┘   └─────────────┘   │   (1,500)     │
          │             ▼                            └───────────────┘
          │      ┌──────────────┐
          │      │loan_payments│  还款记录 (~15,000)
          │      └──────────────┘
          ▼
    ┌──────────────┐
    │ transactions │
    └──────────────┘
```

### 表说明

| 表名 | 行数 | 说明 |
|------|------|------|
| `branches` | 20 | 银行分支机构 |
| `employees` | 200 | 员工（经理、柜员、信贷员等） |
| `customers` | 5,000 | 客户（含信用评分、收入等） |
| `accounts` | 8,000 | 账户（储蓄/支票/信用/房贷/投资） |
| `transactions` | ~80,000 | 交易记录（余额逻辑正确） |
| `loans` | 1,200 | 贷款（个人/车贷/房贷/经营贷/学生贷） |
| `loan_payments` | ~15,000 | 贷款还款记录 |
| `credit_cards` | 3,000 | 信用卡（卡号脱敏） |
| `investment_portfolios` | 1,500 | 投资组合 |

**总计约 11.4 万行数据**

## 在 nl2sql 项目中使用

### 1. 添加数据源

通过前端界面或 API 添加 PostgreSQL 数据源：

```bash
curl -X POST http://localhost:8000/api/datasources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Finance Test DB",
    "type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "finance_db",
    "username": "nl2sql",
    "password": "nl2sql123"
  }'
```

### 2. 导入 Schema

```bash
# 使用项目自带的 schema import 功能
# 或通过前端触发
```

## 典型测试问题

### 简单

1. 总共有多少位客户？
2. 所有活跃账户的总余额是多少？
3. 列出所有分支机构的名称和所在城市。
4. 有多少张信用卡处于活跃状态？
5. 员工的平均工资是多少？

### 中等

1. 哪个城市的分支机构最多？
2. 按账户类型统计平均余额。
3. 2024 年每月的贷款发放总额是多少？
4. 找出有贷款逾期的客户名单。
5. 风险评分最高的前 10 位客户是谁？
6. 各分支机构的员工数量分别是多少？
7. 平均每笔交易金额是多少？按交易类型分组。
8. 储蓄账户和支票账户的客户数量对比。

### 困难

1. 每位客户的总资产（存款 + 投资 - 贷款）排名。
2. 交易金额最高的 Top 10 客户。
3. 各分支机构的存贷比（存款总额 / 贷款总额）。
4. 2024 年信用卡平均利用率（余额 / 额度）排名前 5 的客户。
5. 贷款逾期次数最多的客户及其总逾期金额。
6. 按月统计新增客户数和流失客户数。
7. 不同职业群体的平均贷款金额对比。
8. 投资组合风险等级与客户年收入的相关性。

## 管理命令

```bash
# 启动 PostgreSQL
docker compose up -d postgres

# 停止
docker compose stop postgres

# 重启
docker compose restart postgres

# 查看日志
docker compose logs -f postgres

# 进入 psql
docker compose exec -it postgres psql -U nl2sql -d finance_db

# 完全删除（包括数据）
docker compose down -v postgres

# 重新生成数据（先清空再生成）
docker compose exec -T postgres psql -U nl2sql -d finance_db -c "
  DROP SCHEMA public CASCADE;
  CREATE SCHEMA public;
"
bash backend/scripts/finance_db/init.sh
```

## 数据可重复性

数据生成使用固定随机种子（seed=42），每次生成的结果完全一致。如需修改数据量，编辑 `generate_data.py` 顶部的常量。
