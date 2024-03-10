from pydantic import BaseModel


class Config(BaseModel):
    mal_client_id: str
    """MyAnimeList API client id"""
