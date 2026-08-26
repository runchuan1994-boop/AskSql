"""验证修复后 SQL 执行是否正常（修正 executor key）"""
from nl2sql.schema.loader import SchemaLoader
from nl2sql.agent.dispatcher import DispatcherAgent
from nl2sql.executor.base import ExecutionResult
from unittest.mock import MagicMock
import os

schema_file = "config/schemas/sample/ecommerce.yaml"
loader = SchemaLoader()
ds_schema = loader.load_from_yaml(schema_file)

print(f"Schema datasource_id: {ds_schema.datasource_id}")

# mock executor - 用正确的 key
mock_executor = MagicMock()
def mock_execute(sql):
    return ExecutionResult(
        success=True,
        sql=sql,
        columns=["order_date", "order_count", "buyer_count", "total_sales_amount"],
        rows=[
            ("2024-01-01", 120, 100, 15000.0),
            ("2024-01-02", 145, 125, 18000.0),
            ("2024-01-03", 168, 140, 22000.0),
        ],
        row_count=3,
        duration_ms=10,
    )
mock_executor.execute.side_effect = mock_execute

ds_id = ds_schema.datasource_id  # 用 schema 中的 ID
print(f"Executor key: {ds_id}")

events = []
sqls = []
exec_results = []

def event_cb(evt_type, data):
    events.append((evt_type, data))
    if evt_type == "sql_generated":
        sql = data.get("sql", "")
        sqls.append(sql)
        print(f"  [SQL #{len(sqls)}] {sql[:80]}...")
    elif evt_type == "sql_executed":
        exec_results.append(True)
        print(f"  [执行成功] {data.get('row_count')} 行")
    elif evt_type == "sql_execution_failed":
        exec_results.append(False)
        print(f"  [执行失败] {str(data.get('error', ''))[:80]}")
    elif evt_type == "final_result":
        print(f"  [最终] success={data.get('success')}")

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

exec_result = result.get('execution_result')
if exec_result:
    print(f"  exec success: {exec_result.success}")
    if not exec_result.success:
        print(f"  exec error: {exec_result.error[:100]}")

answer = result.get('answer', '')[:120]
print(f"  answer: {answer}")
print(f"  事件总数: {len(events)}")
print(f"  SQL 生成次数: {len(sqls)}")
print(f"  执行成功次数: {sum(1 for r in exec_results if r)}")
print(f"  执行失败次数: {sum(1 for r in exec_results if not r)}")
