import anitopy
import argparse
import os
import re
import asyncio
import aiohttp

from anilist_resolver import (
    resolve_title,
    build_series,
    resolve_episode,
    sanitize,
    rebase_series,
    pick_title
)


# =========================
# FALLBACK (OLD SYSTEM)
# =========================

ANIME_ROOT = r"\\Server\Videos\Anime"
ANIME_MOVIES_ROOT = r"\\Server\Videos\Anime Movies"

def fallback_anitopy(anime_video: str):
    old_file_name = os.path.basename(anime_video)
    parsed = anitopy.parse(old_file_name)

    episode_number = parsed.get("episode_number")
    anime_title = str(parsed.get("anime_title")).replace(" - ", " ")

    anime_year = parsed.get("anime_year")

    # First try to find an existing folder that already contains a year
    existing_folder = find_existing_anime_folder(anime_title)

    if existing_folder:
        folder_title = existing_folder
    elif anime_year:
        folder_title = f"{anime_title} ({anime_year})"
    else:
        folder_title = anime_title

    if episode_number is None:
        new_file_name = anime_title
        new_directory = os.path.join(
            ANIME_MOVIES_ROOT,
            folder_title
        )
    else:
        anime_season = f"{int(parsed.get('anime_season', 1)):02}"

        new_file_name = f"{anime_title} - S{anime_season}E{episode_number}"

        new_directory = os.path.join(
            ANIME_ROOT,
            folder_title,
            f"Season {anime_season}"
        )

    os.makedirs(new_directory, exist_ok=True)
    return new_directory, new_file_name


def find_existing_anime_folder(title: str):
    """
    Search existing anime folders and return the actual folder name
    if a title match is found after removing '(YEAR)'.
    """

    normalized_title = title.casefold().strip()

    try:
        for folder in os.listdir(ANIME_ROOT):
            full_path = os.path.join(ANIME_ROOT, folder)

            if not os.path.isdir(full_path):
                continue

            # Remove trailing " (2024)"
            folder_without_year = re.sub(
                r"\s*\(\d{4}\)$",
                "",
                folder
            ).casefold().strip()

            if folder_without_year == normalized_title:
                print(f"Found existing folder match: '{folder}' for title '{title}'")
                return folder

    except OSError:
        pass

    return None


# =========================
# MAIN (AniList + fallback)
# =========================

async def main(anime_video: str, retries=3):

    old_file_name = os.path.basename(anime_video)
    parsed = anitopy.parse(old_file_name)

    episode_number = parsed.get("episode_number")
    print(parsed.get("anime_title"))
    raw_title = str(parsed.get("anime_title")).replace(" - ", " ")

    season_number = parsed.get("anime_season")

    if season_number is not None:
        season_number = int(season_number)
    
    episode = int(episode_number or 1)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(
            limit=20,
            ttl_dns_cache=300,
            enable_cleanup_closed=True
        ),
        timeout=aiohttp.ClientTimeout(total=10)
    ) as session:
        for attempt in range(retries):
            try:
                root = await resolve_title(session, raw_title, season_number)

                if not root:
                    raise ValueError("No AniList match")

                fmt = (root.get("format") or "").upper()

                if fmt in ("TV", "ONA"):
                    series = await build_series(session, root)
                    base_media = series[0] if series else root
                    
                    series = rebase_series(series, season_number)
                else:
                    base_media = root
                    series = [root]

                anime_title = sanitize(pick_title(base_media))
                anime_year = base_media.get("seasonYear")

                season_index, episode_index, eps = resolve_episode(
                    series,
                    episode,
                    start_season=season_number
                )

                folder_title = (
                    f"{anime_title} ({anime_year})"
                    if anime_year
                    else anime_title
                )

                if episode_number is None:
                    new_directory = os.path.join(
                        ANIME_MOVIES_ROOT,
                        folder_title
                    )
                    new_file_name = anime_title

                else:
                    anime_season = f"{season_index:02d}"

                    new_directory = os.path.join(
                        ANIME_ROOT,
                        folder_title,
                        f"Season {anime_season}"
                    )

                    if eps and eps != float("inf"):
                        width = max(2, len(str(int(eps))))
                        episode_str = str(episode_index).zfill(width)
                    else:
                        episode_str = f"{episode_index:02d}"

                    new_file_name = f"{anime_title} - S{anime_season}E{episode_str}"

                os.makedirs(new_directory, exist_ok=True)
                print("AniList success")
                return new_directory, new_file_name

            except Exception as e:
                wait = 5 ** attempt
                print(f"AniList error (attempt {attempt+1}/{retries}): {e}")

                if attempt < retries - 1:
                    print(f"Retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    print("AniList failed after retries. Using fallback.")
                    return fallback_anitopy(anime_video)

# =========================
# CLI
# =========================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("anime_video")
    args = parser.parse_args()

    folder, name = asyncio.run(main(args.anime_video))
    print(f"{folder}|{name}")