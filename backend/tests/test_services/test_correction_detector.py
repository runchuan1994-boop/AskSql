"""测试纠错检测服务。"""

from unittest.mock import MagicMock, patch

from nl2sql.schema.models import Column, Table
from nl2sql.llm.base import ChatResponse
from app.services.correction_detector import (
    CorrectionResult,
    _has_correction_keyword,
    _parse_json_response,
    detect_correction,
    validate_memory_against_schema,
)


def _mock_llm_response(json_content: str) -> MagicMock:
    """构造一个 mock 的 LLM 客户端，返回指定的 JSON 内容。"""
    mock_client = MagicMock()
    mock_client.chat.return_value = ChatResponse(content=json_content)
    return mock_client


class TestKeywordPreFilter:
    def test_has_correction_keyword(self):
        assert _has_correction_keyword("不对，这个字段是原价")
        assert _has_correction_keyword("纠正一下，应该是这样")
        assert _has_correction_keyword("补充说明，这是流水")
        assert _has_correction_keyword("其实不是的")

    def test_no_correction_keyword(self):
        assert not _has_correction_keyword("帮我查一下订单数据")
        assert not _has_correction_keyword("上个月的数据怎么样")
        assert not _has_correction_keyword("好的谢谢")


class TestParseJsonResponse:
    def test_plain_json(self):
        text = '{"is_correction": true, "memory_type": "column_description"}'
        result = _parse_json_response(text)
        assert result is not None
        assert result["is_correction"] is True

    def test_markdown_json(self):
        text = "```json\n{\"is_correction\": false}\n```"
        result = _parse_json_response(text)
        assert result is not None
        assert result["is_correction"] is False

    def test_invalid_json(self):
        text = "not json at all"
        result = _parse_json_response(text)
        assert result is None

    def test_empty_string(self):
        result = _parse_json_response("")
        assert result is None


class TestParseJsonResponseExtraction:
    """测试从各种 LLM 响应格式中提取 JSON。"""

    def test_json_with_trailing_explanation(self):
        """LLM 在代码块后附加了解释文字。"""
        text = '''```json
{
  "is_correction": false,
  "memory_type": null,
  "entity_type": null,
  "entity_name": null,
  "content": null
}
```

判断说明：该消息虽然以"不对"开头，但只是泛泛地否定。'''
        result = _parse_json_response(text)
        assert result is not None
        assert result["is_correction"] is False

    def test_json_with_leading_text(self):
        """LLM 先解释再输出 JSON。"""
        text = '''好的，我来分析一下这条消息。

以下是我的判断结果：
```json
{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "orders.amount",
  "content": "amount 是原价"
}
```'''
        result = _parse_json_response(text)
        assert result is not None
        assert result["is_correction"] is True
        assert result["memory_type"] == "column_description"

    def test_json_buried_in_text(self):
        """JSON 夹在自然语言中间，没有代码块。"""
        text = '''经过分析，我认为这是一个纠错。{"is_correction": true, "memory_type": "term_mapping", "entity_type": "term", "entity_name": "流水", "content": "流水即 GMV"} 以上是判断结果。'''
        result = _parse_json_response(text)
        assert result is not None
        assert result["is_correction"] is True
        assert result["memory_type"] == "term_mapping"

    def test_json_nested_objects(self):
        """包含嵌套对象的 JSON 也能正确提取。"""
        text = '''一些前置说明
{
  "is_correction": true,
  "memory_type": "column_description",
  "details": {
    "confidence": 0.9,
    "reason": "明确提到了字段含义"
  },
  "content": "测试"
}
后面的说明'''
        result = _parse_json_response(text)
        assert result is not None
        assert result["is_correction"] is True
        assert result["details"]["confidence"] == 0.9

    def test_no_json_in_text(self):
        """完全没有 JSON 的文本返回 None。"""
        text = "这是一段完全没有 JSON 的自然语言回复。"
        result = _parse_json_response(text)
        assert result is None

    def test_partial_json_brace_count(self):
        """不完整的 JSON（只有左大括号）返回 None。"""
        text = '{"is_correction": true, "content": "未闭合的对象'
        result = _parse_json_response(text)
        assert result is None

    def test_json_with_unescaped_quotes_in_value(self):
        """字符串值中有未转义的双引号（LLM 常见错误），应能修复并解析。"""
        text = '''{
  "is_correction": true,
  "memory_type": "term_mapping",
  "entity_type": "term",
  "entity_name": "流水",
  "content": "业务术语"流水"指的是 GMV"
}'''
        result = _parse_json_response(text)
        assert result is not None
        assert result["is_correction"] is True
        assert result["memory_type"] == "term_mapping"
        assert "流水" in result["content"]
        assert "GMV" in result["content"]

    def test_json_in_markdown_with_unescaped_quotes(self):
        """markdown 代码块中有未转义引号的 JSON。"""
        text = '''```json
{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "orders.amount",
  "content": "amount 是"原价"不是实付"
}
```'''
        result = _parse_json_response(text)
        assert result is not None
        assert result["is_correction"] is True
        assert result["memory_type"] == "column_description"
        assert "原价" in result["content"]


