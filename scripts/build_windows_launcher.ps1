[CmdletBinding()]
param(
    [string]$OutputDirectory = "artifacts",
    [string]$NodeRoot = "",
    [string]$ExpectedNodeVersion = "22.23.1"
)

$ErrorActionPreference = "Stop"
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Join-Path $workspaceRoot "launcher\ClaudeZh.Launcher"
$payloadResource = Join-Path $projectRoot "Payload\payload.zip"
$outputRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $workspaceRoot $OutputDirectory)
)
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "claude-zh-launcher-" + [Guid]::NewGuid().ToString("N")
)

if ([string]::IsNullOrWhiteSpace($NodeRoot)) {
    $NodeRoot = Split-Path -Parent (Get-Command node -ErrorAction Stop).Source
}
$NodeRoot = [System.IO.Path]::GetFullPath($NodeRoot)
$nodeExecutable = Join-Path $NodeRoot "node.exe"
$nodeLicense = Join-Path $NodeRoot "LICENSE"
if (-not (Test-Path -LiteralPath $nodeExecutable -PathType Leaf)) {
    throw "Node executable not found: $nodeExecutable"
}
if (-not (Test-Path -LiteralPath $nodeLicense -PathType Leaf)) {
    throw "Node LICENSE not found: $nodeLicense"
}
$actualNodeVersion = (& $nodeExecutable --version).TrimStart("v")
if ($actualNodeVersion -ne $ExpectedNodeVersion) {
    throw "Expected Node $ExpectedNodeVersion, found $actualNodeVersion."
}

function Copy-WorkspaceItem {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,
        [Parameter(Mandatory = $true)]
        [string]$DestinationRoot
    )
    $source = Join-Path $workspaceRoot $RelativePath
    $destination = Join-Path $DestinationRoot $RelativePath
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
}

