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

SANITIZE_RE = re.compile(r"\s*[<>:\"/\\|?*]\s*")
SPACE_RE = re.compile(r"\s+")


def sanitize(name: str) -> str:
    if not name:
        return ""

    name = SANITIZE_RE.sub(" ", name)
    name = SPACE_RE.sub(" ", name)

    return name.rstrip(". ").strip()


def normalize_title(title: str) -> str:
    if not title:
        return ""

    title = title.casefold()
    title = re.sub(r"[:!?,.'\"`]", "", title)
    title = re.sub(r"[-_/\\]+", " ", title)

    return SPACE_RE.sub(" ", title).strip()


def similarity(a: str, b: str) -> float:
    a = normalize_title(a)
    b = normalize_title(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 100.0

    return SequenceMatcher(None, a, b).ratio() * 100.0


def _format_type(value: Optional[str]) -> str:
    if not value:
        return ""

    value = value.upper().strip()

    aliases = {
        "TV SPECIAL": "TV_SPECIAL",
    }

    return aliases.get(value, value)


def _extract_year(aired: Any) -> Optional[int]:
    if not isinstance(aired, dict):
        return None

    date_value = aired.get("from")

    if not date_value:
        return None

    match = re.match(r"(\d{4})", str(date_value))

    return int(match.group(1)) if match else None


def _title_entries_to_dict(titles: Any) -> dict:
    result = {
        "default": None,
        "japanese": None,
        "english": None,
        "synonyms": [],
    }

    if not titles:
        return result

    for entry in titles:
        if hasattr(entry, "title"):
            title = entry.title
            title_type = entry.type
        elif isinstance(entry, dict):
            title = entry.get("title")
            title_type = entry.get("type")
        else:
            continue

        if not title:
            continue

        title_type = (title_type or "").casefold()

        if title_type == "default":
            result["default"] = title

        elif title_type == "japanese":
            result["japanese"] = title

        elif title_type == "english":
            result["english"] = title

        elif title_type == "synonym":
            result["synonyms"].append(title)

    return result


def _extract_titles_from_search_result(node: dict) -> dict:
    result = {
        "default": None,
        "japanese": None,
        "english": None,
        "synonyms": [],
    }

    for entry in node.get("titles", []) or []:
        title = entry.get("title")
        title_type = (entry.get("type") or "").casefold()

        if not title:
            continue

        if title_type == "default":
            result["default"] = title

        elif title_type == "japanese":
            result["japanese"] = title

        elif title_type == "english":
            result["english"] = title

        elif title_type == "synonym":
            result["synonyms"].append(title)

    # Fallback for results without a titles array
    if not result["default"]:
        result["default"] = node.get("title")

    return result


def _normalize_search_result(node: dict) -> dict:
    titles = _extract_titles_from_search_result(node)
    aired = node.get("aired") or {}
    media_type = _format_type(node.get("type"))

    mal_id = node.get("mal_id")

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

    titles = _title_entries_to_dict(
        getattr(anime, "titles", [])
    )

    aired = getattr(anime, "aired", {}) or {}
    media_type = _format_type(
        getattr(anime, "type", "")
    )

    mal_id = getattr(anime, "malId", None)

    return {
        "id": mal_id,
        "malId": mal_id,
        "title": titles.get("default"),
        "titles": titles,
        "format": media_type,
        "type": media_type,
        "episodes": getattr(anime, "episodes", 0) or 0,
        "season": None,
        "seasonYear": _extract_year(aired),
        "aired": aired,
        "url": getattr(anime, "url", None),
        "relations": getattr(anime, "relations", []) or [],
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

    result = []

    for key in (
        "default",
        "japanese",
        "english",
    ):
        title = titles.get(key)

        if title:
            result.append(title)

    for title in titles.get("synonyms", []) or []:
        if title:
            result.append(title)

    # Fallback
    if not result:
        title = media.get("title")

        if title:
            result.append(title)

    return result


def pick_title(media: dict) -> str:
    default = (media.get("titles") or {}).get("default")

    if default:
        return sanitize(default)

    title = media.get("title")

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

    title = " ".join(get_all_titles(media)).casefold()

    if (
        re.search(r"\b(ova|special)\b", title)
        and fmt not in ("TV", "ONA", "MOVIE")
    ):
        return True

    return (
        fmt in ("TV", "ONA")
        and media.get("episodes") == 1
    )


def base_series_key(title: str) -> str:
    """
    Normalize titles so different parts of the same numbered season
    share the same key.

    Examples:

        2nd Season
        2nd Season Part 2

    both become:

        season 2

    while:

        2nd Season
        3rd Season

    remain different.
    """
    title = normalize_title(title)

    # Remove "Part N".
    title = re.sub(
        r"\bpart\s+\d+\b",
        "",
        title,
    )

    # Normalize ordinal season names.
    title = re.sub(
        r"\b(\d+)(?:st|nd|rd|th)\s+season\b",
        r"season \1",
        title,
    )

    return SPACE_RE.sub(" ", title).strip()


def _relation_candidates(media: dict, relation_name: str) -> list[int]:
    result = []

    for relation in media.get("relations", []) or []:
        if (
            (relation.get("relation") or "").casefold()
            != relation_name.casefold()
        ):
            continue

        for entry in relation.get("entry", []) or []:
            if (
                (entry.get("type") or "").casefold()
                != "anime"
            ):
                continue

            mal_id = entry.get("mal_id")

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
    """
    Return normalized base-series keys for all available title variants.

    This allows season parts to be matched even when "Part N" only
    appears in an English title or synonym rather than the default title.
    """
    return {
        base_series_key(title)
        for title in get_all_titles(media)
        if title
    }


def _merge_season_parts(series: list[dict]) -> list[dict]:
    """
    Merge entries representing multiple parts of the same season.

    Example:

        Season 2
        Season 2 Part 2

    becomes one season with the combined episode count.
    """
    if not series:
        return []

    merged = []

    for media in series:
        if not merged:
            merged.append(media)
            continue

        previous = merged[-1]

        if base_series_keys(previous) & base_series_keys(media):
            previous["episodes"] = (
                (previous.get("episodes") or 0)
                + (media.get("episodes") or 0)
            )
            continue

        merged.append(media)

    return merged


async def resolve_title(
    jikan,
    title: str,
    season_number: Optional[int] = None,
) -> Optional[dict]:
    if not title:
        return None

    result = await jikan.search_anime(
        query=title,
        limit=10,
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


async def build_series(jikan, root_media: dict) -> list[dict]:
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

    # Walk backwards through prequels.
    current = root_media
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
            "Prequel",
        ):
            candidate = (
                series_by_id.get(mal_id)
                or await _get_related(jikan, mal_id)
            )

            if candidate and not is_skippable(candidate):
                candidates.append(candidate)

        if not candidates:
            break

        previous = min(
            candidates,
            key=lambda media: (
                format_priority(media),
                -(media.get("seasonYear") or 0),
            ),
        )

        previous_id = previous.get("malId")

        if previous_id in series_by_id:
            break

        series_by_id[previous_id] = previous
        current = previous

    # Walk forwards through sequels.
    current = root_media
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
            "Sequel",
        ):
            candidate = (
                series_by_id.get(mal_id)
                or await _get_related(jikan, mal_id)
            )

            if candidate and not is_skippable(candidate):
                candidates.append(candidate)

        if not candidates:
            break

        next_media = min(
            candidates,
            key=lambda media: (
                format_priority(media),
                media.get("seasonYear") or 9999,
            ),
        )

        next_id = next_media.get("malId")

        if next_id in series_by_id:
            break

        series_by_id[next_id] = next_media
        current = next_media

    series = list(series_by_id.values())

    filtered = [
        media
        for media in series
        if media.get("format") in ("TV", "ONA")
    ]

    if filtered:
        series = filtered

    series = _sort_series(series)
    series = _merge_season_parts(series)

    result = []
    seen_ids = set()

    for media in series:
        mal_id = media.get("malId")

        if mal_id in seen_ids:
            continue

        seen_ids.add(mal_id)
        print(media.get("title"), media.get("episodes"))
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
