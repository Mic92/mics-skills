//! LLM-friendly pueue frontend.
//!
//! Commands are read from stdin (never re-tokenized by a shell), exit codes
//! always reflect the task result, output is never truncated by default and
//! every task is labeled with the calling agent's session so concurrent
//! agents sharing one daemon don't step on each other.

use std::{
    collections::HashMap,
    env, error, fmt, fs,
    io::{self, Read, Write},
    path::{Path, PathBuf},
    process, str, thread,
    time::Duration,
};

use lexopt::{
    Arg::{Long, Short, Value},
    Parser, ValueExt,
};
use pueue_lib::{
    message::{
        AddRequest, KillRequest, Request, Response, RestartRequest, StreamRequest, TaskSelection,
        TaskToRestart,
    },
    network_blocking::{
        protocol::{receive_bytes, receive_response, send_bytes, send_request},
        socket::{ConnectionSettings, GenericBlockingStream, get_client_stream},
    },
    settings::Settings,
    state::State,
    task::{Task, TaskResult, TaskStatus},
};

/// "Not done yet, come back later": detach timeout, running task in `log`.
/// 124 is unsuitable because tasks wrapping timeout(1) legitimately exit 124.
const EXIT_PENDING: i32 = 75;
const DEFAULT_TIMEOUT_SECS: u64 = 100;

type Error = Box<dyn error::Error>;

fn die(msg: impl fmt::Display) -> ! {
    eprintln!("queue: {msg}");
    process::exit(1);
}

fn main() {
    let mut parser = Parser::from_env();
    let cmd = match parser.next() {
        Ok(Some(Value(cmd))) => cmd.string().unwrap_or_else(|err| die(err)),
        Ok(Some(Long("help") | Short('h'))) | Ok(None) => {
            println!("{USAGE}");
            return;
        }
        Ok(Some(arg)) => die(arg.unexpected()),
        Err(err) => die(err),
    };
    let result = match cmd.as_str() {
        "run" => run(&mut parser),
        "wait" => wait(&mut parser),
        "log" => log(&mut parser),
        "status" => status(&mut parser),
        "kill" => kill(&mut parser),
        "restart" => restart(&mut parser),
        "ps" => ps(&mut parser),
        "help" => {
            println!("{USAGE}");
            return;
        }
        _ => die(format!("unknown subcommand '{cmd}'\n{USAGE}")),
    };
    match result {
        Ok(code) => process::exit(code),
        Err(err) => die(err),
    }
}

const USAGE: &str = "\
usage: queue <subcommand> [options]

  run [--timeout SECS] [--detach] [--after ID...] [-C DIR] [--name NAME] [--tail-ok N]
       read command from stdin, enqueue, stream output, exit with its exit code
  wait [ID...] [--timeout SECS] [--tail-ok N]
       attach to tasks (default: all own tasks); exit non-zero if any failed
  log [ID] [--lines N]
       full log + status header; without ID: most recent own task
  status [--all] [--json]
       one line per task (own session only unless --all)
  restart ID
       re-enqueue a finished task with its stored command and attach
  kill ID
       kill an own-session task
  ps ID [--json]
       pid, RSS and CPU time of a running task's process tree

Commands are passed on stdin, e.g.:  queue run <<'EOF' ... EOF
Exit code 75 means: still running, resume with `queue wait <id>`.";

struct Daemon {
    stream: GenericBlockingStream,
    pueue_dir: PathBuf,
}

impl Daemon {
    fn connect() -> Result<Self, Error> {
        let (settings, _) = Settings::read(&None)?;
        let shared = settings.shared;
        let connection: ConnectionSettings = shared.clone().try_into()?;
        let mut stream = match get_client_stream(connection) {
            Ok(stream) => stream,
            Err(_) => Self::start_daemon(&shared)?,
        };
        let secret = fs::read(shared.shared_secret_path())
            .map_err(|err| format!("reading pueue secret: {err}"))?;
        send_bytes(&secret, &mut stream)?;
        let version = receive_bytes(&mut stream)?;
        if version.is_empty() {
            return Err("daemon rejected the shared secret".into());
        }
        Ok(Self {
            stream,
            pueue_dir: shared.pueue_directory(),
        })
    }

