```bat
@echo off
setlocal

echo ================================
echo Convert-and-Move-Anime Setup
echo ================================
echo.

REM =================================
REM Check system Python
REM =================================

echo Checking Python...

python --version
if errorlevel 1 (
    echo Python is not installed.
    echo Please install Python and run this setup again.
    pause
    exit /b 1
)

echo Python found:
where python
echo.

REM =================================
REM Install base Python dependencies
REM =================================

echo Installing Python dependencies...

python -m pip install --upgrade pip
python -m pip install -r "%~dp0requirements.txt"

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install Python dependencies.
    pause
    exit /b 1
)

REM =================================
REM Enter VapourSynth directory
REM =================================

echo.
echo Entering VapourSynth directory...

pushd "%~dp0vapoursynth-portable" || (
    echo ERROR: Could not find vapoursynth-portable.
    echo Expected location:
    echo "%~dp0vapoursynth-portable"
    pause
    exit /b 1
)

REM =================================
REM Check VapourSynth Python
REM =================================

echo.
echo Checking VapourSynth Python...

python --version
if errorlevel 1 (
    echo Python is not available from the VapourSynth environment.
    popd
    pause
    exit /b 1
)

echo Python location:
where python

REM =================================
REM Install PyTorch / Torch-TensorRT
REM =================================

echo.
echo Installing PyTorch and Torch-TensorRT...

python -m pip install -U torch torchvision torch_tensorrt ^
    --index-url https://download.pytorch.org/whl/cu128 ^
    --extra-index-url https://pypi.nvidia.com ^
    --no-build-isolation

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install PyTorch/Torch-TensorRT.
    popd
    pause
    exit /b 1
)

REM =================================
REM Create required directories
REM =================================

echo.
echo Creating required directories...

if not exist "Lib\site-packages\vsdrba\models" (
    mkdir "Lib\site-packages\vsdrba\models"
)

REM =================================
REM Download RIFE models
REM =================================

echo.
echo Downloading RIFE models...

python -m vsdrba

if errorlevel 1 (
    echo.
    echo ERROR: Failed to download RIFE models.
    popd
    pause
    exit /b 1
)

REM =================================
REM Return to original directory
REM =================================

popd

echo.
echo ================================
echo Setup complete!
echo ================================
pause
```
