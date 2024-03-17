import json
import nonebot
from pathlib import Path
from datetime import datetime
from nonebot.log import logger
from typing import List, Awaitable
from nonebot.params import CommandArg
from datetime import datetime, timedelta
from nonebot.adapters import Event, Bot, Message
from nonebot import require, get_driver, on_command

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_apscheduler")

import nonebot_plugin_localstore as store
from nonebot_plugin_alconna import UniMessage, Image, Text, At, Target
from nonebot_plugin_apscheduler import scheduler

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import Config
from .utils import fetch_url
from .notice import Notification
from .api import MyAnimeList, Jikan
from .models.myanimelist import Season, AnimeData
from .maps import (
    media_type_map,
    status_map,
    source_map,
    season_cn_map,
    day_of_the_week_map,
)
from .data_source import (
    User,
    Base,
    AnimeGroup,
    AnimeDetailData,
    AnimeSummaryBase,
    AnimeSummaryData,
)


if getattr(nonebot, "get_plugin_config"):
    config = nonebot.get_plugin_config(Config)
else:
    config = Config.parse_obj(get_driver().config)  # type: ignore


data_file: Path = store.get_data_file("nonebot_plugin_anime_notification", "users.db")
anime_summary_data_file: Path = store.get_data_file(
    "nonebot_plugin_anime_notification", "anime_summary_data.db"
)


engine = create_engine(f"sqlite:///{data_file.resolve()}")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

anime_summary_engine = create_engine(f"sqlite:///{anime_summary_data_file.resolve()}")
AnimeSummaryBase.metadata.create_all(anime_summary_engine)
AnimeSummarySession = sessionmaker(bind=anime_summary_engine)
anime_summary_session = AnimeSummarySession()

mal_api = MyAnimeList(config.mal_client_id)
jikan_api = Jikan()

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
    broadcast = json.loads(anime_detail.broadcast)

    msg = UniMessage()

    msg += Image(url=main_picture["large"])
    msg += f"{alternative_titles.get('ja') or alternative_titles.get('en') or alternative_titles['synonyms'][0]}\n"
    msg += f"共 {anime_detail.num_episodes} 集, {status_map[anime_detail.status]}\n"
    msg += f"开始放送时间: {anime_detail.start_date}, 是 {start_season['year']} 年 {season_cn_map[start_season['season']]}季番\n" if start_season["year"] != "unknown" else "开始放送时间: 未知\n"
    msg += f"放送时间: 每{day_of_the_week_map[broadcast['day_of_the_week']]} {broadcast['start_time']}\n" if broadcast["day_of_the_week"] != "unknown" else "放送时间: 未知\n"
    msg += f"类型: {source_map[anime_detail.source]} {media_type_map[anime_detail.media_type]}\n"
    msg += (
        f"每集平均时长: {round(anime_detail.average_episode_duration / 60, 2)} 分钟\n"
    )
    msg += f"制作公司: {', '.join([studio['name'] for studio in studios])}\n"
    msg += f"观看详情: {statistics['status']['watching']} 正在观看, {statistics['status']['completed']} 已观看, {statistics['status']['on_hold']} 暂时搁置, {statistics['status']['dropped']} 弃坑, {statistics['status']['plan_to_watch']} 计划观看\n"
    msg += f"共 {statistics['num_list_users']} 人观看"
    return msg


def build_notice_func(anime_group: AnimeGroup) -> Awaitable:
    async def none():
        return None

    anime_detail = (
        session.query(AnimeDetailData).filter_by(id=anime_group.anime_id).first()
    )
    if anime_detail is None:
        return none

    user_id = anime_group.user_id
    group_id = anime_group.group_id

    target = Target(group_id, "", False, False)

    async def inner():
        bot = nonebot.get_bot()

        now = datetime.now()

        start_time = (
            datetime.strptime(anime_detail.start_date, "%Y-%m-%d")
            if anime_detail.start_date != ""
            else datetime.now()
        )
        end_time = (
            datetime.strptime(anime_detail.end_date, "%Y-%m-%d")
            if anime_detail.end_date != ""
            else datetime.now()
        )

        if not (start_time <= now <= end_time):
            return None

        alternative_titles = json.loads(anime_detail.alternative_titles)
        msg = At("user", user_id) + Text(
            f"你订阅的番剧: {alternative_titles.get('ja') or alternative_titles.get('en') or alternative_titles['synonyms'][0]} 开始放送啦！"
        )
        await msg.send(target, bot)

    return inner


