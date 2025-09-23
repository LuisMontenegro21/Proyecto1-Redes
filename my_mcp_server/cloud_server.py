import httpx
from typing import Any, Optional
from mcp.server.fastmcp import FastMCP
import json
import asyncio
import logging
from pydantic import BaseModel

mcp = FastMCP(name="CloudServer")
SATELLITE_API = "https://tle.ivanstanojevic.me/api"
# for some reason it only works with this
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; mcp-client/1.0; +https://example.com)",
    "Connection": "close",
}
class Satellite(BaseModel):
    id: str
    name: str


@mcp.tool()
async def search_satellites(input: Satellite) -> dict:    
    '''
    Searches information from a satellite
    '''
    url = f"{SATELLITE_API}/tle/"  

    data = await make_request(url=url, params={"search": input.name})
    if not isinstance(data, dict):
        return {}
    
    members = data.get("member", [])
    if not members:
        return f"No members found"
    
    data = await asyncio.gather(*[format_information(m) for m in members])
    return data

@mcp.tool()
async def search_satellite_by_id(input: Satellite) -> dict:
    '''
    Gets information from a satellite using the ID
    '''
    url = f"{SATELLITE_API}/tle/{input.id}"
    data = await make_request(url=url)
    if  not isinstance(data, dict):
        return {}
    data = await asyncio.gather(format_information(data))
    logging.info("Using tool search_satellite_by_id")
    return data

async def make_request(url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any] | None:
    '''
    Helper function to make requests to the API
    '''
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


def main():
    try:
        mcp.run(
            transport="streamable-http"
        )
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()