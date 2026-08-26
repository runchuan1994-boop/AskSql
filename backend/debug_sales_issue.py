"""调试 PostgreSQL 数据源下'最近销售数据怎么样'不生成 SQL 的问题"""
import asyncio
import sys

async def main():
    from app.services.datasource_service import get_datasource
    from nl2sql.schema.loader import SchemaLoader
    from nl2sql.agent.dispatcher import DispatcherAgent
    from nl2sql.executor.factory import create_executor
    from app.core.config import settings
    
    ds_id = "66446863"  # finance_db_postgresql
    ds = get_datasource(ds_id, include_password=True)
    print(f"数据源: {ds.get('name')}")
    print(f"类型: {ds.get('type')}")
    print(f"Host: {ds.get('host')}:{ds.get('port')}")
    print(f"Database: {ds.get('database')}")
    
    # 检查 schema
    loader = SchemaLoader()
    schema_file = ds.get("schema_file", "")
    print(f"\nSchema file: {schema_file}")
    
    import os
    if not os.path.exists(schema_file):
        print("  Schema 文件不存在！")
        # 试试本地路径
        local_path = schema_file.replace("/app/", "./")
        if os.path.exists(local_path):
            print(f"  但本地路径存在: {local_path}")
            schema_file = local_path
    
    try:
        ds_schema = loader.load_from_yaml(schema_file)
        tables = ds_schema.db_schema.tables
        print(f"  表数量: {len(tables)}")
        for t in tables[:10]:
            print(f"    - {t.name} ({len(t.columns)} 列): {t.description[:60]}")
    except Exception as e:
        print(f"  Schema 加载失败: {e}")
        return

    # 检查数据库连接
    from app.services.datasource_service import build_db_url
    db_url = build_db_url(ds)
    print(f"\nDB URL: {db_url[:60]}...")
    
    try:
        executor = create_executor(
            datasource_id=ds_id,
            datasource_type=ds["type"],
            db_url=db_url,
            timeout_seconds=10,
        )
        # 尝试执行一个简单查询
        result = executor.execute("SELECT 1")
        print(f"  连接测试: {'成功' if result.success else '失败 - ' + str(result.error)}")
    except Exception as e:
        print(f"  执行器创建失败: {e}")
        return
    
    # 构建 dispatcher 并运行
    events = []
    def event_cb(evt_type, data):
        events.append((evt_type, data))
        print(f"  [EVENT] {evt_type}")
    
    dispatcher = DispatcherAgent(
        project_id="6afb8fed",
        datasources=[ds_schema],
        executors={ds_id: executor},
        event_callback=event_cb,
        max_iterations=3,
        max_probe_iterations=2,
    )
    
    print(f"\n=== 运行查询: 最近销售数据怎么样 ===")
    try:
        result = dispatcher.run("最近销售数据怎么样", [])
        print(f"\n=== 结果 ===")
        print(f"  status: {result.get('status')}")
        print(f"  intent: {result.get('intent_type')}")
        print(f"  sql: {str(result.get('sql', ''))[:200]}")
        print(f"  answer: {str(result.get('answer', ''))[:200]}")
        print(f"  error: {result.get('error')}")
        print(f"  iteration: {result.get('iteration')}")
        
        exec_result = result.get('execution_result')
        if exec_result:
            print(f"  exec success: {exec_result.success}")
            print(f"  exec error: {exec_result.error if not exec_result.success else 'N/A'}")
    except Exception as e:
        print(f"\n异常: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n=== 事件列表 ===")
    for evt, data in events:
        data_preview = str(data)[:100]
        print(f"  {evt}: {data_preview}")

asyncio.run(main())
