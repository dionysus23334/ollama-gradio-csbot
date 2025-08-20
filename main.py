# main.py
from fsm import NegotiationCtx, NegotiationModel
from bridge import run_fsm_turn
import json
from llama import *


if __name__ == "__main__":
    ctx = NegotiationCtx(list_price=500, bar_price=400, stop_floor=420, max_concessions=5)
    fsm = NegotiationModel(ctx)

    while True:
        user_text = input("用户：").strip()
        if not user_text:
            continue
        if user_text.lower() in {"q", "quit", "exit"}:
            break

        out = run_fsm_turn(fsm, user_text)
        reply = nlg_from_core_view(user_text, out["core_view"], value_reasons=["正品保障与售后", "做工与用料优于同级"])

        print("\n[LLM抽取 user_summary]")
        print(out["user_summary"])

        print("\n[FSM snapshot]")
        print(out["fsm_snapshot"])

        print("\n[FSM contract]")
        from pprint import pprint
        pprint(out["fsm_contract"])

        print("\n[CORE VIEW → 喂给 LLM 话术层]")
        print(json.dumps(out["core_view"], ensure_ascii=False, indent=2))

        print("\n最终回复：")
        print(reply)

        print("-" * 60)
