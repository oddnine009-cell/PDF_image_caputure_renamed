param(
    [Parameter(Mandatory=$true)][string]$TextFile,
    [Parameter(Mandatory=$true)][string]$Out,
    [string]$Font = 'KaiTi',
    [int]$Width = 1240,
    [int]$Height = 1754
)
# Renders a fake "scanned assignment" page to JPEG.
# All Chinese text comes from $TextFile (UTF-8) so this script stays ASCII-only,
# which keeps Windows PowerShell 5.1 from misreading it as GBK.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$lines = Get-Content -LiteralPath $TextFile -Encoding UTF8
$name  = if ($lines.Count -ge 1) { $lines[0] } else { '' }
$class = if ($lines.Count -ge 2) { $lines[1] } else { '' }
$title = if ($lines.Count -ge 3) { $lines[2] } else { '' }
$label = if ($lines.Count -ge 4) { $lines[3] } else { '' }
$body  = if ($lines.Count -ge 5) { $lines[4..($lines.Count-1)] } else { @() }

$bmp = New-Object System.Drawing.Bitmap $Width, $Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::White)
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

$printFont = New-Object System.Drawing.Font('SimSun', 30, [System.Drawing.FontStyle]::Regular)
$labelFont = New-Object System.Drawing.Font('SimSun', 32, [System.Drawing.FontStyle]::Regular)
$nameFont  = New-Object System.Drawing.Font($Font, 52, [System.Drawing.FontStyle]::Regular)
$smallFont = New-Object System.Drawing.Font('SimSun', 26, [System.Drawing.FontStyle]::Regular)
$black = [System.Drawing.Brushes]::Black
$gray  = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(120,120,120))

$g.DrawString($title, $printFont, $black, 90, 80)
$g.DrawLine((New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(200,200,200), 2)), 90, 140, ($Width - 90), 140)

$g.DrawString($class, $labelFont, $gray, 90, 180)
$g.DrawString(' / ', $labelFont, $gray, 300, 180)

# name label (printed) + handwritten-looking name (KaiTi, slightly rotated)
$g.DrawString($label, $labelFont, $black, 90, 250)
$state = $g.Save()
$g.TranslateTransform(260, 252)
$g.RotateTransform(-3.5)
$g.DrawString($name, $nameFont, $black, 0, 0)
$g.Restore($state)
$g.DrawLine((New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(90,90,90), 2)), 255, 340, 780, 340)

$y = 430
foreach ($line in $body) {
    $g.DrawString($line, $smallFont, $black, 90, $y)
    $y += 62
}

$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Jpeg)
$bmp.Dispose()
