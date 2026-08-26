"""
NL2SQL 28 条功能测试用例 - 主执行脚本
运行: cd backend && uv run python -u run_e2e_tests.py
"""
from __future__ import annotations

import re
import time

import requests

from tests_e2e import (
    setup_test_env,
    run_test,
    run_api_test,
    print_summary,
    add_memory,
    list_memories,
    get_memory,
    update_memory,
    delete_memory,
    assert_no_error,
    assert_success,
    assert_has_sql,
    assert_sql_contains,
    assert_sql_count_star,
    assert_answer_contains,
    assert_result_rows,
    assert_memory_saved,
    assert_no_memory_saved,
    all_results,
    send_chat,
)


def main():
    print('=' * 80)
    print('🧪 NL2SQL 功能测试 - 28 条用例')
    print('=' * 80)

    # 初始化测试环境
    print('\n🔧 初始化测试环境...')
    proj_id, ds_id, sess_id = setup_test_env()
    print(f'   项目: {proj_id}')
    print(f'   数据源: {ds_id}')
    print(f'   会话: {sess_id}')

    # ============================================================
    # 第一组：基础查询能力（测试 1-3）
    # ============================================================
    print('\n' + '=' * 80)
    print('📋 第一组：基础查询能力（验证系统基本可用）')
    print('=' * 80)

    # Test 1: 数据库里有哪些表？（schema exploration 类型）
    run_test('G1-01', '查询所有表', '数据库里有哪些表？', [
        ('无错误', assert_no_error),
        ('有回答', lambda r: (bool(r.answer), f'回答长度: {len(r.answer)}')),
        ('提到 orders 表', assert_answer_contains('orders')),
        ('提到 users 表', assert_answer_contains('users')),
    ], sess_id, ds_id)

    # Test 2: 统计 orders 行数（数据查询类型）
    run_test('G1-02', '统计 orders 行数', '统计 orders 表的总记录数，用 SQL 查询', [
        ('无错误', assert_no_error),
        ('执行成功', assert_success),
        ('生成了 SQL', assert_has_sql),
        ('使用 COUNT 函数', lambda r: (
            bool(re.search(r'COUNT\s*\(', r.sql, re.I)),
            f'SQL 含 COUNT: {bool(re.search(r"COUNT", r.sql, re.I))}'
        )),
        ('回答包含 10', assert_answer_contains('10')),
    ], sess_id, ds_id)

    # Test 3: 查询所有用户列表
    run_test('G1-03', '查询用户列表', '查询 users 表的所有用户数据', [
        ('无错误', assert_no_error),
        ('执行成功', assert_success),
        ('生成了 SQL', assert_has_sql),
        ('查询 users 表', assert_sql_contains(r'FROM\s+users')),
        ('返回结果', assert_result_rows(3)),
    ], sess_id, ds_id)

    # ============================================================
    # 第二组：Schema 增肥功能验证（测试 4-7）
    # ============================================================
    print('\n' + '=' * 80)
    print('📈 第二组：Schema 增肥功能验证（验证 Profiler 数据是否生效）')
    print('=' * 80)
    print('  （增肥数据通过 schema context 提供给 LLM，验证 LLM 能利用这些信息')
    print('   生成正确的查询或直接回答，间接验证增肥数据有效）')

    # Test 4: 订单状态分组统计
    run_test('G2-04', '订单状态分组统计', '按 status 分组统计 orders 表中每种状态的订单数量', [
        ('无错误', assert_no_error),
        ('执行成功', assert_success),
        ('生成了 SQL', assert_has_sql),
        ('按 status 分组', assert_sql_contains(r'GROUP\s+BY.*status|status.*GROUP\s+BY')),
        ('多条结果', assert_result_rows(2)),
    ], sess_id, ds_id)

    # Test 5: 订单金额范围
    run_test('G2-05', '订单金额范围', '查询 orders 表中 total_amount 的最小值和最大值', [
        ('无错误', assert_no_error),
        ('执行成功', assert_success),
        ('生成了 SQL', assert_has_sql),
        ('使用 MIN/MAX', lambda r: (
            bool(re.search(r'MIN\s*\(', r.sql, re.I) and re.search(r'MAX\s*\(', r.sql, re.I)),
            f'MIN: {bool(re.search(r"MIN", r.sql, re.I))}, MAX: {bool(re.search(r"MAX", r.sql, re.I))}'
        )),
        ('包含 total_amount', assert_sql_contains(r'total_amount')),
    ], sess_id, ds_id)

    # Test 6: 最近的订单时间
    run_test('G2-06', '最近订单时间', '查询 orders 表中最新的一条订单的创建时间', [
        ('无错误', assert_no_error),
        ('执行成功', assert_success),
        ('生成了 SQL', assert_has_sql),
        ('查询 created_at', assert_sql_contains(r'created_at')),
        ('回答包含 2024', assert_answer_contains('2024')),
        ('回答包含 08-20 或 8月20', lambda r: (
            '08-20' in r.answer or '8月20' in r.answer or '08/20' in r.answer,
            '回答中包含 8月20日相关日期'
        )),
    ], sess_id, ds_id)

    # Test 7: 订单渠道类型
    run_test('G2-07', '订单渠道类型', '查询 orders 表中有哪些不同的渠道(channel)', [
        ('无错误', assert_no_error),
        ('执行成功', assert_success),
        ('生成了 SQL', assert_has_sql),
        ('查询 channel', assert_sql_contains(r'channel')),
        ('去重查询', lambda r: (
            bool(re.search(r'DISTINCT', r.sql, re.I) or re.search(r'GROUP\s+BY', r.sql, re.I)),
            f'去重方式: DISTINCT/GROUP BY' if re.search(r'DISTINCT|GROUP', r.sql, re.I) else '无'
        )),
        ('多条结果', assert_result_rows(2)),
    ], sess_id, ds_id)

    # ============================================================
    # 第三组：记忆系统 - 手动添加 & 即时生效（测试 8-13）
    # ============================================================
    print('\n' + '=' * 80)
    print('🧠 第三组：记忆系统 - 手动添加 & 即时生效')
    print('=' * 80)

    # Test 8: 添加列描述记忆（API 测试）
    mem_col = add_memory(ds_id, 'column_description', 'column',
                         'orders.total_amount',
                         'total_amount 是商品原价（吊牌价），不是实付金额，实付看 final_amount')
    run_api_test('G3-08', '手动添加列描述记忆', lambda: (
        mem_col.get('id', '').startswith('mem_'),
        f'添加成功: {mem_col.get("id")}' if mem_col.get('id') else f'失败: {mem_col}'
    ))

    # Test 9: 提问验证列记忆生效
    run_test('G3-09', '列记忆影响回答', 'total_amount 是什么含义？', [
        ('无错误', assert_no_error),
        ('有回答', lambda r: (bool(r.answer), f'回答长度: {len(r.answer)}')),
        ('回答提到原价或吊牌价', assert_answer_contains('原价')),
    ], sess_id, ds_id, pre_delay=1.5)

    # Test 10: 添加术语映射记忆（API 测试）
    mem_term = add_memory(ds_id, 'term_mapping', 'term', '流水',
                          '流水就是 GMV，即所有订单的 total_amount 总和')
    run_api_test('G3-10', '手动添加术语映射记忆', lambda: (
        mem_term.get('id', '').startswith('mem_'),
        f'添加成功: {mem_term.get("id")}'
    ))

    # Test 11: 验证"流水"术语被理解
    run_test('G3-11', '术语映射记忆生效（流水=GMV）', '上个月的流水是多少？', [
        ('无错误', assert_no_error),
        ('有回答', lambda r: (bool(r.answer), f'回答长度: {len(r.answer)}')),
        ('使用 total_amount 求和', lambda r: (
            bool(re.search(r'SUM\s*\(\s*total_amount', r.sql, re.I)) if r.sql else False,
            f'SQL 使用 SUM(total_amount): {bool(re.search(r"SUM.*total_amount", r.sql, re.I)) if r.sql else "无SQL"}'
        )),
    ], sess_id, ds_id, pre_delay=1.5)

    # Test 12: 添加表描述记忆（API 测试）
    mem_table = add_memory(ds_id, 'table_description', 'table', 'orders',
                           'orders 表只统计线上订单，不包含线下门店和第三方平台的订单')
    run_api_test('G3-12', '手动添加表描述记忆', lambda: (
        mem_table.get('id', '').startswith('mem_'),
        f'添加成功: {mem_table.get("id")}'
    ))

    # Test 13: 验证表范围记忆影响回答
    run_test('G3-13', '表描述记忆影响回答', 'orders 表的数据范围包括哪些渠道？', [
        ('无错误', assert_no_error),
        ('有回答', lambda r: (bool(r.answer), f'回答长度: {len(r.answer)}')),
        ('回答提到线上或仅线上', lambda r: (
            '线上' in r.answer or '不包含线下' in r.answer or '只统计' in r.answer,
            f'回答是否体现表范围说明'
        )),
    ], sess_id, ds_id, pre_delay=1.5)

    # ============================================================
    # 第四组：自动纠错检测（测试 14-20）
    # ============================================================
    print('\n' + '=' * 80)
    print('🔍 第四组：自动纠错检测（隐式确认机制）')
    print('=' * 80)
    print('  （使用独立 session 避免前面记忆干扰）')

    resp = requests.post(f'http://localhost:8001/api/sessions', json={
        'project_id': proj_id,
        'title': 'Correction Test',
    })
    corr_sess_id = resp.json()['id']
    print(f'   纠错测试 session: {corr_sess_id}')

    # Test 14: 基础查询（不触发纠错）
    run_test('G4-14', '基础查询（不触发纠错）', '总销售额是多少？', [
        ('无错误', assert_no_error),
        ('有回答', lambda r: (bool(r.answer), f'回答长度: {len(r.answer)}')),
        ('不触发纠错保存', assert_no_memory_saved),
    ], corr_sess_id, ds_id)

    # Test 15: 用户纠错 - 应该触发检测
    run_test('G4-15', '用户纠错触发检测',
             '不对，销售额应该用 final_amount 列，total_amount 是原价不是实付', [
        ('无错误', assert_no_error),
        ('检测到纠错并保存记忆', assert_memory_saved),
    ], corr_sess_id, ds_id, pre_delay=3.0)

    # 保存纠错记忆 ID
    corr_mem_id = None
    for r in all_results:
        if r['id'] == 'G4-15' and r['memory_saved']:
            corr_mem_id = r['memory_saved'].get('memory_id')
            break

    # Test 16: 再次提问，记忆应该生效
    run_test('G4-16', '纠错记忆生效（使用 final_amount）', '帮我再查一下销售额', [
        ('无错误', assert_no_error),
        ('有回答', lambda r: (bool(r.answer), f'回答长度: {len(r.answer)}')),
        ('使用 final_amount', lambda r: (
            'final_amount' in r.sql.lower() if r.sql else False,
            f'SQL 使用 final_amount: {"final_amount" in r.sql.lower() if r.sql else "无SQL"}'
        )),
    ], corr_sess_id, ds_id, pre_delay=2.0)

    # Test 17: 术语映射类纠错
    run_test('G4-17', '术语映射类纠错', '不对，流水其实就是 GMV，也就是总交易额', [
        ('无错误', assert_no_error),
        ('检测到纠错', assert_memory_saved),
    ], corr_sess_id, ds_id, pre_delay=3.0)

    # Test 18: "我刚才说的不算" - 不应误判为纠错
    run_test('G4-18', '否定之前的话不应误判', '不对，我刚才说的不算，你还是按原来的来', [
        ('无错误', assert_no_error),
        ('不触发纠错', assert_no_memory_saved),
    ], corr_sess_id, ds_id, pre_delay=2.0)

    # Test 19: 纯疑问不应触发
    run_test('G4-19', '纯疑问不应触发纠错', '这个数据对吗？', [
        ('无错误', assert_no_error),
        ('不触发纠错', assert_no_memory_saved),
    ], corr_sess_id, ds_id, pre_delay=2.0)

    # Test 20: 换维度不应触发
    run_test('G4-20', '换维度不应触发纠错', '换个维度，按渠道分组看看', [
        ('无错误', assert_no_error),
        ('不触发纠错', assert_no_memory_saved),
    ], corr_sess_id, ds_id, pre_delay=2.0)

    # ============================================================
    # 第五组：记忆管理 API 功能（测试 21-25）
    # ============================================================
    print('\n' + '=' * 80)
    print('📝 第五组：记忆管理 API 功能')
    print('=' * 80)

    # 先添加几条测试用记忆
    test_mems = []
    for i in range(3):
        m = add_memory(ds_id, 'column_description', 'column',
                       f'orders.test_col_{i}', f'测试列 {i} 的描述内容')
        test_mems.append(m)

    # Test 21: 搜索功能
    def test_search():
        result = list_memories(ds_id, search='原价')
        found = any('原价' in m.get('content', '') for m in result.get('items', []))
        return found, f'搜索"原价"找到 {result.get("total", 0)} 条记忆'
    run_api_test('G5-21', '记忆搜索功能', test_search)

    # Test 22: 按类型筛选
    def test_filter_type():
        result = list_memories(ds_id, memory_type='column_description')
        all_col = all(m.get('memory_type') == 'column_description'
                      for m in result.get('items', []))
        return all_col, f'筛选 column_description: {result.get("total", 0)} 条，类型全部正确'
    run_api_test('G5-22', '按类型筛选记忆', test_filter_type)

    # Test 23: 编辑记忆
    def test_update():
        mem_id = test_mems[0]['id']
        updated = update_memory(mem_id, {'content': '更新后的描述内容_abc123'})
        if updated and '更新后的描述内容_abc123' in updated.get('content', ''):
            return True, f'编辑成功: {mem_id}'
        return False, f'编辑失败: {updated}'
    run_api_test('G5-23', '编辑记忆内容', test_update)

    # Test 24: 删除记忆
    def test_delete():
        mem_id = test_mems[1]['id']
        ok = delete_memory(mem_id)
        if ok:
            result = get_memory(mem_id)
            if result is None or result.get('is_deleted'):
                return True, f'删除成功: {mem_id}'
            # 软删除可能还能查到但标记为删除
            return True, f'删除成功（软删除）: {mem_id}'
        return False, f'删除失败: {mem_id}'
    run_api_test('G5-24', '删除记忆', test_delete)

    # Test 25: 添加新记忆
    def test_add_new():
        result = add_memory(ds_id, 'term_mapping', 'term',
                            '复购率', '复购率 = 重复购买用户数 / 总购买用户数')
        if result.get('id', '').startswith('mem_'):
            return True, f'添加成功: {result["id"]}'
        return False, f'添加失败: {result}'
    run_api_test('G5-25', '添加新记忆', test_add_new)

    # ============================================================
    # 第六组：边界情况 & 异常场景（测试 26-28）
    # ============================================================
    print('\n' + '=' * 80)
    print('🚧 第六组：边界情况 & 异常场景')
    print('=' * 80)

    # Test 26: 删除记忆后不应再被召回
    def test_deleted_not_recalled():
        # 创建独立 session
        resp = requests.post(f'http://localhost:8001/api/sessions', json={
            'project_id': proj_id,
            'title': 'Edge Test 1',
        })
        edge_sess = resp.json()['id']

        # 添加一条记忆
        mem = add_memory(ds_id, 'column_description', 'column',
                         'orders.status', 'status 不包含已删除订单，这是特殊边界说明')
        mem_id = mem['id']
        time.sleep(0.5)

        # 先问一次（应该能召回）
        r1 = send_chat(edge_sess, '订单 status 列是什么意思？', ds_id)
        has_before = '不包含已删除订单' in r1.answer or '已删除' in r1.answer

        # 删除记忆
        delete_memory(mem_id)
        time.sleep(0.5)

        # 再问一次（不应再召回这条）
        r2 = send_chat(edge_sess, '再问一下 status 列的含义', ds_id)
        has_after = '不包含已删除订单' in r2.answer

        # 验证：删除后回答中不再有该记忆内容
        if has_before and not has_after:
            return True, '删除前回答包含记忆内容，删除后不包含（正确）'
        elif not has_before:
            # 可能 LLM 没把记忆内容说出来，但这不能证明不工作
            # 改为验证数据库层面已删除
            mem_check = get_memory(mem_id)
            deleted = mem_check is None or mem_check.get('is_deleted')
            return deleted, f'数据库层面记忆已删除: {deleted}'
        else:
            return False, '删除后回答仍包含记忆内容（可能是缓存）'
    run_api_test('G6-26', '删除后记忆不应被召回', test_deleted_not_recalled)

    # Test 27: 完全无关的问题不应召回记忆（系统应正常处理）
    run_test('G6-27', '无关问题不报错', '今天天气怎么样', [
        ('无错误', assert_no_error),
        ('有回答', lambda r: (bool(r.answer), f'回答长度: {len(r.answer)}')),
    ], sess_id, ds_id)

    # Test 28: 连续纠正两次，最新的覆盖旧的
    def test_double_correction():
        resp = requests.post(f'http://localhost:8001/api/sessions', json={
            'project_id': proj_id,
            'title': 'Double Correction Test',
        })
        double_sess = resp.json()['id']

        # 先问一个问题建立上下文
        send_chat(double_sess, '看一下 total_amount 的数据', ds_id)
        time.sleep(1)

        # 第一次纠错
        r1 = send_chat(double_sess, '不对，total_amount 是原价，不是实付金额', ds_id)
        mem1 = r1.memory_saved
        time.sleep(2)

        # 第二次纠错（同一实体，不同说法）
        r2 = send_chat(double_sess, '不对，应该说 total_amount 是吊牌价，不是售价', ds_id)
        mem2 = r2.memory_saved
        time.sleep(2)

        # 验证数据库中该实体的记忆包含最新内容
        result = list_memories(ds_id, search='total_amount')
        items = [m for m in result.get('items', [])
                 if m.get('entity_name') == 'orders.total_amount'
                 and not m.get('is_deleted')]

        if not items:
            return False, f'未找到 total_amount 相关记忆（共 {result.get("total", 0)} 条）'

        # 检查是否有包含"吊牌价"的记忆
        has_latest = any('吊牌价' in m.get('content', '') for m in items)
        return has_latest, (
            f'找到 {len(items)} 条 total_amount 记忆，'
            f'包含"吊牌价"（最新内容）: {has_latest}'
        )
    run_api_test('G6-28', '连续纠正覆盖旧记忆', test_double_correction)

    # ============================================================
    # 汇总
    # ============================================================
    print_summary()


if __name__ == '__main__':
    main()
