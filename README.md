# Claude Code Sampling Parameters Proxy

Control temperature, top-p, and top-k for Claude Code via a local proxy.

## Quick Start

1. **Start the proxy with your desired parameters:**
   ```bash
   python claude_proxy.py -t 0.7 -p 0.95 -k 40
   ```

2. **Run Claude Code through the proxy:**
   ```bash
   ANTHROPIC_BASE_URL=http://127.0.0.1:8080 claude
   ```

## CLI Options

```
-t, --temperature  Temperature (0.0-1.0)
-p, --top-p        Top-p / nucleus sampling (0.0-1.0)
-k, --top-k        Top-k sampling (1-100+)
-c, --config       Path to JSON config file
    --port         Port to listen on (default: 8080)
    --host         Host to bind to (default: 127.0.0.1)
```

Examples:
```bash
python claude_proxy.py -t 0.7
python claude_proxy.py -p 0.95 -k 40
python claude_proxy.py --config ~/.claude/sampling.json
python claude_proxy.py -c config.json -t 0.5  # CLI overrides file
```

## Max Tokens

For max output tokens, use Claude Code's built-in environment variable:

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8080 CLAUDE_CODE_MAX_OUTPUT_TOKENS=16000 claude
```

## How It Works

```
Claude Code → claude_proxy.py → Anthropic API
                     ↑
        Injects temperature/top_p/top_k
        from CLI args or config file
```

The proxy:
1. Receives API requests from Claude Code
2. Injects sampling parameters into the request body
3. Forwards to Anthropic's API

## Config File Format

```json
{
  "temperature": 0.7,
  "top_p": 0.95,
  "top_k": 40
}
```

Omit a key or set to `null` to use the API default. CLI args override config file values.

## Parameter Reference

| Parameter | Range | Description |
|-----------|-------|-------------|
| temperature | 0.0-1.0 | Randomness. 0=deterministic, 1=creative |
| top_p | 0.0-1.0 | Nucleus sampling threshold |
| top_k | 1-100+ | Only sample from top K tokens |

