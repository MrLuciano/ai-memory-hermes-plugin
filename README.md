# ai-memory Hermes Memory Provider Plugin

Connects [Hermes Agent](https://github.com/NousResearch/hermes-agent) to [ai-memory](https://github.com/akitaonrails/ai-memory) as a first-class memory provider.

## Quick Start

```bash
# Install plugin
mkdir -p "$HERMES_HOME/plugins/ai-memory"
cp -r plugins/memory/ai-memory/* "$HERMES_HOME/plugins/ai-memory/"

# Enable
hermes plugins enable ai-memory
hermes memory setup

# Verify
hermes memory status
```

## Development

```bash
uv sync
uv run ruff check .
uv run mypy .
uv run pytest --cov
```

## Project Structure

```
plugins/memory/ai-memory/
├── __init__.py   # Plugin entry point
├── plugin.yaml   # Hermes metadata
├── provider.py   # AiMemoryProvider implementation
├── client.py     # AiMemoryClient HTTP wrapper
├── config.py     # Config schema + persistence
└── README.md     # Plugin setup instructions
```
