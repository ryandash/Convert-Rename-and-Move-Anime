import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

import aiohttp
from jikanpy import AioJikan, exceptions


@dataclass
class TitleEntry:
    title: str
    type: str


@dataclass
class MinimalAnime:
    malId: int
    type: str
    titles: List[TitleEntry] = field(default_factory=list)
    relations: List[dict] = field(default_factory=list)
    episodes: int = 0
    url: Optional[str] = None
    aired: dict[str, Any] = field(default_factory=dict)


class TaskLimiterConfiguration:
    def __init__(
        self,
        max_tasks: int,
        period_sec: float,
    ):
        self.max_tasks = max_tasks
        self.period_sec = period_sec
        self._timestamps: List[float] = []

    async def wait_for_slot(self) -> None:
        now = time.monotonic()

        self._timestamps = [
            timestamp
            for timestamp in self._timestamps
            if now - timestamp < self.period_sec
        ]

        if len(self._timestamps) >= self.max_tasks:
            wait_time = (
                self.period_sec
                - (now - self._timestamps[0])
            )
            await asyncio.sleep(wait_time)

        self._timestamps.append(time.monotonic())


class TaskLimiter:
    def __init__(
        self,
        configs: List[TaskLimiterConfiguration],
    ):
        self.configs = configs
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            for config in self.configs:
                await config.wait_for_slot()


class SafeJikan:
    def __init__(
        self,
        request_delay: float = 0.5,
        max_concurrent: int = 10,
    ):
        self.request_delay = request_delay
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Keep the existing API endpoint.
        self.aio_jikan = AioJikan(
            selected_base="https://api.tenrai.org/v1"
        )

        self._last_request = 0.0
        self._request_lock = asyncio.Lock()

        self.limiter = TaskLimiter([
            TaskLimiterConfiguration(3, 1.0),
            TaskLimiterConfiguration(4, 4.0),
        ])

    async def _wait_for_slot(self) -> None:
        async with self._request_lock:
            now = time.monotonic()
            elapsed = now - self._last_request

            if elapsed < self.request_delay:
                await asyncio.sleep(
                    self.request_delay - elapsed
                )

            self._last_request = time.monotonic()

    async def _retry_on_failure(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        delay = 1.0
        max_delay = 60.0
        attempt = 0

        while True:
            try:
                async with self.semaphore:
                    await self.limiter.acquire()
                    await self._wait_for_slot()

                    return await func(
                        *args,
                        **kwargs,
                    )

            except exceptions.APIException as e:
                code = (
                    getattr(e, "status", None)
                    or getattr(e, "status_code", None)
                    or getattr(e, "code", None)
                )

                if code in (429, 500, 502, 503, 504):
                    attempt += 1

                    reason = (
                        "Rate limited"
                        if code == 429
                        else f"Server error {code}"
                    )

                    print(
                        f"[Jikan] {reason} "
                        f"(attempt {attempt}). "
                        f"Retrying in {delay:.1f}s..."
                    )

                    await asyncio.sleep(delay)
                    delay = min(delay * 1.5, max_delay)

                elif code == 404:
                    print(
                        "[Jikan] Resource not found (404). "
                        "Returning None."
                    )
                    return None

                else:
                    print(
                        f"[Jikan] Non-retryable API error "
                        f"{code}: {e}"
                    )
                    raise

            except (
                asyncio.TimeoutError,
                aiohttp.ClientError,
                OSError,
            ) as e:
                attempt += 1

                print(
                    f"[Jikan] Request error: {e} "
                    f"(attempt {attempt}). "
                    f"Retrying in {delay:.1f}s..."
                )

                await asyncio.sleep(delay)
                delay = min(delay * 1.5, max_delay)

    async def anime_list(self, **kwargs) -> dict:
        url = f"{self.aio_jikan.base}/anime"
        session = await self.aio_jikan._get_session()

        response = await session.get(
            url,
            params=kwargs,
        )

        return await self.aio_jikan._wrap_response(
            response,
            str(response.url),
        )

    async def search_anime(
        self,
        query: str | None = None,
        type_: str | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> dict:
        if (
            query is None
            and type_ is None
            and page is None
        ):
            raise ValueError(
                "search_anime() requires at least one of: "
                "query, type_, or page."
            )

        if query is not None:
            query = query.strip()

            if len(query) < 3:
                return None

            query = query[:180].rstrip()

        params = {}

        if query:
            params["q"] = query

        if type_:
            params["type"] = type_

        if limit:
            params["limit"] = limit

        if page:
            params["page"] = page

        result = await self._retry_on_failure(
            self.anime_list,
            **params,
        )

        if not result:
            return None

        result["data"] = [
            anime
            for anime in result.get("data", [])
            if not (
                anime.get("rating") or ""
            ).lower().startswith("rx")
        ]

        return result

    async def get_anime_full(
        self,
        mal_id: int,
    ) -> Optional[MinimalAnime]:
        data = await self._retry_on_failure(
            self.aio_jikan.anime,
            mal_id,
            extension="full",
        )

        if not data:
            return None

        node = data.get("data") or {}

        titles = [
            TitleEntry(
                title=entry["title"],
                type=entry["type"],
            )
            for entry in node.get("titles", [])
            if entry.get("title")
        ]

        relations = []

        for relation in node.get("relations", []):
            entries = [
                entry
                for entry in relation.get("entry", [])
                if (
                    entry.get("type") or ""
                ).lower() != "manga"
            ]

            if entries:
                relations.append({
                    "relation": relation.get(
                        "relation",
                        "",
                    ),
                    "entry": entries,
                })

        return MinimalAnime(
            malId=mal_id,
            type=(node.get("type") or "").lower(),
            titles=titles,
            relations=relations,
            episodes=node.get("episodes") or 0,
            url=node.get("url"),
            aired=node.get("aired") or {},
        )

    async def close(self) -> None:
        await self.aio_jikan.close()