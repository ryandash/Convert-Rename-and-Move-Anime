import re
import asyncio
import aiohttp
from difflib import SequenceMatcher

ANILIST_URL = "https://graphql.anilist.co"


# =========================
# HTTP CLIENT HELPERS
# =========================

async def anilist_search(session, query: str):
    gql = """
    query ($search: String) {
      Page(perPage: 5) {
        media(search: $search, type: ANIME) {
          id
          title { romaji english native }
          synonyms
          season
          seasonYear
          episodes
          format
          relations {
            edges {
              relationType
              node {
                id
              }
            }
          }
        }
      }
    }
    """

    payload = {"query": gql, "variables": {"search": query}}

    async with session.post(ANILIST_URL, json=payload) as resp:
        data = await resp.json()

    return data["data"]["Page"]["media"]


async def anilist_get_media_batch(session, ids: list[int]):
    gql = """
    query ($ids: [Int]) {
      Page(page: 1, perPage: 50) {
        media(id_in: $ids) {
          id
          title { romaji english native }
          synonyms
          season
          seasonYear
          episodes
          format
          relations {
            edges {
              relationType
              node { 
                id 
              }
            }
          }
        }
      }
    }
    """

    payload = {"query": gql, "variables": {"ids": ids}}

    async with session.post(ANILIST_URL, json=payload) as resp:
        data = await resp.json()

    return data["data"]["Page"]["media"]


# =========================
# UTILITIES
# =========================

def pick_title(media):
    t = media.get("title", {})
    return t.get("romaji") or t.get("english") or "Unknown"


NORMALIZE_RE = re.compile(r"[:!]")
def normalize(s):
    return NORMALIZE_RE.sub(" ", s).lower().strip()

def similarity(a, b):
    return int(SequenceMatcher(None, a, b).ratio() * 100)

SANITIZE_RE = re.compile(r"\s*[<>:\"/\\|?*]\s*")
SPACE_RE = re.compile(r"\s+")

def sanitize(name: str) -> str:
    if not name:
        return ""

    name = SANITIZE_RE.sub(" ", name)
    name = SPACE_RE.sub(" ", name)

    return name.strip()


# =========================
# SERIES BUILDER (FIXED)
# =========================

def is_skippable(media):
    if not media:
        return True

    fmt = (media.get("format") or "").upper()
    title = (media.get("title", {}).get("romaji") or "").lower()

    is_ova = fmt == "OVA"
    is_special = fmt in ("SPECIAL", "TV_SPECIAL")

    # optional fallback title detection (AniList sometimes lies)
    if "ova" in title:
        is_ova = True

    if "special" in title and "tv special" not in title:
        is_special = True

    is_wrong_type = fmt not in ("TV", "ONA", "MOVIE", "TV_SPECIAL", "")

    is_single_episode = (media.get("episodes") == 1 and fmt != "MOVIE")

    return is_ova or is_special or is_wrong_type or is_single_episode

FORMAT_PRIORITY = {
    "TV": 0,
    "ONA": 1,
    "TV_SPECIAL": 2,
    "MOVIE": 3,
    "OVA": 4,
    "SPECIAL": 5,
}

def get_type_priority(media):
    return FORMAT_PRIORITY.get(
        (media.get("format") or "").upper(),
        999
    )

PART_RE = re.compile(r"\bpart\s*\d+\b")
def base_series_key(media):
    title = media.get("title", {})
    name = title.get("romaji") or title.get("english") or ""
    name = normalize(name)

    # remove "part X"
    name = PART_RE.sub("", name)
    name = SPACE_RE.sub(" ", name).strip()

    return name

