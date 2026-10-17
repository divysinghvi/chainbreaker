# ChainBreaker

## MCP server (Claude Desktop)

```json
{
  "mcpServers": {
    "chainbreaker": {
      "command": "/ABSOLUTE/PATH/chainbreaker/.venv/bin/python",
      "args": ["-m", "chainbreaker.mcp_server"],
      "env": { "FALKORDB_HOST": "localhost", "FALKORDB_PORT": "6379", "FALKORDB_PASSWORD": "chainbreaker" }
    }
  }
}
```
