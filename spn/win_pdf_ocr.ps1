param(
    [Parameter(Mandatory=$true)][string]$Pdf,
    [Parameter(Mandatory=$true)][string]$OutJson,
    [int]$Page = 0,
    [int]$Width = 1600,
    [string]$Region = '',
    [string]$PreviewPng = '',
    [int]$PreviewWidth = 420,
    [switch]$RenderOnly
)
# Render one PDF page and OCR it with the built-in Windows engine.
# Stays ASCII-only on purpose (PS 5.1 reads scripts as GBK otherwise).
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Runtime.WindowsRuntime

[Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataWriter, Windows.Storage.Streams, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Pdf.PdfPageRenderOptions, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null

$asTaskOp = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})
$asTaskAction = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
})[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskOp.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    try { $netTask.Wait(-1) | Out-Null }
    catch {
        $e = $_.Exception
        while ($e.InnerException) { $e = $e.InnerException }
        throw ($e.GetType().Name + ': ' + $e.Message)
    }
    $netTask.Result
}
function AwaitAction($WinRtAction) {
    $netTask = $asTaskAction.Invoke($null, @($WinRtAction))
    try { $netTask.Wait(-1) | Out-Null }
    catch {
        $e = $_.Exception
        while ($e.InnerException) { $e = $e.InnerException }
        throw ($e.GetType().Name + ': ' + $e.Message)
    }
}
function NewMemStream([byte[]]$bytes) {
    $ms = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    $dw = New-Object Windows.Storage.Streams.DataWriter($ms)
    $dw.WriteBytes($bytes)
    Await ($dw.StoreAsync()) ([uint32]) | Out-Null
    $dw.DetachStream() | Out-Null
    $ms.Seek(0) | Out-Null
    return $ms
}
function ReadMemStream($ms) {
    $ms.Seek(0) | Out-Null
    $size = [int]$ms.Size
    $dr = New-Object Windows.Storage.Streams.DataReader($ms)
    Await ($dr.LoadAsync([uint32]$size)) ([uint32]) | Out-Null
    $bytes = New-Object byte[] $size
    $dr.ReadBytes($bytes)
    $dr.DetachStream() | Out-Null
    return ,$bytes
}

$result = @{ lines = @(); boxes = @(); width = 0; height = 0; pages = 0; engine = ''; error = '' }
try {
    $pdfBytes = [System.IO.File]::ReadAllBytes($Pdf)
    $inStream = NewMemStream $pdfBytes
    $doc = Await ([Windows.Data.Pdf.PdfDocument]::LoadFromStreamAsync($inStream)) ([Windows.Data.Pdf.PdfDocument])
    if ($Page -ge $doc.PageCount) { throw "page $Page out of range ($($doc.PageCount))" }
    $result.pages = $doc.PageCount
    $pdfPage = $doc.GetPage($Page)

    $opts = New-Object Windows.Data.Pdf.PdfPageRenderOptions
    $opts.DestinationWidth = [uint32]$Width

    $renderStream = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    AwaitAction ($pdfPage.RenderToStreamAsync($renderStream, $opts))
    $pngBytes = ReadMemStream $renderStream

    $srcImg = [System.Drawing.Image]::FromStream((New-Object System.IO.MemoryStream(,$pngBytes)))
    $result.width = $srcImg.Width
    $result.height = $srcImg.Height

    if ($Region -ne '') {
        $parts = $Region.Split(',')
        $x0 = [int]([double]$parts[0] * $srcImg.Width)
        $y0 = [int]([double]$parts[1] * $srcImg.Height)
        $x1 = [int]([double]$parts[2] * $srcImg.Width)
        $y1 = [int]([double]$parts[3] * $srcImg.Height)
        $w = [Math]::Max(1, $x1 - $x0)
        $h = [Math]::Max(1, $y1 - $y0)
        $crop = New-Object System.Drawing.Bitmap $w, $h
        $cg = [System.Drawing.Graphics]::FromImage($crop)
        $cg.DrawImage($srcImg, (New-Object System.Drawing.Rectangle 0, 0, $w, $h),
                      (New-Object System.Drawing.Rectangle $x0, $y0, $w, $h),
                      [System.Drawing.GraphicsUnit]::Pixel)
        $cg.Dispose()
        $cropStream = New-Object System.IO.MemoryStream
        $crop.Save($cropStream, [System.Drawing.Imaging.ImageFormat]::Png)
        $pngBytes = $cropStream.ToArray()
        $crop.Dispose()
    }
    $srcImg.Dispose()

    if ($PreviewPng -ne '') {
        $prevImg = [System.Drawing.Image]::FromStream((New-Object System.IO.MemoryStream(,$pngBytes)))
        $scale = [Math]::Min(1.0, [double]$PreviewWidth / $prevImg.Width)
        $pw = [Math]::Max(1, [int]($prevImg.Width * $scale))
        $ph = [Math]::Max(1, [int]($prevImg.Height * $scale))
        $pbmp = New-Object System.Drawing.Bitmap $pw, $ph
        $pg = [System.Drawing.Graphics]::FromImage($pbmp)
        $pg.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $pg.DrawImage($prevImg, 0, 0, $pw, $ph)
        $pg.Dispose()
        $prevImg.Dispose()
        $pbmp.Save($PreviewPng, [System.Drawing.Imaging.ImageFormat]::Jpeg)
        $pbmp.Dispose()
    }

    if (-not $RenderOnly) {
        $imgStream = NewMemStream $pngBytes
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($imgStream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $sb = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

        $lang = New-Object Windows.Globalization.Language 'zh-Hans-CN'
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
        if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
        if (-not $engine) { throw 'no OCR recognizer available' }
        $result.engine = $engine.RecognizerLanguage.LanguageTag

        $ocr = Await ($engine.RecognizeAsync($sb)) ([Windows.Media.Ocr.OcrResult])
        $texts = @()
        $boxes = @()
        foreach ($line in $ocr.Lines) {
            $texts += $line.Text
            $bx1 = 1e9; $by1 = 1e9; $bx2 = -1.0; $by2 = -1.0
            foreach ($wd in $line.Words) {
                $r = $wd.BoundingRect
                if ($r.X -lt $bx1) { $bx1 = $r.X }
                if ($r.Y -lt $by1) { $by1 = $r.Y }
                if (($r.X + $r.Width) -gt $bx2) { $bx2 = $r.X + $r.Width }
                if (($r.Y + $r.Height) -gt $by2) { $by2 = $r.Y + $r.Height }
            }
            $boxes += @{
                x = [double]$bx1; y = [double]$by1
                w = [double]($bx2 - $bx1); h = [double]($by2 - $by1)
            }
        }
        $result.lines = $texts
        $result.boxes = $boxes
    }
}
catch {
    $result.error = $_.Exception.Message
}

$json = $result | ConvertTo-Json -Depth 4 -Compress
[System.IO.File]::WriteAllText($OutJson, $json, (New-Object System.Text.UTF8Encoding($false)))
if ($result.error -ne '') { exit 2 } else { exit 0 }
