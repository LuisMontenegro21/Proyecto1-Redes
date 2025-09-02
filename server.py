import httpx
from mcp.server.fastmcp import FastMCP
from mcp import types

API_BASE = "" # API URL
mcp = FastMCP("") # place here the API

class Server:
    def __init__(self) -> None:
        pass

    async def fetch_data(self):
        pass
    
    @mcp.tool()
    async def get_info(self):
        pass

    # place more functions here
    # ... 
    # ...