# Project Configuration

## Python Environment

This project uses a Python virtual environment (venv).

### Setup

```bash
# Activate the virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running Commands

When running Python commands in this project, always use the virtual environment:

```bash
# Make sure venv is activated first
source venv/bin/activate

# Then run your commands
python main.py
uvicorn main:app --reload
```

### Deactivate

```bash
deactivate
```

## Environment Settings

Claude Code should use the Python interpreter from the venv:
- Python path: `./venv/bin/python`
- Pip path: `./venv/bin/pip`
