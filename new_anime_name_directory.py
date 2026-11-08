import anitopy
import argparse
import os
import re
import asyncio
import unicodedata

from safe_jikan import SafeJikan

from jikan_resolver import (
    rebase_series,
    resolve_title,
    build_series,
    resolve_episode,
    sanitize,
    pick_title,
    find_first_season_parent
)


ANIME_ROOT = r"Z:\Anime"
ANIME_MOVIES_ROOT = r"Z:\Anime Movies"

ANIME_SPECIALS_FOLDER = "Specials"

SPECIAL_FORMATS = {"TV_SPECIAL", "SPECIAL", "OVA"}
SERIES_FORMATS = {"TV", "ONA"}

class NoJikanMatchError(Exception):
    pass

def fallback_anitopy(anime_video: str):
    """
    Fallback naming system used when Jikan cannot resolve the anime.
    """
    parsed = anitopy.parse(os.path.basename(anime_video))

    episode_number = parsed.get("episode_number")
    anime_title = sanitize_filename(
        str(parsed.get("anime_title") or "Unknown").replace(" - ", " ")
    )

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


def sanitize_filename(title: str) -> str:
    """
    Replace special characters and symbols with spaces.
    Preserve letters, numbers, and normal filename punctuation.
    """

    title = unicodedata.normalize("NFKC", str(title))


    title = re.sub(r"[^\w\s().-]", " ", title, flags=re.UNICODE)

    # Replace underscores with spaces too.
    title = title.replace("_", " ")

    # Collapse consecutive spaces.
    title = re.sub(r"\s+", " ", title)

    return title.strip(" .-")


def build_folder_title(title: str, year: int | None) -> str:
    return f"{title} ({year})" if year else title


def build_movie_path(anime_title: str, anime_year: int | None):
    return create_path(
        os.path.join(ANIME_MOVIES_ROOT, build_folder_title(anime_title, anime_year)),
        anime_title,
    )


def build_special_path(
    parent_title: str,
    parent_year: int | None,
    anime_title: str,
    mal_id: int | None,
    episode_number: int | None,
):
    parent_folder = build_folder_title(parent_title, parent_year)
    special_folder = (
        f"{anime_title} [mal-{mal_id}]"
        if mal_id is not None
        else anime_title
    )

    episode_number = episode_number or 1
    directory = os.path.join(
        ANIME_ROOT,
        parent_folder,
        ANIME_SPECIALS_FOLDER,
        special_folder,
    )
    filename = f"{anime_title} - S00E{episode_number:02d}"

    return create_path(directory, filename)


def build_series_path(
    anime_title: str,
    anime_year: int | None,
    season_number: int,
    episode_number: int,
):
    season = f"{season_number:02d}"
    return create_path(
        os.path.join(
            ANIME_ROOT,
            build_folder_title(anime_title, anime_year),
            f"Season {season}",
        ),
        f"{anime_title} - S{season}E{episode_number:02d}",
    )


def create_path(directory: str, filename: str):
    os.makedirs(directory, exist_ok=True)
    return directory, filename


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
                    raise NoJikanMatchError(
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

                if fmt in SERIES_FORMATS:
                    series = await build_series(jikan, root)
                    series = series or [root]

                    print("\n=== All Seasons Found ===")
                    for i, media in enumerate(series, start=1):
                        print(
                            f"Season {i:02d}: "
                            f"{pick_title(media)} | "
                            f"MAL ID: {media.get('malId') or media.get('id')} | "
                            f"Episodes: {media.get('episodes')} | "
                            f"Year: {media.get('seasonYear')}"
                        )
                    print("=========================\n")

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

                elif fmt in SPECIAL_FORMATS:
                    series = [root]
                    actual_season = 0
                    base_media = root
                
                else:
                    series = [root]
                    actual_season = requested_season
                    base_media = root

                anime_title = sanitize_filename(
                    sanitize(pick_title(base_media))
                )
                anime_year = base_media.get("seasonYear")

                if fmt in SPECIAL_FORMATS:
                    mal_id = root.get("malId") or root.get("id")

                    parent_title, parent_year = await find_first_season_parent(
                        jikan,
                        root,
                    )

                    if not parent_title:
                        return build_series_path(
                            anime_title,
                            anime_year,
                            season_index,
                            episode_index,
                        )

                    return build_special_path(
                        parent_title,
                        parent_year,
                        anime_title,
                        mal_id,
                        episode_number
                    )

                elif episode_number is None:
                    return build_movie_path(
                        anime_title,
                        anime_year,
                    )

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

                    return build_series_path(
                        anime_title,
                        anime_year,
                        season_index,
                        episode_index,
                    )

            except NoJikanMatchError as e:
                print(f"Jikan error: {e}")
                print("No Jikan match found. Using fallback.")
                return fallback_anitopy(anime_video)

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