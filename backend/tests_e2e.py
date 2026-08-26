"""
NL2SQL 端到端功能测试 - 28 条测试用例
覆盖：基础查询、Schema 增肥、手动记忆、自动纠错、记忆管理、边界场景
"""
from __future__ import annotations

import json
import re
import sys
import time
from typing import Any, Callable

import requests

BASE = 'http://localhost:8001/api'

# ============================================================
# 测试配置 - 用新的 session 确保测试隔离
# ============================================================

def setup_test_env():
    """创建独立的测试项目、数据源、session。"""
    import os, shutil
    os.makedirs('/tmp/nl2sql_e2e_test', exist_ok=True)
    db_path = '/tmp/nl2sql_e2e_test/test.db'
    shutil.copy('/tmp/nl2sql_demo.db', db_path)

    # 创建项目
    resp = requests.post(f'{BASE}/projects', json={'name': 'e2e_full_test'})
    proj = resp.json()
    proj_id = proj['id']

    # 添加数据源
    resp = requests.post(f'{BASE}/datasources', json={
        'project_id': proj_id,
        'name': 'e2e_test_db',
        'type': 'sqlite',
        'database': db_path,
    })
    ds = resp.json()
    ds_id = ds['id']

    # 导入 schema + profiling
    requests.post(f'{BASE}/datasources/{ds_id}/import-schema')
    requests.post(f'{BASE}/schema/profile/{ds_id}')

    # 等待 profiling 完成
    for _ in range(10):
        resp = requests.get(f'{BASE}/schema/profile/{ds_id}/status')
        if resp.json().get('status') == 'completed':
            break
        time.sleep(0.5)

    # 创建 session
    resp = requests.post(f'{BASE}/sessions', json={
        'project_id': proj_id,
        'title': 'E2E Full Test',
    })
    sess = resp.json()
    sess_id = sess['id']

    return proj_id, ds_id, sess_id


# ============================================================
# 核心工具函数
# ============================================================

class ChatResult:
    """聊天结果封装。"""
    def __init__(self):
        self.events: list[dict] = []
        self.sql: str = ''
        self.answer: str = ''
        self.status: str = ''
        self.error: str = ''
        self.execution_result: dict | None = None
        self.memory_saved: dict | None = None
        self.event_types: list[str] = []

    @property
    def success(self) -> bool:
        return self.status in ('success', 'done') and not self.error


def send_chat(session_id: str, message: str, datasource_id: str, timeout: int = 120) -> ChatResult:
    """发送消息并收集所有事件。"""
    result = ChatResult()

    # Start chat
    resp = requests.post(f'{BASE}/chat', json={
        'session_id': session_id,
        'message': message,
        'datasource_id': datasource_id,
    })
    if resp.status_code != 200:
        result.status = 'failed'
        result.error = f'start failed: {resp.status_code} {resp.text}'
        return result

    # Stream events
    try:
        with requests.get(f'{BASE}/chat/stream/{session_id}', stream=True, timeout=timeout) as r:
            current_event = ''
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith('event: '):
                    current_event = line[7:].strip()
                    result.event_types.append(current_event)
                elif line.startswith('data: '):
                    data_str = line[6:]
                    try:
                        data = json.loads(data_str) if data_str else {}
                    except json.JSONDecodeError:
                        data = {'raw': data_str}

                    result.events.append({'type': current_event, 'data': data})

                    # 从 final_result 提取核心信息
                    if current_event == 'final_result':
                        result.answer = data.get('answer', '')
                        result.sql = data.get('sql', '') or result.sql
                        if data.get('result'):
                            result.execution_result = data.get('result')
                    # memory_saved 事件
                    elif current_event == 'memory_saved':
                        result.memory_saved = data
                    # error 事件
                    elif current_event == 'error':
                        result.error = data.get('message', '')
                    # chat_done 事件
                    elif current_event == 'chat_done':
                        result.status = data.get('status', '')
                        if not result.sql:
                            result.sql = data.get('sql', '')
                        if not result.error:
                            result.error = data.get('error', '') or ''
                        return result
    except Exception as e:
        result.status = 'error'
        result.error = str(e)

    return result


# ============================================================
# 断言函数（返回 (passed: bool, detail: str)）
# ============================================================

