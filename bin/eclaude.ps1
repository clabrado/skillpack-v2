# eclaude.ps1 — open a brand-new Claude Code session in its own Windows terminal.
#
# Windows counterpart to eclaude.sh.
#
#   .\eclaude.ps1 [-Cwd <dir>] [-Name <name>] [-DryRun]
#
# IMPORTANT: latch does not run on Windows. Its supervisor needs the Unix
# terminal interface (termios/tty/fcntl), so sessions started here are NOT
# watchable or steerable from another window — /steer and /drive will not work
# against them. The session itself is completely normal.

param(
    [string]$Cwd  = $HOME,
    [string]$Name = "",
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Cwd -PathType Container)) {
    Write-Error "eclaude: no such directory: $Cwd"
    exit 1
}

function Find-Bin($names) {
    foreach ($n in $names) {
        $cmd = Get-Command $n -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        $local = Join-Path $HOME ".local\bin\$n.exe"
        if (Test-Path -LiteralPath $local) { return $local }
    }
    return $null
}

$claude = Find-Bin @('claude-stable', 'claude')
if (-not $claude) {
    Write-Error "eclaude: no 'claude' or 'claude-stable' on PATH or in ~\.local\bin"
    exit 1
}

# $Name is accepted so the same call shape works on both platforms, but it only
# means something to latch — say so rather than silently ignoring it.
if ($Name) {
    Write-Warning "eclaude: -Name is a latch session name and latch does not run on Windows; ignoring it."
}

$command = "cd `"$Cwd`"; & `"$claude`" --dangerously-skip-permissions"

if ($DryRun) {
    Write-Output $command
    exit 0
}

# Windows Terminal if present (it is the default on Windows 11), otherwise a
# plain PowerShell window. Never silently do nothing.
$wt = Get-Command wt -ErrorAction SilentlyContinue
if ($wt) {
    Start-Process wt -ArgumentList @(
        'new-tab', '--startingDirectory', $Cwd,
        'powershell', '-NoExit', '-Command', "& `"$claude`" --dangerously-skip-permissions"
    )
    Write-Output "eclaude: opened a new Windows Terminal tab in $Cwd"
} else {
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-Command', $command
    )
    Write-Output "eclaude: opened a new PowerShell window in $Cwd"
}

Write-Output "eclaude: this session is NOT watchable from another window (latch is Unix-only)."
