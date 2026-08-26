"""纠错检测服务：从用户消息中检测是否为纠错/补充，并提取结构化记忆。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client

logger = logging.getLogger(__name__)


# 纠错关键词列表（用于预筛）
CORRECTION_KEYWORDS = [
    "不对", "不是", "错了", "纠正", "补充", "说明", "解释一下",
    "其实", "应该是", "指的是", "实际上", "搞错了", "更正",
    "注意", "提醒你", "告诉你", "不是的", "不对的",
    "说错了", "讲错了", "不对哦",
    "no,", "not ", "wrong", "actually", "correction",
]


def _has_correction_keyword(text: str) -> bool:
    """检查文本是否包含纠错关键词（快速预筛）。"""
    text_lower = text.lower()
    for kw in CORRECTION_KEYWORDS:
        if kw.lower() in text_lower:
            return True
    return False


DETECTION_SYSTEM_PROMPT = """你是一位数据库 schema 知识抽取专家。

任务：判断用户的消息是否在纠正或补充数据库 schema 的业务含义。

什么算纠错/补充（is_correction = true）：
1. 纠正字段的业务含义（如："amount 不是实付金额，是原价"）
2. 补充表的业务范围（如："这个表只存主站订单"）
3. 解释业务术语（如："流水就是 GMV"）
4. 说明指标计算口径（如："转化率 = 下单用户数 / 访问用户数"）
5. 指出表关联的注意事项（如："关联时注意 NULL 值"）
6. 补充列的枚举值或业务含义

什么不算纠错（is_correction = false）：
1. 普通的追问或换维度（"再看看上个月的"）
2. 数据本身的疑问（"这个数不对吧" 但没说为什么不对）
3. 请求重新查询（"重新查一下"）
4. 表达满意/感谢（"好的，谢谢"）
5. 纯技术问题（"SQL 报错了"）

输出格式：严格的 JSON 格式，包含以下字段：
- is_correction: boolean，是否为纠错/补充
- memory_type: string，记忆类型（仅 is_correction=true 时有效）
  - column_description（列的业务含义补充）
  - table_description（表的业务含义补充）
  - metric_definition（业务指标计算口径）
  - term_mapping（业务术语映射）
  - join_hint（表关联提示）
- entity_type: string，实体类型（column / table / metric / term）
- entity_name: string，实体名称（列名用 table.column 格式，或直接列名）
- content: string，整理后的规范表述（简洁明了的一句话）

如果 is_correction = false，其余字段可以为 null 或空字符串。

⚠️ 重要：JSON 字符串中的双引号必须转义为 \\\"，content 字段内的中文引号「」或不用引号，
绝对不要在 JSON 字符串值中直接使用未转义的英文双引号。
只输出 JSON，不要输出其他解释文字。

请仔细判断，宁缺毋滥，不要误判。"""


@dataclass
class CorrectionResult:
    """纠错检测结果。"""
    is_correction: bool
    memory_type: str | None = None
    entity_type: str | None = None
    entity_name: str | None = None
    content: str = ""
    raw_content: str = ""


def _try_repair_json(json_str: str) -> dict | None:
    """尝试修复常见的 JSON 格式问题（如字符串中未转义的双引号）。

    策略：逐行扫描，识别 `"key": "value"` 模式，
    对于 value 部分中多余的双引号，尝试通过上下文推断正确边界。
    """
    # 只处理常见情况：每一行一个 key-value 对
    lines = json_str.split("\n")
    repaired_lines = []

    for line in lines:
        stripped = line.strip()
        # 匹配 "key": "value" 模式（value 中可能有未转义的双引号）
        m = re.match(r'^"(\w+)":\s*"(.*)"\s*,?\s*$', stripped)
        if m:
            key = m.group(1)
            # value 可能包含未转义的双引号 —— 我们假设
            # 从第一个 " 之后到行末最后一个 " 之前都是 value
            # 然后将 value 内部的双引号替换为中文引号
            after_colon = stripped.split(":", 1)[1].strip()
            # 去掉开头的 " 和结尾的 "（以及可能的逗号）
            if after_colon.startswith('"'):
                after_colon = after_colon[1:]
            # 去掉结尾的 ", 或 "
            after_colon = re.sub(r'"\s*,?\s*$', '', after_colon)
            # 将内部所有未转义的 " 替换为 「」 对（简单替换）
            # 更保守的做法：所有双引号都转义
            repaired_value = after_colon.replace('\\"', '\x00').replace('"', '\\"').replace('\x00', '\\"')
            trailing_comma = "," if stripped.rstrip().endswith(",") else ""
            repaired_lines.append(f'  "{key}": "{repaired_value}"{trailing_comma}')
        else:
            repaired_lines.append(line)

    repaired = "\n".join(repaired_lines)
    try:
        return json.loads(repaired)
    except (json.JSONDecodeError, TypeError):
        return None


def _parse_json_response(text: str) -> dict | None:
    """从 LLM 响应中解析 JSON。

    支持以下格式：
    1. 纯 JSON 字符串
    2. ```json ... ``` 包裹的 markdown 代码块
    3. JSON 在文本中间（前后有说明文字）
    4. 代码块后还有额外说明文字
    5. JSON 中有常见格式问题（未转义的引号等）
    """
    if not text:
        return None

    text = text.strip()

    def _try_parse(s: str) -> dict | None:
        """尝试解析 JSON，失败则尝试修复。"""
        try:
            return json.loads(s.strip())
        except (json.JSONDecodeError, TypeError):
            pass
        # 尝试修复
        repaired = _try_repair_json(s.strip())
        if repaired is not None:
            return repaired
        return None

    # 策略 1：直接尝试解析（纯 JSON）
    result = _try_parse(text)
    if result is not None:
        return result

    # 策略 2：提取 markdown 代码块中的 JSON
    code_block_match = re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if code_block_match:
        result = _try_parse(code_block_match.group(1))
        if result is not None:
            return result

    # 策略 3：从文本中提取第一个完整的 JSON 对象（{...}）
    brace_count = 0
    start = -1
    for i, char in enumerate(text):
        if char == "{":
            if brace_count == 0:
                start = i
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0 and start >= 0:
                result = _try_parse(text[start:i + 1])
                if result is not None:
                    return result
                start = -1  # 继续找下一个

    return None


def detect_correction(
    user_message: str,
    context: list[dict] | None = None,
) -> CorrectionResult:
    """检测用户消息是否为纠错/补充。

    Args:
        user_message: 用户消息文本
        context: 上下文消息列表（可选，[{role, content}, ...]）

    Returns:
        CorrectionResult
    """
    # 1. 关键词预筛：没有关键词直接跳过
    if not _has_correction_keyword(user_message):
        return CorrectionResult(is_correction=False, raw_content=user_message)

    # 2. 太短的消息跳过
    if len(user_message.strip()) < 4:
        return CorrectionResult(is_correction=False, raw_content=user_message)

    # 3. LLM 检测
    try:
        # 构建上下文
        context_text = ""
        if context:
            context_lines = []
            for msg in context[-6:]:  # 最近 6 条
                role = "用户" if msg.get("role") == "user" else "助手"
                context_lines.append(f"{role}: {msg.get('content', '')}")
            context_text = "对话上下文：\n" + "\n".join(context_lines) + "\n\n"

        user_msg = f"""{context_text}当前用户消息：
{user_message}

