# Convert-and-Move-Anime
Interoplate anime to 48fps using rife and upscale anime to 4k in vapoursynth, and moving the anime into proper subfolders to allow Plex or Jellyfin to auto add the anime.

## Script autoconvert.bat
(Given an anime video, interpolate to 48fps and upscale to 4k)
- Use python script to extract anime title using anitopy
- Use AniList to identify the correct anime title, season, and episode for the given anime
- Make a full path directory and create the necessary folders for Jellyfin or Plex using python
- Use ffmpeg with vapoursynth script to upscale to 4k and interpolate to 48fps outputting as an mp4 file
- Clean up downloads by deleting all empty folders
-----------------------------------------------

#### Final result:
    [Anime Folder]
	    [Season]
	        [anime mp4 file]
			[anime subtitle files]
-----------------------------------------------

### Scripts can be simplified and improved but should work as is for common downloaded anime episodes **WITH** changes to directory information.
### The variable `%UserDirectory%` can be changed to the `%UserProfile%` path on windows which is the common location for documents and downloads.
### Suggestions on how to improve the scripts are welcome and appreciated, but I rarely visit this repository so do not expect any quick responses.
-----------------------------------------------

## Dependencies:
  - [VapourSynth](https://www.vapoursynth.com/doc/installation.html)
    VapourSynth Plugins to put in vs-plugins (script is made for NVIDIA gpu) (already included in repo)
      - [LSMASHSource](https://github.com/HomeOfAviSynthPlusEvolution/L-SMASH-Works/releases/)
      - [libvs_placebol](https://github.com/Lypheo/vs-placebo/releases)
      - [vs-miscfilter](https://github.com/vapoursynth/vs-miscfilters-obsolete/releases)
  - [FFmpeg](https://ffmpeg.org/download.html)
  - [Python](https://www.python.org/downloads/)
  - Anime4k shaders can be downloaded from repository or directly from [Anime4k](https://github.com/bloc97/Anime4K) (Shaders in repository are the original anime4k shaders merged together into 1 file for each mode for simplicity)

## Instructions:
1. Clone Repository
2. Move autoconvert.bat and new_anime_name_directory.py into Documents folder
3. Get vapoursynth portable into Documents folder
4. Get and extract dll files for LSMASHSource, libvs_placebol, and vs-miscfilter into vs-plugins folder (can be found in cloned repo)
5. Download ffmpeg and extract bin folder contents to vapoursynth-portable folder
6. Download and install python
7. Run `python -m pip install anitopy` in command line
8. In command line navigate to VapourSynth python and run 
```command
python -m pip install -U packaging setuptools wheel
python -m pip install -U torch torchvision torch_tensorrt --index-url https://download.pytorch.org/whl/cu128 --extra-index-url https://pypi.nvidia.com --no-build-isolation 
python -m pip install -U cupy-cuda12x
python -m pip install -U vsdrba
```
9. Navigate to Lib\site-packages\vsdrba in vapoursynth-portable and add a folder named models if it does not exist
10. In command line navigate to VapourSynth python and run `python -m vsdrba`
11. Download an anime into your downloads folder
12. Add environment path variable UserDirectory=%UserProfile%
13. Run autoconvert.bat