    /// Launch pueued and retry connecting while it initializes.
    fn start_daemon(shared: &pueue_lib::settings::Shared) -> Result<GenericBlockingStream, Error> {
        let pueued = env::var("QUEUE_PUEUED").unwrap_or_else(|_| "pueued".to_string());
        process::Command::new(&pueued)
            .arg("-d")
            .stdout(process::Stdio::null())
            .stderr(process::Stdio::null())
            .status()
            .map_err(|err| format!("starting {pueued}: {err}"))?;
        for _ in 0..50 {
            thread::sleep(Duration::from_millis(100));
            let connection: ConnectionSettings = shared.clone().try_into()?;
            if let Ok(stream) = get_client_stream(connection) {
                return Ok(stream);
            }
        }
        Err("pueue daemon did not come up within 5s".into())
    }

    fn request(&mut self, request: Request) -> Result<Response, Error> {
        send_request(request, &mut self.stream)?;
        Ok(receive_response(&mut self.stream)?)
    }

    fn state(&mut self) -> Result<State, Error> {
        match self.request(Request::Status)? {
            Response::Status(state) => Ok(*state),
            other => Err(format!("unexpected response to status request: {other:?}").into()),
        }
    }

    fn task(&mut self, id: usize) -> Result<Task, Error> {
        self.state()?
            .tasks
            .remove(&id)
            .ok_or_else(|| format!("task {id} does not exist").into())
    }

    /// Best-effort removal of a delivered task. The daemon refuses to remove
    /// tasks that others depend on, which is exactly what we want for
    /// `--after` pipelines, so failures are ignored.
    fn auto_clean(&mut self, id: usize) {
        let _ = self.request(Request::Remove(vec![id]));
    }
}

/// The session id of the outermost agent in our ancestry.
///
/// Env vars alone cannot encode nesting order (a nested agent inherits the
/// outer agent's vars), so we walk the PID chain and use the *highest*
/// ancestor that carries an agent session id. Falls back to plain env
/// lookup where /proc is unavailable.
fn session() -> Option<String> {
    if let Ok(session) = env::var("QUEUE_SESSION") {
        return Some(session);
    }
    const VARS: [&str; 2] = ["CLAUDE_CODE_SESSION_ID", "PI_SESSION_ID"];
    let mut outermost = None;
    let mut pid = process::id();
    while pid > 1 {
        let Ok(status) = fs::read_to_string(format!("/proc/{pid}/status")) else {
            break;
        };
        let Some(ppid) = status
            .lines()
            .find_map(|l| l.strip_prefix("PPid:"))
            .and_then(|v| v.trim().parse::<u32>().ok())
        else {
            break;
        };
        if let Ok(environ) = fs::read(format!("/proc/{ppid}/environ")) {
            for entry in environ.split(|&b| b == 0) {
                let Ok(entry) = str::from_utf8(entry) else {
                    continue;
                };
                if let Some((key, value)) = entry.split_once('=') {
                    if VARS.contains(&key) && !value.is_empty() {
                        outermost = Some(value.to_string());
                    }
                }
            }
        }
        pid = ppid;
    }
    outermost.or_else(|| VARS.iter().find_map(|var| env::var(var).ok()))
}

fn make_label(session: &Option<String>, name: &Option<String>) -> Option<String> {
    match (session, name) {
        (Some(session), Some(name)) => Some(format!("q:{session}:{name}")),
        (Some(session), None) => Some(format!("q:{session}")),
        (None, Some(name)) => Some(name.clone()),
        (None, None) => None,
    }
}

/// Does a task belong to the given session?
/// Without a session (interactive use) everything matches.
fn owned(task: &Task, session: &Option<String>) -> bool {
    let Some(session) = session else { return true };
    let prefix = format!("q:{session}");
    match &task.label {
        Some(label) => label == &prefix || label.starts_with(&format!("{prefix}:")),
        None => false,
    }
}