async def is_group(event: Event, bot: Bot) -> bool:
    return not UniMessage.get_target(event, bot).private


async def get_animes_by_title(title: str) -> List[int]:
    animes = await jikan_api.get_anime_search(title, limit=3)
    return [
        {
            "id": anime["mal_id"],
            "title": anime["title_japanese"],
            "image": await fetch_url(anime["images"]["jpg"]["large_image_url"]),
        }
        for anime in animes["data"]
    ]


async def commit_anime_detail_data(
    anime_id: int, anime_detail_dict: dict
) -> AnimeDetailData:
    if (
        anime_detail := session.query(AnimeDetailData).filter_by(id=anime_id).first()
    ) is not None:
        return anime_detail

    anime_detail = AnimeDetailData(
        id=anime_id,
        title=anime_detail_dict["title"],
        main_picture=json.dumps(anime_detail_dict["main_picture"]),
        alternative_titles=json.dumps(anime_detail_dict["alternative_titles"]),
        start_date=anime_detail_dict["start_date"],
        synopsis=anime_detail_dict["synopsis"],
        broadcast=json.dumps(
            anime_detail_dict.get(
                "broadcast", {"day_of_the_week": "unknown", "start_time": "00:00"}
            )
        ),
        media_type=anime_detail_dict["media_type"],
        status=anime_detail_dict["status"],
        num_episodes=anime_detail_dict["num_episodes"],
        start_season=json.dumps(
            anime_detail_dict.get(
                "start_season", {"year": "unknown", "season": "unknown"}
            )
        ),
        source=anime_detail_dict["source"],
        average_episode_duration=anime_detail_dict["average_episode_duration"],
        background=anime_detail_dict["background"],
        studios=json.dumps(anime_detail_dict["studios"]),
        statistics=json.dumps(anime_detail_dict["statistics"]),
    )
    session.add(anime_detail)
    session.commit()
    return anime_detail


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
    anime_data_list: List[AnimeData] = [
        await func for func in tasks
    ]  # await asyncio.gather(*tasks)
    # gather 爬取会 timeout

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


# 如果数据库为空，爬取番剧数据
if (
    anime_summary_session.query(AnimeSummaryData).first() is None
    or len(anime_summary_session.query(AnimeSummaryData).all()) == 0
):
    get_driver().on_startup(fetch_anime)

# 每天 0 点更新番剧数据
scheduler.add_job(fetch_anime, "cron", hour=0, minute=0, second=0)

notification = Notification(
    [
        {
            "func": build_notice_func(anime_group),
            "day": (broadcast := json.loads(anime_group.anime.broadcast))[
                "day_of_the_week"
            ],
            "hour": int(broadcast["start_time"].split(":")[0]),
            "minute": int(broadcast["start_time"].split(":")[1]),
            "anime_id": anime_group.anime_id,
            "group_id": anime_group.group_id,
            "user_id": anime_group.user_id,
        }
        for anime_group in session.query(AnimeGroup).all()
    ]
)
get_driver().on_startup(notification.update_notification)

