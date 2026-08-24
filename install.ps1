# install.ps1 — install skillpack v2 into %USERPROFILE%\.claude\skills on Windows.
#
# Refuses to overwrite. If a skill of that name already exists this stops and
# shows what differs — moving your copy aside is your decision. Nothing is
# ever deleted.
#
# /steer and /drive are NOT installed on Windows: they need latch, whose
# supervisor requires the Unix terminal interface. Installing a skill that
# cannot work would be worse than leaving it out.

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$src  = Join-Path $root 'skills'
$dest = if ($env:CLAUDE_SKILLS_DIR) { $env:CLAUDE_SKILLS_DIR } else { Join-Path $HOME '.claude\skills' }

$skills        = @('turbo', 'standup', 'readout', 'sid', 'eclaude')
$unixOnly      = @('steer', 'drive')

if (-not (Test-Path -LiteralPath $src)) {
    Write-Error "error: no skills\ directory beside this script"
    exit 1
}
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$conflicts = 0
foreach ($s in $skills) {
    $target = Join-Path $dest $s
    if (Test-Path -LiteralPath $target) {
        Write-Output "SKIP  $s - already exists at $target"
        $srcHashes = Get-ChildItem -Recurse -File -LiteralPath (Join-Path $src $s) |
                     ForEach-Object { (Get-FileHash $_.FullName).Hash } | Sort-Object
        $dstHashes = Get-ChildItem -Recurse -File -LiteralPath $target |
                     ForEach-Object { (Get-FileHash $_.FullName).Hash } | Sort-Object
        if (($srcHashes -join ',') -ne ($dstHashes -join ',')) {
            Write-Output "      and it DIFFERS from this pack's copy - reconcile it yourself"
        } else {
            Write-Output "      (identical - nothing to do)"
        }
        $conflicts++
        continue
    }
    Copy-Item -Recurse -LiteralPath (Join-Path $src $s) -Destination $target
    Write-Output "OK    $s -> $target"
}

Write-Output ""
Write-Output "NOT installed on Windows: $($unixOnly -join ', ')"
Write-Output "  These need latch, and latch's supervisor requires the Unix terminal"
Write-Output "  interface (termios/tty/fcntl). They cannot work here, so they are not"
Write-Output "  installed rather than installed and silently doing nothing."

if ($conflicts -gt 0) {
    Write-Output ""
    Write-Output "$conflicts skill(s) left untouched. Move your copy aside and re-run to install those."
}

Write-Output ""
if (-not $env:SKILLPACK_NOTIFY_TO) {
    Write-Output "NOTE: SKILLPACK_NOTIFY_TO is not set, so /turbo and /standup will print their"
    Write-Output "      final report to the console only and say that no message was sent."
    Write-Output "      There is no iMessage on Windows - point SKILLPACK_NOTIFY_BIN at any"
    Write-Output "      command taking: <bin> send --to <recipient> --service imessage --text <body>"
    Write-Output "      (a one-line wrapper around ntfy, Pushover, or a Teams/Slack webhook)."
}
Write-Output "Done. In Claude Code: /turbo, /standup, /readout, /sid, /eclaude"