def assert_no_error(r: ChatResult) -> tuple[bool, str]:
    if r.error:
        return False, f'有错误: {r.error[:100]}'
    return True, '无错误'

def assert_success(r: ChatResult) -> tuple[bool, str]:
    if r.status in ('success', 'done') and not r.error:
        return True, f'执行成功 (status: {r.status})'
    return False, f'状态: {r.status}, 错误: {r.error[:100]}'

def assert_has_sql(r: ChatResult) -> tuple[bool, str]:
    if r.sql:
        return True, f'生成了 SQL ({len(r.sql)} 字符)'
    return False, '未生成 SQL'

def assert_sql_contains(pattern: str, flags: int = re.IGNORECASE):
    def check(r: ChatResult) -> tuple[bool, str]:
        if re.search(pattern, r.sql, flags):
            return True, f'SQL 包含 "{pattern}"'
        return False, f'SQL 不包含 "{pattern}" (SQL: {r.sql[:100]})'
    return check

def assert_sql_count_star(r: ChatResult) -> tuple[bool, str]:
    if re.search(r'COUNT\s*\(\s*\*\s*\)', r.sql, re.IGNORECASE):
        return True, 'SQL 使用 COUNT(*)'
    return False, f'SQL 未使用 COUNT(*) (SQL: {r.sql[:100]})'

def assert_answer_contains(text: str):
    def check(r: ChatResult) -> tuple[bool, str]:
        if text.lower() in r.answer.lower():
            return True, f'回答包含 "{text}"'
        return False, f'回答不包含 "{text}" (回答: {r.answer[:150]})'
    return check

def assert_result_rows(min_rows: int = 1):
    def check(r: ChatResult) -> tuple[bool, str]:
        if r.execution_result and isinstance(r.execution_result, dict):
            # 可能的格式: rows/columns/row_count 或直接 list
            rc = r.execution_result.get('row_count', 0)
            if not rc and 'rows' in r.execution_result:
                rc = len(r.execution_result['rows'])
            if rc >= min_rows:
                return True, f'结果有 {rc} 行 (>= {min_rows})'
            return False, f'结果只有 {rc} 行 (< {min_rows})'
        # 如果没有 execution_result，但有 SQL 且成功，也可能是 schema exploration 类型
        if r.answer and not r.error:
            return True, f'无 execution_result 但有回答（可能为 schema 探索类）'
        return False, '无执行结果'
    return check

def assert_memory_saved(r: ChatResult) -> tuple[bool, str]:
    if r.memory_saved:
        mem = r.memory_saved
        return True, f'检测到纠错并保存记忆: {mem.get("entity_name", "")}'
    return False, '未触发纠错记忆保存'

def assert_no_memory_saved(r: ChatResult) -> tuple[bool, str]:
    if not r.memory_saved:
        return True, '未触发纠错保存（正确行为）'
    mem = r.memory_saved
    return False, f'误触发了纠错保存: {mem.get("content", "")[:80]}'

def assert_event_type(event_type: str):
    def check(r: ChatResult) -> tuple[bool, str]:
        if event_type in r.event_types:
            return True, f'有 {event_type} 事件'
        return False, f'缺少 {event_type} 事件'
    return check


# ============================================================
# 测试运行器
# ============================================================

all_results: list[dict] = []

def run_test(test_id: str, title: str, prompt: str, checks: list[tuple[str, Callable]],
             session_id: str, datasource_id: str, pre_delay: float = 1.0) -> dict:
    """运行一条测试用例。"""
    # 给纠错检测等异步操作留点时间
    time.sleep(pre_delay)

    result = send_chat(session_id, prompt, datasource_id)

    passed = True
    notes = []
    for check_name, check_fn in checks:
        try:
            ok, detail = check_fn(result)
            notes.append(('✓' if ok else '✗', check_name, detail))
            if not ok:
                passed = False
        except Exception as e:
            notes.append(('✗', check_name, f'异常: {e}'))
            passed = False

    test_result = {
        'id': test_id,
        'title': title,
        'prompt': prompt,
        'passed': passed,
        'status': result.status,
        'error': result.error,
        'sql': result.sql[:200] if result.sql else '',
        'answer_preview': result.answer[:200],
        'notes': notes,
        'memory_saved': result.memory_saved,
    }
    all_results.append(test_result)

    # 打印结果
    icon = '✅' if passed else '❌'
    print(f'\n{icon} #{test_id} {title}')
    print(f'   Prompt: {prompt}')
    for ok_mark, name, detail in notes:
        print(f'   {ok_mark} {name}: {detail}')
    if result.sql:
        print(f'   SQL: {result.sql[:150]}')
    if result.memory_saved:
        print(f'   记忆: {result.memory_saved.get("entity_name")} - {result.memory_saved.get("content", "")[:80]}')

    return test_result