/// Print the last `lines` lines, announcing how much was skipped.
fn print_tail(output: &str, lines: usize, hint: &str) {
    let all: Vec<&str> = output.lines().collect();
    let start = all.len().saturating_sub(lines);
    if start > 0 {
        println!("[{start} lines omitted - {hint}]");
    }
    for line in &all[start..] {
        println!("{line}");
    }
}

/// The human-readable `--name` part of a `q:<session>:<name>` label.
fn task_name(task: &Task) -> Option<&str> {
    task.label.as_deref()?.splitn(3, ':').nth(2)
}

/// Human-readable state plus the exit code once the task is done.
fn task_summary(task: &Task) -> (String, Option<i32>) {
    let runtime = |start: &chrono::DateTime<chrono::Local>,
                   end: Option<&chrono::DateTime<chrono::Local>>| {
        let end = end.copied().unwrap_or_else(chrono::Local::now);
        format!("{}s", (end - *start).num_seconds())
    };
    match &task.status {
        TaskStatus::Queued { .. } => ("queued".into(), None),
        TaskStatus::Stashed { .. } => ("stashed".into(), None),
        TaskStatus::Locked { .. } => ("locked".into(), None),
        TaskStatus::Running { start, .. } => (format!("running {}", runtime(start, None)), None),
        TaskStatus::Paused { start, .. } => (format!("paused {}", runtime(start, None)), None),
        TaskStatus::Done {
            start, end, result, ..
        } => {
            let runtime = runtime(start, Some(end));
            match result {
                TaskResult::Success => (format!("success {runtime}"), Some(0)),
                TaskResult::Failed(code) => (format!("failed exit={code} {runtime}"), Some(*code)),
                // 128+9: the shell convention for SIGKILLed processes.
                TaskResult::Killed => (format!("killed {runtime}"), Some(137)),
                // 127: the shell convention for "command not found".
                TaskResult::FailedToSpawn(err) => {
                    (format!("failed-to-spawn ({err}) {runtime}"), Some(127))
                }
                TaskResult::Errored => (format!("errored {runtime}"), Some(1)),
                TaskResult::DependencyFailed => (format!("dependency-failed {runtime}"), Some(1)),
            }
        }
    }
}

fn timeout_from(flag: Option<u64>) -> Duration {
    let secs = flag
        .or_else(|| env::var("QUEUE_TIMEOUT").ok().and_then(|v| v.parse().ok()))
        .unwrap_or(DEFAULT_TIMEOUT_SECS);
    Duration::from_secs(secs)
}

/// Detach watchdog: reads on the daemon stream block indefinitely while a
/// task is silent, so a plain read timeout would corrupt protocol framing
/// mid-frame. Exiting the process instead is safe by design: the task lives
/// in the daemon and detaching performs no cleanup.
fn spawn_watchdog(deadline: Duration, ids: Vec<usize>) {
    thread::spawn(move || {
        thread::sleep(deadline);
        let ids = ids
            .iter()
            .map(|id| id.to_string())
            .collect::<Vec<_>>()
            .join(" ");
        eprintln!("\nstill running, resume with: queue wait {ids}");
        process::exit(EXIT_PENDING);
    });
}

