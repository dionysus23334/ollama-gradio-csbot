
# -*- coding: utf-8 -*-
"""
Gradio 调试台：议价机器人 (Bargaining Bot Debugger) · 极简清爽版（修复：对话历史持久化）

特点：
- 顶部宽屏对话区（输入框 + 发送按钮与对话框在一起）。
- 聊天气泡保留但**无背景色**，白底黑字；尽量减少色块。
- **已修复历史丢失**：使用 st_history 显式回传与保存，保证多轮对话可见。
- 下方参数区与调试区：同时查看最新与历史的 Contract/CoreView。

启动：
  python app.py
"""

from __future__ import annotations
import json
import time
from typing import Any, List, Tuple, Dict

import gradio as gr

from fsm import NegotiationCtx, NegotiationModel
from bridge import run_fsm_turn
from llama import nlg_from_core_view

# ---------------- 工具函数 ----------------

def pretty_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"<JSON 序列化失败: {e}>{obj}"


def _init_model(list_price: int, bar_price: int, stop_floor: int, max_concessions: int):
    ctx = NegotiationCtx(
        list_price=list_price,
        bar_price=bar_price,
        stop_floor=stop_floor,
        max_concessions=max_concessions,
    )
    fsm = NegotiationModel(ctx)
    history: List[Tuple[str, str]] = []
    return ctx, fsm, history


# ---------------- 回调 ----------------

def on_reset(list_price, bar_price, stop_floor, max_concessions):
    ctx, fsm, history = _init_model(list_price, bar_price, stop_floor, max_concessions)
    # 返回顺序与 outputs 对应
    return (
        ctx,                 # st_ctx
        fsm,                 # st_fsm
        history,             # st_history (清空)
        history,             # chatbot 清空
        [],                  # st_contract_list
        [],                  # st_coreview_list
        "", "", "", "",      # box_user_summary, box_snapshot, box_contract_latest, box_core_latest
        gr.update(value=[], visible=False),   # grid_changes
        gr.update(value=[], visible=False),   # contracts_json_all
        gr.update(value=[], visible=False),   # coreviews_json_all
    )


def on_user_message(
    user_text: str,
    ctx: NegotiationCtx,
    fsm: NegotiationModel,
    chat_history: List[Tuple[str, str]],
    value_reasons: str,
    contract_list: List[Dict[str, Any]],
    coreview_list: List[Dict[str, Any]],
):
    if not user_text or not user_text.strip():
        # 不改动历史，直接回填现有组件
        return (
            chat_history,  # chatbot
            chat_history,  # st_history
            gr.update(), gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(),
            contract_list, coreview_list,
        )

    out = run_fsm_turn(fsm, user_text)
    reasons = [r.strip() for r in value_reasons.split("|") if r.strip()] or ["正品保障与售后", "做工与用料优于同级"]
    reply = nlg_from_core_view(user_text, out["core_view"], value_reasons=reasons)

    # 维护历史（关键：既更新 Chatbot，也更新 st_history）
    chat_history = (chat_history or []) + [(user_text, reply)]

    user_summary = out.get("user_summary", "")
    snapshot = out.get("fsm_snapshot", "")
    contract_latest = out.get("fsm_contract", {})
    core_latest = out.get("core_view", {})

    contract_list = (contract_list or []) + [contract_latest]
    coreview_list = (coreview_list or []) + [core_latest]

    # 变化轨迹（按需自定义）
    changes = []
    for k in ["intent", "price", "should_concede", "concession_step", "stance", "finalized"]:
        if k in core_latest:
            changes.append([time.strftime("%H:%M:%S"), k, str(core_latest[k])])

    return (
        chat_history,                 # chatbot
        chat_history,                 # st_history（同步保存）
        user_summary, snapshot,
        pretty_json(contract_latest), pretty_json(core_latest),
        gr.update(value=changes, visible=True),
        gr.update(value=contract_list, visible=True),
        gr.update(value=coreview_list, visible=True),
        contract_list, coreview_list,
    )


# ---------------- UI ----------------

