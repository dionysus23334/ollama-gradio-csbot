# Ollama Gradio CS Bot (MVP)

本项目提供一个最小可用的 **Gradio（Gradio）** 对话试验台，调用本地 **Ollama** 的 `/api/chat`，
用于评估 `llama3.1` 的对话质量与客服机器人 **系统提示词（System Prompt）** 的效果。

## 1. 先决条件
- 安装 Ollama 并拉取模型：
  ```bash
  ollama run llama3.1
