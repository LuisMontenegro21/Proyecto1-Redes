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
SOLAR_API = "https://power.larc.nasa.gov/api/temporal/daily/point"
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

class Satellite(BaseModel):
    id: str
    name: str


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


def _safe_list(val):
    return val if isinstance(val, list) else []

def _safe_val(obj, key, default=None):

    if isinstance(obj, dict):
        val = obj.get(key, default)
        return default if val is None else val
    return default

@mcp.tool()
async def list_hazards(input: Hazards) -> dict:
    """List natural hazards near a location (EONET + DONKI)."""
    logging.info("Using tool list_hazards")
    events = []

    # ----- EONET -----
    eonet = await make_request(
        EONET_API,
        params={"status": "all", "start": input.start_date, "end": input.end_date}
    )
    eonet_events = _safe_list(_safe_val(eonet, "events", []))

    cats_filter = {c.lower() for c in (input.categories or [])} or None

    for ev in eonet_events:
        ev_categories = _safe_list(_safe_val(ev, "categories", []))
        ev_cat_titles = {(_safe_val(c, "title", "") or "").lower() for c in ev_categories if isinstance(c, dict)}
        if cats_filter and not (ev_cat_titles & cats_filter):
            continue

        nearest, ndist = None, None
        for g in _safe_list(_safe_val(ev, "geometry", [])):
            if _safe_val(g, "type", None) != "Point":
                continue
            coords = _safe_list(_safe_val(g, "coordinates", []))
            if len(coords) < 2:
                continue
            lon, lat = coords[0], coords[1]
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                continue

            d = haversine_km((input.lat, input.lon), (lat, lon))
            if ndist is None or d < ndist:
                ndist, nearest = d, (lat, lon, _safe_val(g, "date", None))

        if ndist is not None and ndist <= getattr(input, "radius_km", 250):
            href = None
            links = _safe_list(_safe_val(ev, "links", []))
            if links and isinstance(links[0], dict):
                href = _safe_val(links[0], "href", None)

            events.append({
                "source": "EONET",
                "title": _safe_val(ev, "title", None),
                "category": [_safe_val(c, "title", None) for c in ev_categories if isinstance(c, dict)],
                "distance_km": round(ndist, 1),
                "when": nearest[2] if nearest else None,
                "lat": nearest[0] if nearest else None,
                "lon": nearest[1] if nearest else None,
                "id": _safe_val(ev, "id", None),
                "link": href
            })

    donki = await make_request(
        DONKI_API,
        params={"startDate": input.start_date, "endDate": input.end_date, "api_key": NASA_KEY}
    )

    if isinstance(donki, dict) and "error" in donki:

        events.append({
            "source": "DONKI",
            "title": "DONKI error",
            "category": ["Space Weather"],
            "distance_km": None,
            "when": None,
            "lat": None, "lon": None,
            "id": None,
            "link": None,
            "note": _safe_val(_safe_val(donki, "error", {}), "message", "Unknown DONKI error")
        })
    else:
        for al in _safe_list(donki):
            events.append({
                "source": "DONKI",
                "title": _safe_val(al, "messageType", "Alert"),
                "category": ["Space Weather"],
                "distance_km": None,
                "when": _safe_val(al, "messageIssueTime", None),
                "lat": None, "lon": None,
                "id": _safe_val(al, "alertId", None),
                "link": _safe_val(al, "link", None)
            })

    return {"events": events}




async def solar_weather(input: SolarWindow):
    """Rank dates by solar potential and low precip; exclude severe space weather."""

    params = {
        "parameters":"ALLSKY_SFC_SW_DWN,PRECTOTCORR",
        "community":"RE",
        "longitude":input.lon,
        "latitude":input.lat,
        "start":input.start_date.replace("-",""),
        "end":input.end_date.replace("-",""),
        "format":"JSON"
    }
    power = await make_request(SOLAR_API, params)
    d = power["properties"]["parameter"]
    sw = d.get("ALLSKY_SFC_SW_DWN",{})
    pr = d.get("PRECTOTCORR",{})


    alerts = await make_request(
        DONKI_API,
        params={"startDate":input.start_date,"endDate":input.end_date,"api_key":NASA_KEY}
    )
    alert_days = {a["messageIssueTime"][:10] for a in alerts if "messageIssueTime" in a}

    def _score(day):
        ssw = float(sw.get(day, 0.0))        
        p = float(pr.get(day, 0.0))           
        penalty = 0.0
        if day in alert_days: 
            penalty += 0.3  
        penalty += min(p/20.0, 1.0)           
        raw = (ssw / 8.0)                     
        return max(raw - penalty, -1.0)

    rows=[]
    for day in sorted(set(sw.keys())|set(pr.keys())):
        rows.append({
            "date": day,
            "solar_irradiance": sw.get(day),
            "precip": pr.get(day),
            "space_weather_ok": day not in alert_days,
            "score": round(_score(day), 3)
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    return {"windows": rows[:7], "all": rows}



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
    logging.info("Starting up server")
    try: 
        mcp.run(
            transport="stdio",
        )
    except KeyboardInterrupt:
        logging.info("Stopped server : KeyboardInterrupt")

if __name__ == '__main__':
    main()