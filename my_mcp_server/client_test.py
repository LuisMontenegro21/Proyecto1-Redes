import asyncio
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

@asynccontextmanager
async def filesystem_session(allowed_paths):
    """
    allowed_paths: list[str] of absolute directories the server may access.
                   On Windows, prefer r'C:\\path\\to\\dir' or use double backslashes.
    """
    server = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", *allowed_paths],
        # env=None, cwd=None, encoding='utf-8' are fine with defaults
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session  # use inside the context

# --- example usage ---
async def demo():
    # replace with folders you actually want to allow:
    paths = [r"C:\Users\L Montenegro\Documents\GitHub\Proyecto1-Redes\my_mcp_server"]
    async with filesystem_session(paths) as session:
        tools = (await session.list_tools()).tools
        print("Tools:", [t.name for t in tools])
        roots = await session.list_tools()
        print("tools:", roots.tools)

if __name__ == "__main__":
    asyncio.run(demo())
