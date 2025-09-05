# client_test.py
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    # Point this at your server; use absolute path if you prefer
    server = StdioServerParameters(
        command="uv",          # or "uv"
        args=["run", "python", "server.py"],        # if using uv: command="uv", 
        env=None
    )

    async with stdio_client(server) as (read, write):
        session = await ClientSession(read, write).__aenter__()
        try:
            await session.initialize()

            # 1) List tools
            tools_resp = await session.list_tools()
            tool_names = [t.name for t in tools_resp.tools]
            print("Tools:", tool_names)

            # 2) Call a tool (use one of your real tool names and args)
            # Prefer the convenience method:
            if tool_names:
                result = await session.call_tool(tool_names[0], {"query": "35932"})
                print("Tool result:", result.content)
        finally:
            await session.__aexit__(None, None, None)






if __name__ == "__main__":
    asyncio.run(main())