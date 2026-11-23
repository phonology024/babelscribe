#!/usr/bin/env bash
# CI checks of the installed app on macOS and Linux (check_install.ps1 does the same for Windows).
#
#   check_install.sh install-macos   out/babelscribe-macos-arm64.dmg      # mount, copy to /Applications, check it
#   check_install.sh install-deb     out/babelscribe-linux-x64.deb        # apt installs it (and what it depends on)
#   check_install.sh extract-appimage out/babelscribe-linux-x64.AppImage  # unpack it to look inside
#   check_install.sh launch-macos                                         # starts the app, waits, quits it like Cmd+Q
#   check_install.sh launch-linux COMMAND...                              # the same under Xvfb, closed like a window
#   check_install.sh no-leftovers                                         # no engine, whisper-cli or ffmpeg running
#
# Each install step writes `engine=<path>` to $GITHUB_OUTPUT: the engine inside the installed app, which the next
# steps run a real transcription with.
set -euo pipefail

ok() { echo "ok: $*"; }
fail() { echo "FAILED: $*" >&2; exit 1; }
need() { [[ -e "$1" ]] || fail "missing: $1"; ok "$1"; }
output() { [[ -z "${GITHUB_OUTPUT:-}" ]] || echo "$1=$2" >> "$GITHUB_OUTPUT"; }

leftovers() {
  # -f: the name of a program the engine started is a path (ffmpeg comes from imageio-ffmpeg: ffmpeg-<os>-<arch>-vX)
  pgrep -fl 'babelscribe-engine|whisper-cli|ffmpeg-(linux|macos)' || true
}

no_leftovers() {
  for _ in $(seq 1 20); do
    [[ -z "$(leftovers)" ]] && { ok "no babelscribe-engine, whisper-cli or ffmpeg is running"; return 0; }
    sleep 0.5
  done
  leftovers >&2
  fail "the engine or a program it started is still running"
}

installed_engine_checks() {   # $1 = the engine program, $2 = the folder that holds licenses/
  need "$1"
  need "$(dirname "$1")/_internal/base_library.zip"
  need "$2/licenses/LICENSE.txt"
  need "$2/licenses/THIRD-PARTY-app.md"
  [[ -x "$1" ]] || fail "$1 is not executable"
  echo "engine version: $("$1" --version)"
  output engine "$1"
}

