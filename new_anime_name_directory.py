import anitopy
import argparse
import os
import re
import asyncio

from safe_jikan import SafeJikan

from jikan_resolver import (
    rebase_series,
    resolve_title,
    build_series,
    resolve_episode,
    sanitize,
    pick_title,
)


ANIME_ROOT = r"Z:\Anime"
ANIME_MOVIES_ROOT = r"Z:\Anime Movies"


def fallback_anitopy(anime_video: str):
    """
    Fallback naming system used when Jikan cannot resolve the anime.
    """
    parsed = anitopy.parse(os.path.basename(anime_video))

    episode_number = parsed.get("episode_number")
    anime_title = str(
        parsed.get("anime_title") or "Unknown"
    ).replace(" - ", " ")

    anime_year = parsed.get("anime_year")

    existing_folder = find_existing_anime_folder(anime_title)

    if existing_folder:
        folder_title = existing_folder
    elif anime_year:
        folder_title = f"{anime_title} ({anime_year})"
    else:
        folder_title = anime_title

    if episode_number is None:
        new_directory = os.path.join(
            ANIME_MOVIES_ROOT,
            folder_title,
        )
        new_file_name = anime_title

    else:
        anime_season = f"{int(parsed.get('anime_season', 1)):02d}"

        new_directory = os.path.join(
            ANIME_ROOT,
            folder_title,
            f"Season {anime_season}",
        )

        new_file_name = (
            f"{anime_title} - "
            f"S{anime_season}E{episode_number}"
        )

    os.makedirs(new_directory, exist_ok=True)

    return new_directory, new_file_name


def find_existing_anime_folder(title: str):
    """
    Return an existing anime folder whose title matches after removing
    a trailing (YEAR).
    """
    normalized_title = title.casefold().strip()

    try:
        for folder in os.listdir(ANIME_ROOT):
            full_path = os.path.join(ANIME_ROOT, folder)

            if not os.path.isdir(full_path):
                continue

            folder_title = re.sub(
                r"\s*\(\d{4}\)$",
                "",
                folder,
            ).casefold().strip()

            if folder_title == normalized_title:
                print(
                    f"Found existing folder match: "
                    f"'{folder}' for title '{title}'"
                )
                return folder

    except OSError:
        pass

    return None


def remove_year_from_title(title: str):
    """
    Remove a trailing anime year such as:
        Title 2025
        Title (2025)
    """
    return re.sub(
        r"\s*\(?\b(19\d{2}|20\d{2})\)?$",
        "",
        title,
    ).strip()


async def main(anime_video: str, retries: int = 5):
    """
    Resolve an anime filename using Jikan.

    Falls back to AniPy if Jikan cannot resolve the anime.
    """
    parsed = anitopy.parse(os.path.basename(anime_video))

    episode_number = parsed.get("episode_number")
    if episode_number is not None:
        episode_number = int(episode_number)

    parsed_title = parsed.get("anime_title")

    if not parsed_title:
        print("Could not determine anime title from filename.")
        return fallback_anitopy(anime_video)

    print("title:", parsed_title)
    print("year:", parsed.get("anime_year"))

    raw_title = remove_year_from_title(
        str(parsed_title).replace(" - ", " ")
    )

    season_number = parsed.get("anime_season")

    if isinstance(season_number, list):
        season_number = season_number[0]

    if season_number is not None:
        season_number = int(season_number)

    requested_season = season_number or 1

    jikan = SafeJikan()

    try:
        for attempt in range(retries):
            try:
                print(
                    f"Jikan resolution attempt "
                    f"{attempt + 1}/{retries}"
                )

                root = await resolve_title(
                    jikan,
                    raw_title,
                    requested_season,
                )

                if not root:
                    raise ValueError(
                        f"No Jikan match found for '{raw_title}'"
                    )

                root_id = root.get("malId") or root.get("id")

                print(
                    f"Jikan match: "
                    f"{pick_title(root)} "
                    f"(MAL ID: {root_id})"
                )

                fmt = (
                    root.get("format")
                    or root.get("type")
                    or ""
                ).upper()

                if fmt in ("TV", "ONA"):
                    series = await build_series(jikan, root)
                    series = series or [root]

                    root_index = next(
                        (
                            i
                            for i, media in enumerate(series)
                            if (
                                media.get("malId")
                                or media.get("id")
                            ) == root_id
                        ),
                        0,
                    )

                    actual_season = (
                        requested_season + root_index
                    )

                    base_media = series[0]

                else:
                    series = [root]
                    actual_season = requested_season
                    base_media = root

                anime_title = sanitize(
                    pick_title(base_media)
                )

                anime_year = base_media.get("seasonYear")

                if episode_number is None:
                    folder_title = (
                        f"{anime_title} ({anime_year})"
                        if anime_year
                        else anime_title
                    )

                    new_directory = os.path.join(
                        ANIME_MOVIES_ROOT,
                        folder_title,
                    )

                    new_file_name = anime_title

                else:
                    rebased_series = rebase_series(
                        series,
                        actual_season,
                    )
                    
                    season_index, episode_index = resolve_episode(
                        rebased_series,
                        episode_number,
                        start_season=actual_season,
                    )

                    anime_season = f"{season_index:02d}"

                    relative_index = (
                        season_index - actual_season
                    )

                    episode_count = None

                    if 0 <= relative_index < len(rebased_series):
                        episode_count = rebased_series[
                            relative_index
                        ].get("episodes")

                    if episode_count and episode_count > 0:
                        width = max(
                            2,
                            len(str(int(episode_count))),
                        )
                        episode_str = str(
                            episode_index
                        ).zfill(width)
                    else:
                        episode_str = str(
                            episode_index
                        ).zfill(2)

                    folder_title = (
                        f"{anime_title} ({anime_year})"
                        if anime_year
                        else anime_title
                    )

                    new_directory = os.path.join(
                        ANIME_ROOT,
                        folder_title,
                        f"Season {anime_season}",
                    )

                    new_file_name = (
                        f"{anime_title} - "
                        f"S{anime_season}"
                        f"E{episode_str}"
                    )

                os.makedirs(
                    new_directory,
                    exist_ok=True,
                )

                print("Jikan success")

                return new_directory, new_file_name

            except Exception as e:
                print(
                    f"Jikan error "
                    f"(attempt {attempt + 1}/{retries}): {e}"
                )

                if attempt < retries - 1:
                    wait = 5 ** attempt
                    print(f"Retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    print(
                        "Jikan failed after retries. "
                        "Using fallback."
                    )
                    return fallback_anitopy(anime_video)

    finally:
        await jikan.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("anime_video")
    args = parser.parse_args()

    folder, name = asyncio.run(
        main(args.anime_video)
    )

    print(f"{folder}|{name}")