/// Stream one task to completion, print its status line, auto-clean it and
/// return its exit code.
fn attach(daemon: &mut Daemon, id: usize, tail_ok: Option<usize>) -> Result<i32, Error> {
    send_request(
        Request::Stream(StreamRequest {
            tasks: TaskSelection::TaskIds(vec![id]),
            lines: None,
        }),
        &mut daemon.stream,
    )?;

    let mut buffer = String::new();
    loop {
        match receive_response(&mut daemon.stream)? {
            Response::Stream(chunk) => {
                for (_, text) in chunk.logs {
                    if tail_ok.is_some() {
                        buffer.push_str(&text);
                    } else {
                        print!("{text}");
                        let _ = io::stdout().flush();
                    }
                }
            }
            Response::Close => break,
            // The daemon reports mid-stream problems ("task has been
            // removed", "log file has gone away") as Failure or Success.
            Response::Failure(text) | Response::Success(text) => return Err(text.into()),
            other => return Err(format!("unexpected response: {other:?}").into()),
        }
    }

    let task = daemon.task(id)?;
    let (summary, code) = task_summary(&task);
    let code = code.ok_or_else(|| format!("task {id} stream closed but task not done"))?;
    if let Some(lines) = tail_ok {
        if code == 0 {
            print_tail(&buffer, lines, &format!("full log: queue log {id}"));
        } else {
            print!("{buffer}");
        }
    }
    println!("task={id} {summary}");
    daemon.auto_clean(id);
    Ok(code)
}

fn run(parser: &mut Parser) -> Result<i32, Error> {
    let mut timeout = None;
    let mut detach = false;
    let mut after = Vec::new();
    let mut dir = None;
    let mut name = None;
    let mut tail_ok = None;

    while let Some(arg) = parser.next()? {
        match arg {
            Long("timeout") => timeout = Some(parser.value()?.parse()?),
            Long("detach") => detach = true,
            Long("after") => {
                for value in parser.values()? {
                    after.push(value.parse()?);
                }
            }
            Short('C') => dir = Some(parser.value()?.string()?),
            Long("name") => name = Some(parser.value()?.string()?),
            Long("tail-ok") => tail_ok = Some(parser.value()?.parse()?),
            _ => return Err(arg.unexpected().into()),
        }
    }

    let mut command = String::new();
    io::stdin().read_to_string(&mut command)?;
    let command = command.trim().to_string();
    if command.is_empty() {
        return Err("no command on stdin; use: queue run <<'EOF' ... EOF".into());
    }

    let path = match dir {
        Some(dir) => fs::canonicalize(&dir).map_err(|err| format!("-C {dir}: {err}"))?,
        None => env::current_dir()?,
    };
    let session = session();

    let mut daemon = Daemon::connect()?;
    let response = daemon.request(Request::Add(AddRequest {
        command,
        path,
        envs: env::vars().collect::<HashMap<_, _>>(),
        start_immediately: false,
        stashed: false,
        group: "default".to_string(),
        enqueue_at: None,
        dependencies: after,
        priority: None,
        label: make_label(&session, &name),
    }))?;
    let added = match response {
        Response::AddedTask(added) => added,
        Response::Failure(text) => return Err(text.into()),
        other => return Err(format!("unexpected response: {other:?}").into()),
    };
    let id = added.task_id;
    eprintln!("task={id}");

    if added.group_is_paused {
        eprintln!("group is paused, task will not start (fix with: pueue start)");
        return Ok(EXIT_PENDING);
    }
    if detach {
        return Ok(0);
    }
    spawn_watchdog(timeout_from(timeout), vec![id]);
    attach(&mut daemon, id, tail_ok)
}

fn wait(parser: &mut Parser) -> Result<i32, Error> {
    let mut timeout = None;
    let mut tail_ok = None;
    let mut ids = Vec::new();

    while let Some(arg) = parser.next()? {
        match arg {
            Long("timeout") => timeout = Some(parser.value()?.parse()?),
            Long("tail-ok") => tail_ok = Some(parser.value()?.parse()?),
            Value(value) => ids.push(value.parse()?),
            _ => return Err(arg.unexpected().into()),
        }
    }

    let mut daemon = Daemon::connect()?;
    if ids.is_empty() {
        let session = session();
        let state = daemon.state()?;
        ids = state
            .tasks
            .values()
            .filter(|task| owned(task, &session))
            .map(|task| task.id)
            .collect();
        if ids.is_empty() {
            println!("no tasks");
            return Ok(0);
        }
    }

    spawn_watchdog(timeout_from(timeout), ids.clone());
    let mut first_failure = 0;
    for id in ids {
        let code = attach(&mut daemon, id, tail_ok)?;
        if first_failure == 0 {
            first_failure = code;
        }
    }
    Ok(first_failure)
}

