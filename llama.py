# nlg_from_core_view.py
import json
import re
import requests
from typing import Dict, Any, List, Optional

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_MODEL = "llama3.1"

SYSTEM_PROMPT = """
你是一名电商客服的“语言层”助手，只能基于我提供的 core_view（结构化状态）生成中文回复，且必须遵守：
1) 价格与状态以 core_view 为准，禁止修改或推测未给出的字段。
2) 回复中的所有“价格”只能使用 offer_to_show，并且不得低于 lowest_price；不要出现其他数字。
3) 只能表达 allowed_actions 中允许的动作；若 can_negotiate=false，禁止提出新的让价或条件。
4) 若 phase="ACCEPT"，以确认成交、下一步操作为导向。
5) 语气专业、礼貌、简洁（尽可能少于2句，不超过50个字）；不要输出任何 JSON 或解释性前后缀。
请包含一句“我们给出的成交价为<offer_to_show>元”（把尖括号内容替换为具体数字），
不要出现其他价格相关数字或历史报价，直接给出回复，不要掺入杂质。
""".strip()

def make_user_prompt(
    last_user_text: str,
    core_view: Dict[str, Any],
    value_reasons: Optional[List[str]] = None,
    cta: Optional[str] = None,
) -> str:
    """把上一句+合同拼成给 LLM 的用户侧提示"""
    extra = []
    if value_reasons:
        extra.append(f"价值点（至多使用2个）：{'；'.join(value_reasons[:2])}")
    if cta:
        extra.append(f"结尾CTA：{cta}")
    extra_block = ("\n" + "\n".join(extra)) if extra else ""
    return f"""
# 上一句用户输入
「{last_user_text}」

# core_view（只读约束）
{json.dumps(core_view, ensure_ascii=False, indent=2)}

请根据以上信息，直接输出给用户看的中文话术（少于2句），
以“确认成交与下一步安排”为导向；可点到产品价值，但不要新增价格或承诺。{extra_block}
""".strip()

def call_ollama_chat(system_prompt: str, user_prompt: str,
                     base_url: str = OLLAMA_BASE, model: str = OLLAMA_MODEL) -> str:
    url = f"{base_url.rstrip('/')}/api/chat"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    resp = requests.post(url, json={"model": model, "messages": messages, "stream": False}, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return (data.get("message", {}) or {}).get("content", "").strip()

def enforce_floor(text: str, lowest_price: int) -> str:
    """把文本中低于红线的数字替换为红线，避免穿底"""
    def repl(m):
        n = int(m.group(0))
        return str(max(n, lowest_price))
    return re.sub(r"\d{2,6}", repl, text)

def nlg_from_core_view(
    last_user_text: str,
    core_view: Dict[str, Any],
    value_reasons: Optional[List[str]] = None,
    # cta: Optional[str] = "若确认我可立即为你锁单并优先发货",
    cta: Optional[str] = "",
    base_url: str = OLLAMA_BASE,
    model: str = OLLAMA_MODEL,
) -> str:
    """主入口：返回给用户看的话术（已做价格红线校验）"""
    user_prompt = make_user_prompt(last_user_text, core_view, value_reasons, cta)
    raw = call_ollama_chat(SYSTEM_PROMPT, user_prompt, base_url, model)

    # 价格红线兜底
    floor = int(core_view.get("lowest_price", 0))
    safe_text = enforce_floor(raw, floor)

    # 只允许出现 offer_to_show 这一个价格（尽量减少其他数字）
    offer = str(core_view.get("offer_to_show", ""))
    if offer:
        # 可选进一步限制：若出现多个不同数字，强制把非 offer 的数字替换为 offer
        nums = set(re.findall(r"\d{2,6}", safe_text))
        for n in nums:
            if n != offer:
                safe_text = re.sub(rf"\b{n}\b", offer, safe_text)

    return safe_text

# ---------------- 使用示例 ----------------
if __name__ == "__main__":
    core_view = {
        "customer_price": 455,
        "ai_offer": 455,
        "offer_to_show": 455,
        "lowest_price": 420,
        "phase": "ACCEPT",
        "intent": "counter_offer",
        "can_negotiate": False,
        "allowed_actions": ["CONCESSION", "HOLD", "ACCEPT"]
    }
    last_user = "450能不能再便宜点？"
    reply = nlg_from_core_view(last_user, core_view,
                               value_reasons=["正品保障与售后", "做工与用料优于同级"])
    print(reply)
