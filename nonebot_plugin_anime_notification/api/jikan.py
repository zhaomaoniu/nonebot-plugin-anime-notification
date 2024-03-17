import aiohttp


class Jikan:
    def __init__(self) -> None:
        self._base_url = "https://api.jikan.moe/v4"

    async def get_anime_search(self, q: str, sfw: bool = True, limit: int = 10):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self._base_url}/anime?q={q}&limit={limit}&sfw={str(sfw).lower()}",
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to search anime: {await response.text()}")
                return await response.json()
