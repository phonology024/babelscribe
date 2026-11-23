// babelscribe desktop: a window around the babelscribe command line.
//
// The engine is babelscribe-engine, the PyInstaller build of the Python CLI (packaging/standalone). It is run with
// --progress-json and its output lines are handed to the window as they come; all the transcription logic stays in
// Python. This file only starts and stops it and does the few things a web page cannot: file picker, file sizes,
// reading the written subtitles back, opening files and folders.
//
// Where the engine is, and how it is started and stopped, differs by system:
//   Windows      a Tauri sidecar (babelscribe-engine.exe next to the app, its _internal folder beside it), run through
//                the shell plugin and stopped with `taskkill /T`.
//   macOS, Linux the whole engine folder is a resource (<resources>/engine/babelscribe-engine with its _internal
//                folder), because a sidecar and the resources are in different folders in a .app, an AppImage and a
//                .deb. It is run as the leader of its own process group; stopping it signals the group, so whisper-cli
//                and ffmpeg end with it.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::Path;
#[cfg(unix)]
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use serde::Serialize;
use tauri::ipc::Channel;
use tauri::{AppHandle, Manager, RunEvent, State, Theme, WebviewWindow};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;
#[cfg(windows)]
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
#[cfg(windows)]
use tauri_plugin_shell::ShellExt;

/// What stops a running engine: its sidecar handle on Windows, its process group on macOS and Linux.
#[cfg(windows)]
type Running = CommandChild;
#[cfg(unix)]
struct Running {
    /// The engine's pid, which is also the id of its process group (it was started as the group's leader).
    pgid: i32,
}

/// The running engine, if any, with the number of its run (a stopped run's late exit must not clear a newer one).
#[derive(Default)]
struct Engine {
    child: Mutex<Option<(u64, Running)>>,
    runs: AtomicU64,
}

#[derive(Clone, Serialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
enum EngineMessage {
    Stdout { line: String },
    Stderr { line: String },
    Exit { code: Option<i32> },
    Error { message: String },
}

fn text(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).trim_end_matches(['\r', '\n']).to_string()
}

#[tauri::command]
fn run_engine(app: AppHandle, engine: State<'_, Engine>, args: Vec<String>, on_event: Channel<EngineMessage>) -> Result<(), String> {
    let mut slot = engine.child.lock().map_err(|e| e.to_string())?;
    if slot.is_some() {
        return Err("babelscribe is already running".into());
    }
    // The slot stays locked until the run is in it: an engine that ends at once must find its own entry to clear.
    let run = engine.runs.fetch_add(1, Ordering::SeqCst) + 1;
    let running = start_engine(&app, args, on_event, run)?;
    *slot = Some((run, running));
    Ok(())
}

/// Called when run `run` has ended: empties the slot, unless a newer run is already in it.
fn finished(app: &AppHandle, run: u64) {
    if let Ok(mut slot) = app.state::<Engine>().child.lock() {
        if matches!(slot.as_ref(), Some((r, _)) if *r == run) {
            *slot = None;
        }
    }
}

#[cfg(windows)]
fn start_engine(app: &AppHandle, args: Vec<String>, on_event: Channel<EngineMessage>, run: u64) -> Result<Running, String> {
    let (mut rx, child) = app
        .shell()
        .sidecar("babelscribe-engine")
        .map_err(|e| e.to_string())?
        .args(args)
        .spawn()
        .map_err(|e| e.to_string())?;
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            let message = match event {
                CommandEvent::Stdout(b) => EngineMessage::Stdout { line: text(&b) },
                CommandEvent::Stderr(b) => EngineMessage::Stderr { line: text(&b) },
                CommandEvent::Error(e) => EngineMessage::Error { message: e },
                CommandEvent::Terminated(p) => {
                    finished(&app, run);
                    EngineMessage::Exit { code: p.code }
                }
                _ => continue,
            };
            let _ = on_event.send(message);
        }
    });
    Ok(child)
}

/// The engine program inside the app's resources (see the header: macOS, Linux).
#[cfg(unix)]
fn engine_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().resource_dir().map_err(|e| e.to_string())?;
    let exe = dir.join("engine").join("babelscribe-engine");
    if exe.is_file() {
        Ok(exe)
    } else {
        Err(format!("the engine is missing from this installation: {}", exe.display()))
    }
}

