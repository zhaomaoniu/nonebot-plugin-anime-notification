import json
import asyncio
import nonebot
from pathlib import Path
from typing import List, Dict
from nonebot.log import logger
from nonebot.params import CommandArg
from datetime import datetime, timedelta
from nonebot.adapters import Event, Bot, Message
from nonebot import require, get_driver, on_command

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")

import nonebot_plugin_localstore as store
from nonebot_plugin_alconna import UniMessage, Image

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import Config
from .api import MyAnimeList
from .utils import fuzzy_match
from .maps import media_type_map, status_map, source_map, season_cn_map
from .models.myanimelist import Data, Season, AnimeData, AlternativeTitles
from .data_source import (
    User,
    AnimeSummaryData,
    AnimeDetailData,
    AnimeGroup,
    Base,
    AnimeSummaryBase,
)


if getattr(nonebot, "get_plugin_config"):
    config = nonebot.get_plugin_config(Config)
else:
    config = Config.parse_obj(get_driver().config)  # type: ignore


data_file: Path = store.get_data_file("nonebot_plugin_anime_notification", "users.db")
anime_summary_data_file: Path = store.get_data_file(
    "nonebot_plugin_anime_notification", "anime_summary_data.db"
)


engine = create_engine(f"sqlite:///{data_file.resolve()}", echo=True)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

anime_summary_engine = create_engine(
    f"sqlite:///{anime_summary_data_file.resolve()}", echo=True
)
AnimeSummaryBase.metadata.create_all(anime_summary_engine)
AnimeSummarySession = sessionmaker(bind=anime_summary_engine)
anime_summary_session = AnimeSummarySession()

mal_api = MyAnimeList(config.mal_client_id)

season_map = {0: "winter", 1: "spring", 2: "summer", 3: "fall"}
season_index_map = {v: k for k, v in season_map.items()}


