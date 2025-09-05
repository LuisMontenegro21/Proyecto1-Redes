# Run Claude Desktop

### Prerequisites
It is easier if you have uv installed

Windows: <br>
`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`<br>
Mac / Linux: <br>
`curl -LsSf https://astral.sh/uv/install.sh | sh`<br>

Then restart the terminal and check if it was correctly installed.<br>
`uv --version`<br>

### Install
Go to your terminal and run<br>
`cd my_mcop_server`
`uv pip install -e .`

### How to run the server on Claude Desktop
This was tested using Claude Desktop for the moment. You need to <br>
You need to go to Settings -> Developer and add the following config to Claude. <br>
Add a new configuration of a server and copy this on claude_settings.json depending on 
where my-mcp-server.exe is located. Place absolute path.

```
{
  "mcpServers": {
    "satellite": {
      "command": "<ABSOLUTE_PATH_TO>my_mcp_server\\.venv\\Scripts\\my-mcp-server.exe",
      "args": [],
      "transport": "stdio"
    }
  }
}
```
