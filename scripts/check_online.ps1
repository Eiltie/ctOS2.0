param(
    [string]$Site = "https://ctos2.cn",
    [int]$Times = 3
)

# 连续访问线上关键资源，检查是否间歇性超时。
# 用法：powershell -ExecutionPolicy Bypass -File scripts\check_online.ps1
#
# 检查三个地方：后端存活、首页 HTML、前端 JS 产物
# （产物文件名带哈希，所以从首页 HTML 里现取，避免写死会过期）

$paths = @("/health", "/")
$ok = 0
$fail = 0

Write-Host "检查：$Site"
Write-Host "每项 $Times 次"
Write-Host ""

# 从首页 HTML 里取一个真实的 /static/... 资源路径
try {
    $html = (Invoke-WebRequest -Uri ($Site.TrimEnd("/") + "/") -UseBasicParsing -TimeoutSec 12).Content
    $match = [regex]::Match($html, '/static/[^"]+\.js')
    if ($match.Success) { $paths += $match.Value }
} catch {
    # 取不到就只查前两项
}

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
