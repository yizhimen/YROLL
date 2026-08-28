// YROLL 桌面壳（Tauri）：spawn 后端 → 窗口加载本地服务 → 关窗杀后端。
//
// 后端来源：
//   - 开发（debug）：仓库 .venv 的 python -m yroll.cli.main serve
//   - 发布（release）：随包资源里的 yroll-backend.exe（PyInstaller 单文件）
//
// 架构不变：GUI/API/WS 仍是同一个 FastAPI 进程，壳只管生命周期。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

struct Backend(Mutex<Option<Child>>);

fn project_dir() -> PathBuf {
    std::env::var("YROLL_PROJECT")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            // 开发：gui/src-tauri 上两级 = 仓库根
            let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../projects/jdz-chaishao");
            if dev.exists() {
                dev
            } else {
                std::env::temp_dir().join("yroll-project")
            }
        })
}

fn spawn_backend() -> Option<Child> {
    let port_up = TcpStream::connect("127.0.0.1:8765").is_ok();
    if port_up {
        return None; // 已有后端在跑（如开发时手动起的），直接复用
    }
    let project = project_dir();
    let child = if cfg!(debug_assertions) {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        Command::new(root.join(".venv/Scripts/python.exe"))
            .args(["-m", "yroll.server.sidecar", "serve"])
            .arg(&project)
            .arg("--port")
            .arg("8765")
            .current_dir(&root)
            .env("PYTHONIOENCODING", "utf-8")
            .spawn()
            .expect("无法启动 Python 后端")
    } else {
        let exe = std::env::current_exe()
            .expect("exe 路径")
            .parent()
            .expect("exe 目录")
            .join("yroll-backend.exe");
        Command::new(exe)
            .arg("serve")
            .arg(&project)
            .arg("--port")
            .arg("8765")
            .spawn()
            .expect("无法启动内嵌后端")
    };
    // 等端口就绪（最多 30s，PyInstaller onefile 首次解压较慢）
    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        if TcpStream::connect("127.0.0.1:8765").is_ok() {
            break;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    Some(child)
}

fn main() {
    let backend = Backend(Mutex::new(spawn_backend()));
    tauri::Builder::default()
        .manage(backend)
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                use tauri::Manager;
                let state = window.state::<Backend>();
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
                // 壳的使命结束：窗口没了就退出（后端子进程已杀）
                std::process::exit(0);
            }
        })
        .run(tauri::generate_context!())
        .expect("Tauri 运行失败");
}