search_anime = on_command("搜索番剧", aliases={"番剧搜索"})
subscribe = on_command("订阅番剧", aliases={"番剧订阅"}, rule=is_group)
unsubscribe = on_command("取消订阅番剧", aliases={"番剧取消订阅"}, rule=is_group)
my_subscriptions = on_command("我的订阅", aliases={"订阅列表"}, rule=is_group)


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
            msg = At("user", event.get_user_id()) + Text(
                "找到以下番剧, 使用`搜索番剧 [番剧ID]`来获取详细信息吧：\n"
            )
            for anime in animes:
                msg += Text(f"\nNo. {anime['id']}: {anime['title']}\n")
                msg += Image(raw=anime["image"])
            await search_anime.finish(await UniMessage(msg).export(bot))
    else:
        anime_id = int(str_arg)
        anime_detail = session.query(AnimeDetailData).filter_by(id=anime_id).first()
        if anime_detail is None:
            # 写入新番剧数据
            try:
                anime_detail_dict = await mal_api.get_anime_detail(anime_id)
                anime_detail = await commit_anime_detail_data(
                    anime_id, anime_detail_dict
                )
            except Exception as e:
                logger.error(f"获取番剧信息失败: {e.__class__.__name__}: {e}")
                await search_anime.finish("获取番剧信息失败，请检查番剧ID是否正确")

        await build_anime_info_message(anime_detail).send(
            UniMessage.get_target(event, bot), bot, at_sender=event.get_user_id()
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
            msg = At("user", event.get_user_id()) + Text(
                "找到以下番剧, 使用`搜索番剧 [番剧ID]`来获取详细信息吧：\n"
            )
            for anime in animes:
                msg += Text(f"\nNo. {anime['id']}: {anime['title']}\n")
                msg += Image(raw=anime["image"])
            await subscribe.finish(await UniMessage(msg).export(bot))
    else:
        anime_id = int(str_arg)
        anime_detail = session.query(AnimeDetailData).filter_by(id=anime_id).first()
        if anime_detail is None:
            # 写入新番剧数据
            try:
                anime_detail_dict = await mal_api.get_anime_detail(anime_id)
                anime_detail = await commit_anime_detail_data(
                    anime_id, anime_detail_dict
                )
            except Exception as e:
                logger.error(f"获取番剧信息失败: {e.__class__.__name__}: {e}")
                await subscribe.finish("获取番剧信息失败，请检查番剧ID是否正确")

        if json.loads(anime_detail.broadcast)["day_of_the_week"] == "unknown":
            await subscribe.finish("番剧放送时间未知，无法订阅")

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

        # 添加定时任务
        notice_func = build_notice_func(anime_group)
        await notification.add_notification(
            {
                "func": notice_func,
                "day": (broadcast := json.loads(anime_detail.broadcast))[
                    "day_of_the_week"
                ],
                "hour": int(broadcast["start_time"].split(":")[0]),
                "minute": int(broadcast["start_time"].split(":")[1]),
                "anime_id": anime_group.anime_id,
                "group_id": anime_group.group_id,
                "user_id": anime_group.user_id,
            }
        )
        await ("订阅成功！\n" + build_anime_info_message(anime_detail)).send(
            target, bot, at_sender=event.get_user_id()
        )


@unsubscribe.handle()
async def handle_unsubscribe(bot: Bot, event: Event, arg: Message = CommandArg()):
    if (str_arg := arg.extract_plain_text().strip()) == "" or not str_arg.isdigit():
        await unsubscribe.finish("格式错误，请输入`取消订阅番剧 [番剧ID]`")
    else:
        anime_id = int(str_arg)
        anime_detail = session.query(AnimeDetailData).filter_by(id=anime_id).first()
        if anime_detail is None:
            # 写入新番剧数据
            try:
                anime_detail_dict = await mal_api.get_anime_detail(anime_id)
                anime_detail = await commit_anime_detail_data(
                    anime_id, anime_detail_dict
                )
            except Exception as e:
                logger.error(f"获取番剧信息失败: {e.__class__.__name__}: {e}")
                await unsubscribe.finish("获取番剧信息失败，请检查番剧ID是否正确")

        target = UniMessage.get_target(event, bot)
        anime_group = (
            session.query(AnimeGroup)
            .filter_by(user_id=event.get_user_id(), anime_id=anime_detail.id)
            .first()
        )
        if anime_group is None:
            await unsubscribe.finish("你还没有订阅这部番剧")
        session.delete(anime_group)
        session.commit()

        # 删除定时任务
        await notification.remove_notification(
            {
                "anime_id": anime_group.anime_id,
                "group_id": anime_group.group_id,
                "user_id": anime_group.user_id,
            }
        )
        await UniMessage("取消订阅成功！\n").send(
            target, bot, at_sender=event.get_user_id()
        )


@my_subscriptions.handle()
async def handle_my_subscriptions(bot: Bot, event: Event):
    anime_groups = (
        session.query(AnimeGroup)
        .filter_by(user_id=event.get_user_id())
        .join(AnimeDetailData)
        .all()
    )
    if len(anime_groups) == 0:
        await my_subscriptions.finish("你还没有订阅任何番剧")
    else:
        msg = At("user", event.get_user_id()) + Text("你订阅的番剧有：\n")
        for anime_group in anime_groups:
            anime_detail = (
                session.query(AnimeDetailData)
                .filter_by(id=anime_group.anime_id)
                .first()
            )
            alternative_titles = json.loads(anime_detail.alternative_titles)
            broadcast = json.loads(anime_detail.broadcast)
            msg += Text(
                f"\nNo. {anime_detail.id}: {alternative_titles.get('ja') or alternative_titles.get('en') or alternative_titles['synonyms'][0]}\n"
                + f"放送时间: 每{day_of_the_week_map[broadcast['day_of_the_week']]} {broadcast['start_time']}\n"
            )
        await my_subscriptions.finish(await UniMessage(msg).export(bot))
