# 🗂 Ollama Llama3.1 客服机器人

一个基于 **Ollama** + **Gradio** 的本地客服机器人，支持流式输出、多轮记忆、系统提示词编辑。  
无需联网调用外部 API，全部推理在本地运行。

---

## 📦 功能特性
- **流式生成**：实时输出模型生成内容
- **多轮对话记忆**：保存历史上下文
- **系统提示词可编辑**：可随时修改角色设定
- **本地部署**：基于 Ollama 在本地推理
- **Gradio Web 界面**：跨平台浏览器访问

---

## 📋 运行环境要求
- 操作系统：Windows / macOS / Linux
- Python：≥ 3.10
- Ollama：已安装（[下载地址](https://ollama.ai)）
- 显卡（推荐）：支持 GPU 加速（CPU 也可运行，但速度较慢）

---

## 🚀 快速开始

### 1️⃣ 下载项目
```bash
git clone https://github.com/你的仓库名/ollama-gradio-csbot.git
cd ollama-gradio-csbot
```

### 2️⃣ 安装 Ollama 并启动服务

1. 从 Ollama 官网 下载并安装
2. 启动 Ollama 服务：

```
ollama serve
```

Ollama 默认监听地址为 `http://localhost:11434`

### 3️⃣ 下载模型

```
ollama pull llama3.1
```

可用 `ollama list` 查看已下载的模型。

> 💡 **可选**：如果需要添加**知识库 / 语义搜索**功能，请下载嵌入模型：
>
> ```
> ollama pull nomic-embed-text
> ```
>
> 用途：将句子映射为向量，用于相似度搜索、FAQ 匹配等。

### 4️⃣ 创建 Python 虚拟环境并安装依赖

```
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境（Windows PowerShell）
. .\.venv\Scripts\Activate.ps1

# macOS / Linux
# source .venv/bin/activate

# 升级 pip & wheel
python -m pip install -U pip wheel

# 安装依赖
pip install -r requirements.txt
```

### 5️⃣ 配置环境变量（可选）

复制 `.env.example` 为 `.env`，并根据需要修改：

```
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
TEMPERATURE=0.7
```

### 6️⃣ 运行项目

```
python app_gradio.py
```

运行后浏览器会自动打开：

```
http://127.0.0.1:5000
```

------

## 💻 使用方法

- 左侧可编辑**系统提示词（System Prompt）**
- 右侧可切换模型名 / Ollama 服务地址 / 温度参数
- 输入问题后回车或点击**发送**即可对话
- 点击**清空对话**重置上下文
- 点击**从文件载入**可加载 `prompt.txt` 与 `dialogues.json` 历史记录

------

## 🛠 常见问题

### ❓ 启动时报 `localhost is not accessible`

- 可能是代理或安全软件劫持了 localhost

- 解决方法：在 `app_gradio.py` 中把

  ```
  server_name="0.0.0.0"
  ```

  改为

  ```
  server_name="127.0.0.1"
  ```

### ❓ 报错 `TypeError: argument of type 'bool' is not iterable`

- 原因：Gradio 版本过旧
- 解决：

```
pip install -U gradio gradio_client
```

### ❓ 模型无法调用

- 确认 Ollama 服务已运行：

```
ollama serve
```

- 确认 `llama3.1` 已下载：

```
ollama list
```

------

## 📂 项目结构

```
ollama-gradio-csbot/
├── app_gradio.py         # 主程序入口
├── requirements.txt      # Python 依赖
├── prompt.txt            # 系统提示词文件
├── dialogues.json        # 历史对话记录
├── .env.example          # 环境变量示例文件
└── scripts/              # 脚本工具
```

------

## 📜 许可证

本项目采用 **MIT License**，允许商用、修改、分发，但需保留原作者版权声明，且不承担任何使用风险的法律责任。

------

## ⚡ 一键运行脚本（Windows）

如果不想手动输入命令，可以直接运行：

```
powershell -ExecutionPolicy Bypass -File scripts\run_windows.ps1
```

------

## 🔮 计划功能

- 知识库接入（RAG）
- FAQ 智能匹配
- 多模型切换
- 模型自动下载检测