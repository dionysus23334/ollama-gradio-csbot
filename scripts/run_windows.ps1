# 在项目根目录执行：powershell -ExecutionPolicy Bypass -File .\scripts\run_windows.ps1
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip wheel
pip install -r requirements.txt
if (Test-Path ".env") { Write-Host ".env 已存在" } else { Copy-Item ".env.example" ".env" }
python app_gradio.py
