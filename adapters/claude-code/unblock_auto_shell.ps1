# /llm_harness/adapters/claude-code/unblock_auto_shell.ps1
# Terminal-Only emergency exit: removes only Terminal-Only's auto-shell hooks from Claude Code's user settings, with a backup, without needing Python. Run setup.cmd again to put them back.
param([string]$Settings = (Join-Path $env:USERPROFILE '.claude\settings.json'))
$utf8 = New-Object System.Text.UTF8Encoding $false
$marks = 'auto_shell_hook.cmd', 'auto_shell_hook.ps1', 'new_turn_hook.py', 'pretooluse_hook.py'
function Test-Ours($hook) {
    $parts = @([string]$hook.command) + @($hook.args | ForEach-Object { [string]$_ })
    $text = $parts -join ' '
    foreach ($m in $marks) { if ($text -like "*$m*") { return $true } }
    return $false
}
$ocBase = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $env:USERPROFILE '.config' }
$ocPlugin = Join-Path $ocBase 'opencode\plugins\terminal-only\index.ts'
if (Test-Path -LiteralPath $ocPlugin) {
    Move-Item -LiteralPath $ocPlugin -Destination ($ocPlugin + '.disabled') -Force
    Write-Output "OpenCode: the Terminal-Only plugin was switched off ($ocPlugin renamed to .disabled). Restart OpenCode. Run setup.cmd again to switch it back on."
}
if (-not (Test-Path -LiteralPath $Settings)) {
    Write-Output "No Claude Code user settings at $Settings, so there was nothing to remove."
    exit 0
}
try { $s = [IO.File]::ReadAllText($Settings, $utf8) | ConvertFrom-Json }
catch {
    Write-Output "Claude Code's settings at $Settings could not be read, so they were left untouched. Fallback for one run: claude --settings '{""disableAllHooks"": true}'"
    exit 1
}
Copy-Item -LiteralPath $Settings -Destination ($Settings + '.llm_harness-unblock-backup') -Force
$removed = 0
if (($s.PSObject.Properties.Name -contains 'hooks') -and $s.hooks) {
    foreach ($ev in @($s.hooks.PSObject.Properties.Name)) {
        $kept = @()
        foreach ($g in @($s.hooks.$ev)) {
            if ($g.PSObject.Properties.Name -contains 'hooks') {
                $hs = @()
                foreach ($h in @($g.hooks)) { if (Test-Ours $h) { $removed++ } else { $hs += $h } }
                if ($hs.Count -eq 0) { continue }
                $g.hooks = $hs
            }
            $kept += $g
        }
        if ($kept.Count -eq 0) { $s.hooks.PSObject.Properties.Remove($ev) } else { $s.hooks.$ev = $kept }
    }
}
$json = ConvertTo-Json -InputObject $s -Depth 32
[IO.File]::WriteAllText($Settings, $json, $utf8)
Write-Output "Removed $removed Terminal-Only hook(s) from $Settings (backup: $Settings.llm_harness-unblock-backup). Restart Claude Code. Run setup.cmd again to reinstall them."
exit 0
