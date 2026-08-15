@echo off

set "pythonPath=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe"
set "LOCKFILE=%UserDirectory%\Documents\AnimeEncode.lock"
set "file="
set "filename="
set "newDirectory="
set "newFileName="

if exist "%LOCKFILE%" (
    set /p LOCKTIME=<"%LOCKFILE%"

    if not defined LOCKTIME (
        del "%LOCKFILE%"
        goto CONTINUE_LOCK
    )

	setlocal EnableDelayedExpansion

    for /f %%a in ('
        powershell -NoProfile -Command ^
        "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - !LOCKTIME!"
    ') do set ELAPSED=%%a
	
    if not defined ELAPSED set ELAPSED=999999

    echo !ELAPSED!
    if !ELAPSED! LSS 3600 (
        echo Another encoder instance appears to be running.
        exit /b
    )
    endlocal

    echo Removing stale lock.
    del "%LOCKFILE%"
)

:CONTINUE_LOCK

REM Update lock file with current timestamp
for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do (
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
%pythonPath% -m pip install --upgrade pip
%pythonPath% -m pip install -r "%~dp0requirements.txt"

timeout /t 5 /nobreak

:start
pushd "%UserDirectory%\Documents\vapoursynth-portable"
for /r "%UserDirectory%\Downloads\" %%f in (*.mkv) do (
	
	set "file=%%f"
	set "filename=%%~nf"

	set "isVersioned=0"

	powershell -NoProfile -Command "if ('%%~nf' -match '(?:\d| )v[2-9]\b') { exit 0 } else { exit 1 }"
	if not errorlevel 1 (
		set "isVersioned=1"
		echo This is a versioned release
	)

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

	REM Update lock file with current timestamp
	for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do (
		echo %%a>"%LOCKFILE%"
	)

	set "encodedVideo=!newDirectory!\!newFileName!.mp4"

	set "videoExists=0"

	if exist "!encodedVideo!" (
		set "videoExists=1"
		echo Video already exists
	)

	set "audiocodec="

	for /f %%a in ('
		ffprobe -v error -select_streams a:0 ^
		-show_entries stream^=codec_name ^
		-of default^=nokey^=1:noprint_wrappers^=1 "!file!"
	') do set "audiocodec=%%a"

	echo Audio codec: !audiocodec!

	if /I "!audiocodec!"=="aac" (
		set "audiocmd=-c:a copy"
	) else (
		set "audiocmd=-c:a aac -q:a 3"
	)

	if "!isVersioned!"=="0" (
		set "temporaryVideo=!tempOutput!\!newFileName!.mp4"
	) else (
		set "temporaryVideo=!newDirectory!\!newFileName!.mp4"
	)

	REM Upscale 4k 48fps and encode to HEVC using NVENC
	if "!videoExists!"=="0" (
		if "!isVersioned!"=="0" (
			call vspipe --arg source="!file!" -c y4m "encode 4k 48fps.vpy" - | ffmpeg -y -f yuv4mpegpipe -i pipe:0 -i "!file!" -c:v hevc_nvenc -cq 26 -rc vbr -bf 5 -refs 4 -preset p5 -spatial-aq 1 -temporal-aq 1 -aq-strength 10 -map 0:v -map 1:a !audiocmd! -sn "!temporaryVideo!"

			if exist "!temporaryVideo!" (
				set "videoExists=1"
			)
		)
	)

	if "!videoExists!"=="1" (
		REM Extract all subtitles
		set "counter=0"
		
		for /f "tokens=1,2,3 delims=," %%a in ('ffprobe -loglevel error -select_streams s -show_entries stream^=index^,codec_name:stream_tags^=language -of csv^=p^=0 "!file!"') do (
			set "sub_index=%%a"
			set "codec=%%b"
			set "lang=%%c"

			if /I "!lang!"=="eng" (
				
				set "langFull=default.eng"

				REM Set extension and codec option

				set "codec_arg=-c:s copy"
				if /I "!codec!"=="hdmv_pgs_subtitle" (
					set "ext=sup"
				) else if /I "!codec!"=="dvd_subtitle" (
					set "ext=sub"
				) else if /I "!codec!"=="dvb_subtitle" (
					set "ext=sub"
				) else if /I "!codec!"=="xsub" (
					set "ext=sub"
				) else (
					set "ext=ass"
					set "codec_arg=-c:s ass"
				)

				set "outfile=!newDirectory!\!newFileName!.!langFull!.!counter!.!ext!"

				REM Extract subtitle
				if /I "!ext!"=="ass" (

					REM Intermediate files stay in tempOutput
					
					set "tempAss=!tempOutput!\!newFileName!.subtitle.!counter!.tmp.ass"
					set "resampledAss=!tempOutput!\!newFileName!.subtitle.!counter!.resampled.ass"

					echo Extracting ASS subtitle...
					echo Temporary: !tempAss!

					REM Extract subtitle to temporary location
					ffmpeg -y -i "!file!" -map 0:!sub_index! -c:s ass "!tempAss!"

					REM Resample subtitle to 4k
					aegisub-cli "!tempAss!" "!resampledAss!" tool/resampleres --video "!temporaryVideo!"


					if exist "!resampledAss!" (
						echo SUCCESS - output created

						REM Convert resampled ASS to UTF-8 with BOM
						echo Converting ASS subtitle to UTF-8 with BOM...
						powershell -NoProfile -Command "$p='!resampledAss!'; $c=[System.IO.File]::ReadAllText($p); [System.IO.File]::WriteAllText($p,$c,(New-Object System.Text.UTF8Encoding($true)))"
					) else (
						echo FAILED - output missing
					)

					REM Move resampled subtitle to final location
					if exist "!resampledAss!" (
						move /Y "!resampledAss!" "!outfile!"
					) else (
						echo ERROR: resampling failed.
						echo Copying original ASS instead.
						move /Y "!tempAss!" "!outfile!"
					)

					REM Cleanup temporary ASS
					del "!tempAss!" 2>nul
					del "!resampledAss!" 2>nul

				) else (
					ffmpeg -y -i "!file!" -map 0:!sub_index! !codec_arg! "!outfile!"
				)

				set /a "counter+=1"
			)
		)
	)

	if exist "!temporaryVideo!" (
		move /Y "!temporaryVideo!" "!encodedVideo!"
	)
	
	del "!file!" /q /s

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
