from typing import List, Awaitable, TypedDict
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .maps import day_of_the_week_num_map


class NoticeData(TypedDict):
    day: str
    hour: str
    minute: str
    func: Awaitable
    anime_id: int
    group_id: str
    user_id: str


class Notification:
    def __init__(self, data: List[NoticeData]) -> None:
        self.data: List[NoticeData] = data
        self.scheduler = AsyncIOScheduler()

    async def update_notification(self) -> None:
        # 删除原有的定时任务，重新添加新的定时任务
        self.scheduler.remove_all_jobs()
        for notice in self.data:
            self.scheduler.add_job(
                notice["func"],
                "cron",
                day_of_week=day_of_the_week_num_map[notice["day"]],
                # day_of_week 0-6 代表周一到周日
                hour=notice["hour"],
                minute=notice["minute"],
            )
        if not self.scheduler.running:
            self.scheduler.start()

    async def add_notification(self, notice: NoticeData) -> None:
        self.data.append(notice)
        await self.update_notification()

    async def remove_notification(self, notice: NoticeData) -> None:
        # 使用 anime_id, group_id, user_id 作为唯一标识
        for i, n in enumerate(self.data):
            if (
                n["anime_id"] == notice["anime_id"]
                and n["group_id"] == notice["group_id"]
                and n["user_id"] == notice["user_id"]
            ):
                self.data.pop(i)
                break
        await self.update_notification()
