# /llm_harness/adapters/claude-code/auto_shell_hook.ps1
# Terminal-Only auto-shell hook launcher for Claude Code (both hooks run through it). It finds the Terminal-Only project from the hook's working folder without Python: outside such a project it exits at once and says nothing; inside one it hands the hook input to the Python hook, and when Python cannot be found, cannot start or fails, it blocks only that project.
param([string]$Mode = 'pretool')
$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$raw = [Console]::In.ReadToEnd()

function Find-HarnessRoot([string]$start) {
    $homeDir = [IO.Path]::GetFullPath($env:USERPROFILE).TrimEnd('\')
    $cur = [IO.Path]::GetFullPath($start)
    while ($cur) {
        $mem = Join-Path $cur '.llm_harness'
        $isMem = (Test-Path -LiteralPath $mem -PathType Container) -and -not (Test-Path -LiteralPath (Join-Path $mem 'harness.py'))
        $isState = Test-Path -LiteralPath (Join-Path $cur '.git\llm_harness') -PathType Container
        if (($isMem -or $isState) -and ($cur.TrimEnd('\') -ne $homeDir)) { return $cur }
        $parent = [IO.Path]::GetDirectoryName($cur)
        if (-not $parent -or $parent -eq $cur) { return $null }
        $cur = $parent
    }
    return $null
}

$root = $null
# Comment (decision): when the project cannot even be identified, nothing is blocked, so a broken hook never locks the user out of unrelated projects
try {
    $cwd = $null
    try { $cwd = ($raw | ConvertFrom-Json).cwd } catch { }
    if (-not $cwd) { $cwd = (Get-Location).Path }
    $root = Find-HarnessRoot $cwd
} catch { exit 0 }
if (-not $root) { exit 0 }

function Block([string]$why) {
    if ($Mode -eq 'prompt') {
        [Console]::Error.WriteLine("llm_harness: $why, so this prompt is held back in the Terminal-Only project $root; other projects are not affected.")
        exit 2
    }
    $reason = "Terminal-Only auto-shell: $why, so tools are blocked in this project ($root) until that is fixed; other projects are not affected. Emergency exit: unblock_auto_shell.cmd in the harness folder."
    $out = ConvertTo-Json -Compress -Depth 5 -InputObject @{ hookSpecificOutput = @{ hookEventName = 'PreToolUse'; permissionDecision = 'deny'; permissionDecisionReason = $reason } }
    [Console]::Out.Write($out)
    exit 0
}

$hook = Join-Path $PSScriptRoot $(if ($Mode -eq 'prompt') { 'new_turn_hook.py' } else { 'pretooluse_hook.py' })
$pyName = if ($env:LLM_HARNESS_PYTHON) { $env:LLM_HARNESS_PYTHON } else { 'python' }
$py = Get-Command $pyName -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $py) { Block "Python ($pyName) could not be found" }
if (-not (Test-Path -LiteralPath $hook)) { Block "the hook script $hook is missing" }
try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $py.Source
    $psi.Arguments = '"' + $hook + '"'
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = $utf8
    $psi.StandardErrorEncoding = $utf8
    $p = [System.Diagnostics.Process]::Start($psi)
    $bytes = $utf8.GetBytes($raw)
    $p.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
    $p.StandardInput.Close()
    $stdout = $p.StandardOutput.ReadToEnd()
    $stderr = $p.StandardError.ReadToEnd()
    $p.WaitForExit()
} catch { Block ("Python could not start: " + $_.Exception.Message) }
# Comment (workaround): Windows may answer 'python' with a Store shortcut that exits with an error instead of running Python; any exit other than 0 or 2 counts as Python failing
if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 2) { Block ("the Python hook failed (exit " + $p.ExitCode + ")") }
if ($Mode -ne 'prompt' -and $p.ExitCode -eq 0 -and -not $stdout.Trim()) { Block "the Python hook gave no decision" }
[Console]::Out.Write($stdout)
if ($stderr) { [Console]::Error.Write($stderr) }
exit $p.ExitCode