def get_time_info(dt: datetime):
    year = dt.year
    season = season_map[(dt.month - 1) // 3]
    return {"year": year, "season": season}


def build_anime_info_message(anime_detail: AnimeDetailData) -> UniMessage:
    main_picture = json.loads(anime_detail.main_picture)
    alternative_titles = json.loads(anime_detail.alternative_titles)
    start_season = json.loads(anime_detail.start_season)
    studios = json.loads(anime_detail.studios)
    statistics = json.loads(anime_detail.statistics)

    msg = UniMessage()

    msg += Image(url=main_picture["large"])
    msg += f"{alternative_titles['jp'] or alternative_titles['en'] or alternative_titles['synonyms'][0]}\n"
    msg += f"共 {anime_detail.num_episodes} 集, {status_map[anime_detail.status]}\n"
    msg += f"开始放送时间: {anime_detail.start_date}, 是 {start_season['year']} 年 {season_cn_map[start_season['season']]} 季番\n"
    msg += f"类型: {source_map[anime_detail.source]} {media_type_map[anime_detail.media_type]}\n"
    msg += f"每集平均时长: {anime_detail.average_episode_duration / 60} 分钟\n"
    msg += f"制作公司: {', '.join([studio['name'] for studio in studios])}\n"
    msg += f"观看详情: {statistics['status']['watching']} 正在观看, {statistics['status']['completed']} 已观看, {statistics['status']['on_hold']} 暂时搁置, {statistics['status']['dropped']} 弃坑, {statistics['status']['plan_to_watch']} 计划观看\n"
    msg += f"共 {statistics['num_list_users']} 人观看"
    return msg


async def is_group(event: Event, bot: Bot) -> bool:
    return not UniMessage.get_target(event, bot).private


async def get_animes_by_title(title: str):
    # 读取数据库
    # 把已有番剧数据都读取出来
    anime_detail_data_list = session.query(AnimeDetailData).all()

    # 建立 id 到 alternative_titles 的映射
    id_to_alternative_titles: Dict[int, List[str]] = {}
    for anime_detail_data in anime_detail_data_list:
        alternative_titles: AlternativeTitles = json.loads(
            anime_detail_data.alternative_titles
        )
        id_to_alternative_titles[anime_detail_data.id] = []
        for title in alternative_titles.values():
            if isinstance(title, str):
                id_to_alternative_titles[anime_detail_data.id].append(title)
            elif isinstance(title, list):
                id_to_alternative_titles[anime_detail_data.id].extend(title)

    # 模糊匹配
    return fuzzy_match(title, id_to_alternative_titles, 3)


@get_driver().on_startup
async def fetch_anime():
    # 读取数据库，如果没有往后三个季度的数据就爬取数据
    anime_data = anime_summary_session.query(AnimeSummaryData).all()

    if anime_data is not None and len(anime_data) != 0:
        logger.info("番剧数据存在，正在检查是否需要更新")
        # 找到季节最新的数据
        latest_season: Season = json.loads(anime_data[0].season)
        for data in anime_data:
            last_season: Season = json.loads(data.season)

            if (
                last_season["year"] > latest_season["year"]
                and season_index_map[last_season["season"]]
                > season_index_map[latest_season["season"]]
            ):
                latest_season = last_season

        # 判断最新的季节是否是当前季节后的第三个季节
        time_info = get_time_info(datetime.now() + timedelta(days=3 * 30))
        year: int = time_info["year"]
        season: str = time_info["season"]
        if (
            latest_season["year"] >= year
            and season_index_map[latest_season["season"]] >= season_index_map[season]
        ):
            logger.info("番剧数据已为最新")
            return None

    # 爬取往后三个季度的番剧消息
    # 获取当前季度
    time_info = get_time_info(datetime.now())
    year: int = time_info["year"]
    season: str = time_info["season"]

    # 使用 gather 并发获取三个季度的番剧信息
    tasks = []
    for _ in range(3):
        tasks.append(mal_api.get_seasonal_anime(year, season))
        if season == "fall":
            year += 1
        season = season_map[(season_index_map[season] + 1) % 4]

    logger.info("正在爬取番剧数据")
    anime_data_list: List[AnimeData] = [await func for func in tasks] # await asyncio.gather(*tasks)

    # 将获取到的番剧信息存入数据库
    for anime_data in anime_data_list:
        for data in anime_data["data"]:
            # 确保ID唯一
            anime = (
                anime_summary_session.query(AnimeSummaryData)
                .filter_by(id=data["node"]["id"])
                .first()
            )
            if anime is not None:
                continue

            anime = AnimeSummaryData(
                id=data["node"]["id"],
                data=json.dumps(data["node"]),
                pagging=json.dumps(anime_data["paging"]),
                season=json.dumps(anime_data["season"]),
                last_update=int(datetime.now().timestamp()),
            )
            anime_summary_session.add(anime)
    anime_summary_session.commit()

    # 判断是否有番剧详情数据，如果没有就爬取
    anime_detail_data_list = session.query(AnimeDetailData).all()
    anime_detail_id_list = [
        anime_detail_data.id for anime_detail_data in anime_detail_data_list
    ]

    # 进行数据扁平化
    anime_summary_list: List[Data] = []
    for anime_data in anime_data_list:
        anime_summary_list.extend(anime_data["data"])
    anime_summary_id_list = [
        anime_summary["node"]["id"] for anime_summary in anime_summary_list
    ]

    anime_id_list: List[str] = list(
        set(anime_summary_id_list) - set(anime_detail_id_list)
    )

    if len(anime_id_list) == 0:
        logger.info("番剧详情数据已为最新")
        return None

    # gather 获取近三个季度番剧详情
    tasks = []
    for anime_id in anime_id_list:
        tasks.append(mal_api.get_anime_detail(anime_id))
    logger.info("正在爬取番剧详情数据")
    anime_detail_data_list = [await func for func in tasks] # await asyncio.gather(*tasks)

    # 将获取到的番剧详情存入数据库
    for anime_detail_data in anime_detail_data_list:
        # 确保ID唯一
        anime = (
            session.query(AnimeDetailData).filter_by(id=anime_detail_data["id"]).first()
        )
        if anime is not None:
            continue

        anime = AnimeDetailData(
            id=anime_detail_data["id"],
            title=anime_detail_data["title"],
            main_picture=json.dumps(anime_detail_data["main_picture"]),
            alternative_titles=json.dumps(anime_detail_data["alternative_titles"]),
            start_date=anime_detail_data["start_date"],
            synopsis=anime_detail_data["synopsis"],
            media_type=anime_detail_data["media_type"],
            status=anime_detail_data["status"],
            num_episodes=anime_detail_data["num_episodes"],
            start_season=json.dumps(anime_detail_data["start_season"]),
            source=anime_detail_data["source"],
            average_episode_duration=anime_detail_data["average_episode_duration"],
            background=anime_detail_data["background"],
            studios=json.dumps(anime_detail_data["studios"]),
            statistics=json.dumps(anime_detail_data["statistics"]),
        )
        session.add(anime)

    session.commit()


search_anime = on_command("搜索番剧")
subscribe = on_command("订阅番剧", rule=is_group)


@search_anime.handle()
async def handle_search(bot: Bot, event: Event, arg: Message = CommandArg()):
    if (str_arg := arg.extract_plain_text().strip()) == "":
        await search_anime.finish("格式错误，请输入`搜索番剧 [番剧名称/番剧ID]`")
    elif not str_arg.isdigit():
        animes = await get_animes_by_title(str_arg)

        # 生成消息
        if len(animes) == 0:
            await search_anime.finish("没有找到相关番剧，换换关键词试试吧")
        else:
            msg = "找到以下番剧, 使用`搜索番剧 [番剧ID]`来获取详细信息吧：\n"
            for anime in animes:
                msg += f"{anime['id']}: {anime['match']}\n"
            await search_anime.finish(msg)
    else:
        anime_id = int(str_arg)
        anime_detail = session.query(AnimeDetailData).filter_by(id=anime_id).first()
        if anime_detail is None:
            await search_anime.finish("没有找到相关番剧，请检查番剧ID是否正确")
        else:
            await build_anime_info_message(anime_detail).send(
                UniMessage.get_target(event, bot), bot, at_sender=True
            )


@subscribe.handle()
async def handle_subscribe(bot: Bot, event: Event, arg: Message = CommandArg()):
    if (str_arg := arg.extract_plain_text().strip()) == "":
        await subscribe.finish("格式错误，请输入`订阅番剧 [番剧名称/番剧ID]`")
    elif not str_arg.isdigit():
        animes = await get_animes_by_title(str_arg)

        # 生成消息
        if len(animes) == 0:
            await subscribe.finish("没有找到相关番剧，换换关键词试试吧")
        else:
            msg = "找到以下番剧，请再次使用`订阅番剧 [番剧ID]`：\n"
            for anime in animes:
                msg += f"{anime['id']}: {anime['match']}\n"
            await subscribe.finish(msg)
    else:
        anime_id = int(str_arg)
        anime_detail = session.query(AnimeDetailData).filter_by(id=anime_id).first()
        if anime_detail is None:
            await subscribe.finish("没有找到相关番剧，请检查番剧ID是否正确")
        else:
            target = UniMessage.get_target(event, bot)
            user = session.query(User).filter_by(user_id=event.get_user_id()).first()

            if user is None:
                user = User(user_id=event.get_user_id())
                session.add(user)
                session.commit()

            anime_group = AnimeGroup(
                user_id=user.user_id,
                anime_id=anime_detail.id,
                group_id=target.id or target.parent_id,
            )
            session.add(anime_group)
            session.commit()
            await ("订阅成功！\n" + build_anime_info_message(anime_detail)).send(
                target, bot, at_sender=True
            )
