import aiohttp


async def fetch_url(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Failed to fetch url: {await response.text()}")
            return await response.read()
