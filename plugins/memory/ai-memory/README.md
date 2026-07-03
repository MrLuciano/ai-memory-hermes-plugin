# ai-memory Hermes Memory Provider

Connects Hermes Agent to an ai-memory server for long-term wiki memory.

## Requirements

- Python 3.10+
- Hermes Agent with plugin support
- ai-memory server running locally or on LAN

## Setup

1. Start ai-memory:
   ```
   curl -fsSL https://raw.githubusercontent.com/alphaonedev/ai-memory-mcp/main/install.sh | sh
   ai-memory serve
   ```

2. Install plugin:
   ```bash
   mkdir -p "$HERMES_HOME/plugins/ai-memory"
   cp -r * "$HERMES_HOME/plugins/ai-memory/"
   ```

3. Enable in Hermes:
   ```bash
   hermes plugins enable ai-memory
   hermes memory setup
   ```

4. Verify:
   ```bash
   hermes memory status
   ```

## Tools

- `ai_memory_search` — search the wiki
- `ai_memory_write` — write a new page
- `ai_memory_status` — health check
