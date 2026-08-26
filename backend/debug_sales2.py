"""用 ecommerce schema + mock executor 验证销售查询 SQL 生成"""
from nl2sql.schema.loader import SchemaLoader
from nl2sql.agent.dispatcher import DispatcherAgent
from nl2sql.executor.base import ExecutionResult
from unittest.mock import MagicMock
import os

schema_file = "config/schemas/sample/ecommerce.yaml"
print(f"Schema: {schema_file}, exists: {os.path.exists(schema_file)}")

loader = SchemaLoader()
ds_schema = loader.load_from_yaml(schema_file)
tables = ds_schema.db_schema.tables
print(f"表数量: {len(tables)}")
for t in tables:
    col_names = [c.name for c in t.columns[:5]]
    print(f"  - {t.name} ({len(t.columns)} 列): {t.description[:50]}")
    print(f"    列: {', '.join(col_names)}...")

# mock executor：返回假的成功结果
mock_executor = MagicMock()
def mock_execute(sql):
    return ExecutionResult(
        success=True,
        sql=sql,
        columns=["date", "total_sales", "order_count"],
        rows=[
            ("2024-01-01", 15000, 120),
            ("2024-01-02", 18000, 145),
            ("2024-01-03", 22000, 168),
        ],
        row_count=3,
        duration_ms=10,
    )
mock_executor.execute.side_effect = mock_execute

ds_id = "test-ds"
events = []
sqls = []

def event_cb(evt_type, data):
    events.append((evt_type, data))
    if evt_type == "sql_generated":
        sql = data.get("sql", "")
        sqls.append(sql)
        print(f"  [SQL #{len(sqls)}] {sql[:120]}")
    elif evt_type == "sql_executed":
        print(f"  [执行成功] {data.get('row_count')} 行")
    elif evt_type == "sql_execution_failed":
        print(f"  [执行失败] {str(data.get('error', ''))[:80]}")
    elif evt_type == "intent_analysis":
        intent = data.get("intent", {})
        tables_ = [t.get("name") for t in intent.get("tables", [])] if isinstance(intent, dict) else []
        print(f"  [意图分析] tables={tables_}")
    elif evt_type == "reflection":
        print(f"  [反思] satisfied={data.get('satisfied')}, revision={data.get('needs_revision')}")
    elif evt_type == "final_result":
        print(f"  [最终] success={data.get('success')}, sql_len={len(data.get('sql', ''))}")

dispatcher = DispatcherAgent(
    project_id="test",
    datasources=[ds_schema],
    executors={ds_id: mock_executor},
    event_callback=event_cb,
    max_iterations=2,
    max_probe_iterations=1,
)

print(f"\n=== 查询: 最近销售数据怎么样 ===")
result = dispatcher.run("最近销售数据怎么样", [])

print(f"\n=== 结果 ===")
print(f"  status: {result.get('status')}")
print(f"  iteration: {result.get('iteration')}")
sql = result.get("sql", "") or ""
print(f"  sql 长度: {len(sql)}")
if sql:
    print(f"  sql 预览:\n{sql[:300]}")
else:
    print("  SQL 为空!")

print(f"\n  answer 预览: {str(result.get('answer', ''))[:150]}")
print(f"\n  事件总数: {len(events)}")
print(f"  SQL 生成次数: {len(sqls)}")