fn log(parser: &mut Parser) -> Result<i32, Error> {
    let mut lines = None;
    let mut id = None;
    while let Some(arg) = parser.next()? {
        match arg {
            Long("lines") => lines = Some(parser.value()?.parse()?),
            Value(value) => id = Some(value.parse()?),
            _ => return Err(arg.unexpected().into()),
        }
    }

    let mut daemon = Daemon::connect()?;
    let id = match id {
        Some(id) => id,
        None => {
            let session = session();
            daemon
                .state()?
                .tasks
                .values()
                .filter(|task| owned(task, &session))
                .map(|task| task.id)
                .max()
                .ok_or("no tasks")?
        }
    };
    let task = daemon.task(id)?;
    let (summary, code) = task_summary(&task);
    println!("task={id} {summary}");

    // The daemon only serves logs snappy-compressed; reading the local file
    // keeps us dependency-free. Our daemon is always on the same machine.
    let path = daemon.pueue_dir.join("task_logs").join(format!("{id}.log"));
    let output = match fs::read_to_string(&path) {
        Ok(output) => output,
        Err(_) => String::new(), // not started yet
    };
    match lines {
        Some(lines) => print_tail(&output, lines, "omit --lines for everything"),
        None => print!("{output}"),
    }
    Ok(code.unwrap_or(EXIT_PENDING))
}

fn status(parser: &mut Parser) -> Result<i32, Error> {
    let mut all = false;
    let mut json = false;
    while let Some(arg) = parser.next()? {
        match arg {
            Long("all") => all = true,
            Long("json") => json = true,
            _ => return Err(arg.unexpected().into()),
        }
    }

    let session = session();
    let mut daemon = Daemon::connect()?;
    let state = daemon.state()?;
    let tasks: Vec<&Task> = state
        .tasks
        .values()
        .filter(|task| all || owned(task, &session))
        .collect();

    if json {
        let items: Vec<serde_json::Value> = tasks
            .iter()
            .map(|task| {
                let (summary, code) = task_summary(task);
                let status = summary.split(' ').next().unwrap_or("unknown").to_string();
                let (start, end) = task.start_and_end();
                serde_json::json!({
                    "id": task.id,
                    "status": status,
                    "exit_code": code,
                    "label": task.label,
                    "name": task_name(task),
                    "command": task.original_command,
                    "path": task.path,
                    "start": start.map(|t| t.to_rfc3339()),
                    "end": end.map(|t| t.to_rfc3339()),
                })
            })
            .collect();
        println!("{}", serde_json::to_string_pretty(&items)?);
        return Ok(0);
    }

    if tasks.is_empty() {
        println!("no tasks");
        return Ok(0);
    }
    for task in tasks {
        let (summary, _) = task_summary(task);
        let mut command = task.original_command.replace('\n', " ");
        if command.chars().count() > 100 {
            command = format!("{}...", command.chars().take(100).collect::<String>());
        }
        let name = task_name(task)
            .map(|n| format!(" [{n}]"))
            .unwrap_or_default();
        println!("{} {summary}{name} {command}", task.id);
    }
    Ok(0)
}

fn kill(parser: &mut Parser) -> Result<i32, Error> {
    let mut id = None;
    while let Some(arg) = parser.next()? {
        match arg {
            Value(value) => id = Some(value.parse()?),
            _ => return Err(arg.unexpected().into()),
        }
    }
    let id: usize = id.ok_or("usage: queue kill ID")?;

    let session = session();
    let mut daemon = Daemon::connect()?;
    let task = daemon.task(id)?;
    if !owned(&task, &session) {
        return Err(format!("task {id} belongs to another session; refusing to kill").into());
    }
    match daemon.request(Request::Kill(KillRequest {
        tasks: TaskSelection::TaskIds(vec![id]),
        signal: None,
    }))? {
        Response::Success(text) => {
            println!("{text}");
            Ok(0)
        }
        Response::Failure(text) => Err(text.into()),
        other => Err(format!("unexpected response: {other:?}").into()),
    }
}

