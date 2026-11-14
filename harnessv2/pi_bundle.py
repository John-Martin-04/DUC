"""Pack everything one simulated home needs to run on a Raspberry Pi.

The Pi then holds that home completely: its recorded events (the "sensors"),
the home broker, the gateway and its local store. The federation broker also
runs on the Pi and is the only thing reachable from the network; the
coordinator and recorder on the laptop connect to it. Sensor traffic stays on
the Pi's loopback interface and cannot leave the device.

Creates
  bundles/pi_<home>.tar.gz   copy to the Pi and unpack
  duc.env                    this machine's network settings (Pi address, shared secret)

Usage (from DUC/harnessv2, on the laptop)
  python pi_bundle.py --home csh101 --dataset ../data/processed/pilot5 --pi-host 192.168.1.50
"""

from __future__ import annotations

import argparse
import io
import json
import secrets
import tarfile
from pathlib import Path

import pandas as pd

import hconfig as H

S = H.S
CODE = ["audit/config.py", "audit/scripts/utils.py"]
PI_FILES = ["hconfig.py", "messages.py", "gateway.py", "replay.py", "brokers.py", "verify_windows.py",
            "check_access.py", "pi_setup.sh", "pi_run.sh", "requirements-pi.txt"]
PIPE_FILES = ["settings.py", "windows.py", "common.py"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", required=True)
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--pi-host", required=True, help="the Pi's IP address or hostname on your network")
    args = ap.parse_args()

    repo = S.REPO
    dataset = args.dataset.resolve()
    schema = json.loads((dataset / "schema.json").read_text())
    if args.home not in schema["homes"]:
        raise SystemExit(f"{args.home} is not in dataset {schema['name']}: {schema['homes']}")
    rel = lambda p: str(Path(p).resolve().relative_to(repo))

    env = H.ROOT / "duc.env"
    secret = None
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("DUC_SECRET="):
                secret = line.split("=", 1)[1].strip()
    secret = secret or secrets.token_hex(12) + "-"
    fed_port = H.addr(H.FED_BROKER)[1]

    out = H.ROOT / "bundles"
    out.mkdir(exist_ok=True)
    path = out / f"pi_{args.home}.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        def add_file(src: Path, arc: str) -> None:
            tar.add(src, arcname=f"DUC/{arc}")

        def add_text(text: str, arc: str, mode: int = 0o644) -> None:
            data = text.encode()
            info = tarfile.TarInfo(f"DUC/{arc}")
            info.size, info.mode = len(data), mode
            tar.addfile(info, io.BytesIO(data))

        for f in CODE:
            add_file(repo / f, f)
        for f in PIPE_FILES:
            add_file(repo / "pipelinev2" / f, f"pipelinev2/{f}")
        for f in PI_FILES:
            add_file(H.ROOT / f, f"harnessv2/{f}")
        # Label map(s) and only this home's rows of the sensor inventory.
        for lm in {S.audit.MAPPINGS_DIR / "label_map.csv", S.audit.SHARED_LABEL_MAP}:
            if lm.exists():
                add_file(lm, rel(lm))
        inv = pd.read_csv(S.INVENTORY, dtype=str, keep_default_na=False)
        add_text(inv[inv["home"] == args.home].to_csv(index=False), rel(S.INVENTORY))
        # The home's recorded events (its "sensors") and its rows of the dataset (for the check).
        add_file(S.EVENTS_DIR / f"{args.home}.parquet", rel(S.EVENTS_DIR / f"{args.home}.parquet"))
        add_file(dataset / "schema.json", f"{rel(dataset)}/schema.json")
        add_file(dataset / f"{args.home}.parquet", f"{rel(dataset)}/{args.home}.parquet")
        # The Pi's settings: sensor traffic local only, federation broker on the network.
        add_text("\n".join([
            f"DUC_SECRET={secret}", "DUC_HOME_BIND=127.0.0.1", "DUC_FED_BIND=0.0.0.0",
            f"PI_HOME={args.home}", f"PI_DATASET=../{rel(dataset)}",
            f"PI_ALL_HOMES={','.join(schema['homes'])}",
            *(["AUDIT_SAMPLE=1"] if S.SAMPLE else []), ""]), "harnessv2/duc.env", 0o600)

    env.write_text(f"# Network settings for the laptop side. Delete this file to run everything locally again.\n"
                   f"DUC_SECRET={secret}\nDUC_FED_BROKER={args.pi_host}:{fed_port}\n")
    env.chmod(0o600)
    print(f"Bundle: {path} ({path.stat().st_size / 1e6:.1f} MB)")
    print(f"Laptop settings written to {env} (federation broker at {args.pi_host}:{fed_port})")
    print("Next: copy the bundle to the Pi, unpack it, and run pi_setup.sh then pi_run.sh there.")


if __name__ == "__main__":
    main()
