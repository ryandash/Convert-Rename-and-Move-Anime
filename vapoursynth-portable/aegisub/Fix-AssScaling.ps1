
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

# Map renamed styles to their original style names.
# Edit these mappings if your style naming changes.

$StyleAliases = @{
    "main"              = "Internal"
    "top"               = "Overlap top"
    "italics"           = "Internal"
    "italicstop"        = "Overlap top"
    "flashback"         = "Flashback"
    "flashback italics" = "Flashback"
}

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
# Get ASS resolution
# ------------------------------------------------------------

function Get-AssResolution {
    param(
        [string]$SubtitleFile
    )

    $PlayResX = $null
    $PlayResY = $null

    $Lines = Get-Content -LiteralPath $SubtitleFile -Encoding UTF8

    foreach ($Line in $Lines) {

        if ($Line -match '^\s*\[' -and
            $Line -notmatch '^\s*\[\s*Script Info\s*\]\s*$') {

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

    if ($null -eq $PlayResX -or $null -eq $PlayResY) {
        throw "Unable to determine PlayResX / PlayResY: $SubtitleFile"
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
        return $Value.ToString(
            "0",
            [System.Globalization.CultureInfo]::InvariantCulture
        )
    }

    return $Value.ToString(
        "0.######",
        [System.Globalization.CultureInfo]::InvariantCulture
    )
}

# ------------------------------------------------------------
# Load tag configuration
# ------------------------------------------------------------

Write-Host ""
Write-Host "Loading tag configuration..." -ForegroundColor Cyan

$Tags = @{}

foreach ($Line in Get-Content -LiteralPath $Config -Encoding UTF8) {

    $Line = $Line.Trim()

    if ([string]::IsNullOrWhiteSpace($Line)) {
        continue
    }

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
        throw "Invalid scaling mode '$Mode' for tag '$Tag'."
    }

    $Tags[$Tag.ToLowerInvariant()] = $Mode
}

if ($Tags.Count -eq 0) {
    throw "No tags were specified in: $Config"
}

# ------------------------------------------------------------
# Determine resolutions
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

# ------------------------------------------------------------
# Load original style definitions
#
# ASS style field positions:
#
# 16 = Outline
# 17 = Shadow
#
# ------------------------------------------------------------

Write-Host ""
Write-Host "Loading original style definitions..." -ForegroundColor Cyan

$OriginalStyles = @{}

$OriginalLines = Get-Content `
    -LiteralPath $OriginalSubtitles `
    -Encoding UTF8

foreach ($Line in $OriginalLines) {

    if ($Line -notmatch '^\s*Style\s*:') {
        continue
    }

    $Fields = $Line -split ','

    if ($Fields.Count -lt 18) {
        continue
    }

    $StyleName = ($Fields[0] -replace '^\s*Style\s*:\s*', '').Trim()

    $OriginalStyles[$StyleName.ToLowerInvariant()] = @{
        Outline = $Fields[16].Trim()
        Shadow  = $Fields[17].Trim()
    }
}

if ($OriginalStyles.Count -eq 0) {
    throw "No original ASS styles were found."
}

# ------------------------------------------------------------
# Restore style-level Outline and Shadow
# ------------------------------------------------------------

function Process-StyleLine {
    param(
        [string]$Line
    )

    if ($Line -notmatch '^\s*Style\s*:') {
        return $Line
    }

    $Fields = $Line -split ','

    if ($Fields.Count -lt 18) {
        return $Line
    }

    $StyleName = ($Fields[0] -replace '^\s*Style\s*:\s*', '').Trim()

    $LookupName = $StyleName.ToLowerInvariant()

    # Apply renamed style mapping.

    if ($script:StyleAliases.ContainsKey($LookupName)) {
        $LookupName = $script:StyleAliases[$LookupName].ToLowerInvariant()
    }

    # Restore exact original values when a matching style exists.

    if ($script:OriginalStyles.ContainsKey($LookupName)) {

        $OriginalStyle = $script:OriginalStyles[$LookupName]

        $Fields[16] = $OriginalStyle.Outline
        $Fields[17] = $OriginalStyle.Shadow

        Write-Host (
            "  Restored style: {0} (Outline={1}, Shadow={2})" -f
            $StyleName,
            $Fields[16],
            $Fields[17]
        ) -ForegroundColor Green

    }
    else {

        # Generated or unmatched styles:
        # Reverse the resampling scale.

        $Outline = 0.0
        $Shadow = 0.0

        $OutlineParsed = [double]::TryParse(
            $Fields[16].Trim(),
            [System.Globalization.NumberStyles]::Float,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$Outline
        )

        $ShadowParsed = [double]::TryParse(
            $Fields[17].Trim(),
            [System.Globalization.NumberStyles]::Float,
            [System.Globalization.CultureInfo]::InvariantCulture,
            [ref]$Shadow
        )

        if ($OutlineParsed) {
            $Fields[16] = Format-AssNumber ($Outline / $script:ScaleX)
        }

        if ($ShadowParsed) {
            $Fields[17] = Format-AssNumber ($Shadow / $script:ScaleX)
        }

        Write-Host (
            "  Unscaled generated style: {0} (Outline={1}, Shadow={2})" -f
            $StyleName,
            $Fields[16],
            $Fields[17]
        ) -ForegroundColor Yellow
    }

    return ($Fields -join ',')
}

# ------------------------------------------------------------
# ASS override tag pattern
# ------------------------------------------------------------

$TagPattern = '\\([a-zA-Z]+)([-+]?(?:\d+(?:\.\d*)?|\.\d+))'

# ------------------------------------------------------------
# Process override blocks
# ------------------------------------------------------------

function Process-OverrideBlock {
    param(
        [AllowEmptyString()]
        [string]$Block
    )

    return [regex]::Replace(
        $Block,
        $script:TagPattern,
        {
            param($Match)

            $TagName = $Match.Groups[1].Value
            $ValueText = $Match.Groups[2].Value

            $TagKey = $TagName.ToLowerInvariant()

            if (-not $script:Tags.ContainsKey($TagKey)) {
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

            $Mode = $script:Tags[$TagKey]

            switch ($Mode) {

                "x" {
                    $NewValue = $Value / $script:ScaleX
                }

                "y" {
                    $NewValue = $Value / $script:ScaleY
                }

                "uniform" {
                    $NewValue = $Value / $script:ScaleX
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
# Process ASS line
# ------------------------------------------------------------

function Process-AssLine {
    param(
        [AllowEmptyString()]
        [string]$Line
    )

    if ([string]::IsNullOrEmpty($Line)) {
        return $Line
    }

    # Restore style-level Outline and Shadow.

    if ($Line -match '^\s*Style\s*:') {
        return Process-StyleLine $Line
    }

    # Correct dialogue override tags.

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
# Process resampled subtitle
# ------------------------------------------------------------

Write-Host ""
Write-Host "Reading resampled subtitle..." -ForegroundColor Cyan

$Lines = Get-Content `
    -LiteralPath $ResampledSubtitles `
    -Encoding UTF8

Write-Host ""
Write-Host "Restoring style Outline and Shadow..." -ForegroundColor Cyan

Write-Host ""
Write-Host "Correcting configured override tags..." -ForegroundColor Cyan

$ProcessedLines = foreach ($Line in $Lines) {
    Process-AssLine $Line
}

# ------------------------------------------------------------
# Write UTF-8 with BOM
# ------------------------------------------------------------

Write-Host ""
Write-Host "Writing corrected subtitle..." -ForegroundColor Cyan

$Utf8Bom = New-Object System.Text.UTF8Encoding($true)

[System.IO.File]::WriteAllLines(
    $ResampledSubtitles,
    [string[]]$ProcessedLines,
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
Write-Host "Original ASS :" $OriginalWidth "x" $OriginalHeight
Write-Host "Resampled ASS:" $ResampledWidth "x" $ResampledHeight

Write-Host ""
Write-Host "Restored style properties:"
Write-Host "  Outline"
Write-Host "  Shadow"

Write-Host ""
Write-Host "Corrected override tags:"

foreach ($Entry in $Tags.GetEnumerator()) {
    Write-Host ("  \{0} ({1})" -f $Entry.Key, $Entry.Value)
}

Write-Host ""
Write-Host "Updated:"
Write-Host "  $ResampledSubtitles"
Write-Host ""