请判断这条用户消息是否在纠正或补充数据库 schema 的业务含义。
输出 JSON。"""

        messages = [
            Message(role=MessageRole.SYSTEM, content=DETECTION_SYSTEM_PROMPT),
            Message(role=MessageRole.USER, content=user_msg),
        ]

        llm = create_llm_client()
        response = llm.chat(messages, temperature=0.0)

        parsed = _parse_json_response(response.content)
        if parsed is None:
            logger.warning("Failed to parse correction detection response: %s", response.content)
            return CorrectionResult(is_correction=False, raw_content=user_message)

        is_correction = bool(parsed.get("is_correction", False))

        if not is_correction:
            return CorrectionResult(is_correction=False, raw_content=user_message)

        memory_type = parsed.get("memory_type") or ""
        entity_type = parsed.get("entity_type") or ""
        entity_name = parsed.get("entity_name") or ""
        content = parsed.get("content") or ""

        # 校验 memory_type 是否合法
        valid_types = {"column_description", "table_description",
                       "metric_definition", "term_mapping", "join_hint"}
        if memory_type not in valid_types:
            return CorrectionResult(is_correction=False, raw_content=user_message)

        if not content:
            return CorrectionResult(is_correction=False, raw_content=user_message)

        return CorrectionResult(
            is_correction=True,
            memory_type=memory_type,
            entity_type=entity_type or None,
            entity_name=entity_name or None,
            content=content.strip(),
            raw_content=user_message,
        )

    except Exception as e:
        logger.warning("Correction detection failed: %s", e)
        return CorrectionResult(is_correction=False, raw_content=user_message)


def validate_memory_against_schema(
    correction: CorrectionResult,
    tables: list,
) -> CorrectionResult:
    """验证提取的记忆是否与 schema 中的实体匹配。

    对于 table_description / column_description / join_hint，
    检查 entity_name 对应的表/列是否真实存在。

    对于 term_mapping / metric_definition，不需要验证。
    """
    if not correction.is_correction:
        return correction

    mem_type = correction.memory_type
    entity_name = correction.entity_name or ""

    # 术语/指标不需要验证
    if mem_type in ("term_mapping", "metric_definition"):
        return correction

    # 表级验证
    if mem_type in ("table_description", "join_hint"):
        table_names = {t.name for t in tables}
        if entity_name in table_names:
            return correction
        # 模糊匹配：表名包含 entity_name 或反之
        for t in tables:
            if entity_name.lower() in t.name.lower() or t.name.lower() in entity_name.lower():
                correction.entity_name = t.name
                return correction
        # 找不到对应的表，取消纠错判定
        correction.is_correction = False
        return correction

    # 列级验证
    if mem_type == "column_description":
        # entity_name 可能是 table.column 或 column
        if "." in entity_name:
            table_name, col_name = entity_name.rsplit(".", 1)
        else:
            table_name = ""
            col_name = entity_name

        # 找表
        matching_tables = []
        if table_name:
            for t in tables:
                if table_name.lower() in t.name.lower() or t.name.lower() in table_name.lower():
                    matching_tables.append(t)
        else:
            matching_tables = list(tables)

        # 在匹配的表中找列
        for t in matching_tables:
            for col in t.columns:
                if col.name.lower() == col_name.lower():
                    correction.entity_name = f"{t.name}.{col.name}"
                    return correction

        # 找不到对应的列，取消纠错判定
        correction.is_correction = False
        return correction

    return correction