step="${1:?step}"; shift || true
case "$step" in
  install-macos)
    dmg="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
    mnt="$(mktemp -d)"
    hdiutil attach -nobrowse -readonly -mountpoint "$mnt" "$dmg" > /dev/null
    ls -la "$mnt"
    app=/Applications/babelscribe.app
    rm -rf "$app"
    cp -R "$mnt/babelscribe.app" /Applications/
    hdiutil detach "$mnt" -quiet
    need "$app/Contents/MacOS/babelscribe"
    installed_engine_checks "$app/Contents/Resources/engine/babelscribe-engine" "$app/Contents/Resources"
    # Apple Silicon refuses an app with no valid signature ("is damaged"); ad-hoc is the signature without a certificate
    codesign --verify --deep --strict --verbose=2 "$app"
    details="$(codesign -dv "$app" 2>&1)"
    echo "$details"
    [[ "$details" == *"Signature=adhoc"* ]] || fail "the app is not ad-hoc signed"
    ok "valid ad-hoc signature"
    /usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$app/Contents/Info.plist"
    lipo -archs "$app/Contents/MacOS/babelscribe"
    ;;

  install-deb)
    deb="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
    sudo apt-get install -y "$deb"
    dpkg -L babelscribe | head -40
    engine="$(dpkg -L babelscribe | grep '/engine/babelscribe-engine$')"
    [[ -n "$engine" ]] || fail "the package has no engine"
    # not /usr/bin/babelscribe: that name is the command line (pip), which an app must not shadow on the PATH
    need /usr/bin/babelscribe-desktop
    [[ -n "$(dpkg -L babelscribe | grep '^/usr/share/applications/.*[.]desktop$')" ]] || fail "no .desktop file"
    ok "an application menu entry"
    installed_engine_checks "$engine" "$(dirname "$(dirname "$engine")")"
    missing="$(ldd /usr/bin/babelscribe-desktop | grep 'not found' || true)"
    [[ -z "$missing" ]] || fail "the app needs libraries that are not installed: $missing"
    ok "every library the app needs is installed"
    ;;

  extract-appimage)
    image="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
    chmod +x "$image"
    rm -rf squashfs-root
    "$image" --appimage-extract > /dev/null
    engine="$(find squashfs-root -path '*/engine/babelscribe-engine' | head -1)"
    [[ -n "$engine" ]] || fail "the AppImage has no engine"
    installed_engine_checks "$engine" "$(dirname "$(dirname "$engine")")"
    ;;

  launch-macos)
    open -n /Applications/babelscribe.app
    sleep 15
    pgrep -x babelscribe > /dev/null || fail "the app is not running 15 s after it was opened"
    ok "the app is still running after 15 s"
    screencapture -x "${SHOT:-launch-macos.png}" || true
    # what Cmd+Q and Quit in the Dock do: ask the app to quit
    osascript -e 'tell application "babelscribe" to quit'
    for _ in $(seq 1 30); do pgrep -x babelscribe > /dev/null || break; sleep 0.5; done
    pgrep -x babelscribe > /dev/null && fail "the app did not quit when asked to"
    ok "the app quit when asked to"
    no_leftovers
    ;;

  launch-linux)
    export DISPLAY=:99
    Xvfb :99 -screen 0 1280x800x24 > xvfb.log 2>&1 &
    xvfb=$!
    trap 'kill $xvfb 2>/dev/null || true' EXIT
    # wait until the X server answers: a program started before that cannot open the display (no fixed sleeps)
    for _ in $(seq 1 60); do xdpyinfo -display :99 > /dev/null 2>&1 && break; sleep 0.5; done
    xdpyinfo -display :99 > /dev/null 2>&1 || { cat xvfb.log; fail "the X server (Xvfb) does not answer after 30 s"; }
    ok "the X server answers"
    eval "$(dbus-launch --sh-syntax)"       # a session bus, as on a desktop
    openbox > openbox.log 2>&1 &            # a window manager: closing a window needs one to ask the app politely
    for _ in $(seq 1 60); do wmctrl -m > /dev/null 2>&1 && break; sleep 0.5; done
    wmctrl -m > /dev/null 2>&1 || { cat openbox.log; fail "no window manager is running after 30 s"; }
    ok "the window manager is running: $(wmctrl -m | head -1)"
    export LIBGL_ALWAYS_SOFTWARE=1
    "$@" > app.log 2>&1 &
    app=$!
    diagnose() {
      echo "--- windows (wmctrl -l):"; wmctrl -l || true
      echo "--- X tree:"; xwininfo -root -tree | head -40 || true
      echo "--- processes:"; ps -eo pid,ppid,stat,args | grep -E "babelscribe|WebKit|openbox|Xvfb" | grep -v grep || true
      echo "--- app.log:"; tail -50 app.log || true
      echo "--- openbox.log:"; tail -20 openbox.log || true
    }
    sleep 15
    kill -0 "$app" 2> /dev/null || { diagnose; fail "the app is not running 15 s after it was started"; }
    ok "the app is still running after 15 s"
    import -window root "${SHOT:-launch-linux.png}" 2> /dev/null || true
    # the window: wait for it, it may take the web view a few seconds more
    for _ in $(seq 1 30); do wmctrl -l | grep -q . && break; sleep 1; done
    wmctrl -l | grep -q . || { diagnose; fail "the app is running but has no window"; }
    ok "the app has a window: $(wmctrl -l | head -1)"
    import -window root "${SHOT:-launch-linux.png}" 2> /dev/null || true
    wmctrl -c babelscribe || { diagnose; fail "no window called babelscribe"; }
    for _ in $(seq 1 30); do kill -0 "$app" 2> /dev/null || break; sleep 0.5; done
    kill -0 "$app" 2> /dev/null && fail "the app did not quit when its window was closed"
    ok "the app quit when its window was closed"
    no_leftovers
    ;;

  no-leftovers) no_leftovers ;;
  *) fail "unknown step $step" ;;
esac
