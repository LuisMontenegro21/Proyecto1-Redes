from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
import asyncio

async def main():
    server = StdioServerParameters(
        command="C:\\Users\\lpmon\\Documents\\Github\\Proyecto1-Redes\\my_mcp_server\\.venv\\Scripts\\my-mcp-server.exe",
        args=[],  
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

            # 2) Call list_hazards
            if "list_hazards" in tool_names:
                result = await session.call_tool("list_hazards", {
                    "input": {
                        "lat": 14.6,
                        "lon": -90.5,
                        "start_date": "2025-06-01",
                        "end_date": "2025-09-16",
                        "radius_km": 1500
                        # categories omitted on purpose
                    }
                })
                print("Tool result:", result.content)
            else:
                print("list_hazards tool not found!")

        finally:
            await session.__aexit__(None, None, None)

if __name__ == "__main__":
    asyncio.run(main())
