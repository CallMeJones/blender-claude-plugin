# Privacy

Blender Agent Bridge is designed to keep project context local unless the user asks an assistant or MCP client to use it.

## Local Data

The add-on may store local Blender Text datablocks for chat history, transcripts, pending scripts, script logs, repair context, and agent memory. It may also write docs caches, checkpoints, viewport screenshots, and audit logs under user-controlled local paths.

Viewport screenshots are generated only when visual context is requested. Saved `.blend` files store captures under a project-local `.claude_blender/captures/<session_id>` folder by default. Unsaved or unwritable projects use the global `~/.claude_blender/captures/<project_id>/<session_id>` fallback, and a custom capture cache preference acts as a custom base directory. Treat project-local captures as generated artifacts unless you intentionally keep them.

The default audit log path is:

```text
~/.claude_blender/audit.jsonl
```

Audit entries record tool names, success/failure status, risk labels, and redacted argument summaries. Script/code fields, tokens, keys, passwords, and credential-like fields are redacted.

## Data Sent To Providers

When the in-Blender Claude assistant calls Anthropic, it can send:

- the user prompt;
- compact scene context;
- selected tool schemas;
- docs snippets;
- agent memory when enabled;
- viewport screenshots only when the Viewport toggle is enabled.

The localhost MCP bridge itself does not call an LLM provider. External MCP clients decide what to send to their own model provider after reading resources or tool results.

## User Controls

- Keep screenshots off unless visual context is needed.
- Use `Clear Memory` for a fresh local agent thread.
- Use `Reject Script` for unwanted pending Python.
- Use `Revoke Trust` to end a runtime external script trust preset before it expires.
- Delete local checkpoint, screenshot, docs-cache, and audit files from disk when no longer needed.
