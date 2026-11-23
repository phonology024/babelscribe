// babelscribe desktop: a window around the babelscribe command line.
//
// The engine is babelscribe-engine.exe, the PyInstaller build of the Python CLI (packaging/standalone), shipped as a
// Tauri sidecar. It is run with --progress-json and its output lines are handed to the window as they come; all the
// transcription logic stays in Python. This file only starts and stops it and does the few things a web page cannot:
// file picker, file sizes, reading the written subtitles back, opening files and folders.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use serde::Serialize;
use tauri::ipc::Channel;
use tauri::{AppHandle, Manager, RunEvent, State, Theme, WebviewWindow};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// The running engine, if any, with the number of its run (a stopped run's late exit must not clear a newer one).
#[derive(Default)]
struct Engine {
    child: Mutex<Option<(u64, CommandChild)>>,
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
    let (mut rx, child) = app
        .shell()
        .sidecar("babelscribe-engine")
        .map_err(|e| e.to_string())?
        .args(args)
        .spawn()
        .map_err(|e| e.to_string())?;
    let run = engine.runs.fetch_add(1, Ordering::SeqCst) + 1;
    *slot = Some((run, child));
    drop(slot);

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            let message = match event {
                CommandEvent::Stdout(b) => EngineMessage::Stdout { line: text(&b) },
                CommandEvent::Stderr(b) => EngineMessage::Stderr { line: text(&b) },
                CommandEvent::Error(e) => EngineMessage::Error { message: e },
                CommandEvent::Terminated(p) => {
                    if let Ok(mut slot) = app.state::<Engine>().child.lock() {
                        if matches!(slot.as_ref(), Some((r, _)) if *r == run) {
                            *slot = None;
                        }
                    }
                    EngineMessage::Exit { code: p.code }
                }
                _ => continue,
            };
            let _ = on_event.send(message);
        }
    });
    Ok(())
}

/// Ends the engine and everything it started: whisper-cli and ffmpeg are its child processes, and killing only
/// babelscribe-engine.exe would leave them running on the GPU.
fn stop_engine(engine: &Engine) {
    let taken = engine.child.lock().ok().and_then(|mut slot| slot.take());
    if let Some((_, child)) = taken {
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            let _ = std::process::Command::new("taskkill")
                .args(["/PID", &child.pid().to_string(), "/T", "/F"])
                .creation_flags(CREATE_NO_WINDOW)
                .status();
        }
        let _ = child.kill();
    }
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
            if let RunEvent::Exit = event {
                stop_engine(&app.state::<Engine>()); // closing the window never leaves whisper-cli running
            }
        });
}
