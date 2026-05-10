#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
PID_FILE = BASE / 'server.pid'
LOG_FILE = BASE / 'server.log'
HOST = '127.0.0.1'
PORT = 8765


def is_port_open(host: str = HOST, port: int = PORT, timeout: float = 0.5) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding='utf-8').strip())
    except Exception:
        return None


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def status() -> int:
    pid = read_pid()
    alive = bool(pid and process_alive(pid))
    port = is_port_open()
    print(f'pid_file={pid} alive={alive} port_8765={port}')
    if alive and port:
        return 0
    return 1


def start() -> int:
    # already running
    pid = read_pid()
    if pid and process_alive(pid) and is_port_open():
        print(f'already running pid={pid}')
        return 0

    python_bin = sys.executable
    cmd = [python_bin, str(BASE / 'server.py')]

    with LOG_FILE.open('ab') as logf:
        # detached process group (works on mac/linux)
        p = subprocess.Popen(
            cmd,
            cwd=str(BASE),
            stdout=logf,
            stderr=logf,
            preexec_fn=os.setsid if hasattr(os, 'setsid') else None,
            close_fds=True,
        )

    PID_FILE.write_text(str(p.pid), encoding='utf-8')

    for _ in range(40):
        if is_port_open():
            print(f'started pid={p.pid}')
            return 0
        if p.poll() is not None:
            print(f'failed: process exited code={p.returncode}')
            return 2
        time.sleep(0.2)

    print('failed: timeout waiting for port 8765')
    return 3


def stop() -> int:
    pid = read_pid()
    if not pid:
        print('not running (no pid file)')
        return 0

    if not process_alive(pid):
        PID_FILE.unlink(missing_ok=True)
        print('not running (stale pid file removed)')
        return 0

    try:
        os.killpg(pid, signal.SIGTERM) if hasattr(os, 'killpg') else os.kill(pid, signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass

    for _ in range(30):
        if not process_alive(pid):
            PID_FILE.unlink(missing_ok=True)
            print(f'stopped pid={pid}')
            return 0
        time.sleep(0.1)

    try:
        os.killpg(pid, signal.SIGKILL) if hasattr(os, 'killpg') else os.kill(pid, signal.SIGKILL)
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    PID_FILE.unlink(missing_ok=True)
    print(f'killed pid={pid}')
    return 0


def restart() -> int:
    stop()
    return start()


def main() -> int:
    ap = argparse.ArgumentParser(description='Manage local debug server')
    ap.add_argument('action', choices=['start', 'stop', 'restart', 'status'])
    args = ap.parse_args()

    if args.action == 'start':
        return start()
    if args.action == 'stop':
        return stop()
    if args.action == 'restart':
        return restart()
    return status()


if __name__ == '__main__':
    raise SystemExit(main())
