#!/usr/bin/env python3
"""
Run a shell command on a Tencent Cloud CVM via TAT (Automation Tools).

Reads credentials from env vars TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY
so they never land on disk or in tccli's persistent config.

Two usage modes:

  1) Inline command (single shell command, anything you would normally type):

       python3 tat_run.py \\
         --region ap-hongkong --instance-id ins-xxxx \\
         --command 'docker ps --format "{{.Names}}"'

  2) Ship a local Python script into a container and run it:

       python3 tat_run.py \\
         --region ap-hongkong --instance-id ins-xxxx \\
         --container monitor-server-monitor-server-1 \\
         --remote-script ./query_newapi_tpm_rpm.py \\
         --remote-args '--start "2026-05-14 16:00" --end "2026-05-14 17:00" \\
                        --username askmanyai --models "gpt-5.5=gpt-5.5"'

Mode 2 base64-encodes the local script, drops it on the CVM under /tmp,
docker-cp's it into the container, runs `docker exec <container> python /tmp/<name>`,
prints stdout, and removes the temporary file on the host.

The script does not require the `tccli` Python SDK -- it calls the `tccli` CLI
binary via subprocess. Install with `pip install tccli` if you don't have it.

Read-only: this helper never modifies persistent config, never writes files
outside /tmp on either the local box or the remote.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def _require_env() -> tuple[str, str]:
    sid = os.environ.get("TENCENTCLOUD_SECRET_ID")
    skey = os.environ.get("TENCENTCLOUD_SECRET_KEY")
    if not sid or not skey:
        sys.stderr.write(
            "ERROR: TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY must be set in env.\n"
            "       Set them for this invocation only; do not persist to ~/.tccli or shell rc.\n"
        )
        sys.exit(2)
    return sid, skey


def _tccli(args: list[str], sid: str, skey: str) -> dict:
    """Call tccli with credentials passed via env (not via persisted config)."""
    env = {**os.environ, "TENCENTCLOUD_SECRET_ID": sid, "TENCENTCLOUD_SECRET_KEY": skey}
    p = subprocess.run(["tccli", *args], capture_output=True, text=True, env=env)
    if p.returncode != 0:
        sys.stderr.write(f"tccli failed: {' '.join(args[:3])}...\n{p.stderr}")
        sys.exit(p.returncode)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(f"tccli returned non-JSON: {p.stdout[:500]}\n")
        sys.exit(3)


def run_tat(
    region: str,
    instance_id: str,
    command: str,
    sid: str,
    skey: str,
    timeout_seconds: int = 600,
    poll_seconds: int = 2,
    poll_max_iters: int = 300,
) -> tuple[str, str, Optional[int], str]:
    """Returns (stdout, stderr, exit_code, task_status)."""
    enc = base64.b64encode(command.encode()).decode()
    inv = _tccli(
        [
            "tat", "RunCommand",
            "--region", region,
            "--Content", enc,
            "--InstanceIds", json.dumps([instance_id]),
            "--CommandType", "SHELL",
            "--Username", "root",
            "--Timeout", str(timeout_seconds),
            "--WorkingDirectory", "/root",
        ],
        sid, skey,
    )
    invocation_id = inv["InvocationId"]

    for _ in range(poll_max_iters):
        r = _tccli(
            [
                "tat", "DescribeInvocationTasks",
                "--region", region,
                "--Filters", json.dumps([{"Name": "invocation-id", "Values": [invocation_id]}]),
            ],
            sid, skey,
        )
        tasks = r.get("InvocationTaskSet") or []
        if tasks:
            t = tasks[0]
            status = t["TaskStatus"]
            if status in ("SUCCESS", "FAILED", "TIMEOUT", "TERMINATED"):
                tr = t.get("TaskResult") or {}
                out_b64 = tr.get("Output", "") or ""
                err = tr.get("ErrorOutput", "") or ""
                exit_code = tr.get("ExitCode")
                try:
                    out = base64.b64decode(out_b64).decode("utf-8", "replace") if out_b64 else ""
                except Exception:
                    out = out_b64
                return out, err, exit_code, status
        time.sleep(poll_seconds)

    return "", f"timeout waiting for invocation {invocation_id}", None, "TIMEOUT"


def _build_remote_payload(
    container: str,
    remote_script_path: Path,
    remote_args: str,
    remote_python: str = "python",
) -> str:
    """Compose a single shell command that ships the script into the container and runs it."""
    src = remote_script_path.read_bytes()
    b64 = base64.b64encode(src).decode()
    fname = remote_script_path.name
    safe_name = "".join(ch if ch.isalnum() or ch in "_-." else "_" for ch in fname)
    host_tmp = f"/tmp/{safe_name}"
    ctr_tmp = f"/tmp/{safe_name}"
    # Use bash -c so multi-step shell pipelines work; quote container name to be safe.
    return (
        f"set -e; "
        f"echo {shlex.quote(b64)} | base64 -d > {shlex.quote(host_tmp)}; "
        f"docker cp {shlex.quote(host_tmp)} {shlex.quote(container)}:{ctr_tmp}; "
        f"docker exec {shlex.quote(container)} {shlex.quote(remote_python)} {ctr_tmp} {remote_args}; "
        f"rc=$?; "
        f"rm -f {shlex.quote(host_tmp)}; "
        f"exit $rc"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--region", required=True, help="Tencent Cloud region, e.g. ap-hongkong")
    p.add_argument("--instance-id", required=True, help="CVM InstanceId, e.g. ins-xxxxxxxx")
    p.add_argument("--timeout", type=int, default=600, help="TAT command timeout in seconds (default 600)")

    p.add_argument("--command", help="Inline shell command to run on the CVM (mode 1)")
    p.add_argument("--container", help="Docker container name on the CVM (mode 2)")
    p.add_argument("--remote-script", help="Path to a local Python script to ship and execute (mode 2)")
    p.add_argument(
        "--remote-args",
        default="",
        help="Argument string passed to the remote script in mode 2. Quote shell-style.",
    )
    p.add_argument("--remote-python", default="python", help="Python binary inside the container (default: python)")
    p.add_argument("--print-command", action="store_true", help="Print the assembled command and exit (debug)")

    args = p.parse_args()
    sid, skey = _require_env()

    if args.command and args.remote_script:
        sys.stderr.write("ERROR: pass either --command (mode 1) or --remote-script (mode 2), not both.\n")
        sys.exit(2)

    if args.remote_script:
        if not args.container:
            sys.stderr.write("ERROR: --container is required when using --remote-script.\n")
            sys.exit(2)
        script_path = Path(args.remote_script)
        if not script_path.is_file():
            sys.stderr.write(f"ERROR: remote script not found: {script_path}\n")
            sys.exit(2)
        command = _build_remote_payload(
            container=args.container,
            remote_script_path=script_path,
            remote_args=args.remote_args,
            remote_python=args.remote_python,
        )
    elif args.command:
        command = args.command
    else:
        sys.stderr.write("ERROR: provide --command or --remote-script.\n")
        sys.exit(2)

    if args.print_command:
        print(command)
        return

    out, err, exit_code, status = run_tat(
        region=args.region,
        instance_id=args.instance_id,
        command=command,
        sid=sid,
        skey=skey,
        timeout_seconds=args.timeout,
    )
    # Mirror remote stdout/stderr to local stdout/stderr; exit with the remote exit code.
    sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    if status != "SUCCESS":
        sys.stderr.write(f"\n[tat_run] task status: {status}\n")
    sys.exit(exit_code if exit_code is not None else 1)


if __name__ == "__main__":
    main()
