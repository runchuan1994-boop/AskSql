"""验证 intent 字段在 state dict 中是对象还是 dict"""
from nl2sql.agent.state import AgentState, IntentResult

# 构建 state 然后 dump
intent = IntentResult(tables=[{"name": "orders", "reason": "test"}])
state = AgentState(
    project_id="test",
    user_query="test",
    intent=intent,
)

state_dict = state.model_dump(mode="python")
print(f"state_dict type: {type(state_dict)}")
print(f"intent in state_dict: {'intent' in state_dict}")
print(f"intent type: {type(state_dict.get('intent'))}")

intent_val = state_dict.get("intent")
print(f"intent.tables: ", end="")
try:
    print(intent_val.tables)
except AttributeError as e:
    print(f"AttributeError: {e}")

print(f"intent['tables']: ", end="")
try:
    print(intent_val['tables'])
except (TypeError, KeyError) as e:
    print(f"Error: {e}")