/// Hands every line of a stream (without its line end) to `each`, until the stream ends.
#[cfg(unix)]
fn lines<R: std::io::Read>(stream: R, mut each: impl FnMut(String)) {
    use std::io::BufRead;
    let mut reader = std::io::BufReader::new(stream);
    let mut buf = Vec::new();
    loop {
        buf.clear();
        match reader.read_until(b'\n', &mut buf) {
            Ok(0) | Err(_) => break,
            Ok(_) => each(text(&buf)),
        }
    }
}

/// Reads one of the engine's output streams on its own thread and sends each line to the window.
#[cfg(unix)]
fn forward<R: std::io::Read + Send + 'static>(
    stream: Option<R>,
    on_event: Channel<EngineMessage>,
    message: fn(String) -> EngineMessage,
) -> std::thread::JoinHandle<()> {
    std::thread::spawn(move || {
        if let Some(stream) = stream {
            lines(stream, |line| {
                let _ = on_event.send(message(line));
            });
        }
    })
}

/// Starts the engine with its output piped, as the leader of a new process group: signalling the group reaches
/// whisper-cli and ffmpeg too. The group's id is the child's pid.
#[cfg(unix)]
fn spawn_in_own_group(exe: &Path, args: &[String]) -> std::io::Result<std::process::Child> {
    use std::os::unix::process::CommandExt;
    use std::process::{Command, Stdio};

    let mut command = Command::new(exe);
    command
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .process_group(0);
    if std::env::var_os("APPIMAGE").is_some() {
        // An AppImage points the library path at its own libraries (WebKitGTK, GTK ...). The engine and the programs
        // it starts bring theirs, or use the system's, and must not load those.
        command.env_remove("LD_LIBRARY_PATH");
    }
    command.spawn()
}

#[cfg(unix)]
fn start_engine(app: &AppHandle, args: Vec<String>, on_event: Channel<EngineMessage>, run: u64) -> Result<Running, String> {
    let exe = engine_path(app)?;
    let mut child = spawn_in_own_group(&exe, &args).map_err(|e| format!("could not start {}: {e}", exe.display()))?;
    let pgid = child.id() as i32;
    let out = forward(child.stdout.take(), on_event.clone(), |line| EngineMessage::Stdout { line });
    let err = forward(child.stderr.take(), on_event.clone(), |line| EngineMessage::Stderr { line });

    let app = app.clone();
    std::thread::spawn(move || {
        let status = child.wait();
        // The engine is gone; anything of its group still running (a whisper-cli it did not wait for) goes with it.
        signal_group(pgid, libc::SIGKILL);
        let _ = out.join();
        let _ = err.join();
        finished(&app, run);
        let _ = on_event.send(EngineMessage::Exit { code: status.ok().and_then(|s| s.code()) });
    });
    Ok(Running { pgid })
}

/// Sends `signal` to every process of the group. A group with nothing left in it is not an error.
#[cfg(unix)]
fn signal_group(pgid: i32, signal: i32) {
    if pgid > 1 {
        // SAFETY: kill(2) with a negative pid addresses a process group; it touches no memory of ours.
        unsafe {
            libc::kill(-pgid, signal);
        }
    }
}

#[cfg(unix)]
fn group_is_running(pgid: i32) -> bool {
    // SAFETY: as above; signal 0 only checks that the group has a process (it fails with ESRCH when it has none).
    pgid > 1 && unsafe { libc::kill(-pgid, 0) } == 0
}

