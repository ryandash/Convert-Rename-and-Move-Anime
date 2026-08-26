param(
    [Parameter(Mandatory = $true)]
    [string]$OriginalSubtitles,

    [Parameter(Mandatory = $true)]
    [string]$ResampledSubtitles
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

$Config = Join-Path $PSScriptRoot "unscale-tags.txt"

# ------------------------------------------------------------
# Check files
# ------------------------------------------------------------

if (-not (Test-Path -LiteralPath $OriginalSubtitles)) {
    throw "Original subtitle file not found: $OriginalSubtitles"
}

if (-not (Test-Path -LiteralPath $ResampledSubtitles)) {
    throw "Resampled subtitle file not found: $ResampledSubtitles"
}

if (-not (Test-Path -LiteralPath $Config)) {
    throw "Configuration file not found: $Config"
}

# ------------------------------------------------------------
# Get ASS PlayResX / PlayResY
# ------------------------------------------------------------

function Get-AssResolution {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SubtitleFile
    )

    $PlayResX = $null
    $PlayResY = $null

    # Read the file as text.
    #
    # UTF8 detection is handled by .NET when a BOM is present.
    $Lines = Get-Content `
        -LiteralPath $SubtitleFile `
        -Encoding UTF8

    foreach ($Line in $Lines) {

        # Stop once we reach the first section after [Script Info]
        if ($Line -match '^\s*\[' -and $Line -notmatch '^\s*\[\s*Script Info\s*\]\s*$') {
            if ($null -ne $PlayResX -and $null -ne $PlayResY) {
                break
            }
        }

        if ($Line -match '^\s*PlayResX\s*:\s*(\d+(?:\.\d+)?)\s*$') {
            $PlayResX = [double]$Matches[1]
        }

        if ($Line -match '^\s*PlayResY\s*:\s*(\d+(?:\.\d+)?)\s*$') {
            $PlayResY = [double]$Matches[1]
        }
    }

    if ($null -eq $PlayResX) {
        throw "PlayResX was not found in: $SubtitleFile"
    }

    if ($null -eq $PlayResY) {
        throw "PlayResY was not found in: $SubtitleFile"
    }

    return @{
        Width  = $PlayResX
        Height = $PlayResY
    }
}

# ------------------------------------------------------------
# Format ASS numbers
# ------------------------------------------------------------

function Format-AssNumber {
    param(
        [double]$Value
    )

    $Value = [Math]::Round($Value, 6)

    if ($Value -eq [Math]::Truncate($Value)) {
        return ([int]$Value).ToString(
            [System.Globalization.CultureInfo]::InvariantCulture
        )
    }

    return $Value.ToString(
        "0.######",
        [System.Globalization.CultureInfo]::InvariantCulture
    )
}

# ------------------------------------------------------------
# Load configuration
#
# Example:
#
# bord uniform
# xbord x
# ybord y
# shad uniform
# blur uniform
#
# Valid modes:
#
# uniform
# x
# y
#
# If no mode is specified, uniform is assumed.
# ------------------------------------------------------------

Write-Host ""
Write-Host "Loading tag configuration..." -ForegroundColor Cyan

$Tags = @{}

