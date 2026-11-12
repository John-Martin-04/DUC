"""Check that the brokers enforce the household boundary.

Logs in as one home's gateway and tries what it must not be able to do:
read another home's sensor events, read another home's model update, and
publish an update under another home's name. Run with the brokers up.

Usage (from DUC/harness)
  python check_access.py --as-home csh101 --other csh102
"""

from __future__ import annotations

import argparse
import sys
import time

import hconfig as H


def listen(user: str, broker: tuple[str, int], topics: list[str], cid: str):
    got: list[str] = []
    c = H.client(user, cid)
    c.on_connect = lambda c, u, f, rc, p: c.subscribe([(t, 1) for t in topics])
    c.on_message = lambda c, u, m: got.append(m.topic)
    c.connect(*broker)
    c.loop_start()
    return c, got


def send(user: str, broker: tuple[str, int], topic: str, cid: str) -> None:
    c = H.client(user, cid)
    c.connect(*broker)
    c.loop_start()
    c.publish(topic, b"probe", qos=1).wait_for_publish(timeout=5)
    time.sleep(0.3)
    c.loop_stop()
    c.disconnect()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-home", required=True)
    ap.add_argument("--other", required=True)
    a = ap.parse_args()
    me, other = a.as_home, a.other
    home_b, fed_b = H.home_broker(other), H.addr(H.FED_BROKER)

    spy_home, got_home = listen(me, home_b, ["home/#"], "probe-spy-home")
    spy_fed, got_fed = listen(me, fed_b, ["fl/#"], "probe-spy-fed")
    server, got_server = listen("coordinator", fed_b, ["fl/round/+/update/+"], "probe-server")
    time.sleep(1)
    send("replay", home_b, f"home/{other}/probe", "probe-p1")          # another home's sensor event
    send("replay", home_b, f"home/{me}/probe", "probe-p2")              # control: own namespace
    send(other, fed_b, f"fl/round/0/update/{other}", "probe-p3")        # another home's update
    send(me, fed_b, f"fl/round/0/update/{other}", "probe-p4")           # forged update
    send(me, fed_b, f"fl/round/0/update/{me}", "probe-p5")              # control: own update
    time.sleep(1)
    for c in (spy_home, spy_fed, server):
        c.loop_stop()
        c.disconnect()

    checks = [
        (f"{me} cannot read {other}'s home topics", f"home/{other}/probe" not in got_home),
        (f"{me} can read its own home topics", f"home/{me}/probe" in got_home),
        (f"{me} cannot read {other}'s model update", not any("/update/" in t for t in got_fed)),
        (f"{me} cannot publish an update as {other}",
         got_server.count(f"fl/round/0/update/{other}") == 1),
        (f"{me} can publish its own update", f"fl/round/0/update/{me}" in got_server),
    ]
    for text, ok in checks:
        print(("PASS  " if ok else "FAIL  ") + text)
    sys.exit(0 if all(ok for _, ok in checks) else 1)


if __name__ == "__main__":
    main()