fn restart(parser: &mut Parser) -> Result<i32, Error> {
    let mut timeout = None;
    let mut id = None;
    while let Some(arg) = parser.next()? {
        match arg {
            Long("timeout") => timeout = Some(parser.value()?.parse()?),
            Value(value) => id = Some(value.parse()?),
            _ => return Err(arg.unexpected().into()),
        }
    }
    let id: usize = id.ok_or("usage: queue restart ID")?;

    let session = session();
    let mut daemon = Daemon::connect()?;
    let task = daemon.task(id)?;
    if !owned(&task, &session) {
        return Err(format!("task {id} belongs to another session; refusing to restart").into());
    }
    if !task.is_done() {
        return Err(format!("task {id} is not finished; use queue wait {id}").into());
    }
    match daemon.request(Request::Restart(RestartRequest {
        tasks: vec![TaskToRestart {
            task_id: id,
            original_command: task.original_command.clone(),
            path: task.path.clone(),
            label: task.label.clone(),
            priority: task.priority,
        }],
        start_immediately: false,
        stashed: false,
    }))? {
        Response::Success(_) => {}
        Response::Failure(text) => return Err(text.into()),
        other => return Err(format!("unexpected response: {other:?}").into()),
    }
    eprintln!("task={id}");
    spawn_watchdog(timeout_from(timeout), vec![id]);
    attach(&mut daemon, id, None)
}

fn ps(parser: &mut Parser) -> Result<i32, Error> {
    let mut json = false;
    let mut id = None;
    while let Some(arg) = parser.next()? {
        match arg {
            Long("json") => json = true,
            Value(value) => id = Some(value.parse()?),
            _ => return Err(arg.unexpected().into()),
        }
    }
    let id: usize = id.ok_or("usage: queue ps ID [--json]")?;

    if !Path::new("/proc/self/stat").exists() {
        return Err("queue ps needs /proc and is only supported on Linux".into());
    }

    let mut daemon = Daemon::connect()?;
    let task = daemon.task(id)?;
    let (summary, _) = task_summary(&task);
    if !task.is_running() {
        return Err(format!("task {id} is not running ({summary})").into());
    }
    // The protocol exposes no pid, but the daemon writes these two vars back
    // into task.envs on spawn; together they uniquely identify the worker
    // process among the running tasks.
    let worker_id = task
        .envs
        .get("PUEUE_WORKER_ID")
        .ok_or("task has no PUEUE_WORKER_ID")?;
    let group = task
        .envs
        .get("PUEUE_GROUP")
        .ok_or("task has no PUEUE_GROUP")?;

    let worker_pid = find_worker(worker_id, group).ok_or("worker process not found in /proc")?;
    let procs = process_tree(worker_pid);

    if json {
        let items: Vec<serde_json::Value> = procs
            .iter()
            .map(|p| {
                serde_json::json!({
                    "pid": p.pid,
                    "rss_kb": p.rss_kb,
                    "cpu_seconds": p.cpu_seconds,
                    "command": p.command,
                })
            })
            .collect();
        println!(
            "{}",
            serde_json::to_string_pretty(&serde_json::json!({
                "task": id, "status": summary, "processes": items,
            }))?
        );
        return Ok(0);
    }

    println!("task={id} {summary}");
    println!("{:<8} {:>10} {:>10} COMMAND", "PID", "RSS", "CPU");
    let (mut total_rss, mut total_cpu) = (0u64, 0f64);
    for p in &procs {
        total_rss += p.rss_kb;
        total_cpu += p.cpu_seconds;
        println!(
            "{:<8} {:>10} {:>10} {}",
            p.pid,
            fmt_kb(p.rss_kb),
            fmt_secs(p.cpu_seconds),
            p.command
        );
    }
    println!(
        "{:<8} {:>10} {:>10}",
        "total",
        fmt_kb(total_rss),
        fmt_secs(total_cpu)
    );
    Ok(0)
}