async def build_series(session, root_media):
    root = (await anilist_get_media_batch(session, [root_media["id"]]))[0]

    cache = {root["id"]: root}

    async def get_media(mid):
        if mid not in cache:
            cache[mid] = (await anilist_get_media_batch(session, [mid]))[0]
        return cache[mid]

    async def get_best_relation(media, relation_type):
        candidates = []

        for edge in media.get("relations", {}).get("edges", []):
            if edge.get("relationType") != relation_type:
                continue

            node = edge.get("node")
            if not node:
                continue

            candidate = await get_media(node["id"])

            candidates.append(candidate)

        if not candidates:
            return None

        candidates.sort(
            key=lambda x: (
                get_type_priority(x),
                x.get("seasonYear") or 9999,
                {"WINTER": 0,
                 "SPRING": 1,
                 "SUMMER": 2,
                 "FALL": 3}.get(x.get("season"), 99)
            )
        )

        return candidates[0]

    # Walk backwards

    prequels = []
    current = root

    visited = {root["id"]}

    while True:
        prev = await get_best_relation(current, "PREQUEL")

        if not prev or prev["id"] in visited:
            break

        visited.add(prev["id"])

        if not is_skippable(prev):
            prequels.append(prev)

        current = prev

    prequels.reverse()

    # Walk forwards

    sequels = []
    current = root

    while True:
        nxt = await get_best_relation(current, "SEQUEL")

        if not nxt or nxt["id"] in visited:
            break

        visited.add(nxt["id"])

        if not is_skippable(nxt):
            sequels.append(nxt)

        current = nxt

    series = []

    series.extend(prequels)

    if not is_skippable(root):
        series.append(root)

    series.extend(sequels)

    # Merge entries with the same base series key.
    grouped = {}

    for media in series:
        key = base_series_key(media)
        eps = media.get("episodes") or float("inf")

        if key not in grouped:
            grouped[key] = dict(media)
            grouped[key]["_episode_sum"] = eps
        else:
            grouped[key]["_episode_sum"] += eps

    result = list(grouped.values())

    for media in result:
        print("Media episode sum", media["_episode_sum"], "for", pick_title(media))
        media["episodes"] = media["_episode_sum"]
        del media["_episode_sum"]

    return result


def rebase_series(series, start_season):
    start_index = max(start_season - 1, 0)
    return series[start_index:]


# =========================
# RESOLVE TITLE
# =========================

def get_all_titles(media):
    t = media.get("title", {})

    titles = [
        t.get("romaji"),
        t.get("english"),
        t.get("native"),
    ]

    titles.extend(media.get("synonyms") or [])

    return list(dict.fromkeys(filter(None, titles)))

def format_priority(media):
    fmt = (media.get("format") or "").upper()
    return FORMAT_PRIORITY.get(fmt, 999)

async def resolve_title(session, title: str, season_number: int | None):
    results = await anilist_search(session, title)

    if season_number is None or season_number == 0:
        # Movie/OVA/Special release
        allowed = {"MOVIE", "OVA", "SPECIAL", "TV_SPECIAL"}
    else:
        # Normal season
        allowed = {"TV", "ONA"}

    filtered = [
        m for m in results
        if (m.get("format") or "").upper() in allowed
    ]

    # Fall back if filtering removed everything.
    if filtered:
        results = filtered

    results.sort(key=format_priority)

    if not results:
        return None

    best = None
    best_score = -1

    normalized_title = normalize(title)

    for m in results:
        titles = [x for x in get_all_titles(m) if x]

        score = max(
            similarity(normalize(t), normalized_title)
            for t in titles
        )

        print(
            f"Score {score} ({m['format']}) for {pick_title(m)} against {title}"
        )

        if score == 100:
            return m

        if score > best_score:
            best_score = score
            best = m

    return best

# =========================
# EPISODE MAPPING
# =========================

def resolve_episode(series, episode_number, start_season=1):
    season = start_season
    print("Starting season:", season)

    for media in series:
        print("Checking media:", media.get("title", {}).get("romaji"))
        eps = media.get("episodes")

        if eps is None:
            return season, episode_number, None

        print(eps, "episodes")
        if episode_number > eps:
            episode_number -= eps
            print("Episode number:", episode_number)

            season += 1
        else:
            return season, episode_number, eps

    return season, episode_number, None
