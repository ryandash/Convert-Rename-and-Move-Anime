import anitopy
import argparse
import os
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

def fallback_anitopy(anime_video: str):
    path, old_file_name = os.path.dirname(anime_video), os.path.basename(anime_video)
    parsed = anitopy.parse(old_file_name)

    episode_number = parsed.get("episode_number")
    anime_title = str(parsed.get("anime_title")).replace(" - ", " ")

    anime_year = parsed.get("anime_year")
    if anime_year:
        anime_title = f"{anime_title} ({anime_year})"

    if episode_number is None:
        new_file_name = anime_title
        new_directory = os.path.join(
            r"\\Server\Videos\Anime Movies", 
            anime_title
        )
    else:
        anime_season = f"{int(parsed.get('anime_season', 1)):02}"
        new_file_name = f"{anime_title} - S{anime_season}E{episode_number}"
        new_directory = os.path.join(
            r"\\Server\Videos\Anime",
            anime_title,
            f"Season {anime_season}"
        )

    os.makedirs(new_directory, exist_ok=True)
    return new_directory, new_file_name


# =========================
# MAIN (AniList + fallback)
# =========================

async def main(anime_video: str, retries=3):

    old_file_name = os.path.basename(anime_video)
    parsed = anitopy.parse(old_file_name)

    episode_number = parsed.get("episode_number")
    print(parsed.get("anime_title"))
    raw_title = str(parsed.get("anime_title")).replace(" - ", " ")

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
                root = await resolve_title(session, raw_title)

                if not root:
                    raise ValueError("No AniList match")

                series = await build_series(session, root)

                base_media = series[0] if series else root

                anime_title = sanitize(pick_title(base_media))
                anime_year = base_media.get("seasonYear")

                episode = int(episode_number or 1)
                parsed_season = int(parsed.get("anime_season") or 1)

                series = rebase_series(series, parsed_season)

                season_index, episode_index, eps = resolve_episode(
                    series,
                    episode,
                    start_season=parsed_season
                )

                folder_title = (
                    f"{anime_title} ({anime_year})"
                    if anime_year
                    else anime_title
                )

                if episode_number is None:
                    new_directory = os.path.join(
                        r"\\Server\Videos\Anime Movies",
                        folder_title
                    )
                    new_file_name = anime_title

                else:
                    anime_season = f"{season_index:02d}"

                    new_directory = os.path.join(
                        r"\\Server\Videos\Anime",
                        folder_title,
                        f"Season {anime_season}"
                    )

                    if eps and eps != float("inf"):
                        episode_str = str(episode_index).zfill(len(str(int(eps))))
                    else:
                        episode_str = f"{episode_index:02d}"
                        

                    new_file_name = f"{anime_title} - S{anime_season}E{episode_str}"

                os.makedirs(new_directory, exist_ok=True)
                print("AniList success")
                return new_directory, new_file_name

            except Exception as e:
                wait = 2 ** attempt
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