//! Integration tests against a private pueued instance.

use std::{
    fs,
    io::Write,
    path::PathBuf,
    process::{Command, Output, Stdio},
};

/// Private pueued in a temp dir, shut down on drop.
struct Sandbox {
    dir: PathBuf,
    config: PathBuf,
}

impl Sandbox {
    fn new(name: &str) -> Self {
        // /tmp, not $TMPDIR: the nix darwin sandbox TMPDIR pushes the unix
        // socket path past the 104 byte sun_path limit.
        let dir = PathBuf::from(format!("/tmp/queue-test-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        let config = dir.join("pueue.yml");
        let d = dir.display();
        fs::write(
            &config,
            format!(
                "shared:\n  pueue_directory: {d}\n  runtime_directory: {d}\n  unix_socket_path: {d}/sock\n\
                 client: {{}}\ndaemon: {{}}\n"
            ),
        )
        .unwrap();
        Sandbox { dir, config }
    }

    fn queue(&self, args: &[&str], stdin: &str) -> Output {
        let mut child = Command::new(env!("CARGO_BIN_EXE_queue"))
            .args(args)
            .env("PUEUE_CONFIG_PATH", &self.config)
            .env("QUEUE_SESSION", "test")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .expect("spawn queue");
        child
            .stdin
            .take()
            .unwrap()
            .write_all(stdin.as_bytes())
            .unwrap();
        child.wait_with_output().unwrap()
    }

    fn run(&self, command: &str) -> (usize, String) {
        let out = self.queue(&["run"], command);
        let stderr = String::from_utf8(out.stderr).unwrap();
        let stdout = String::from_utf8(out.stdout).unwrap();
        assert!(out.status.success(), "queue run failed: {stderr}{stdout}");
        let id = stderr
            .lines()
            .find_map(|l| l.strip_prefix("task="))
            .unwrap_or_else(|| panic!("no task= line in {stderr:?}"))
            .parse()
            .unwrap();
        (id, stdout)
    }
}

impl Drop for Sandbox {
    fn drop(&mut self) {
        let _ = Command::new("pueue")
            .args(["shutdown"])
            .env("PUEUE_CONFIG_PATH", &self.config)
            .output();
        std::thread::sleep(std::time::Duration::from_millis(300));
        let _ = fs::remove_dir_all(&self.dir);
    }
}

/// Regression: delivered tasks were removed, pueue (ids = max+1) recycled the id.
#[test]
fn task_ids_are_not_reused() {
    let sandbox = Sandbox::new("reuse");
    let (first, _) = sandbox.run("echo one");
    let (second, _) = sandbox.run("echo two");
    assert_ne!(first, second, "second run reused id of the first");

    let out = sandbox.queue(&["log", &first.to_string()], "");
    let stdout = String::from_utf8(out.stdout).unwrap();
    assert!(
        !stdout.contains("two"),
        "queue log {first} shows a different task: {stdout}"
    );
}

/// Finished tasks must still be garbage collected eventually.
#[test]
fn old_delivered_tasks_are_cleaned() {
    let sandbox = Sandbox::new("clean");
    let (first, _) = sandbox.run("echo one");
    sandbox.run("echo two");
    sandbox.run("echo three");

    let out = sandbox.queue(&["status", "--json"], "");
    let tasks: Vec<serde_json::Value> = serde_json::from_slice(&out.stdout).unwrap();
    let ids: Vec<u64> = tasks.iter().map(|t| t["id"].as_u64().unwrap()).collect();
    assert!(
        !ids.contains(&(first as u64)),
        "task {first} still listed: {ids:?}"
    );
}