/// SIGTERM to the group, then SIGKILL for whatever is still there after about two seconds.
#[cfg(unix)]
fn terminate_group(pgid: i32) {
    signal_group(pgid, libc::SIGTERM);
    for _ in 0..20 {
        if !group_is_running(pgid) {
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
    signal_group(pgid, libc::SIGKILL);
}

/// Ends the engine and everything it started: whisper-cli and ffmpeg are its child processes, and ending only
/// babelscribe-engine would leave them running on the GPU.
fn stop_engine(engine: &Engine) {
    let taken = engine.child.lock().ok().and_then(|mut slot| slot.take());
    if let Some((_, running)) = taken {
        end(running);
    }
}

#[cfg(windows)]
fn end(child: Running) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    let _ = std::process::Command::new("taskkill")
        .args(["/PID", &child.pid().to_string(), "/T", "/F"])
        .creation_flags(CREATE_NO_WINDOW)
        .status();
    let _ = child.kill();
}

#[cfg(unix)]
fn end(running: Running) {
    terminate_group(running.pgid);
}

#[tauri::command]
async fn cancel_engine(engine: State<'_, Engine>) -> Result<(), String> {
    stop_engine(&engine);
    Ok(())
}

#[tauri::command]
async fn pick_file(app: AppHandle) -> Option<String> {
    app.dialog()
        .file()
        .set_title("Choose a video or audio file")
        .add_filter("Video or audio", &[
            "mp4", "mkv", "mov", "avi", "webm", "m4v", "mp3", "wav", "m4a", "aac", "flac", "ogg", "opus", "wma",
        ])
        .add_filter("All files", &["*"])
        .blocking_pick_file()
        .and_then(|p| p.into_path().ok())
        .map(|p| p.to_string_lossy().into_owned())
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct FileInfo {
    exists: bool,
    is_file: bool,
    size: u64,
}

#[tauri::command]
fn file_info(path: String) -> FileInfo {
    match std::fs::metadata(&path) {
        Ok(m) => FileInfo { exists: true, is_file: m.is_file(), size: m.len() },
        Err(_) => FileInfo { exists: false, is_file: false, size: 0 },
    }
}

/// Only the kinds of file babelscribe writes; the window has no reason to read or launch anything else.
fn written_by_babelscribe(path: &str) -> Result<(), String> {
    let ext = Path::new(path)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if ["srt", "vtt", "txt", "json", "ass"].contains(&ext.as_str()) {
        Ok(())
    } else {
        Err(format!("not a subtitle or transcript file: {path}"))
    }
}

#[tauri::command]
async fn read_text(path: String) -> Result<String, String> {
    written_by_babelscribe(&path)?;
    let size = std::fs::metadata(&path).map_err(|e| e.to_string())?.len();
    if size > 64 * 1024 * 1024 {
        return Err(format!("{path} is too large to show"));
    }
    let bytes = std::fs::read(&path).map_err(|e| e.to_string())?;
    Ok(String::from_utf8_lossy(&bytes).into_owned())
}

#[tauri::command]
fn open_path(app: AppHandle, path: String) -> Result<(), String> {
    written_by_babelscribe(&path)?;
    app.opener().open_path(path, None::<&str>).map_err(|e| e.to_string())
}

#[tauri::command]
fn show_in_folder(app: AppHandle, path: String) -> Result<(), String> {
    app.opener().reveal_item_in_dir(path).map_err(|e| e.to_string())
}

/// The title bar follows the window's light/dark choice; None follows Windows.
#[tauri::command]
fn set_theme(window: WebviewWindow, theme: Option<String>) -> Result<(), String> {
    let theme = match theme.as_deref() {
        Some("dark") => Some(Theme::Dark),
        Some("light") => Some(Theme::Light),
        _ => None,
    };
    window.set_theme(theme).map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(Engine::default())
        .invoke_handler(tauri::generate_handler![
            run_engine,
            cancel_engine,
            pick_file,
            file_info,
            read_text,
            open_path,
            show_in_folder,
            set_theme
        ])
        .build(tauri::generate_context!())
        .expect("error while building the babelscribe window")
        .run(|app, event| {
            // Closing the window, Quit from the menu or the Dock (macOS), Alt+F4 ...: none of them may leave
            // whisper-cli running. Stopping twice is harmless: the second finds nothing to stop.
            if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
                stop_engine(&app.state::<Engine>());
            }
        });
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::io::Read;
    use std::os::unix::process::CommandExt;
    use std::process::{Child, Command, Stdio};
    use std::time::{Duration, Instant};

    fn is_running(pid: i32) -> bool {
        // SAFETY: signal 0 only checks that the process exists.
        unsafe { libc::kill(pid, 0) == 0 }
    }

    /// Starts `script` as the leader of a new group, as the app starts the engine. It prints the pids it started.
    fn start(script: &str) -> (Child, Vec<i32>) {
        let mut child = Command::new("sh")
            .args(["-c", script])
            .stdout(Stdio::piped())
            .process_group(0)
            .spawn()
            .expect("sh starts");
        let mut line = Vec::new();
        let out = child.stdout.as_mut().expect("piped");
        let mut byte = [0u8; 1];
        while out.read(&mut byte).expect("read") == 1 && byte[0] != b'\n' {
            line.push(byte[0]);
        }
        let pids = String::from_utf8(line).unwrap().split_whitespace().map(|p| p.parse().unwrap()).collect();
        (child, pids)
    }

    fn all_gone(pids: &[i32], within: Duration) -> bool {
        let until = Instant::now() + within;
        while Instant::now() < until {
            if pids.iter().all(|p| !is_running(*p)) {
                return true;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        false
    }

    #[test]
    fn ending_the_group_ends_what_the_engine_started() {
        let (mut engine, kids) = start("sleep 300 & a=$!; sleep 300 & b=$!; echo $a $b; wait");
        assert_eq!(kids.len(), 2);
        assert!(kids.iter().all(|p| is_running(*p)));
        terminate_group(engine.id() as i32);
        let _ = engine.wait();
        assert!(all_gone(&kids, Duration::from_secs(5)), "children left running: {kids:?}");
    }

    #[test]
    fn a_process_that_ignores_sigterm_is_killed() {
        let (mut engine, kids) = start("trap '' TERM; sleep 300 & echo $!; wait");
        assert_eq!(kids.len(), 1);
        let began = Instant::now();
        terminate_group(engine.id() as i32);
        let _ = engine.wait();
        assert!(all_gone(&kids, Duration::from_secs(5)), "child left running: {kids:?}");
        assert!(began.elapsed() < Duration::from_secs(8));
    }

    #[test]
    fn a_group_that_is_already_gone_is_not_an_error() {
        let mut engine = Command::new("true").process_group(0).spawn().expect("true starts");
        let pgid = engine.id() as i32;
        let _ = engine.wait();
        terminate_group(pgid);
        signal_group(pgid, libc::SIGKILL);
        assert!(!group_is_running(pgid));
    }

    /// The names of the processes in the group (`pgrep -g` lists pid and name; it exits 1 when there is none).
    fn group_members(pgid: i32) -> Vec<String> {
        let out = Command::new("pgrep").args(["-l", "-g", &pgid.to_string()]).output().expect("pgrep runs");
        String::from_utf8_lossy(&out.stdout).lines().map(|l| l.to_string()).collect()
    }

    /// CI only (BABELSCRIBE_TEST_ENGINE = the installed engine, BABELSCRIBE_TEST_WAV = a long recording, a warm
    /// BABELSCRIBE_HOME): the real engine, started as the app starts it, transcribing; stopped as the app stops it
    /// while whisper-cli runs. Nothing of its group may be left.
    #[test]
    fn the_real_engine_and_the_programs_it_started_end_together() {
        let (Some(engine), Some(wav)) = (std::env::var_os("BABELSCRIBE_TEST_ENGINE"), std::env::var_os("BABELSCRIBE_TEST_WAV")) else {
            eprintln!("skipped: BABELSCRIBE_TEST_ENGINE and BABELSCRIBE_TEST_WAV are not set");
            return;
        };
        let wav = wav.to_string_lossy().into_owned();
        // BABELSCRIBE_TEST_FLAVOR: the whisper-cli flavour (default cpu; "default" leaves it to the engine, as on
        // Apple Silicon, which has only a Metal build).
        let flavor = std::env::var("BABELSCRIBE_TEST_FLAVOR").unwrap_or_else(|_| "cpu".to_string());
        let mut args: Vec<String> = [wav.as_str(), "-m", "tiny", "-l", "en", "-f", "txt", "--progress-json"]
            .iter()
            .map(|a| a.to_string())
            .collect();
        if flavor != "default" {
            args.extend(["--flavor".to_string(), flavor]);
        }
        let mut child = spawn_in_own_group(Path::new(&engine), &args).expect("the engine starts");
        let pgid = child.id() as i32;
        let until = Instant::now() + Duration::from_secs(120);
        let mut seen = Vec::new();
        while Instant::now() < until {
            seen = group_members(pgid);
            if seen.iter().any(|m| m.contains("whisper-cli")) || child.try_wait().expect("try_wait").is_some() {
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        assert!(seen.iter().any(|m| m.contains("whisper-cli")), "whisper-cli never ran; group: {seen:?}");
        println!("group while transcribing: {seen:?}");
        terminate_group(pgid);
        let _ = child.wait();
        let until = Instant::now() + Duration::from_secs(10);
        while Instant::now() < until && !group_members(pgid).is_empty() {
            std::thread::sleep(Duration::from_millis(100));
        }
        let left = group_members(pgid);
        assert!(left.is_empty(), "left running after stopping: {left:?}");
        println!("real-engine test: ran, nothing left");
    }

    #[test]
    fn lines_are_split_at_newlines_and_lose_the_line_end() {
        let mut got = Vec::new();
        lines(&b"one\r\ntwo\nlast without a newline"[..], |l| got.push(l));
        assert_eq!(got, ["one", "two", "last without a newline"]);
    }
}
