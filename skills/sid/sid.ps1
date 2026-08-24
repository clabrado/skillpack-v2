# /sid — print this session's id, transcript path, and related identifiers.
# Windows counterpart to sid.sh. Same rule: the authoritative source is
# CLAUDE_CODE_SESSION_ID, which Claude Code exports into every shell it spawns.
# Never guess from "newest .jsonl" — with concurrent sessions, modification
# time is not an identifier.

$ErrorActionPreference = 'Continue'

$sid = $env:CLAUDE_CODE_SESSION_ID
$projects = Join-Path $HOME '.claude\projects'

if ([string]::IsNullOrEmpty($sid)) {
    Write-Output "SESSION ID:  unavailable — CLAUDE_CODE_SESSION_ID is not set in this shell."
    Write-Output "             (Not running under Claude Code, or the variable was stripped.)"
    exit 1
}

Write-Output "SESSION ID:  $sid"

# Transcript lives at ~/.claude/projects/<slug>/<sid>.jsonl, where <slug> is the
# launch directory with separators replaced by '-'. The launch directory is not
# necessarily the current one, so try the derived path first, then search.
$slug = (Get-Location).Path -replace '[\\/:]', '-'
$candidate = Join-Path $projects (Join-Path $slug "$sid.jsonl")
$transcript = $null

if (Test-Path -LiteralPath $candidate) {
    $transcript = $candidate
} elseif (Test-Path -LiteralPath $projects) {
    $found = Get-ChildItem -LiteralPath $projects -Recurse -Depth 1 -Filter "$sid.jsonl" -File -ErrorAction SilentlyContinue |
             Select-Object -First 1
    if ($found) { $transcript = $found.FullName }
}

if ($transcript -and (Test-Path -LiteralPath $transcript)) {
    $item  = Get-Item -LiteralPath $transcript
    $lines = (Get-Content -LiteralPath $transcript -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
    $kb    = [math]::Round($item.Length / 1KB, 1)
    $mtime = $item.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')
    Write-Output "TRANSCRIPT:  $transcript"
    Write-Output "             $lines lines, ${kb}K, last written $mtime"
} else {
    Write-Output "TRANSCRIPT:  not found on disk for $sid"
    Write-Output "             searched $projects (depth 2). A brand-new session may not"
    Write-Output "             have been flushed to disk yet — this is a measured absence,"
    Write-Output "             not proof the session is unrecorded."
}

# Optional extras — printed only when actually present, never invented.
if ($env:CLAUDE_CODE_BRIDGE_SESSION_ID) {
    Write-Output "WEB SESSION: https://claude.ai/code/$($env:CLAUDE_CODE_BRIDGE_SESSION_ID)"
}
if ($env:CLAUDE_PID) { Write-Output "PID:         $($env:CLAUDE_PID)" }
if ($env:CLAUDE_CODE_CHILD_SESSION -eq '1') {
    Write-Output "NOTE:        this is a CHILD session (spawned by another Claude session)."
}
exit 0
