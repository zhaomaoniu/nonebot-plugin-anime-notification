import nonebot
from datetime import datetime
from pathlib import Path
from nonebot import require, get_driver

require("nonebot_plugin_localstore")

import nonebot_plugin_localstore as store

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .api import MyAnimeList
from .config import Config


if getattr(nonebot, "get_plugin_config"):
    config = nonebot.get_plugin_config(Config)
else:
    config = Config.parse_obj(get_driver().config) # type: ignore


data_file: Path = store.get_data_file("nonebot_plugin_anime_notification", "users.db")

engine = create_engine(f'sqlite:///{data_file.resolve()}', echo=True)
Session = sessionmaker(bind=engine)
session = Session()

mal_api = MyAnimeList(config.MAL_CLIENT_ID)

season_map = {
    0: "winter",
    1: "spring",
    2: "summer",
    3: "fall"
}


def get_time_info(dt: datetime):
    year = dt.year
    season = season_map[(dt.month - 1) // 3]
    return {"year": year, "season": season}


@get_driver().on_startup
async def fetch_anime():
    # 爬取往后三个季度的番剧消息
    # 获取当前季度
    time_info = get_time_info(datetime.now())
    year = time_info["year"]
    season = time_info["season"]

    # 获取当前季度的番剧信息

    

