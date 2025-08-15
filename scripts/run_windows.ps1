# Create venv
python -m venv .venv

# Activate venv
. .\.venv\Scripts\Activate.ps1

# Upgrade pip & wheel
python -m pip install -U pip wheel

# Install deps
pip install -r requirements.txt

# Ensure .env exists
if (Test-Path ".env") {
    Write-Host ".env exists"
} else {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env file"
}

# Run the app
python app_gradio.py
