# test.py
import asyncio
from server import make_request

async def main():
    data = await make_request("https://tle.ivanstanojevic.me/api/tle/", params={"search":"33591"})
    print(type(data), ("keys:" + str(list(data.keys()))) if isinstance(data, dict) else data)

asyncio.run(main())