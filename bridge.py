# bridge.py
# 前端输入 → LLM抽取JSON → 解析customer_price → 调用FSM → 返回snapshot/contract
# 依赖：requests（调用本地 Ollama），你的 fsm.py（NegotiationCtx / NegotiationModel）

from typing import Any, Dict, Optional
import json, re, requests


# ====== 你可以在这里切换/配置模型 ======
OLLAMA_BASE = "http://localhost:11434"
OLLAMA_MODEL = "llama3.1"

# ====== System Prompt（固化边界）======
SYSTEM_PROMPT = """你是数据提取器。只根据用户输入生成 JSON，不要输出多余文字。
字段：
- "intent": one of ["counter_offer","accept","ask","other"]
- "customer_price": 整数或 null（如果无法解析）
- "notes": 可选，简短中文
严格输出合法 JSON。"""

# ====== User Prompt 模板（指导模型输出固定 JSON）======
def make_user_prompt(user_text: str) -> str:
    return f"""用户原话：
\"\"\"{user_text}\"\"\"

请输出如下 JSON（不要多余文本、不要解释）：
{{
  "intent": "counter_offer|accept|ask|other",
  "customer_price":  整数或 null,
  "notes": "可选中文备注，不超过20字"
}}"""

# ====== Ollama 调用：得到 JSON 字符串 ======
def call_ollama(user_text: str, base_url: str = OLLAMA_BASE, model: str = OLLAMA_MODEL) -> str:
    url = f"{base_url.rstrip('/')}/api/chat"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": make_user_prompt(user_text)}
    ]
    resp = requests.post(
        url,
        json={"model": model, "messages": messages, "stream": False},
        timeout=120
    )
    resp.raise_for_status()
    data = resp.json()
    return (data.get("message", {}) or {}).get("content", "").strip()

# ====== 解析 LLM 输出为 JSON（带兜底）======
def safe_load_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        # 兜底：从文本里用正则抠数字当 price
        num = extract_price_from_text(text)
        return {"intent": "other", "customer_price": num, "notes": "fallback_from_text"}

# ====== 可复用的数字提取（兜底）======
def extract_price_from_text(text: str) -> Optional[int]:
    m = re.search(r"(\d{2,6})", text.replace(",", "").replace(" ", ""))
    return int(m.group(1)) if m else None

# ====== 封装：前端输入 → user_summary(JSON) ======
def summarize_user_input(user_text: str) -> Dict[str, Any]:
    raw = call_ollama(user_text)
    summary = safe_load_json(raw)
    # 规整字段
    intent = summary.get("intent") or "other"
    price = summary.get("customer_price")
    if price is None:
        price = extract_price_from_text(user_text)
    # 只接受非负整数
    ok = isinstance(price, int) or (isinstance(price, str) and price.isdigit())
    summary["intent"] = intent
    summary["customer_price"] = int(price) if ok else None
    return summary


# ====== 从三份原始数据提炼“核心视图”给 NLG ======
# bridge.py（替换/更新 extract_core_view）
def extract_core_view(user_summary: Dict[str, Any],
                      fsm_snapshot: Dict[str, Any],
                      fsm_contract: Dict[str, Any]) -> Dict[str, Any]:
    customer_price = user_summary.get("customer_price", None)
    intent = (user_summary.get("intent") or "other").lower()

    ai_offer = fsm_snapshot.get("ai_offer")
    phase_from_snapshot = fsm_snapshot.get("state")

    state = fsm_contract.get("state", {})
    phase = state.get("phase", phase_from_snapshot)
    can_negotiate = bool(state.get("can_negotiate", False))
    hard_guards = fsm_contract.get("hard_guards", {})
    lowest_price = hard_guards.get("must_not_price_below", ai_offer)

    actions = fsm_contract.get("actions", {})
    allowed_actions = actions.get("allowed", [])

    # ---- 规则 1：无价但intent=accept，强制显示 ACCEPT（即便FSM已是ACCEPT，这里也保持一致） ----
    if intent == "accept" and (customer_price is None):
        phase = "ACCEPT"
        can_negotiate = False
        allowed_actions = ["ACCEPT"]

    # ---- 规则 2：用户价高于AI价，展示价取更高（不覆盖FSM权威，单独用 offer_to_show 告知LLM） ----
    offer_to_show = ai_offer
    if isinstance(customer_price, int):
        offer_to_show = max(ai_offer, customer_price)

    core = {
        "customer_price": customer_price,
        "ai_offer": ai_offer,              # FSM权威价（保留）
        "offer_to_show": offer_to_show,    # 给LLM展示/话术用
        "lowest_price": lowest_price,
        "phase": phase,
        "intent": intent,
        "can_negotiate": can_negotiate,
        "allowed_actions": allowed_actions,
    }
    return core



# ====== 对接 FSM：把价格喂进去，拿到 snapshot/contract ======
def run_fsm_turn(fsm, user_text: str) -> Dict[str, Any]:
    """
    fsm: 你的 NegotiationModel 实例
    返回结构：
    {
      "user_summary": {...},   # LLM提取结果
      "fsm_snapshot": {...},   # 轻量状态
      "fsm_contract": {...}    # 语言层合同（权威）
    }
    """
    summary = summarize_user_input(user_text)
    price = summary.get("customer_price")

    # 推进 FSM
    if price is not None:
        snap = fsm.input_user_price(price)
    else:
        # 没解析出价格：初始化并停在 WAIT_USER（不让价）
        if fsm.state == "INIT":
            fsm.start()         # INIT -> ANCHOR
            fsm.to_WAIT_USER()  # -> WAIT_USER
        snap = fsm.snapshot()

    contract = fsm.contract()
    # ★ 新增：提炼核心视图
    core_view = extract_core_view(summary, snap, contract)

    return {
        "user_summary": summary,
        "fsm_snapshot": snap,
        "fsm_contract": contract,
        "core_view": core_view,      # ← 新增返回
    }
