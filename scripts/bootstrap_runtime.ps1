param([switch]$Approved, [string]$Archive, [string]$Sha256, [string]$Destination)
$ErrorActionPreference = 'Stop'
$madeTemp = $false
$temp = $null
$copy = $null
# Agent-only native extraction; no execution-policy changes, runtime execution or global installation.
try {
    if (-not $Approved) { throw 'RUNTIME_PERMISSION_REQUIRED' }
    if ($Sha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'RUNTIME_HASH_INVALID' }
    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf) -or (Test-Path -LiteralPath $Destination)) { throw 'RUNTIME_INPUT' }
    if ((Get-Item -LiteralPath $Archive).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'RUNTIME_LINK' }
    $source = [IO.Path]::GetFullPath($Archive)
    $target = [IO.Path]::GetFullPath($Destination)
    $package = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\') + '\'
    if ($target.StartsWith('\\') -or $target.Contains('://') -or ($target + '\').StartsWith($package, [StringComparison]::OrdinalIgnoreCase) -or $package.StartsWith($target.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'RUNTIME_BOUNDARY' }
    # Windows ships tar. Work only on a hash-verified private copy; refuse non-file/link entries before extraction.
    $parent = Split-Path -Parent $target
    $ancestor = Get-Item -LiteralPath $parent
    while ($null -ne $ancestor) {
        if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'RUNTIME_PARENT_LINK' }
        $ancestor = $ancestor.Parent
    }
    $temp = Join-Path $parent ('.report-kit-core-' + [Guid]::NewGuid().ToString())
    $null = New-Item -ItemType Directory -Path $temp
    $madeTemp = $true
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule); Set-Acl -LiteralPath $temp -AclObject $acl
    $copy = Join-Path $temp 'core.tar'; Copy-Item -LiteralPath $source -Destination $copy
    if ((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Sha256) { throw 'RUNTIME_CHECKSUM_FAILED' }
    $names = & tar -tf $copy; if ($LASTEXITCODE -ne 0) { throw 'RUNTIME_ARCHIVE' }
    $types = & tar -tvf $copy; if ($LASTEXITCODE -ne 0) { throw 'RUNTIME_ARCHIVE' }
    foreach ($line in $types) { if (-not $line.StartsWith('-')) { throw 'RUNTIME_LINK' } }
    foreach ($name in $names) {
        if ($name -match '(^/|(^|/)\.\.(/|$)|\\|[\x00-\x1f])' -or $name -notmatch '^(python/|site/|manifests/core\.json$|runtime-receipt\.json$)') { throw 'RUNTIME_PATH' }
    }
    $null = New-Item -ItemType Directory -Path $target
    Set-Acl -LiteralPath $target -AclObject $acl
    & tar -xf $copy -C $target
    if ($LASTEXITCODE -ne 0) { throw 'RUNTIME_EXTRACTION' }
    Write-Output 'RUNTIME_CORE_EXTRACTED_NOT_ACTIVATED'
} catch {
    Write-Error 'Не удалось подготовить компонент Report Kit. Код RUNTIME_BOOTSTRAP_FAILED. Передайте этот код поддержке.'
    exit 1
} finally {
    if ($madeTemp -and $copy -and (Test-Path -LiteralPath $copy)) { Remove-Item -LiteralPath $copy }
    if ($madeTemp -and $temp -and (Test-Path -LiteralPath $temp)) { Remove-Item -LiteralPath $temp }
}