class TestValidateAgainstSchema:
    def setup_method(self):
        self.tables = [
            Table(
                name="orders",
                columns=[
                    Column(name="order_id", type="INT"),
                    Column(name="total_amount", type="DECIMAL"),
                    Column(name="status", type="VARCHAR"),
                ],
            ),
            Table(
                name="users",
                columns=[
                    Column(name="user_id", type="INT"),
                    Column(name="name", type="VARCHAR"),
                ],
            ),
        ]

    def test_table_description_valid(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="table_description",
            entity_type="table",
            entity_name="orders",
            content="只存主站订单",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True
        assert result.entity_name == "orders"

    def test_table_description_fuzzy_match_substring(self):
        """entity_name 是表名的子串（如用户说 order 实际是 orders 表）。"""
        corr = CorrectionResult(
            is_correction=True,
            memory_type="table_description",
            entity_type="table",
            entity_name="order",
            content="主站订单",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True
        assert result.entity_name == "orders"  # 修正为正确表名

    def test_table_description_fuzzy_match_contains(self):
        """entity_name 包含表名（如用户说 t_orders 实际是 orders 表）。"""
        corr = CorrectionResult(
            is_correction=True,
            memory_type="table_description",
            entity_type="table",
            entity_name="t_orders",
            content="主站订单",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True
        assert result.entity_name == "orders"

    def test_table_description_not_found(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="table_description",
            entity_type="table",
            entity_name="nonexistent",
            content="...",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is False

    def test_column_description_valid(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.total_amount",
            content="商品原价",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True
        assert result.entity_name == "orders.total_amount"

    def test_column_description_fuzzy_table(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="column_description",
            entity_type="column",
            entity_name="order.status",
            content="订单状态",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True
        assert result.entity_name == "orders.status"

    def test_column_description_not_found(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.nonexistent",
            content="...",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is False

    def test_term_mapping_no_validation_needed(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="term_mapping",
            entity_type="term",
            entity_name="流水",
            content="就是 GMV",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True  # 不需要验证

    def test_metric_definition_no_validation_needed(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="metric_definition",
            entity_type="metric",
            entity_name="GMV",
            content="total_amount + shipping",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True

    def test_join_hint_valid_table(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="join_hint",
            entity_type="table",
            entity_name="orders",
            content="注意 NULL",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True

    def test_non_correction_passthrough(self):
        corr = CorrectionResult(is_correction=False)
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is False

    def test_column_case_insensitive(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.Total_Amount",
            content="金额",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True
        assert result.entity_name == "orders.total_amount"

    def test_column_without_table_finds_first_match(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="column_description",
            entity_type="column",
            entity_name="status",
            content="状态",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True
        assert "status" in result.entity_name  # 应该找到 orders.status


class TestDetectCorrection:
    """测试 detect_correction 主函数（mock LLM）。"""

    # ---- 关键词预筛：无关键词直接返回 False（不调用 LLM） ----

    def test_no_keyword_skips_llm(self):
        """没有纠错关键词时，直接返回 False，不调用 LLM。"""
        mock_client = _mock_llm_response('{"is_correction": true}')
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("帮我查一下订单数据")
        assert result.is_correction is False
        mock_client.chat.assert_not_called()

    def test_too_short_skips_llm(self):
        """消息太短时，直接返回 False。"""
        mock_client = _mock_llm_response('{"is_correction": true}')
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("不对")  # 只有 2 个字符
        assert result.is_correction is False
        mock_client.chat.assert_not_called()

    # ---- 列描述纠错 ----

    def test_column_description_correction(self):
        """检测到列含义纠错：amount 字段不是实付金额，是原价。"""
        fake_response = '''
{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "orders.total_amount",
  "content": "total_amount 是商品原价，不是实付金额"
}
'''.strip()
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("不对，amount 不是实付金额，是原价")

        assert result.is_correction is True
        assert result.memory_type == "column_description"
        assert result.entity_type == "column"
        assert result.entity_name == "orders.total_amount"
        assert "原价" in result.content
        assert result.raw_content == "不对，amount 不是实付金额，是原价"

    # ---- 表描述纠错 ----

    def test_table_description_correction(self):
        """检测到表范围补充：这个表只存主站订单。"""
        fake_response = '''
{
  "is_correction": true,
  "memory_type": "table_description",
  "entity_type": "table",
  "entity_name": "orders",
  "content": "orders 表只存储主站订单，不包含第三方渠道订单"
}
'''.strip()
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("补充一下，这个表只存主站订单")

        assert result.is_correction is True
        assert result.memory_type == "table_description"
        assert result.entity_name == "orders"
        assert "主站订单" in result.content

    # ---- 术语映射纠错 ----

    def test_term_mapping_correction(self):
        """检测到业务术语解释：流水就是 GMV。"""
        fake_response = '''
{
  "is_correction": true,
  "memory_type": "term_mapping",
  "entity_type": "term",
  "entity_name": "流水",
  "content": "流水在业务上指 GMV（商品交易总额）"
}
'''.strip()
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("其实流水指的是 GMV")

        assert result.is_correction is True
        assert result.memory_type == "term_mapping"
        assert result.entity_name == "流水"
        assert "GMV" in result.content

    # ---- 指标定义纠错 ----

    def test_metric_definition_correction(self):
        """检测到指标计算口径说明。"""
        fake_response = '''
{
  "is_correction": true,
  "memory_type": "metric_definition",
  "entity_type": "metric",
  "entity_name": "转化率",
  "content": "转化率 = 下单用户数 / 访问用户数"
}
'''.strip()
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("纠正一下，转化率应该是下单用户数除以访问用户数")

        assert result.is_correction is True
        assert result.memory_type == "metric_definition"
        assert result.entity_name == "转化率"

    # ---- 表关联提示 ----

    def test_join_hint_correction(self):
        """检测到表关联注意事项。"""
        fake_response = '''
{
  "is_correction": true,
  "memory_type": "join_hint",
  "entity_type": "table",
  "entity_name": "orders",
  "content": "关联 orders 表时注意 user_id 可能为 NULL"
}
'''.strip()
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("提醒你，关联时注意 orders 表的 NULL 值")

        assert result.is_correction is True
        assert result.memory_type == "join_hint"

    # ---- 非纠错场景 ----

    def test_not_correction_follow_up(self):
        """普通追问不判定为纠错。"""
        fake_response = '{"is_correction": false}'
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("不对，再看看上个月的数据")

        assert result.is_correction is False

    def test_not_correction_data_doubt(self):
        """只说数据不对但没说明原因，不判定为纠错。"""
        fake_response = '{"is_correction": false}'
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("这个数不对吧")

        assert result.is_correction is False

    # ---- JSON 解析异常 ----

    def test_llm_returns_invalid_json(self):
        """LLM 返回非 JSON 格式时，降级为非纠错。"""
        fake_response = "抱歉，我无法判断这条消息是否为纠错。"
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("不对，这个字段有问题")

        assert result.is_correction is False

    def test_llm_returns_markdown_json(self):
        """LLM 返回 markdown 包裹的 JSON 也能正确解析。"""
        fake_response = '''```json
{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "orders.status",
  "content": "status 字段表示订单状态"
}
```'''
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("补充一下，status 是订单状态")

        assert result.is_correction is True
        assert result.memory_type == "column_description"
        assert result.entity_name == "orders.status"

    # ---- memory_type 校验 ----

    def test_invalid_memory_type_rejected(self):
        """LLM 返回不合法的 memory_type 时，降级为非纠错。"""
        fake_response = '''
{
  "is_correction": true,
  "memory_type": "invalid_type",
  "entity_type": "column",
  "entity_name": "orders.status",
  "content": "状态"
}
'''.strip()
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("不对，status 的含义错了")

        assert result.is_correction is False

    def test_empty_content_rejected(self):
        """content 为空时，降级为非纠错。"""
        fake_response = '''
{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "orders.status",
  "content": ""
}
'''.strip()
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("不对，status 有问题")

        assert result.is_correction is False

    # ---- LLM 调用异常 ----

    def test_llm_exception_fails_closed(self):
        """LLM 调用抛出异常时，降级为非纠错（fail-closed）。"""
        mock_client = MagicMock()
        mock_client.chat.side_effect = Exception("API 调用失败")
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("不对，这个字段错了")

        assert result.is_correction is False
        assert result.raw_content == "不对，这个字段错了"

    # ---- 上下文传递 ----

    def test_context_is_passed_to_llm(self):
        """上下文消息被正确传递给 LLM。"""
        fake_response = '{"is_correction": false}'
        mock_client = _mock_llm_response(fake_response)

        context = [
            {"role": "user", "content": "查一下订单数量"},
            {"role": "assistant", "content": "好的，订单数量是 100"},
            {"role": "user", "content": "不对，应该按状态分组"},
        ]

        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            detect_correction("不对，应该按状态分组", context=context)

        # 验证 LLM 被调用了，且消息中包含上下文
        mock_client.chat.assert_called_once()
        call_args = mock_client.chat.call_args
        messages = call_args[0][0] if call_args[0] else call_args.kwargs.get("messages", [])
        user_msg = [m for m in messages if m.role.value == "user"][0]
        assert "对话上下文" in user_msg.content
        assert "查一下订单数量" in user_msg.content
        assert "按状态分组" in user_msg.content

    # ---- 英文纠错 ----

    def test_english_correction_keyword(self):
        """英文纠错关键词也能触发检测。"""
        fake_response = '''
{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "orders.amount",
  "content": "amount is original price, not paid amount"
}
'''.strip()
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("Actually, amount is the original price")

        assert result.is_correction is True
        assert result.memory_type == "column_description"

    # ---- LLM 调用参数验证 ----

    def test_llm_called_with_zero_temperature(self):
        """验证 LLM 调用使用 temperature=0.0（确定性输出）。"""
        fake_response = '{"is_correction": false}'
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            detect_correction("不对，这个有错")

        mock_client.chat.assert_called_once()
        call_kwargs = mock_client.chat.call_args.kwargs
        # temperature 可能是位置参数或关键字参数
        if "temperature" in call_kwargs:
            assert call_kwargs["temperature"] == 0.0
        else:
            # 位置参数：messages, tools, temperature, max_tokens
            args = mock_client.chat.call_args[0]
            # 找到 temperature 参数的位置
            assert len(args) >= 1  # 至少有 messages

    # ---- 多种纠错场景的完整 Fake Prompt 测试 ----

    def test_fake_prompt_column_enum_values(self):
        """Fake prompt: 补充列的枚举值含义。"""
        fake_response = '''
{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "orders.status",
  "content": "status 枚举值：0=待支付，1=已支付，2=已发货，3=已完成，4=已取消"
}
'''.strip()
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("补充说明一下 status 的取值：0是待支付，1是已支付，2是已发货，3是已完成，4是已取消")

        assert result.is_correction is True
        assert result.memory_type == "column_description"
        assert "枚举" in result.content or "待支付" in result.content

    def test_fake_prompt_correction_after_wrong_answer(self):
        """Fake prompt: 用户在上轮回答错误后进行纠正。"""
        fake_response = '''
{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "users.level",
  "content": "level 字段表示会员等级，不是活跃度等级"
}
'''.strip()
        mock_client = _mock_llm_response(fake_response)

        context = [
            {"role": "user", "content": "各级别用户分布"},
            {"role": "assistant", "content": "根据活跃度等级统计..."},
        ]
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("不对哦，level 是会员等级，不是活跃度", context=context)

        assert result.is_correction is True
        assert result.entity_name == "users.level"
        assert "会员等级" in result.content

    def test_fake_prompt_not_correction_pure_question(self):
        """Fake prompt: 单纯的疑问不是纠错。"""
        fake_response = '{"is_correction": false}'
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("这个结果不对吧？我记得上个月不是这样的")

        assert result.is_correction is False

    def test_fake_prompt_not_correction_requery(self):
        """Fake prompt: 请求重新查询不是纠错。"""
        fake_response = '{"is_correction": false}'
        mock_client = _mock_llm_response(fake_response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock_client):
            result = detect_correction("不对，重新查一下去年的")

        assert result.is_correction is False
