import re
from difflib import SequenceMatcher
from typing import Any, Optional


FORMAT_PRIORITY = {
    "TV": 0,
    "ONA": 1,
    "TV_SPECIAL": 2,
    "MOVIE": 3,
    "OVA": 4,
    "SPECIAL": 5,
}

SKIP_FORMATS = {
    "OVA",
    "SPECIAL",
    "TV_SPECIAL",
    "MUSIC",
    "CM",
    "PV",
}

SANITIZE_RE = re.compile(r'\s*[<>:"/\\|?*]\s*')
SPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"""[:!?,.'"`]""")
DASH_RE = re.compile(r"[-_/\\]+")
PART_RE = re.compile(r"\bpart\s+\d+\b", re.IGNORECASE)
SEASON_RE = re.compile(
    r"\b(\d+)(?:st|nd|rd|th)\s+season\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"^(\d{4})")

def sanitize(name: str) -> str:
    if not name:
        return ""

    return SPACE_RE.sub(
        " ",
        SANITIZE_RE.sub(" ", name),
    ).rstrip(". ").strip()


def normalize_title(title: str) -> str:
    if not title:
        return ""

    title = title.casefold()
    title = PUNCT_RE.sub("", title)
    title = DASH_RE.sub(" ", title)

    return SPACE_RE.sub(" ", title).strip()


def similarity(a: str, b: str) -> float:
    a = normalize_title(a)
    b = normalize_title(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 100.0

    return SequenceMatcher(None, a, b).ratio() * 100

def _format_type(value: Optional[str]) -> str:
    value = (value or "").upper().strip()

    return {
        "TV SPECIAL": "TV_SPECIAL",
    }.get(value, value)


def _extract_year(aired: Any) -> Optional[int]:
    date_value = _get(aired, "from")

    if not date_value:
        return None

    match = YEAR_RE.match(str(date_value))
    return int(match.group(1)) if match else None


def _empty_titles() -> dict:
    return {
        "default": None,
        "japanese": None,
        "english": None,
        "synonyms": [],
    }

def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(obj, key, default)

def _title_entries_to_dict(titles: Any) -> dict:
    result = _empty_titles()

    for entry in titles or []:
        title = _get(entry, "title")
        title_type = (_get(entry, "type", "") or "").casefold()

        if not title:
            continue

        if title_type in ("default", "japanese", "english"):
            result[title_type] = title

        elif title_type == "synonym":
            result["synonyms"].append(title)

    return result


def _extract_titles_from_search_result(node: dict) -> dict:
    result = _title_entries_to_dict(node.get("titles"))

    if not result["default"]:
        result["default"] = node.get("title")

    return result


def _normalize_search_result(node: dict) -> dict:
    titles = _extract_titles_from_search_result(node)
    aired = node.get("aired") or {}
    mal_id = node.get("mal_id")
    media_type = _format_type(node.get("type"))

    return {
        "id": mal_id,
        "malId": mal_id,
        "title": titles["default"],
        "titles": titles,
        "format": media_type,
        "type": media_type,
        "episodes": node.get("episodes") or 0,
        "season": node.get("season"),
        "seasonYear": _extract_year(aired),
        "aired": aired,
        "url": node.get("url"),
        "relations": [],
    }


def _normalize_minimal_anime(anime: Any) -> Optional[dict]:
    if anime is None:
        return None

    titles = _title_entries_to_dict(_get(anime, "titles"))
    aired = _get(anime, "aired") or {}
    mal_id = _get(anime, "malId")
    media_type = _format_type(_get(anime, "type"))

    return {
        "id": mal_id,
        "malId": mal_id,
        "title": titles["default"],
        "titles": titles,
        "format": media_type,
        "type": media_type,
        "episodes": _get(anime, "episodes", 0) or 0,
        "season": _get(anime, "season"),
        "seasonYear": _extract_year(aired),
        "aired": aired,
        "url": _get(anime, "url"),
        "relations": _get(anime, "relations") or [],
    }


async def _ensure_full_anime(jikan, media: dict) -> Optional[dict]:
    mal_id = media.get("malId") or media.get("id")

    if not mal_id:
        return media

    full = await jikan.get_anime_full(mal_id)

    if full is None:
        return media

    normalized = _normalize_minimal_anime(full)

    if normalized is None:
        return media

    if not normalized.get("titles"):
        normalized["titles"] = media.get("titles", {})

    if not normalized.get("seasonYear"):
        normalized["seasonYear"] = media.get("seasonYear")

    if not normalized.get("season"):
        normalized["season"] = media.get("season")

    return normalized


def get_all_titles(media: dict) -> list[str]:
    titles = media.get("titles") or {}

    result = [
        titles[key]
        for key in ("default", "japanese", "english")
        if titles.get(key)
    ]

    result.extend(
        title
        for title in titles.get("synonyms", []) or []
        if title
    )

    if not result and media.get("title"):
        result.append(media["title"])

    return result


def pick_title(media: dict) -> str:
    titles = media.get("titles") or {}
    title = titles.get("default") or media.get("title")

    return sanitize(title) if title else "Unknown"


def format_priority(media: dict) -> int:
    return FORMAT_PRIORITY.get(
        (media.get("format") or "").upper(),
        99,
    )


def is_skippable(media: dict) -> bool:
    fmt = (media.get("format") or "").upper()

    if fmt in SKIP_FORMATS:
        return True

    if (
        fmt in {"TV", "ONA"}
        and media.get("episodes") == 1
    ):
        return True

    if fmt not in {"TV", "ONA", "MOVIE"}:
        title = " ".join(get_all_titles(media)).casefold()

        if re.search(r"\b(?:ova|special)\b", title):
            return True

    return False


def base_series_key(title: str) -> str:
    title = normalize_title(title)
    title = PART_RE.sub("", title)

    return SPACE_RE.sub(" ", title).strip()


def _relation_candidates(
    media: dict,
    relation_name: str,
) -> list[int]:
    result = []

    for relation in media.get("relations") or []:
        if (
            (_get(relation, "relation", "") or "").casefold()
            != relation_name.casefold()
        ):
            continue

        for entry in _get(relation, "entry", []) or []:
            if (
                (_get(entry, "type", "") or "").casefold()
                == "anime"
            ):
                mal_id = _get(entry, "mal_id")

                if mal_id:
                    result.append(mal_id)

    return result


async def _get_related(jikan, mal_id: int) -> Optional[dict]:
    anime = await jikan.get_anime_full(mal_id)

    if anime is None:
        return None

    return _normalize_minimal_anime(anime)


def _sort_series(series: list[dict]) -> list[dict]:
    return sorted(
        series,
        key=lambda media: (
            media.get("seasonYear") or 9999,
            format_priority(media),
            media.get("malId") or 999999999,
        ),
    )


def base_series_keys(media: dict) -> set[str]:
    return {
        base_series_key(title)
        for title in get_all_titles(media)
        if title
    }


def get_season_number(media: dict) -> int:
    for title in get_all_titles(media):
        match = SEASON_RE.search(title)

        if match:
            return int(match.group(1))

    return 1


def _merge_season_parts(series: list[dict]) -> list[dict]:
    if not series:
        return []

    merged = []

    for media in series:
        season = get_season_number(media)

        if merged and get_season_number(merged[-1]) == season:
            merged[-1]["episodes"] += media.get("episodes") or 0
        else:
            merged.append(media)

    return merged


async def resolve_title(
    jikan,
    title: str,
    season_number: Optional[int] = None,
    year: Optional[int] = None,
) -> Optional[dict]:
    if not title:
        return None

    result = await jikan.search_anime(
        query=title,
        limit=10,
        year=year
    )

    if not result:
        return None

    candidates = []

    for node in result.get("data", []) or []:
        media = _normalize_search_result(node)

        if not media.get("malId"):
            continue

        if is_skippable(media):
            continue

        candidates.append(media)

    if not candidates:
        return None

    if len(candidates) == 1:
        return await _ensure_full_anime(
            jikan,
            candidates[0],
        ) or candidates[0]

    def score_candidates(use_base_title: bool = False):
        scored = []

        for media in candidates:
            titles = get_all_titles(media)

            if use_base_title:
                titles = [
                    candidate.split(":", 1)[0].strip()
                    for candidate in titles
                    if ":" in candidate
                ]

            if not titles:
                continue

            best_score = max(
                similarity(title, candidate)
                for candidate in titles
            )

            type_bonus = 0.0
            fmt = media.get("format")

            if season_number is not None:
                if fmt in ("TV", "ONA"):
                    type_bonus = 5.0
                elif fmt == "MOVIE":
                    type_bonus = -15.0

            scored.append(
                (
                    best_score + type_bonus,
                    best_score,
                    format_priority(media),
                    media,
                )
            )

        scored.sort(
            key=lambda item: (
                item[0],
                -item[2],
            ),
            reverse=True,
        )

        return scored

    # First pass: compare against complete titles.
    scored = score_candidates()

    if scored and scored[0][1] >= 90:
        return await _ensure_full_anime(
            jikan,
            scored[0][3],
        ) or scored[0][3]

    # Second pass: compare against the portion before ":".
    scored = score_candidates(use_base_title=True)

    if scored and scored[0][1] >= 90:
        return await _ensure_full_anime(
            jikan,
            scored[0][3],
        ) or scored[0][3]

    return None


async def _walk_relations(
    jikan,
    root: dict,
    relation_name: str,
    series_by_id: dict[int, dict],
):
    current = root
    visited = set()

    while current:
        current_id = current.get("malId")

        if current_id in visited:
            break

        if current_id:
            visited.add(current_id)

        candidates = []

        for mal_id in _relation_candidates(
            current,
            relation_name,
        ):
            if mal_id in series_by_id:
                candidate = series_by_id[mal_id]
            else:
                candidate = await _get_related(jikan, mal_id)

            if candidate and not is_skippable(candidate):
                candidates.append(candidate)

        if not candidates:
            break

        if relation_name == "Prequel":
            next_media = min(
                candidates,
                key=lambda media: (
                    format_priority(media),
                    -(media.get("seasonYear") or 0),
                ),
            )
        else:
            next_media = min(
                candidates,
                key=lambda media: (
                    format_priority(media),
                    media.get("seasonYear") or 9999,
                ),
            )

        next_id = next_media.get("malId")

        if not next_id or next_id in series_by_id:
            break

        series_by_id[next_id] = next_media
        current = next_media


async def build_series(
    jikan,
    root_media: dict,
) -> list[dict]:

    if not root_media:
        return []

    root_media = await _ensure_full_anime(
        jikan,
        root_media,
    )

    if not root_media:
        return []

    series_by_id = {}

    root_id = root_media.get("malId")

    if root_id:
        series_by_id[root_id] = root_media

    await _walk_relations(
        jikan,
        root_media,
        "Prequel",
        series_by_id,
    )

    await _walk_relations(
        jikan,
        root_media,
        "Sequel",
        series_by_id,
    )

    series = list(series_by_id.values())

    tv_series = [
        media
        for media in series
        if media.get("format") in {"TV", "ONA"}
    ]

    if tv_series:
        series = tv_series

    series = _sort_series(series)
    series = _merge_season_parts(series)

    result = []
    seen_ids = set()

    for media in series:
        mal_id = media.get("malId")

        if mal_id in seen_ids:
            continue

        seen_ids.add(mal_id)

        print(
            media.get("title"),
            media.get("episodes"),
        )

        result.append(media)

    return result


def rebase_series(series: list[dict], start_season: int) -> list[dict]:
    if not series or start_season is None or start_season <= 1:
        return series

    index = start_season - 1

    if index >= len(series):
        return series

    return series[index:]


def resolve_episode(series: list[dict], episode_number: int, start_season: int = 1) -> tuple[int, int]:
    if not series:
        return start_season, episode_number

    if episode_number is None:
        return start_season, 1

    remaining = episode_number
    season = start_season

    for media in series:
        episodes = media.get("episodes") or 0

        if episodes <= 0:
            return season, remaining

        if remaining <= episodes:
            return season, remaining

        remaining -= episodes
        season += 1

    return season, remaining
