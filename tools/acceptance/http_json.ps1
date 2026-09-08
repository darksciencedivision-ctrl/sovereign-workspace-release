# HTTP JSON helper for acceptance. GET/HEAD never send a body.
# Do not type -Body as [string]: Windows PowerShell binds $null to ''.

$script:HttpJsonUtf8 = [Text.UTF8Encoding]::new($false)
$script:HttpJsonLastError = $null

function Invoke-Json {
    param(
        [Parameter(Mandatory = $true)][string] $Method,
        [Parameter(Mandatory = $true)][string] $Url,
        [AllowNull()] $Body,
        [hashtable] $Headers
    )
    $script:HttpJsonLastError = $null
    $methodUpper = $Method.Trim().ToUpperInvariant()
    $req = [Net.HttpWebRequest]::Create($Url)
    $req.Method = $methodUpper
    $req.Timeout = 30000
    $req.ReadWriteTimeout = 30000
    $req.Host = ([Uri]$Url).Authority
    $req.AllowAutoRedirect = $false
    if ($Headers) {
        foreach ($k in $Headers.Keys) { $req.Headers[$k] = [string]$Headers[$k] }
    }
    $sendBody = ($methodUpper -notin @('GET', 'HEAD')) -and ($null -ne $Body)
    if ($sendBody) {
        $payload = [string]$Body
        $bytes = $script:HttpJsonUtf8.GetBytes($payload)
        $req.ContentType = 'application/json'
        $req.ContentLength = $bytes.Length
        $s = $req.GetRequestStream()
        try { $s.Write($bytes, 0, $bytes.Length) } finally { $s.Dispose() }
    }
    try {
        $resp = $req.GetResponse()
    }
    catch [Net.WebException] {
        $script:HttpJsonLastError = $_.Exception.Message
        $resp = $_.Exception.Response
        if (-not $resp) { throw }
    }
    $code = [int]$resp.StatusCode
    $reader = New-Object IO.StreamReader($resp.GetResponseStream())
    try { $text = $reader.ReadToEnd() } finally { $reader.Dispose(); $resp.Dispose() }
    return @{
        Code  = $code
        Text  = $text
        Json  = $(try { $text | ConvertFrom-Json } catch { $null })
        Error = $script:HttpJsonLastError
    }
}

function Wait-Url {
    param(
        [Parameter(Mandatory = $true)][string] $Url,
        [int] $Seconds = 60,
        [System.Diagnostics.Process] $Child
    )
    $deadline = [datetime]::UtcNow.AddSeconds($Seconds)
    $last = $null
    while ([datetime]::UtcNow -lt $deadline) {
        if ($Child -and $Child.HasExited) {
            throw ("child exited {0} while waiting for {1}; last error: {2}" -f `
                   $Child.ExitCode, $Url, $script:HttpJsonLastError)
        }
        try {
            $r = Invoke-Json -Method GET -Url $Url
            if ($r.Code -ge 200 -and $r.Code -lt 300) { return $r }
            $last = "HTTP $($r.Code) $($r.Text)"
        }
        catch {
            $last = $_.Exception.Message
            if ($script:HttpJsonLastError) { $last = $script:HttpJsonLastError }
        }
        Start-Sleep -Milliseconds 200
    }
    throw "timed out waiting for $Url; last error: $last"
}
