import aiohttp

from ..models.myanimelist import AnimeData, AnimeDetail


class MyAnimeList:
    def __init__(self, client_id: str):
        self._client = aiohttp.ClientSession(headers={"X-MAL-CLIENT-ID": client_id})
        self._base_url = "https://api.myanimelist.net/v2"
        self._fields = [
            "id",
            "title",
            "main_picture",
            "alternative_titles",
            "start_date",
            "end_date",
            "synopsis",
            "rank",
            "media_type",
            "status",
            "num_episodes",
            "start_season",
            "broadcast",
            "source",
            "average_episode_duration",
            "background",
            "studios",
            "statistics",
        ]

    async def get_seasonal_anime(self, year: int, season: str) -> AnimeData:
        async with self._client.get(
            f"{self._base_url}/anime/season/{year}/{season}?limit=500",
        ) as response:
            if response.status != 200:
                raise Exception(f"Failed to get seasonal anime: {await response.text()}")
            return await response.json()

    async def get_anime_detail(self, anime_id: int) -> AnimeDetail:
        async with self._client.get(
            f"{self._base_url}/anime/{anime_id}?fields=" + ",".join(self._fields),
        ) as response:
            if response.status != 200:
                raise Exception(f"Failed to get anime detail: {await response.text()}")
            return await response.json()

    async def close(self):
        await self._client.close()
