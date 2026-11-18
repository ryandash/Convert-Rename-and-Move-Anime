@echo off
chcp 65001 >nul

if "%~1" neq "--locked" (
    powershell -NoProfile -Command "$created = $false; $m = New-Object System.Threading.Mutex($true, 'Global\AnimeEncodeMutex', [ref]$created); if (-not $created) { Write-Host 'Another encoder instance is already running. Exiting.'; exit 1 }; $p = Start-Process -FilePath '%~f0' -ArgumentList '--locked' -Wait -NoNewWindow -PassThru; exit $p.ExitCode"
    exit /b %errorlevel%
)

if not defined UserDirectory set "UserDirectory=%USERPROFILE%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "pythonPath=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe"

set "file="
set "filename="
set "newDirectory="
set "newFileName="

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
set "PATH=%CD%;%CD%\lib\site-packages\vapoursynth;%PATH%"
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
		exit /b 1
	)

	if "!newFileName!"=="" (
		echo Failed to find filename.
		pause
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

	set "encodedVideo=!newDirectory!\!newFileName!.mp4"

	set "videoExists=0"

	if exist "!encodedVideo!" (
		set "videoExists=1"
		echo Video already exists
	)

	set "audiocodec="
	for /f %%a in ('ffprobe -v error -select_streams a:0 -show_entries stream^=codec_name -of default^=nokey^=1:noprint_wrappers^=1 "!file!"') do set "audiocodec=%%a"

	set "audiocmd="
	if /I "!audiocodec!"=="aac" set "audiocmd=--audio-source "!file!":copy"
	if defined audiocodec if /I not "!audiocodec!"=="aac" set "audiocmd=--audio-source "!file!":codec=aac;bitrate=192"

	if "!videoExists!"=="0" (
		set "temporaryVideo=!tempOutput!\!newFileName!.mp4"
		set "VS_SOURCE=!file!"
		for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do set "ENCODE_START=%%a"

		NVEncC64.exe --vpy-mt -i "encode 4k 48fps.vpy" --vsdir "%CD%" --vpp-libplacebo-shader shader="shaders/Anime4K_ModeA.glsl",res=3840x2160,resampler=libplacebo-ewa-lanczos --output-res 3840x2160,preserve_aspect_ratio=decrease -c hevc --output-depth 10 --qvbr 21 --qp-min 15 --qp-max 27 --preset p4 --tune hq --lookahead 16 --aq --aq-temporal --aq-strength 4 --bframes 4 --bref-mode middle !audiocmd! --metadata copy --chapter-copy -m movflags:+faststart -o "!temporaryVideo!"
		
		for /f %%a in ('powershell -NoProfile -Command "$elapsed = [TimeSpan]::FromSeconds([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - !ENCODE_START!); '{0:hh\:mm\:ss}' -f $elapsed"') do set "ENCODE_DURATION=%%a"
		echo Encode completed in: !ENCODE_DURATION!

		set "videoExists=1"
	) else (
		set "temporaryVideo=!newDirectory!\!newFileName!.mp4"
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
					ffmpeg -y -hide_banner -loglevel warning -stats -i "!file!" -map 0:!sub_index! -c:s ass "!tempAss!"

					pushd "aegisub"

					echo Current directory: %CD%
					echo Input subtitle: !tempAss!
					echo Output subtitle: !resampledAss!
					echo Video: !temporaryVideo!

					if not exist "!tempAss!" echo ERROR: Input ASS missing
					if not exist "!temporaryVideo!" echo ERROR: Video missing

					REM Resample subtitle to 4k
					aegisub-cli "!tempAss!" "!resampledAss!" tool/resampleres --video "!temporaryVideo!"

					if exist "!resampledAss!" (
						echo SUCCESS - output created

						REM Downscale some override tags in ASS subtitle and convert to UTF-8 with BOM...
						powershell -NoProfile -ExecutionPolicy Bypass -File "Fix-AssScaling.ps1" -OriginalSubtitles "!tempAss!" -ResampledSubtitles "!resampledAss!"
					) else (
						echo FAILED - output missing
						pause
					)

					popd

					REM Move resampled subtitle to final location
					if exist "!resampledAss!" (
						move /Y "!resampledAss!" "!outfile!"
					) else (
						echo ERROR: resampling failed.
						pause
						echo Copying original ASS instead.
						move /Y "!tempAss!" "!outfile!"
					)

					REM Cleanup temporary ASS
					del "!tempAss!" 2>nul
					del "!resampledAss!" 2>nul

				) else (
					ffmpeg -y -hide_banner -loglevel warning -stats -i "!file!" -map 0:!sub_index! !codec_arg! "!outfile!"
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
