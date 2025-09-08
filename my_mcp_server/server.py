# Reference: https://modelcontextprotocol.io/quickstart/client 
import httpx
from typing import Any, Optional
from mcp.server.fastmcp import FastMCP
import json
import sys
import asyncio
import logging
import math
from pydantic import BaseModel



SATELLITE_API = "https://tle.ivanstanojevic.me/api"
EONET_API = "https://eonet.gsfc.nasa.gov/api/v3/events"
DONKI_API = "https://api.nasa.gov/DONKI/alerts"
NASA_KEY = "DEMO"
mcp = FastMCP(name="MyMCPServer")

# configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)

# for some reason it only works with this
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; mcp-client/1.0; +https://example.com)",
    "Connection": "close",
}



class Hazards(BaseModel):
    lat: float
    lon: float
    radius_km: float = 250
    start_date: str
    end_date: str
    categories: list[str] | None = None

class SolarWindow(BaseModel):
    lat: float
    lon: float
    start_date: str
    end_date: str

def haversine_km(a: tuple, b: tuple) -> float:
    # a=(lat,lon), b=(lat,lon)
    R=6371.0
    dlat=math.radians(b[0]-a[0])
    dlon=math.radians(b[1]-a[1])
    s = (math.sin(dlat/2)**2 + math.cos(math.radians(a[0]))*math.cos(math.radians(b[0]))*math.sin(dlon/2)**2)
    return 2*R*math.asin(math.sqrt(s))

@mcp.tool()
async def get_hazards(input: Hazards) -> dict:
    eonet = await make_request(EONET_API, params={"status":"all", "start":input.start_date, "end":input.end_date})
    events = []
    for ev in eonet.get("events",[]):
        if input.categories and ev.get("categories"):
            cats = {c["title"].lower() for c in ev["categories"]}
            if not any(c in cats for c in [c.lower() for c in input.categories]):
                continue

        nearest=None; ndist=None
        for g in ev.get("geometry", []):
            if g.get("type")=="Point":
                lat,lon = g["coordinates"][1], g["coordinates"][0]
                d = haversine_km((input.lat,input.lon),(lat,lon))
                if ndist is None or d<ndist: 
                    ndist, nearest = d, (lat,lon,g.get("date"))
        if ndist is not None and ndist <= input.radius_km:
            events.append({
                "source":"EONET",
                "title":ev.get("title"),
                "category":[c["title"] for c in ev.get("categories",[])],
                "distance_km":round(ndist,1),
                "when":nearest[2],
                "lat":nearest[0],"lon":nearest[1],
                "id":ev.get("id"),
                "link":ev.get("links",[{}])[0].get("href")
            })
        donki = await make_request(DONKI_API, params={"startDate":input.start_date,"endDate":input.end_date,"api_key":NASA_KEY})
        for al in donki:
            events.append({
                "source":"DONKI",
                "title":al.get("messageType","Alert"),
                "category":["Space Weather"],
                "distance_km": None,
                "when": al.get("messageIssueTime"),
                "lat": None, "lon": None,
                "id": al.get("alertId"),
                "link": al.get("link")
            })
    logging.info("Using tool get_hazards")
    return {"events": events}


@mcp.tool()
async def get_satellite_data(query: str) -> str:    
    '''
    Searches information from a satellite
    '''
    url = f"{SATELLITE_API}/tle/"  

    data = await make_request(url=url, params={"search": query})
    if  not isinstance(data, dict):
        return f"Fetching failed for '{query}'"
    
    members = data.get("member", [])
    if not members:
        return f"No members found"
    
    data = await asyncio.gather(*[format_information(m) for m in members])
    logging.info("Using tool get_satellite_data")
    return "\n\n".join(data)

@mcp.tool()
async def get_satellite_by_id(query: str) -> str:
    '''
    Gets information from a satellite using the ID
    '''
    url = f"{SATELLITE_API}/tle/{query}"
    data = await make_request(url=url)
    if  not isinstance(data, dict):
        return f"Fetching failed for '{query}'"
    data = await asyncio.gather(format_information(data))
    logging.info("Using tool get_satellite_by_id")
    return "\n\n".join(data)

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
    logging.info("Starting up server")
    try: 
        mcp.run(
            transport="stdio",
        )
    except KeyboardInterrupt:
        logging.info("Stopped server : KeyboardInterrupt")

if __name__ == '__main__':
    main()