function Remove-StagedItem {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$AllowedRoot
    )
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedRoot = [System.IO.Path]::GetFullPath($AllowedRoot).TrimEnd("\") + "\"
    if (-not $resolvedPath.StartsWith(
        $resolvedRoot,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to remove a path outside the staged app: $resolvedPath"
    }
    if (Test-Path -LiteralPath $resolvedPath) {
        Remove-Item -LiteralPath $resolvedPath -Recurse -Force
    }
}

try {
    $payloadRoot = Join-Path $temporaryRoot "payload"
    $appRoot = Join-Path $payloadRoot "app"
    $runtimeRoot = Join-Path $payloadRoot "runtime"
    $publishRoot = Join-Path $temporaryRoot "publish"
    New-Item -ItemType Directory -Force -Path $appRoot, $runtimeRoot | Out-Null

    @(
        "bin",
        "corpus",
        "patchers",
        "LICENSE",
        "README.md",
        "package.json",
        "package-lock.json"
    ) | ForEach-Object {
        Copy-WorkspaceItem -RelativePath $_ -DestinationRoot $appRoot
    }
    Copy-WorkspaceItem `
        -RelativePath "launcher\pty-smoke.cjs" `
        -DestinationRoot $appRoot

    & npm ci `
        --prefix $appRoot `
        --omit=dev `
        --ignore-scripts `
        --no-audit `
        --no-fund
    if ($LASTEXITCODE -ne 0) {
        throw "npm ci failed while preparing the launcher payload."
    }

    $nodePtyRoot = Join-Path $appRoot "node_modules\node-pty"
    $prebuildRoot = Join-Path $nodePtyRoot "prebuilds"
    Get-ChildItem -LiteralPath $prebuildRoot -Directory |
        Where-Object { $_.Name -ne "win32-x64" } |
        ForEach-Object {
            Remove-StagedItem -Path $_.FullName -AllowedRoot $appRoot
        }
    Get-ChildItem -LiteralPath (
        Join-Path $prebuildRoot "win32-x64"
    ) -File -Filter "*.pdb" -Recurse |
        ForEach-Object {
            Remove-StagedItem -Path $_.FullName -AllowedRoot $appRoot
        }
    @(
        "binding.gyp",
        "build",
        "deps",
        "scripts",
        "src",
        "third_party",
        "typings"
    ) | ForEach-Object {
        Remove-StagedItem `
            -Path (Join-Path $nodePtyRoot $_) `
            -AllowedRoot $appRoot
    }
    Get-ChildItem -LiteralPath (Join-Path $nodePtyRoot "lib") -File -Recurse |
        Where-Object {
            $_.Name.EndsWith(".map") -or $_.Name.EndsWith(".test.js")
        } |
        ForEach-Object {
            Remove-StagedItem -Path $_.FullName -AllowedRoot $appRoot
        }

    Copy-Item -LiteralPath $nodeExecutable -Destination (
        Join-Path $runtimeRoot "node.exe"
    )
    Copy-Item -LiteralPath $nodeLicense -Destination (
        Join-Path $runtimeRoot "LICENSE"
    )

    $manifestPath = Join-Path $payloadRoot "manifest.sha256"
    $manifestLines = Get-ChildItem -LiteralPath $payloadRoot -File -Recurse |
        Where-Object { $_.FullName -ne $manifestPath } |
        ForEach-Object {
            $relative = [System.IO.Path]::GetRelativePath(
                $payloadRoot,
                $_.FullName
            ).Replace("\", "/")
            $hash = (
                Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
            ).Hash.ToLowerInvariant()
            "$hash`t$($_.Length)`t$relative"
        } |
        Sort-Object
    [System.IO.File]::WriteAllLines(
        $manifestPath,
        $manifestLines,
        [System.Text.UTF8Encoding]::new($false)
    )

    New-Item -ItemType Directory -Force -Path (
        Split-Path -Parent $payloadResource
    ) | Out-Null
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $payloadRoot,
        $payloadResource,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )

    $packageVersion = (
        Get-Content -Raw -LiteralPath (Join-Path $workspaceRoot "package.json") |
            ConvertFrom-Json
    ).version
    Push-Location $projectRoot
    try {
        & dotnet publish `
            "ClaudeZh.Launcher.csproj" `
            --configuration Release `
            --runtime win-x64 `
            --output $publishRoot `
            "-p:Version=$packageVersion" `
            "-p:InformationalVersion=$packageVersion"
        if ($LASTEXITCODE -ne 0) {
            throw "dotnet publish failed."
        }
    }
    finally {
        Pop-Location
    }

    New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
    $launcherPath = Join-Path $outputRoot "claude-zh-windows-x64.exe"
    Copy-Item -LiteralPath (
        Join-Path $publishRoot "claude-zh-launcher.exe"
    ) -Destination $launcherPath -Force
    $launcherHash = (
        Get-FileHash -LiteralPath $launcherPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    [System.IO.File]::WriteAllText(
        (Join-Path $outputRoot "SHA256SUMS.windows"),
        "$launcherHash  claude-zh-windows-x64.exe`n",
        [System.Text.UTF8Encoding]::new($false)
    )
    [pscustomobject]@{
        launcher = $launcherPath
        version = $packageVersion
        node = $actualNodeVersion
        size = (Get-Item -LiteralPath $launcherPath).Length
        sha256 = $launcherHash
    } | ConvertTo-Json -Compress
}
finally {
    if (Test-Path -LiteralPath $payloadResource) {
        Remove-Item -LiteralPath $payloadResource -Force
    }
    $tempBase = [System.IO.Path]::GetFullPath(
        [System.IO.Path]::GetTempPath()
    ).TrimEnd("\") + "\"
    $resolvedTemporary = [System.IO.Path]::GetFullPath($temporaryRoot)
    if (
        $resolvedTemporary.StartsWith(
            $tempBase,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -and
        (Split-Path -Leaf $resolvedTemporary).StartsWith(
            "claude-zh-launcher-",
            [System.StringComparison]::OrdinalIgnoreCase
        ) -and
        (Test-Path -LiteralPath $resolvedTemporary)
    ) {
        Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force
    }
}
