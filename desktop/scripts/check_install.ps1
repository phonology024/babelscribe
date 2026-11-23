# CI checks of the Windows installer (see .github/workflows/desktop.yml).
#
#   check_install.ps1 -Step install   -Setup babelscribe-setup.exe   # silent install, then what it wrote
#   check_install.ps1 -Step launch                                   # the installed app starts and stays up
#   check_install.ps1 -Step uninstall                                # silent uninstall removes everything
#   check_install.ps1 -Step oneclick  -Setup babelscribe-setup.exe -Shots shots
#       # a plain double-click run: installs with no questions and starts the app by itself; screenshots in -Shots
param(
  [Parameter(Mandatory)] [ValidateSet("install", "launch", "uninstall", "oneclick")] [string] $Step,
  [string] $Setup,
  [string] $Shots = "shots"
)
$ErrorActionPreference = "Stop"
$dir = Join-Path $env:LOCALAPPDATA "babelscribe"
$app = Join-Path $dir "babelscribe.exe"
$lnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\babelscribe.lnk"
$desk = Join-Path ([Environment]::GetFolderPath("Desktop")) "babelscribe.lnk"
$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\babelscribe"

function Assert($ok, $what) { if (-not $ok) { throw "FAILED: $what" } else { Write-Host "ok: $what" } }

function Check-Installed {
  Assert (Test-Path $app) "the app is at $app"
  Assert (Test-Path (Join-Path $dir "babelscribe-engine.exe")) "the engine is next to it"
  Assert (Test-Path (Join-Path $dir "_internal\base_library.zip")) "the engine's _internal folder is there"
  Assert (Test-Path (Join-Path $dir "babelscribe-mcp.exe")) "babelscribe-mcp.exe (the server AI apps start) is next to the engine"
  Assert (Test-Path (Join-Path $dir "licenses\LICENSE.txt")) "the licences are in the install folder"
  Assert (Test-Path $lnk) "Start menu shortcut $lnk"
  $target = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk).TargetPath
  Assert ($target -eq $app) "the shortcut starts $app (it starts $target)"
  $reg = Get-ItemProperty $key
  Assert ($reg.DisplayName -eq "babelscribe") "Apps list name is babelscribe ($($reg.DisplayName))"
  Assert ($reg.Publisher -eq "babelscribe") "publisher is babelscribe ($($reg.Publisher))"
  Assert ($reg.DisplayIcon -like "*\babelscribe.exe*") "Apps list icon is the app's ($($reg.DisplayIcon))"
  Assert (Test-Path ($reg.UninstallString.Trim('"'))) "uninstaller at $($reg.UninstallString)"
}

function Wait-Gone {
  for ($i = 0; $i -lt 120 -and (Test-Path $dir); $i++) { Start-Sleep -Milliseconds 500 }
  Assert (-not (Test-Path $dir)) "the install folder is gone"
  Assert (-not (Test-Path $key)) "the Apps list entry is gone"
  Assert (-not (Test-Path $lnk)) "the Start menu shortcut is gone"
  Assert (-not (Test-Path $desk)) "the desktop shortcut is gone"
}

function Snap($path) {
  Add-Type -AssemblyName System.Windows.Forms, System.Drawing
  $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
  $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
  $g.Dispose(); $bmp.Dispose()
}

switch ($Step) {
  "install" {
    $p = Start-Process $Setup -ArgumentList "/S" -Wait -PassThru
    Assert ($p.ExitCode -eq 0) "silent install exit code 0 ($($p.ExitCode))"
    Check-Installed
    Assert (-not (Get-Process babelscribe -ErrorAction SilentlyContinue)) "a silent install does not start the app"
    & (Join-Path $dir "babelscribe-engine.exe") --version
  }
  "launch" {
    $p = Start-Process $app -PassThru
    Start-Sleep -Seconds 15
    Assert (-not $p.HasExited) "the app is still running after 15 s"
    Stop-Process -Id $p.Id -Force
    Start-Sleep -Seconds 2
  }
  "uninstall" {
    $un = (Get-ItemProperty $key).UninstallString.Trim('"')
    Start-Process $un -ArgumentList "/S" -Wait   # returns at once: NSIS runs the real uninstaller from a temp copy
    Wait-Gone
  }
  "oneclick" {
    New-Item -ItemType Directory -Force $Shots | Out-Null
    $p = Start-Process $Setup -PassThru            # what a double-click does: no arguments
    $started = $null
    for ($i = 0; $i -lt 240; $i++) {               # up to 2 minutes
      try { Snap (Join-Path $Shots ("install-{0:D3}.png" -f $i)) } catch { if ($i -eq 0) { Write-Host "no screenshots: $_" } }
      if (-not $started -and (Get-Process babelscribe -ErrorAction SilentlyContinue)) { $started = $i }
      if ($started -and $i -ge $started + 16) { break }   # a few seconds of the app window too
      Start-Sleep -Milliseconds 500
    }
    Assert $p.HasExited "the installer closed by itself"
    Assert ($p.ExitCode -eq 0) "installer exit code 0 ($($p.ExitCode))"
    Assert ($null -ne $started) "the app started by itself after the install"
    Check-Installed
    Get-Process babelscribe -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
    # keep every 4th frame and the last ten: enough to see the progress page and the app
    $all = Get-ChildItem $Shots -Filter install-*.png | Sort-Object Name
    for ($j = 0; $j -lt $all.Count - 10; $j++) { if ($j % 4 -ne 0) { Remove-Item $all[$j].FullName } }
  }
}
