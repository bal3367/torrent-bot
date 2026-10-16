# Torrent Bot - download cepat (dibuat otomatis oleh bot, dijalankan lewat: irm <link> | iex)
# 1) pilih link pertama yang hidup (link langsung ke VPS dulu, baru Cloudflare)
# 2) file besar dipecah jadi beberapa bagian, di-download paralel (curl.exe bawaan Windows), lalu digabung
# 3) putus? paste command yang sama lagi - bagian yang sudah selesai tidak di-download ulang
$ErrorActionPreference = 'Stop'
$name = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__NAME_B64__'))
$size = [int64]__SIZE__
$cands = @(__URLS__)
$n = __PARTS__

$dest = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Downloads'
$out = Join-Path $dest $name
if ((Test-Path -LiteralPath $out) -and ((Get-Item -LiteralPath $out).Length -eq $size)) {
    Write-Host "Sudah lengkap: $out" -ForegroundColor Green; return
}

$url = $null
foreach ($u in $cands) {
    $code = & curl.exe -s -o NUL -w '%{http_code}' -I --max-time 10 $u
    if ($code -eq '200') { $url = $u; break }
}
if (-not $url) {
    Write-Host 'Link tidak bisa dibuka. Klik ulang file di bot untuk dapat command baru.' -ForegroundColor Red; return
}
Write-Host "Sumber : $url"
Write-Host "Simpan : $out ($([math]::Round($size / 1MB)) MB)"

$ver = (& curl.exe --version | Select-Object -First 1)
$canParallel = $false
if ($ver -match 'curl (\d+)\.(\d+)') { $canParallel = ([int]$Matches[1] -gt 7) -or ([int]$Matches[1] -eq 7 -and [int]$Matches[2] -ge 66) }

if (-not $canParallel -or $size -lt 50MB) {
    & curl.exe -fL -C - --retry 10 -o $out $url
    if ($LASTEXITCODE -eq 0) { Write-Host "Selesai: $out" -ForegroundColor Green }
    else { Write-Host 'Gagal / putus. Paste command yang sama lagi untuk melanjutkan.' -ForegroundColor Red }
    return
}

$tmp = "$out.parts"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$chunk = [int64][math]::Ceiling($size / $n)
function Get-Parts {
    $list = @()
    for ($i = 0; $i -lt $n; $i++) {
        $s = [int64]$i * $chunk
        if ($s -ge $size) { break }
        $e = [math]::Min($size, $s + $chunk) - 1
        $list += [pscustomobject]@{ Path = (Join-Path $tmp ('part{0:D2}' -f $i)); Start = $s; End = $e; Len = $e - $s + 1 }
    }
    return $list
}
function Test-PartDone($p) { (Test-Path -LiteralPath $p.Path) -and ((Get-Item -LiteralPath $p.Path).Length -eq $p.Len) }

$parts = Get-Parts
for ($attempt = 1; $attempt -le 5; $attempt++) {
    $todo = @($parts | Where-Object { -not (Test-PartDone $_) })
    if ($todo.Count -eq 0) { break }
    Write-Host "Download $($todo.Count) bagian sekaligus (percobaan $attempt)..."
    # --http1.1: tiap bagian koneksi TCP sendiri (HTTP/2 akan menumpuk semuanya di 1 koneksi).
    $ca = @('--parallel', '--parallel-max', "$n")
    $first = $true
    foreach ($p in $todo) {
        if (-not $first) { $ca += '--next' }
        $first = $false
        $ca += @('--http1.1', '-fL', '--retry', '5', '-r', "$($p.Start)-$($p.End)", '-o', $p.Path, $url)
    }
    & curl.exe @ca
}

$missing = @($parts | Where-Object { -not (Test-PartDone $_) })
if ($missing.Count -gt 0) {
    Write-Host "$($missing.Count) bagian belum lengkap. Paste command yang sama lagi untuk melanjutkan." -ForegroundColor Red; return
}
Write-Host 'Menggabungkan bagian...'
$fs = [IO.File]::Create($out)
try {
    foreach ($p in $parts) {
        $in = [IO.File]::OpenRead($p.Path)
        try { $in.CopyTo($fs) } finally { $in.Dispose() }
    }
} finally { $fs.Dispose() }
if ((Get-Item -LiteralPath $out).Length -eq $size) {
    Remove-Item -Recurse -Force -LiteralPath $tmp
    Write-Host "Selesai: $out" -ForegroundColor Green
} else {
    Write-Host 'Ukuran hasil tidak cocok. Paste command yang sama lagi.' -ForegroundColor Red
    Remove-Item -Force -LiteralPath $out
}
