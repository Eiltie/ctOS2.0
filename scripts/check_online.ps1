param(
    [string]$Site = "https://ctos2.cn",
    [int]$Times = 3
)

# 连续访问线上关键资源，检查是否间歇性超时。
# 用法：powershell -ExecutionPolicy Bypass -File scripts\check_online.ps1

$paths = @("/health", "/", "/static/js/app.js")
$ok = 0
$fail = 0

Write-Host "检查：$Site"
Write-Host "每项 $Times 次"
Write-Host ""

foreach ($path in $paths) {
    for ($i = 1; $i -le $Times; $i++) {
        $url = $Site.TrimEnd("/") + $path
        $watch = [Diagnostics.Stopwatch]::StartNew()
        try {
            $res = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 12
            $watch.Stop()
            Write-Host ("  OK   {0}  HTTP {1}  {2:N2}s" -f $path, $res.StatusCode, $watch.Elapsed.TotalSeconds)
            $ok++
        }
        catch {
            $watch.Stop()
            Write-Host ("  FAIL {0}  {1}" -f $path, $_.Exception.Message)
            $fail++
        }
    }
}

Write-Host ""
Write-Host "成功 $ok 次，失败 $fail 次"

if ($fail -gt 0) {
    Write-Host "有失败：先检查 Cloudflare 是否只保留了一个隧道副本。"
    exit 1
}

Write-Host "全部成功"
