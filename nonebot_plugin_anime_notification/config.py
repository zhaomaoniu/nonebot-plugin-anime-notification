from pydantic import BaseModel


class Config(BaseModel):
    MAL_CLIENT_ID: str
    """MyAnimeList API client id"""
