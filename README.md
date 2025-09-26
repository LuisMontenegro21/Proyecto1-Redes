# Proyecto1-Redes

## Description

This project takes adavantage of the MCP (Model Context Protocol) to implement a connection to different servers via a client that feeds the agent. It implements a Filesystem MCP, Github MCP and and a local server. 

The local server provides tools for querying natural hazards and solar weather data using NASA APIs. The client supports interactive chat and tool invocation, allowing users to query these tools or connect to remote MCP endpoints.

## Features

- **Local MCP Server**: Implements tools for hazard and solar weather queries ([my_mcp_server/server.py](my_mcp_server/server.py)).
- **Client**: Interactive chat interface supporting tool invocation and multi-server registration ([my_mcp_server/client.py](my_mcp_server/client.py)).
- **GitHub MCP Integration**: Connects to GitHub Copilot's MCP API for advanced tool access.
- **Filesystem MCP**: Uses the official MCP Filesystem server for file operations.
- **History Logging**: Saves chat and tool invocation history in JSONL format.

## MCP Endpoints Explained

### GitHub MCP

GitHub's MCP endpoint (`https://api.githubcopilot.com/mcp/`) allows you to interact with tools provided by GitHub Copilot, such as code analysis, file operations, and more. Authentication is required via a GitHub token, which can be configured in `.vscode/mcp.json` or via environment variables.

### Filesystem MCP

The Filesystem MCP server (`@modelcontextprotocol/server-filesystem`) exposes your local or project files as MCP tools. This enables file reading, writing, and searching through a standardized protocol. The client can launch this server using `npx` and connect via stdio.

### Local Server Implementation

The local MCP server ([my_mcp_server/server.py](my_mcp_server/server.py)) is a Python process that exposes custom tools for querying NASA APIs. It uses the MCP protocol over stdio, making it compatible with the client and other MCP-compliant agents.

## Installation

1. **Install [uv](https://astral.sh/uv/):**

   - **Windows:**
     ```
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
   - **Mac / Linux:**
     ```
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```

2. **Install dependencies:**
   ```
   cd my_mcp_server
   uv pip install -e .
   ```

## Usage

### Running the Local MCP Server

Start the server:
```
cd my_mcp_server
python server.py
```
Or, if installed as an executable:
```
my-mcp-server
```

### Running the Client

Start the client and choose the mode:
```
cd my_mcp_server
python client.py
```
You will be prompted to select between "filesystem" (for Filesystem MCP and GitHub MCP) or "local" (for the local server).

### Example MCP Configuration

Configure `.vscode/mcp.json` for GitHub MCP access:
```json
{
  "servers": {
    "my-mcp-server-e89de25e": {
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": {
        "Authorization": "Bearer ${input:github_token}"
      },
      "type": "http"
    }
  },
  "inputs": [
    {
      "id": "github_token",
      "description": "GitHub Token",
      "type": "promptString",
      "default": "Github personal access token"
    }
  ]
}
```

## Project Structure

- `my_mcp_server/server.py`: Local MCP server implementation.
- `my_mcp_server/client.py`: Interactive MCP client.
- `my_mcp_server/README.md`: MCP server usage instructions.
- `.vscode/mcp.json`: VSCode MCP server configuration.
- `chat_logs/log.jsonl`: Chat and tool invocation history.



