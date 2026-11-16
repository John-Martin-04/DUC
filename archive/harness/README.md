# MQTT harness

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
| `scenarios/*.json` | one file per experiment: rounds, participation, dropout, seed |

Put this folder at `DUC/harness`, next to `audit/` and `pipeline/`. It imports
the window rules, model and metric from `pipeline/`, so replace `pipeline/`
with the version shipped alongside (it adds `windows.py`).

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
(cd ../pipeline && python build_dataset.py --cap-days 60 --homes $HOMES --name pilot5)
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

## How it behaves

- **Windows by event time.** Gateways use the time inside each event, so replay speed never changes the result. A window stays open 120 s of event time for out-of-order events (`--lateness`); later ones are counted as late and dropped.
- **At-least-once delivery.** QoS 1 can deliver twice; gateways drop repeats by sequence number, and the server accepts one update per home per round and ignores stale ones.
- **Deadlines.** The server aggregates what arrived by `deadline_s`. Below `min_clients` it retries the round. `dropout_p` in the scenario makes gateways skip rounds at random.
- **Metrics without data.** Each round every gateway scores the received model on its own test windows and reports only the numbers.
- **Resume.** The server saves the model after every round; `--resume` continues.
- **Labels** come on their own topic, standing in for an annotation source; sensors never carry them.

## Limits

- Passwords are derived from user names and there is no TLS: fine on one machine, not for real devices.
- A gateway restarted in the middle of a replay starts its store again; replay again.
- Client training uses plain SGD (`client_lr`), unlike the baselines' Adam; not yet tuned on real data.
- Not yet compared number-for-number with TensorFlow Federated on the same scenario.
- FedProx, secure aggregation and differential privacy are not implemented; updates pass through `before_send()` in `gateway.py`, where they would attach.
- `--save-payloads` stores every model message; keep `results/**/payloads/` out of Git.