def build_ui() -> gr.Blocks:
    css = """
    .gradio-container {max-width: 1400px !important}
    /* 气泡极简：无背景色、细边、适度圆角 */
    .message {padding: 12px 14px; border-radius: 12px; background: none !important; box-shadow: none !important; border: 1px solid rgba(0,0,0,0.06);} 
    .message.user {text-align: right;}
    .message.bot {text-align: left;}
    """

    with gr.Blocks(css=css) as demo:
        gr.Markdown("# 🛠️ 议价机器人 · 调试台")

        # 顶部：对话 + 输入同区
        chatbot = gr.Chatbot(label="对话历史", height=540, bubble_full_width=True, show_copy_button=True, likeable=True)
        with gr.Row():
            user_box = gr.Textbox(placeholder="输入用户话术…（回车发送）", lines=2)
            btn_send = gr.Button("发送", variant="primary")

        with gr.Row():
            # 左列：参数
            with gr.Column(scale=3):
                with gr.Group():
                    list_price = gr.Number(value=500, label="标价 list_price", precision=0)
                    bar_price = gr.Number(value=400, label="最低价 bar_price", precision=0)
                    stop_floor = gr.Number(value=420, label="止损价 stop_floor", precision=0)
                    max_concessions = gr.Number(value=5, label="让价次数 max_concessions", precision=0)
                    value_reasons = gr.Textbox(value="正品保障与售后|做工与用料优于同级", label="价值点（|分隔）")
                    btn_reset = gr.Button("🔁 重置会话 / 应用参数", variant="secondary")

            # 右列：调试信息
            with gr.Column(scale=4):
                with gr.Tabs():
                    with gr.TabItem("最新结果"):
                        box_user_summary = gr.Textbox(lines=4, interactive=False, label="LLM抽取 user_summary")
                        box_snapshot = gr.Textbox(lines=6, interactive=False, label="FSM snapshot")
                        box_contract_latest = gr.Code(language="json", interactive=False, label="最新 Contract")
                        box_core_latest = gr.Code(language="json", interactive=False, label="最新 CoreView")
                        grid_changes = gr.Dataframe(headers=["时间", "字段", "值"], value=[], datatype=["str", "str", "str"], interactive=False, visible=False, label="字段变化轨迹")
                    with gr.TabItem("历史 JSON"):
                        contracts_json_all = gr.JSON(value=[], visible=False, label="Contract 历史 List")
                        coreviews_json_all = gr.JSON(value=[], visible=False, label="CoreView 历史 List")

        # 状态
        st_ctx = gr.State()
        st_fsm = gr.State()
        st_history = gr.State([])
        st_contract_list = gr.State([])
        st_coreview_list = gr.State([])

        # 重置与页面加载
        btn_reset.click(
            on_reset,
            [list_price, bar_price, stop_floor, max_concessions],
            [
                st_ctx, st_fsm, st_history, chatbot,
                st_contract_list, st_coreview_list,
                box_user_summary, box_snapshot, box_contract_latest, box_core_latest,
                grid_changes, contracts_json_all, coreviews_json_all,
            ],
        )

        demo.load(
            on_reset,
            [list_price, bar_price, stop_floor, max_concessions],
            [
                st_ctx, st_fsm, st_history, chatbot,
                st_contract_list, st_coreview_list,
                box_user_summary, box_snapshot, box_contract_latest, box_core_latest,
                grid_changes, contracts_json_all, coreviews_json_all,
            ],
        )

        # 发送（回车 & 按钮）
        def _submit(u, c, f, h, v, cl, cv):
            return on_user_message(u, c, f, h, v, cl, cv)

        submit_outputs = [
            chatbot,           # 可见对话
            st_history,        # 保存后的历史
            box_user_summary, box_snapshot, box_contract_latest, box_core_latest,
            grid_changes,
            contracts_json_all, coreviews_json_all,
            st_contract_list, st_coreview_list,
        ]

        user_box.submit(
            _submit,
            [user_box, st_ctx, st_fsm, st_history, value_reasons, st_contract_list, st_coreview_list],
            submit_outputs,
        ).then(lambda: "", None, [user_box])

        btn_send.click(
            _submit,
            [user_box, st_ctx, st_fsm, st_history, value_reasons, st_contract_list, st_coreview_list],
            submit_outputs,
        ).then(lambda: "", None, [user_box])

    return demo


if __name__ == "__main__":
    build_ui().queue().launch(server_port=7860)

