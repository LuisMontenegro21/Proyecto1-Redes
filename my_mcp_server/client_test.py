import asyncio
from contextlib import AsyncExitStack
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.types import Request

async def main():
    async with AsyncExitStack() as stack:
        
        params = StdioServerParameters(
            command="python",
            args=["proxy.py"]
        )
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))

        result = await session.call_tool(
            name="add",
            arguments={"a": 10, "b": 20}
        )

        print("Response from FastAPI via Proxy:", result)

if __name__ == "__main__":
    asyncio.run(main())
