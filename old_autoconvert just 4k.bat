@echo off

for /f "delims=" %%a in ('where powershell') do set "powershell=%%a"
set "pythonPath=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe"

setlocal EnableDelayedExpansion
if not exist "!pythonPath!" (
    echo Python not found. Installing Python 3.13...
    
    winget install Python.Python.3.13 -e --accept-package-agreements --accept-source-agreements --disable-interactivity

    REM Optional: refresh environment if needed
    call refreshenv >nul 2>&1

    REM Test again after install
    if not exist "!pythonPath!" (
        echo Failed to install Python. Exiting.
        exit /b 1
    )
)

echo Using Python: !pythonPath!

REM Upgrade pip and install requirements
set "scriptDir=%~dp0"
!pythonPath! -m pip install --upgrade pip
!pythonPath! -m pip install -r "!scriptDir!requirements.txt"

timeout /t 5 /nobreak
tasklist /fi "ImageName eq VSPipe.exe" /fo csv 2>NUL | find /I "VSPipe.exe">NUL
echo error level !ERRORLEVEL! for hybrid
IF !ERRORLEVEL! NEQ 0 (
	tasklist /fi "ImageName eq ffmpeg.exe" /fo csv 2>NUL | find /I "ffmpeg.exe">NUL
	echo error level !ERRORLEVEL! for ffmpeg
	IF !ERRORLEVEL! NEQ 0 (
		endlocal

		:start
		cd /d "%UserDirectory%\Documents\vapoursynth-portable"
		for /r "%UserDirectory%\Downloads\" %%f in (*.mkv) do (
			set "file=%%f"
			set "filename=%%~nf"

			setlocal EnableDelayedExpansion
			for /f "tokens=1,2 delims=|" %%a in ('!pythonPath! "!UserDirectory!\Documents\new_anime_name_directory.py" "!file!"') do (
				endlocal
				set "newDirectory=%%a"
				set "newFileName=%%b"
				setlocal EnableDelayedExpansion
			)
			echo !newDirectory!
			echo !newFileName!

			set "tempOutput=%UserDirectory%\ConvertedVideos"
			if not exist "!tempOutput!" mkdir "!tempOutput!"

			REM Upscale 4k
			call ffmpeg -y -i "!file!" -init_hw_device "vulkan=vk:0" -vf libplacebo=w=3840:h=2160:upscaler=ewa_lanczos:force_original_aspect_ratio=decrease:custom_shader_path='shaders/Anime4K_ModeA.glsl' -c:v hevc_nvenc -cq 26 -rc vbr -bf 5 -refs 4 -preset p5 "!tempOutput!\!newFileName!.mp4"

			REM Move file to final destination
			move /Y "!tempOutput!\!newFileName!.mp4" "!newDirectory!\!newFileName!.mp4"
			
			set "filename_ps=!newFileName:[=`[!"
			set "filename_ps=!filename_ps:]=`]!"
			set "filename_ps=!filename_ps:'=''!"
			set "directory_ps=!newDirectory:[=`[!"
			set "directory_ps=!directory_ps:]=`]!"
			set "directory_ps=!directory_ps:'=''!"

			REM Extract all subtitles
			set "counter=0"
			for /f "tokens=1,2,3 delims=," %%a in ('ffprobe -loglevel error -select_streams s -show_entries stream^=index^,codec_name:stream_tags^=language -of csv^=p^=0 "!file!"') do (
				set "sub_index=%%a"
				set "codec=%%b"
				set "lang=%%c"
				echo !codec!

				if /I "!lang!"=="eng" (
					set "lang=default.eng"

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

					set "outfile=!newDirectory!\!newFileName!.!lang!.!counter!.!ext!"

					REM Extract subtitle
					if /I "!ext!"=="ass" (
						set "utf8file=!outfile:.ass=.utf8.ass!"
						ffmpeg -y -i "!file!" -map 0:!sub_index! !codec_arg! "!utf8file!"
						!powershell! -Command "Get-Content -Path '!directory_ps!\!filename_ps!.!lang!.!counter!.utf8.ass' -Encoding UTF8 ^| Set-Content -Path '!directory_ps!\!filename_ps!.!lang!.!counter!.ass' -Encoding utf8"
						del "!utf8file!"
					) else (
						ffmpeg -y -i "!file!" -map 0:!sub_index! !codec_arg! "!outfile!"
					)

					set /a "counter+=1"
				)
			)
			del "!file!" /q /s
			endlocal
		)
		
		REM Cleanup empty folders
		cd /d "%UserDirectory%\Downloads\"
		for /f "delims=" %%d in ('dir /ad /s /b ^| sort /R') do rd "%%d" 2>nul

		if exist "%UserDirectory%\Downloads\*.mkv" (
			goto start
		)
	)
)
endlocal