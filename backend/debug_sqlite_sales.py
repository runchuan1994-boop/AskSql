"""用 SQLite 数据源验证销售查询"""
import asyncio

async def main():
    from app.services.datasource_service import get_datasource
    from nl2sql.schema.loader import SchemaLoader
    from nl2sql.agent.dispatcher import DispatcherAgent
    from nl2sql.executor.factory import create_executor
    from app.services.datasource_service import build_db_url
    
    ds_id = "c001239e"  # SQLite 演示数据库
    ds = get_datasource(ds_id, include_password=True)
    print(f"数据源: {ds.get('name')}, 类型: {ds.get('type')}")
    
    # 加载 schema
    loader = SchemaLoader()
    schema_file = ds.get("schema_file", "")
    # 修复路径
    import os
    if not os.path.exists(schema_file):
        schema_file = schema_file.replace("/app/", "./")
    ds_schema = loader.load_from_yaml(schema_file)
    tables = ds_schema.db_schema.tables
    print(f"表数量: {len(tables)}")
    for t in tables:
        print(f"  - {t.name}: {t.description[:50]}")
    
    # 测试连接
    db_url = build_db_url(ds)
    executor = create_executor(
        datasource_id=ds_id,
        datasource_type=ds["type"],
        db_url=db_url,
        timeout_seconds=10,
    )
    result = executor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print(f"\n连接测试: {'成功' if result.success else '失败'}")
    if result.success:
        print(f"  实际表: {[r[0] for r in result.rows]}")
    
    # 事件收集
    events = []
    sqls = []
    def event_cb(evt_type, data):
        events.append((evt_type, data))
        if evt_type == "sql_generated":
            sql = data.get("sql", "")
            sqls.append(sql)
            print(f"  [SQL #{len(sqls)}] {sql[:120]}...")
        elif evt_type == "sql_execution_failed":
            err = data.get("error", "")
            print(f"  [执行失败] {err[:100]}")
        elif evt_type == "sql_executed":
            print(f"  [执行成功] rows={data.get('row_count')}")
        elif evt_type == "final_result":
            print(f"  [最终结果] success={data.get('success')}")
    
    dispatcher = DispatcherAgent(
        project_id="test",
        datasources=[ds_schema],
        executors={ds_id: executor},
        event_callback=event_cb,
        max_iterations=3,
        max_probe_iterations=2,
    )
    
    print(f"\n=== 运行查询: 最近销售数据怎么样 ===")
    result = dispatcher.run("最近销售数据怎么样", [])
    
    print(f"\n=== 结果 ===")
    print(f"  status: {result.get('status')}")
    print(f"  sql 预览: {str(result.get('sql', ''))[:150]}")
    print(f"  answer 预览: {str(result.get('answer', ''))[:150]}")
    print(f"  迭代次数: {result.get('iteration')}")
    
    exec_result = result.get('execution_result')
    if exec_result and exec_result.success:
        print(f"  执行成功，{exec_result.row_count} 行")
    elif exec_result:
        print(f"  执行失败: {exec_result.error[:100]}")

asyncio.run(main())