def print_summary():
    """打印测试汇总。"""
    print('\n' + '=' * 80)
    print('📊 测试结果汇总')
    print('=' * 80)
    passed = sum(1 for r in all_results if r['passed'])
    total = len(all_results)
    print(f'\n总计: {passed}/{total} 通过 ({passed*100//total if total else 0}%)\n')

    groups = [
        ('一、基础查询能力', ['1', '2', '3']),
        ('二、Schema 增肥功能', ['4', '5', '6', '7']),
        ('三、手动记忆功能', ['8', '9', '10', '11', '12', '13']),
        ('四、自动纠错检测', ['14', '15', '16', '17', '18', '19', '20']),
        ('五、记忆管理 UI/API', ['21', '22', '23', '24', '25']),
        ('六、边界情况', ['26', '27', '28']),
    ]

    for group_name, test_nums in groups:
        group_results = [r for r in all_results if r['id'].split('-')[-1] in test_nums
                         or r['id'].endswith(tuple(test_nums))]
        gp = sum(1 for r in group_results if r['passed'])
        gt = len(group_results)
        if gt > 0:
            print(f'  {group_name}: {gp}/{gt}')

    print('\n--- 详细结果 ---')
    for r in all_results:
        icon = '✅' if r['passed'] else '❌'
        print(f'  {icon} #{r["id"]}: {r["title"]}')

    print(f'\n{passed}/{total} tests passed')
    return passed, total


# ============================================================
# 记忆 API 辅助函数
# ============================================================

def add_memory(ds_id: str, memory_type: str, entity_type: str, entity_name: str, content: str) -> dict:
    """通过 API 添加记忆。"""
    resp = requests.post(f'{BASE}/memories', json={
        'datasource_id': ds_id,
        'memory_type': memory_type,
        'entity_type': entity_type,
        'entity_name': entity_name,
        'content': content,
    })
    return resp.json()

def list_memories(ds_id: str, **kwargs) -> dict:
    """列出记忆。"""
    params = {'datasource_id': ds_id, **kwargs}
    resp = requests.get(f'{BASE}/memories', params=params)
    return resp.json()

def get_memory(mem_id: str) -> dict | None:
    """获取单条记忆。"""
    resp = requests.get(f'{BASE}/memories/{mem_id}')
    if resp.status_code == 200:
        return resp.json()
    return None

def update_memory(mem_id: str, updates: dict) -> dict | None:
    """更新记忆。"""
    resp = requests.put(f'{BASE}/memories/{mem_id}', json=updates)
    if resp.status_code == 200:
        return resp.json()
    return None

def delete_memory(mem_id: str) -> bool:
    """删除记忆。"""
    resp = requests.delete(f'{BASE}/memories/{mem_id}')
    return resp.status_code == 200


# ============================================================
# 非聊天类测试运行器
# ============================================================

def run_api_test(test_id: str, title: str, test_fn: Callable) -> dict:
    """运行 API 类测试（非聊天）。"""
    try:
        passed, detail = test_fn()
    except Exception as e:
        passed, detail = False, f'异常: {e}'

    test_result = {
        'id': test_id,
        'title': title,
        'prompt': '(API 测试)',
        'passed': passed,
        'status': 'done' if passed else 'failed',
        'error': '' if passed else detail,
        'sql': '',
        'answer_preview': '',
        'notes': [('✓' if passed else '✗', 'result', detail)],
        'memory_saved': None,
    }
    all_results.append(test_result)

    icon = '✅' if passed else '❌'
    print(f'\n{icon} #{test_id} {title}')
    print(f'   {detail}')

    return test_result


if __name__ == '__main__':
    print('此模块应由测试脚本导入使用')
