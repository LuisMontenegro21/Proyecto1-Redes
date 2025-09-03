# Reference: https://modelcontextprotocol.io/quickstart/client 
import httpx
from typing import Any, Optional
from mcp.server.fastmcp import FastMCP
import json
import sys
import asyncio
# from starlette.middleware.cors import CORSMiddleware
# from starlette.middleware import Middleware
import logging

API_BASE = "https://tle.ivanstanojevic.me/api" # API URL
mcp = FastMCP(name="MyMCPServer")

# configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)

DEFAULT_HEADERS = {
    "Accept": "application/json",
    # Some endpoints close on unknown/empty UA; send a boring browsery UA:
    "User-Agent": "Mozilla/5.0 (compatible; mcp-client/1.0; +https://example.com)",
    # Nudge some servers to avoid keep-alive weirdness
    "Connection": "close",
}

@mcp.tool()
async def get_satellite_data(query: str) -> str:    
    '''
    Gets information of a specific statellite
    '''
    url = f"{API_BASE}/tle/"  

    data = await make_request(url=url, params={"search": query})
    if  not isinstance(data, dict):
        return f"Fetching failed for '{query}'"
    
    members = data.get("member", [])
    if not members:
        return f"No members found"
    
    data = await asyncio.gather(*[format_information(m) for m in members])
    return "\n\n".join(data)

@mcp.tool()
async def get_satellite(query: str) -> str:
    pass


async def make_request(url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any] | None:

    async with httpx.AsyncClient(                    
        timeout=httpx.Timeout(25.0),
        headers=DEFAULT_HEADERS,
        transport=httpx.AsyncHTTPTransport(retries=2),               
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
 
            return response.json()
        except httpx.RemoteProtocolError as e:
            logging.error("RemoteProtocolError for %s: %r", response.request.url if 'r' in locals() else url, e)
            return None
        except httpx.HTTPStatusError as e:
            resp = e.response
            logging.error("HTTP %s for %s\nHeaders: %s\nBody: %s",
                          resp.status_code, resp.request.url, dict(resp.headers), resp.text[:500])
            return None
        except json.JSONDecodeError as e:
            logging.error("JSON decode error for %s: %r (first 200 chars: %s)",
                          response.request.url if 'r' in locals() else url, e, (response.text[:200] if 'r' in locals() else ""))
            return None
        except httpx.RequestError as e:
            logging.error("RequestError for %s: %r", url, e)
            return None
        except Exception as e:
            logging.error("Unexpected error for %s: %r", url, e)
            return None

        
async def format_information(member: dict) -> list[str]:
    """
    Format TLE in a nice way
    """
    sat_id = member.get("satelliteId", "0")
    name = member.get("name", "Unknown")
    date = member.get("date", "n/a")
    line1 = member.get("line1", "Unknown")
    line2 = member.get("line2", "Unknown")

    return (
        f"satelliteId: {sat_id}\n"
        f"name       : {name}\n"
        f"date       : {date}\n"
        f"line1      : {line1}\n"
        f"line2      : {line2}"
    )

if __name__ == '__main__':
    logging.info("Starting up server")
    try: 
        mcp.run(
            transport="stdio",
        )
    except KeyboardInterrupt:
        logging.info("Stopped server : KeyboardInterrupt")