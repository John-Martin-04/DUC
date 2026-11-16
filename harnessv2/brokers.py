"""Start or stop the two local Mosquitto brokers, with one account per client
and access rules that enforce the household boundary.

  home broker        a gateway may only use home/<its own id>/...
  federation broker  a gateway may read the global model and write only its own
                     update, metrics and status; it cannot read other homes' updates

The federation broker needs an account for every home in the run, on
whichever machine it runs. DUC_HOME_BIND / DUC_FED_BIND choose whether a
broker is reachable from the network (0.0.0.0) or only locally (127.0.0.1).

Usage
  python brokers.py start --homes csh101 csh102     # both brokers
  python brokers.py start --only home --homes csh102 csh103
  python brokers.py stop
"""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
import signal
import socket
import subprocess
import sys
import time

import hconfig as H

ACL_HOME = """user replay
topic readwrite home/#

pattern readwrite home/%u/#
"""

ACL_FED = """user coordinator
topic readwrite fl/#

user recorder
topic read fl/#
topic read $SYS/#

pattern read fl/global
pattern write fl/round/+/update/%u
pattern write fl/round/+/metrics/%u
pattern write fl/status/%u
"""

CONF = """listener {port} {host}
allow_anonymous false
password_file {dir}/{name}.passwd
acl_file {dir}/{name}.acl
user {user}
persistence false
max_queued_messages 0
max_inflight_messages 100
sys_interval 2
log_dest file {dir}/{name}.log
pid_file {dir}/{name}.pid
"""


def stop() -> None:
    """Stop our brokers, including any left over from an interrupted run.

    Matches the mosquitto processes by their config file path, so it works even
    when the PID files are missing. The system broker is never matched.
    """
    for name in ("home", "fed"):
        conf = H.BROKER_DIR / f"{name}.conf"
        subprocess.run(["pkill", "-f", f"mosquitto -c {conf}"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        pid = H.BROKER_DIR / f"{name}.pid"
        if pid.exists():
            try:
                os.kill(int(pid.read_text().strip()), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
            pid.unlink(missing_ok=True)
    time.sleep(1)


def wait_port(host: str, port: int, timeout: float = 10) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def start(homes: list[str], which: tuple[str, ...]) -> None:
    if not shutil.which("mosquitto"):
        sys.exit("mosquitto not found. Install it: sudo apt install -y mosquitto")
    stop()
    H.BROKER_DIR.mkdir(parents=True, exist_ok=True)
    users = {"home": ["replay"] + homes, "fed": ["coordinator", "recorder"] + homes}
    acls = {"home": ACL_HOME, "fed": ACL_FED}
    specs = {"home": (H.HOME_BIND, H.addr(H.HOME_BROKER)[1]), "fed": (H.FED_BIND, H.addr(H.FED_BROKER)[1])}
    for name, (host, port) in specs.items():
        if name not in which:
            continue
        pw = H.BROKER_DIR / f"{name}.passwd"
        pw.write_text("")
        pw.chmod(0o600)
        for u in users[name]:
            subprocess.run(["mosquitto_passwd", "-b", str(pw), u, H.password(u)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        acl = H.BROKER_DIR / f"{name}.acl"
        acl.write_text(acls[name])
        acl.chmod(0o600)
        conf = H.BROKER_DIR / f"{name}.conf"
        conf.write_text(CONF.format(port=port, host=host, dir=H.BROKER_DIR, name=name,
                                    user=getpass.getuser()))
        subprocess.run(["mosquitto", "-c", str(conf), "-d"], check=True, stderr=subprocess.DEVNULL)
        if not wait_port("127.0.0.1" if host == "0.0.0.0" else host, port):
            sys.exit(f"{name} broker did not start; see {H.BROKER_DIR}/{name}.log")
        print(f"{name} broker on {host}:{port} ({len(users[name])} accounts)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["start", "stop"])
    ap.add_argument("--homes", nargs="*")
    ap.add_argument("--only", choices=["home", "fed"], help="start just one of the two brokers")
    args = ap.parse_args()
    if args.action == "stop":
        stop()
        print("brokers stopped")
        return
    homes = args.homes or (H.S.SELECTED_HOMES.read_text().split() if H.S.SELECTED_HOMES.exists() else None)
    if not homes:
        sys.exit("Give --homes, or create mappings/selected_homes.txt.")
    start(homes, (args.only,) if args.only else ("home", "fed"))


if __name__ == "__main__":
    main()
