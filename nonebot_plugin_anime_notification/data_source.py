from nonebot import require

require("nonebot_plugin_localstore")

import nonebot_plugin_localstore as store

# 用户数据结构示例
# list(
#     {"user_id": str, "anime_list": list({"anime_detail": AnimeDetail, "group_id": str})}
# )

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True)
    anime_list = relationship("AnimeGroup", back_populates="user")


class AnimeDetailData(Base):
    __tablename__ = "anime_details"

    id = Column(Integer, primary_key=True)
    title = Column(String)
    main_picture = Column(String)  # Store as JSON string
    alternative_titles = Column(String)  # Store as JSON string
    start_date = Column(String)
    synopsis = Column(String)
    media_type = Column(String)
    status = Column(String)
    num_episodes = Column(Integer)
    start_season = Column(String)  # Store as JSON string
    source = Column(String)
    average_episode_duration = Column(Integer)
    background = Column(String)
    studios = Column(String)  # Store as JSON string
    statistics = Column(String)  # Store as JSON string

    groups = relationship("AnimeGroup", back_populates="anime")


class AnimeGroup(Base):
    __tablename__ = "anime_groups"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    anime_id = Column(Integer, ForeignKey("anime_details.id"))
    group_id = Column(String)

    user = relationship("User", back_populates="anime_list")
    anime = relationship("AnimeDetail", back_populates="groups")
