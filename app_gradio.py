# -*- coding: utf-8 -*-
# file: app_gradio.py
import os
import json
import time
import requests
import gradio as gr
from typing import List, Dict, Tuple, Any
from dotenv import load_dotenv

# 读取 .env
load_dotenv()

OLLAMA = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
MODEL  = os.getenv("OLLAMA_MODEL", "llama3.1")
DEFAULT_TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))

PROMPT_FILE = "prompt.txt"
DIALOGUES_FILE = "dialogues.json"

def read_file(path: str, default: str = "") -> str:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_json(path: str, data: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def append_dialogue(path: str, user_text: str, assistant_text: str):
    data = {"examples": []}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception:
                data = {"examples": []}
    data.setdefault("examples", []).append({"user": user_text, "assistant": assistant_text})
    write_json(path, data)

def stream_chat(messages: List[Dict[str, str]], temperature: float = DEFAULT_TEMPERATURE):
    """
    调用 Ollama /api/chat，采用 NDJSON 流式返回。
    messages: [{"role":"system"|"user"|"assistant","content":"..."}]
    """
    url = f"{OLLAMA}/api/chat"
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature}
    }
    with requests.post(url, json=payload, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        partial = ""
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = data.get("message", {})
            token = msg.get("content")
            if token:
                partial += token
                yield partial
            if data.get("done"):
                break

def build_messages(system_prompt: str, history: List[Tuple[str, str]], user_input: str):
    messages: List[Dict[str, str]] = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    for role, content in history:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_input})
    return messages

def on_send(user_input: str, chat_state: List[Tuple[str, str]],
            sys_prompt_text: str, temperature: float,
            model_name: str, base_url: str, chat_ui):
    """
    Gradio 事件回调：流式生成并实时更新 Chatbot。
    chat_state: [("user","..."),("assistant","...")]
    """
    global MODEL, OLLAMA
    MODEL = model_name.strip() or MODEL
    OLLAMA = (base_url.strip() or OLLAMA).rstrip("/")

    messages = build_messages(sys_prompt_text, chat_state, user_input)
    final = ""
    for partial in stream_chat(messages, temperature=temperature):
        final = partial
        tmp = chat_ui + [(user_input, final)]
        yield tmp, chat_state

    chat_state = chat_state + [("user", user_input), ("assistant", final)]
    # 将本轮对话追加保存
    try:
        append_dialogue(DIALOGUES_FILE, user_input, final)
    except Exception:
        pass
    yield chat_ui + [(user_input, final)], chat_state

def on_clear():
    return [], []

def on_load_files():
    sys_prompt_text = read_file(PROMPT_FILE, default="你是一名简洁、稳重、讲逻辑的中文助手。回答应分点、直达要点。")
    examples = []
    if os.path.exists(DIALOGUES_FILE):
        try:
            data = json.loads(read_file(DIALOGUES_FILE, default='{"examples": []}'))
            examples = data.get("examples", [])
        except Exception:
            examples = []
    return sys_prompt_text, json.dumps(examples, ensure_ascii=False, indent=2)

with gr.Blocks(title="Ollama Llama3.1 对话试验台") as demo:
    gr.Markdown("## 🧪 Ollama `llama3.1` 本地对话试验台\n- 支持：**流式（Streaming）**、多轮记忆、在线编辑 **系统提示词（System Prompt）**。\n- 右上角可切换模型名与服务地址。")

    with gr.Row():
        sys_prompt_text = gr.Textbox(label="System Prompt（系统提示）", lines=12)
        with gr.Column():
            model_name = gr.Textbox(value=MODEL, label="模型名（如 llama3.1）")
            base_url   = gr.Textbox(value=OLLAMA, label="Ollama 服务地址")
            temperature = gr.Slider(0.0, 1.5, value=DEFAULT_TEMPERATURE, step=0.1, label="Temperature（采样温度）")
            clear_btn  = gr.Button("清空对话")
            load_btn   = gr.Button("从文件载入 prompt.txt / dialogues.json")

    chat_ui = gr.Chatbot(label="对话窗口", height=420)
    user_in = gr.Textbox(label="输入你的问题", placeholder="在这里输入问题，回车或点击发送", lines=2)
    send_btn = gr.Button("发送 / Send")

    state = gr.State([])  # [("user","..."), ("assistant","...")]

    # 事件绑定（发送）
    send_btn.click(
        on_send,
        inputs=[user_in, state, sys_prompt_text, temperature, model_name, base_url, chat_ui],
        outputs=[chat_ui, state]
    )
    user_in.submit(
        on_send,
        inputs=[user_in, state, sys_prompt_text, temperature, model_name, base_url, chat_ui],
        outputs=[chat_ui, state]
    )

    # 清空
    clear_btn.click(on_clear, outputs=[chat_ui, state])

    # 从文件载入
    load_btn.click(on_load_files, outputs=[sys_prompt_text, gr.Code(label="dialogues.json 预览")])

if __name__ == "__main__":
    # 原来：demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True)
    demo.launch(
        server_name="127.0.0.1",   # 用回环地址，绕过某些代理/安全软件对 localhost 的劫持
        server_port=5000,
        show_error=True,
        inbrowser=True              # 可选：自动打开浏览器
    )