foreach ($Line in Get-Content -LiteralPath $Config -Encoding UTF8) {

    $Line = $Line.Trim()

    # Ignore blank lines
    if ([string]::IsNullOrWhiteSpace($Line)) {
        continue
    }

    # Ignore comments
    if ($Line.StartsWith("#")) {
        continue
    }

    $Parts = $Line -split '\s+'

    $Tag = $Parts[0].TrimStart("\")

    if ([string]::IsNullOrWhiteSpace($Tag)) {
        continue
    }

    $Mode = "uniform"

    if ($Parts.Count -ge 2) {
        $Mode = $Parts[1].ToLowerInvariant()
    }

    if ($Mode -notin @("uniform", "x", "y")) {
        throw "Invalid scaling mode '$Mode' for tag '$Tag'. Valid modes are: uniform, x, y."
    }

    $Tags[$Tag.ToLowerInvariant()] = $Mode
}

if ($Tags.Count -eq 0) {
    throw "No tags were specified in: $Config"
}

# ------------------------------------------------------------
# Determine ASS resolutions
# ------------------------------------------------------------

Write-Host ""
Write-Host "Determining ASS resolutions..." -ForegroundColor Cyan

$Original = Get-AssResolution $OriginalSubtitles
$Resampled = Get-AssResolution $ResampledSubtitles

$OriginalWidth = $Original.Width
$OriginalHeight = $Original.Height

$ResampledWidth = $Resampled.Width
$ResampledHeight = $Resampled.Height

$ScaleX = $ResampledWidth / $OriginalWidth
$ScaleY = $ResampledHeight / $OriginalHeight

Write-Host "Original ASS : $OriginalWidth x $OriginalHeight"
Write-Host "Resampled ASS: $ResampledWidth x $ResampledHeight"
Write-Host "Scale X      : $ScaleX"
Write-Host "Scale Y      : $ScaleY"
Write-Host ""

# ------------------------------------------------------------
# ASS numeric tag pattern
#
# Matches:
#
# \bord3672
# \xbord3672
# \blur48
# \shad20
# \fsp12
#
# Does not match:
#
# \pos(1920,1080)
# \move(...)
#
# ------------------------------------------------------------

$TagPattern = '\\([a-zA-Z]+)([-+]?(?:\d+(?:\.\d*)?|\.\d+))'

# ------------------------------------------------------------
# Process an ASS override block
# ------------------------------------------------------------

function Process-OverrideBlock {
    param(
        [AllowEmptyString()]
        [string]$Block
    )

    return [regex]::Replace(
        $Block,
        $TagPattern,
        {
            param($Match)

            $TagName = $Match.Groups[1].Value
            $ValueText = $Match.Groups[2].Value

            $TagKey = $TagName.ToLowerInvariant()

            # Not configured -> leave unchanged
            if (-not $Tags.ContainsKey($TagKey)) {
                return $Match.Value
            }

            $Value = 0.0

            $Parsed = [double]::TryParse(
                $ValueText,
                [System.Globalization.NumberStyles]::Float,
                [System.Globalization.CultureInfo]::InvariantCulture,
                [ref]$Value
            )

            if (-not $Parsed) {
                return $Match.Value
            }

            $Mode = $Tags[$TagKey]

            switch ($Mode) {

                "x" {
                    $NewValue = $Value / $ScaleX
                }

                "y" {
                    $NewValue = $Value / $ScaleY
                }

                "uniform" {

                    # Uniform tags such as:
                    #
                    # \bord
                    # \shad
                    # \blur
                    #
                    # Ideally ScaleX and ScaleY are identical.
                    #
                    # Use X if they differ.

                    $NewValue = $Value / $ScaleX
                }

                default {
                    $NewValue = $Value
                }
            }

            return "\" + $TagName + (Format-AssNumber $NewValue)
        }
    )
}

# ------------------------------------------------------------
# Process an ASS line
# ------------------------------------------------------------

function Process-AssLine {
    param(
        [AllowEmptyString()]
        [string]$Line
    )

    # Empty line
    if ([string]::IsNullOrEmpty($Line)) {
        return $Line
    }

    return [regex]::Replace(
        $Line,
        '\{[^{}]*\}',
        {
            param($Match)

            Process-OverrideBlock $Match.Value
        }
    )
}

# ------------------------------------------------------------
# Read resampled ASS
# ------------------------------------------------------------

Write-Host "Reading resampled subtitle..." -ForegroundColor Cyan

$Lines = Get-Content `
    -LiteralPath $ResampledSubtitles `
    -Encoding UTF8

# ------------------------------------------------------------
# Process ASS
# ------------------------------------------------------------

Write-Host "Correcting configured override tags..." -ForegroundColor Cyan

$ProcessedLines = foreach ($Line in $Lines) {
    Process-AssLine $Line
}

# ------------------------------------------------------------
# Write UTF-8 with BOM
# ------------------------------------------------------------

Write-Host "Writing UTF-8 BOM subtitle..." -ForegroundColor Cyan

$Utf8Bom = New-Object System.Text.UTF8Encoding($true)

[System.IO.File]::WriteAllLines(
    $ResampledSubtitles,
    $ProcessedLines,
    $Utf8Bom
)

# ------------------------------------------------------------
# Summary
# ------------------------------------------------------------

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "ASS scaling correction complete" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Write-Host "Original ASS :" -NoNewline
Write-Host " $OriginalWidth x $OriginalHeight"

Write-Host "Resampled ASS:" -NoNewline
Write-Host " $ResampledWidth x $ResampledHeight"

Write-Host "Scale X      :" -NoNewline
Write-Host " $ScaleX"

Write-Host "Scale Y      :" -NoNewline
Write-Host " $ScaleY"

Write-Host ""
Write-Host "Corrected tags:" -ForegroundColor Yellow

foreach ($Entry in $Tags.GetEnumerator()) {
    Write-Host ("  \{0} ({1})" -f $Entry.Key, $Entry.Value)
}

Write-Host ""
Write-Host "Updated:"
Write-Host "  $ResampledSubtitles"
Write-Host ""