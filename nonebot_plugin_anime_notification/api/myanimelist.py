from httpx import AsyncClient

from ..models.myanimelist import AnimeData, AnimeDetail


class MyAnimeList:
    def __init__(self, client_id: str):
        self._client = AsyncClient()
        self._base_url = "https://api.myanimelist.net/v2"
        self._headers = {"X-MAL-CLIENT-ID": client_id}
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

    async def get_seasonal_anime(self, year: str, season: str) -> AnimeData:
        response = await self._client.get(
            f"{self._base_url}/anime/season/{year}/{season}?limit=500",
            headers=self._headers,
        )
        if response.status_code != 200:
            raise Exception(f"Failed to get seasonal anime: {response.text}")
        return response.json()

    async def get_anime_detail(self, anime_id: int) -> AnimeDetail:
        response = await self._client.get(
            f"{self._base_url}/anime/{anime_id}?fields=" + ",".join(self._fields),
            headers=self._headers,
        )
        if response.status_code != 200:
            raise Exception(f"Failed to get anime detail: {response.text}")
        return response.json()
