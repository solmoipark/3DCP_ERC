"""pmpredict LLM agent: natural-language access to prediction, inverse design, buildability, literature and the DB.

Layout
  tools/      tool registry (single source of truth) + tool implementations + runtime singletons
  providers/  LLM backends sharing one streaming interface (Anthropic API, OpenAI API, Claude subscription via
              claude-agent-sdk, ChatGPT subscription via Codex CLI, fake for tests)
  core.py     Agent: system prompt, transcript memory, tool execution loop
  memory.py   sessions (~/.pmpredict/agent) and durable notes
  mcp_server  stdio MCP server exposing the registry (used by the Codex provider and any MCP client)
  cli.py      `pmpredict agent`
"""
