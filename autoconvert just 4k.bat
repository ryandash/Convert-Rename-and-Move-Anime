@echo off
chcp 65001 >nul

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "pythonPath=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe"
set "LOCKFILE=%UserDirectory%\Documents\AnimeEncode.lock"

set "file="
set "filename="
set "newDirectory="
set "newFileName="

REM Check existing lock
if exist "%LOCKFILE%" (
    setlocal EnableDelayedExpansion

    REM Get current Unix timestamp
    for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do set "NOW=%%a"

    set "LOCKTIME="
    set /p LOCKTIME=<"%LOCKFILE%"

    if not defined LOCKTIME (
        echo Lockfile is empty. Removing it.
        del "%LOCKFILE%"
    ) else (
        REM Check whether the lock has expired
        if !NOW! GTR !LOCKTIME! (
            echo Existing lock has expired. Removing it.
            del "%LOCKFILE%"
        ) else (
            echo Another encoder instance appears to be running.
            echo Lock expires at Unix timestamp: !LOCKTIME!
            exit /b 1
        )
    )
    endlocal
)

REM Create initial lock: current time + 24 minutes
for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.AddMinutes(24).ToUnixTimeSeconds()"') do (
    echo %%a>"%LOCKFILE%"
)

REM Check if Python is installed, if not install it
if not exist "%pythonPath%" (
    echo Python not found. Installing Python 3.13...
    
    winget install Python.Python.3.13 -e --accept-package-agreements --accept-source-agreements --disable-interactivity

    REM Optional: refresh environment if needed
    call refreshenv >nul 2>&1

    REM Test again after install
    if not exist "%pythonPath%" (
        echo Failed to install Python. Exiting.
        exit /b 1
    )
)

echo Using Python: %pythonPath%

REM Upgrade pip and install requirements
%pythonPath% -m pip install --upgrade pip -q
%pythonPath% -m pip install -r "%~dp0requirements.txt" -q

timeout /t 5 /nobreak

:start
pushd "%UserDirectory%\Documents\vapoursynth-portable"
for /r "%UserDirectory%\Downloads\" %%f in (*.mkv) do (
	
	set "file=%%f"
	set "filename=%%~nf"

	for /f "usebackq tokens=1,* delims=|" %%a in (`%pythonPath% "%UserDirectory%\Documents\new_anime_name_directory.py" "%%f"`) do (
		set "newDirectory=%%a"
		set "newFileName=%%b"
	)

	setlocal EnableDelayedExpansion
	echo !file!
	echo !newDirectory!
	echo !newFileName!

	if "!newDirectory!"=="" (
		echo Failed to find filename.
		pause
		del "%LOCKFILE%"
		exit /b 1
	)

	if "!newFileName!"=="" (
		echo Failed to find filename.
		pause
		del "%LOCKFILE%"
		exit /b 1
	)

	set "tempOutput=%UserDirectory%\ConvertedVideos"
	if not exist "!tempOutput!" mkdir "!tempOutput!"

	REM Get video duration
	set "VIDEO_LENGTH="

	for /f "delims=" %%a in ('
		ffprobe -v error -show_entries format^=duration -of default^=nokey^=1:noprint_wrappers^=1 "!file!"
	') do set "VIDEO_LENGTH=%%a"

	if not defined VIDEO_LENGTH (
		echo ERROR: Unable to determine video duration.
		pause
		exit /b 1
	)

	REM Calculate lock expiration
	set "LOCK_EXPIRY="

	for /f "delims=" %%a in ('powershell -NoProfile -Command "$d = [double]::Parse($env:VIDEO_LENGTH, [Globalization.CultureInfo]::InvariantCulture); [DateTimeOffset]::UtcNow.AddSeconds($d + 600).ToUnixTimeSeconds()"') do (
		set "LOCK_EXPIRY=%%a"
	)

	REM Validate calculated timestamp
	if not defined LOCK_EXPIRY (
		echo ERROR: Failed to calculate lock expiration.
		pause
		exit /b 1
	)

	REM Write expiration timestamp
	echo(!LOCK_EXPIRY!>"%LOCKFILE%"

	REM Display readable expiration time
	for /f "delims=" %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::FromUnixTimeSeconds([long]$env:LOCK_EXPIRY).ToLocalTime().ToString()"') do (
		echo Lock expires: %%a
	)

	echo call ffmpeg -y -i "!file!" -init_hw_device "vulkan=vk:0" -vf libplacebo=w=3840:h=2160:upscaler=ewa_lanczos:force_original_aspect_ratio=decrease:custom_shader_path='shaders/Anime4K_ModeA.glsl' -c:v hevc_nvenc -cq 26 -rc vbr -bf 5 -refs 4 -preset p5 "!tempOutput!\!newFileName!.mp4"

	REM Upscale 4k
	call ffmpeg -y -i "!file!" -init_hw_device "vulkan=vk:0" -vf libplacebo=w=3840:h=2160:upscaler=ewa_lanczos:force_original_aspect_ratio=decrease:custom_shader_path='shaders/Anime4K_ModeA.glsl' -c:v hevc_nvenc -cq 26 -rc vbr -bf 5 -refs 4 -preset p5 "!tempOutput!\!newFileName!.mp4"

	REM Move file to final destination
	set "encodedVideo=!newDirectory!\!newFileName!.mp4"
	move /Y "!tempOutput!\!newFileName!.mp4" "!encodedVideo!"
	
	endlocal
)
popd

REM Cleanup empty folders
cd /d "%UserDirectory%\Downloads\"
for /f "delims=" %%d in ('dir /ad /s /b ^| sort /R') do rd "%%d" 2>nul

if exist "%UserDirectory%\Downloads\*.mkv" (
	goto start
)

del "%LOCKFILE%"
