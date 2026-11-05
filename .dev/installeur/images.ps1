# Images de l'assistant d'installation (Inno Setup), aux couleurs de l'appli, depuis .app\icone.png.
#   panneau-*.bmp  : panneau de gauche (pages Bienvenue et Fin), vert sapin + logo + nom
#   vignette-*.bmp : petit logo en haut à droite des autres pages
# Plusieurs tailles : Inno choisit celle qui correspond à la mise à l'échelle de l'écran (100 % → 250 %).
# Usage (Windows PowerShell 5.1, pour System.Drawing) :
#   powershell -ExecutionPolicy Bypass -File .dev\installeur\images.ps1
Add-Type -AssemblyName System.Drawing
$ici = $PSScriptRoot
$logo = [Drawing.Image]::FromFile((Join-Path (Split-Path (Split-Path $ici)) ".app\icone.png"))
$sapin = [Drawing.ColorTranslator]::FromHtml("#1F5E3B")
$clair = [Drawing.ColorTranslator]::FromHtml("#E7EFE9")

function Nouvelle($l, $h, $fond) {
    $b = New-Object Drawing.Bitmap $l, $h, ([Drawing.Imaging.PixelFormat]::Format24bppRgb)
    $g = [Drawing.Graphics]::FromImage($b)
    $g.SmoothingMode = "AntiAlias"; $g.InterpolationMode = "HighQualityBicubic"; $g.TextRenderingHint = "AntiAliasGridFit"
    $g.Clear($fond)
    return $b, $g
}

foreach ($t in @(@(164, 314), @(192, 386), @(246, 459), @(273, 556), @(328, 628), @(410, 797))) {
    $l, $h = $t; $k = $l / 164
    $b, $g = Nouvelle $l $h $sapin
    # halo discret derrière le logo
    $halo = New-Object Drawing.SolidBrush ([Drawing.Color]::FromArgb(28, 255, 255, 255))
    $d = [int](118 * $k); $g.FillEllipse($halo, [int](($l - $d) / 2), [int]($h * 0.40 - $d / 2), $d, $d)
    $c = [int](84 * $k); $g.DrawImage($logo, [int](($l - $c) / 2), [int]($h * 0.40 - $c / 2), $c, $c)
    $police = New-Object Drawing.Font "Georgia", ([single](17 * $k)), ([Drawing.FontStyle]::Bold), ([Drawing.GraphicsUnit]::Pixel)
    $f = New-Object Drawing.StringFormat; $f.Alignment = "Center"
    $g.DrawString("CV Booster", $police, (New-Object Drawing.SolidBrush $clair), (New-Object Drawing.RectangleF 0, ([single]($h * 0.40 + $d / 2 + 10 * $k)), $l, ([single](40 * $k))), $f)
    $g.Dispose(); $b.Save((Join-Path $ici "panneau-$l.bmp"), [Drawing.Imaging.ImageFormat]::Bmp); $b.Dispose()
}
foreach ($c in 55, 64, 83, 92, 110, 119, 138) {
    $b, $g = Nouvelle $c $c ([Drawing.Color]::White)
    $m = [int]($c * 0.06); $g.DrawImage($logo, $m, $m, $c - 2 * $m, $c - 2 * $m)
    $g.Dispose(); $b.Save((Join-Path $ici "vignette-$c.bmp"), [Drawing.Imaging.ImageFormat]::Bmp); $b.Dispose()
}
$logo.Dispose()
"images : $((Get-ChildItem $ici -Filter *.bmp).Count)"
