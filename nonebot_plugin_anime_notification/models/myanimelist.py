from typing import TypedDict, List


class Picture(TypedDict):
    medium: str
    large: str


class Node(TypedDict):
    id: int
    title: str
    main_picture: Picture


class Data(TypedDict):
    node: Node


class Season(TypedDict):
    year: int
    season: str


class Paging(TypedDict):
    pass  # 没有给出paging的具体结构，所以暂时留空


class Picture(TypedDict):
    medium: str
    large: str


class AlternativeTitles(TypedDict):
    synonyms: List[str]
    en: str
    ja: str


class Studio(TypedDict):
    id: int
    name: str


class StatusStatistics(TypedDict):
    watching: int
    completed: int
    on_hold: int
    dropped: int
    plan_to_watch: str


class Statistics(TypedDict):
    status: StatusStatistics
    num_list_users: int


class Broadcast(TypedDict):
    day_of_the_week: str
    start_time: str


class AnimeData(TypedDict):
    data: List[Data]
    paging: Paging
    season: Season


class AnimeDetail(TypedDict):
    id: int
    title: str
    main_picture: Picture
    alternative_titles: AlternativeTitles
    start_date: str
    end_date: str
    synopsis: str
    broadcast: Broadcast
    media_type: str
    status: str
    num_episodes: int
    start_season: Season
    source: str
    average_episode_duration: int
    background: str
    studios: List[Studio]
    statistics: Statistics
