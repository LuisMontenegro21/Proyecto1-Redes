import httpx
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp import types
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware import Middleware
import logging

API_BASE = "" # API URL
USER_AGENT = ""
mcp = FastMCP(name="MyServer") # place here the API


async def make_request(url: str) -> dict[str, Any]:
    headers = {
        "User-Agent":USER_AGENT,
        "Accept": "application/geo+json"
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=25.0)
            response.raise_for_status()
            return response.json()
        except Exception as excp:
            logging.info(f"Request failed: {excp}")
            return None
        except KeyboardInterrupt:
            logging.info("Request stopped by user")

def format_alert(feature: dict) -> str:
    props = feature["properties"]
    return f"""
        Event: {props.get('event', 'Unknown')}
        Area: {props.get('areaDesc', 'Unknown')}
        Severity: {props.get('severity', 'Unknown')}
        Description: {props.get('description', 'No description available')}
        Instructions: {props.get('instruction', 'No specific instructions provided')}
    """





if __name__ == 'main':

    mcp.run(
        transport="http",
        host="127.0.0.1",
        port=8000,
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=['*']
            )    
        ]
    )