struct ProcInfo {
    pid: u32,
    rss_kb: u64,
    cpu_seconds: f64,
    command: String,
}

fn all_pids() -> Vec<u32> {
    fs::read_dir("/proc")
        .map(|dir| {
            dir.filter_map(|e| e.ok()?.file_name().to_str()?.parse().ok())
                .collect()
        })
        .unwrap_or_default()
}

fn find_worker(worker_id: &str, group: &str) -> Option<u32> {
    let want_worker = format!("PUEUE_WORKER_ID={worker_id}");
    let want_group = format!("PUEUE_GROUP={group}");
    all_pids().into_iter().find(|pid| {
        let Ok(environ) = fs::read(format!("/proc/{pid}/environ")) else {
            return false;
        };
        let mut has_worker = false;
        let mut has_group = false;
        for entry in environ.split(|&b| b == 0) {
            if entry == want_worker.as_bytes() {
                has_worker = true;
            } else if entry == want_group.as_bytes() {
                has_group = true;
            }
        }
        has_worker && has_group
    })
}

/// The worker and all its descendants, in tree discovery order.
fn process_tree(root: u32) -> Vec<ProcInfo> {
    let mut children: HashMap<u32, Vec<u32>> = HashMap::new();
    for pid in all_pids() {
        if let Some((ppid, _, _)) = read_stat(pid) {
            children.entry(ppid).or_default().push(pid);
        }
    }
    let mut result = Vec::new();
    let mut queue = vec![root];
    while let Some(pid) = queue.pop() {
        if let Some(info) = proc_info(pid) {
            result.push(info);
        }
        if let Some(kids) = children.get(&pid) {
            queue.extend(kids);
        }
    }
    result
}

/// (ppid, utime, stime) from /proc/pid/stat. The comm field may contain
/// spaces and parentheses, so parse from after the last ')'.
fn read_stat(pid: u32) -> Option<(u32, u64, u64)> {
    let stat = fs::read_to_string(format!("/proc/{pid}/stat")).ok()?;
    let rest = &stat[stat.rfind(')')? + 2..];
    let fields: Vec<&str> = rest.split_whitespace().collect();
    // fields[0] is state, [1] ppid, [11] utime, [12] stime
    Some((
        fields.get(1)?.parse().ok()?,
        fields.get(11)?.parse().ok()?,
        fields.get(12)?.parse().ok()?,
    ))
}

fn proc_info(pid: u32) -> Option<ProcInfo> {
    let (_, utime, stime) = read_stat(pid)?;
    let clock_ticks = 100.0; // USER_HZ on all relevant platforms
    let status = fs::read_to_string(format!("/proc/{pid}/status")).ok()?;
    let rss_kb = status
        .lines()
        .find_map(|l| l.strip_prefix("VmRSS:"))
        .and_then(|v| v.trim().trim_end_matches(" kB").parse().ok())
        .unwrap_or(0);
    let cmdline = fs::read(format!("/proc/{pid}/cmdline")).ok()?;
    let command = String::from_utf8_lossy(&cmdline)
        .trim_end_matches('\0')
        .replace('\0', " ");
    Some(ProcInfo {
        pid,
        rss_kb,
        cpu_seconds: (utime + stime) as f64 / clock_ticks,
        command,
    })
}

fn fmt_kb(kb: u64) -> String {
    if kb >= 1024 * 1024 {
        format!("{:.1}G", kb as f64 / (1024.0 * 1024.0))
    } else if kb >= 1024 {
        format!("{:.1}M", kb as f64 / 1024.0)
    } else {
        format!("{kb}K")
    }
}

fn fmt_secs(secs: f64) -> String {
    let s = secs as u64;
    format!("{}:{:02}", s / 60, s % 60)
}
