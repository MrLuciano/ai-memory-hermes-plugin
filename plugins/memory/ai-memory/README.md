# ai-memory Hermes Memory Provider

Connects Hermes Agent to an ai-memory server for long-term wiki memory.

## Quick Start

```bash
mkdir -p "$HERMES_HOME/plugins/ai-memory"
cp -r * "$HERMES_HOME/plugins/ai-memory/"
hermes plugins enable ai-memory
hermes memory setup
hermes memory status
```

## Tools

- `ai_memory_search` — search the wiki
- `ai_memory_write` — write a new page
- `ai_memory_status` — health check

## Docs

Full documentation is at the [project root](../../../README.md), with detailed [usage guide](../../../docs/guide.md), [API reference](../../../docs/reference.md), and [troubleshooting](../../../docs/common-problems.md).

## Requirements

- Python 3.10+
- Hermes Agent with plugin support
- ai-memory server running locally or on LAN
- `httpx`
