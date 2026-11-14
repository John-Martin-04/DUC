# MQTT harness v2: runs across machines

Version 2 adds what is needed to put a simulated home on a Raspberry Pi: see
"A home on a Raspberry Pi" below. On one machine it behaves like version 1.

Runs the federated system over real message brokers: sensor streams inside
each home, model updates between homes and the server. It shows that raw data
stays in the home, that gateways build the same windows as the offline
dataset, what the communication really costs, and that rounds survive
dropouts and duplicates. The large experiment grid still runs in simulation.

```
 -- household boundary (one per home) ----------+
 replay.py --> home broker --> gateway.py       |
              home/<id>/events   windows, local |
              home/<id>/labels   store, training|
 -----------------------------------------------+
                      | model updates and metrics only
                      v
            federation broker <--> coordinator.py     recorder.py logs all of it
```

| File | Role |
|---|---|
| `brokers.py` | starts two Mosquitto brokers with one account per client and access rules |
| `replay.py` | CASAS adapter: publishes a home's events and labels as a live stream |
| `gateway.py` | the federated client: dedup, windows, local SQLite store, training, predictions |
| `coordinator.py` | the server: client selection, deadlines, FedAvg, checkpoints, resume |
| `recorder.py` | logs every message that leaves a home, with sizes |
| `verify_windows.py` | checks gateway windows equal the offline dataset |
| `check_access.py` | checks a gateway cannot read or forge another home's data |
| `messages.py`, `aggregation.py`, `hconfig.py` | message formats, FedAvg maths, settings |
| `pi_bundle.py`, `pi_setup.sh`, `pi_run.sh` | pack and run one home on a Raspberry Pi |
| `server_run.sh` | laptop side of a run with a Pi |
| `scenarios/*.json` | one file per experiment: rounds, participation, dropout, seed |

Put this folder at `DUC/harnessv2`, next to `audit/` and `pipelinev2/`. It
imports the window rules, model and metric from `pipelinev2/`. The original
`harness/` and `pipeline/` folders are untouched and still work.

## Setup (once)

```bash
sudo apt install -y mosquitto
cd /mnt/d/Code/SU/PROJECTS/DUC && source .venv/bin/activate
uv pip install paho-mqtt==2.1.0
cd harness && bash run_sample.sh        # about two minutes, fake data
```

The sample run must show three `PASS ... rows identical` lines, rising F1
over six rounds, and end with "Sample run finished".

## Pilot on real homes

Five homes first. Each step in its own terminal, or use `&` as in `run_sample.sh`.

```bash
HOMES="csh101 csh103 csh107 csh119 csh123"
(cd ../pipelinev2 && python build_dataset.py --cap-days 60 --homes $HOMES --name pilot5)
DATA=../data/processed/pilot5

python brokers.py start --homes $HOMES
python gateway.py --dataset $DATA --homes $HOMES &
python recorder.py --run pilot &
python check_access.py --as-home csh101 --other csh103
python replay.py --homes $HOMES --speed 0               # a few minutes
python verify_windows.py --dataset $DATA --homes $HOMES --wait
python coordinator.py --dataset $DATA --scenario scenarios/pilot.json
kill %1 %2; python brokers.py stop
```

The dataset is rebuilt for just these homes because the model's input columns
and classes are the union over the homes in the dataset. All runners must use
the same dataset folder.

Outputs
- `results/harness/<run>/rounds.csv`: per round, updates received, mean and worst home macro-F1 of the model sent out that round, bytes down and up
- `results/harness/<run>/metrics.csv`: macro-F1 per home per round
- `results/harness/<run>/traffic.csv`, `traffic_summary.md`: every message that left a home
- `results/harness/replay_bytes.csv`: bytes of raw events per home, the cost of a centralised upload
- `data/gateways/<home>.sqlite`: each home's local store (never committed)

## A home on a Raspberry Pi

One home runs completely on the Pi: its recorded events (the "sensors"), the
home broker, the gateway and its local store. The federation broker also runs
on the Pi and is the only port open to the network. The laptop runs the
coordinator and recorder, and optionally more simulated homes, and connects
out to the Pi. Sensor traffic stays on the Pi's loopback interface, so it
cannot leave the device; only model messages cross the real network.

```
 Raspberry Pi                                   Laptop (WSL)
 replay -> home broker (127.0.0.1) -> gateway   coordinator, recorder
                    federation broker (0.0.0.0:18840) <----- network ----->  + optional local homes
```

The laptop only makes outgoing connections, so WSL needs no port forwarding.

**1. On the laptop: make the bundle.** Use a dataset that contains the Pi's home.

```bash
cd /mnt/d/Code/SU/PROJECTS/DUC/harnessv2
python pi_bundle.py --home csh101 --dataset ../data/processed/pilot5 --pi-host <the Pi's IP address>
scp bundles/pi_csh101.tar.gz <user>@<the Pi's IP address>:~
```

This also writes `duc.env` here with the Pi's address and a shared secret.
Find the Pi's address with `hostname -I` on the Pi.

**2. On the Pi: unpack, set up once, run.** Needs 64-bit Raspberry Pi OS.

```bash
tar xzf pi_csh101.tar.gz && cd DUC/harnessv2
bash pi_setup.sh          # once: Mosquitto, Python 3.11, TensorFlow; takes a while
bash pi_run.sh            # replays the home, checks the windows, then waits
```

Wait for `PASS ... rows identical` and "Home csh101 is online".

**3. On the laptop: run the server side**, with the other homes simulated locally.

```bash
bash server_run.sh ../data/processed/pilot5 scenarios/pilot.json csh103 csh107 csh119 csh123
```

Leave the home names off to run with the Pi's home alone (set `"min_clients": 1`
in the scenario). Stop the Pi's home with Ctrl+C when done.

To run everything on the laptop again, delete `harnessv2/duc.env`.

Notes
- The bundle holds one home's data, the shared label map, that home's rows of the sensor inventory, and the code the gateway needs. It holds no other home's data.
- Passwords are a shared secret plus the user name, sent unencrypted: fine on your own network, not on a public one. TLS is not set up.
- `duc.env` and `bundles/` must stay out of Git.
- Tested here with the Pi side run from an unpacked bundle on a network address; not tested on a real Pi. TensorFlow 2.14 on the Pi is the step most likely to need attention.

## How it behaves

- **Windows by event time.** Gateways use the time inside each event, so replay speed never changes the result. A window stays open 120 s of event time for out-of-order events (`--lateness`); later ones are counted as late and dropped.
- **At-least-once delivery.** QoS 1 can deliver twice; gateways drop repeats by sequence number, and the server accepts one update per home per round and ignores stale ones.
- **Deadlines.** The server aggregates what arrived by `deadline_s`. Below `min_clients` it retries the round. `dropout_p` in the scenario makes gateways skip rounds at random.
- **Metrics without data.** Each round every gateway scores the received model on its own test windows and reports only the numbers.
- **Resume.** The server saves the model after every round; `--resume` continues.
- **Labels** come on their own topic, standing in for an annotation source; sensors never carry them.

## Limits

- No TLS; passwords are a shared secret plus the user name.
- A gateway restarted in the middle of a replay starts its store again; replay again.
- Client training uses plain SGD (`client_lr`), unlike the baselines' Adam; not yet tuned on real data.
- Not yet compared number-for-number with TensorFlow Federated on the same scenario.
- FedProx, secure aggregation and differential privacy are not implemented; updates pass through `before_send()` in `gateway.py`, where they would attach.
- `--save-payloads` stores every model message; keep `results/**/payloads/` out of Git.
