# CASAS dataset audit: starter kit

Phase 1 of the project: decide which CASAS homes become federated clients,
and build the shared sensor schema and label set. The output is the audit
report (template in `reports/AUDIT_REPORT_TEMPLATE.md`), due at the
6 November seminar.

```
config.py                  thresholds and paths (fix these before profiling)
scripts/parse_casas.py     raw event files -> one table per home
scripts/profile_homes.py   size, sensors, label coverage, gaps, quality flags
scripts/inventory.py       every raw label and sensor, for the mappings
scripts/feasibility.py     windows per class per split -> which homes and classes work
mappings/label_map.csv     DRAFT raw label -> shared label (edit this)
tests/make_sample_data.py  fake data in both CASAS layouts, for testing
run_sample.sh              runs everything on the fake data
env/check_tff.py           checks a TensorFlow Federated install
```

## 0. Set up and test (15 minutes)

The environment is not in the zip on purpose: environments are tied to one
machine, are large, and are never shipped or committed. You create it once.

Use ONE environment for the whole project, at the root of the repository
(not inside `audit/`), on Linux or WSL2. It holds both the audit scripts and
TensorFlow Federated. This exact combination was tested: TFF 0.87.0,
TensorFlow 2.14.1, NumPy 1.25.2, pandas 2.2, pyarrow 17.

```bash
cd /mnt/d/Code/SU/PROJECTS/DUC                     # your repository, in WSL
curl -LsSf https://astral.sh/uv/install.sh | sh    # installs uv; then reopen the terminal
uv venv -p 3.11 .venv                               # uv fetches Python 3.11 if needed
source .venv/bin/activate                           # every time you open a terminal
uv pip install -r audit/requirements.txt "tensorflow-federated==0.87.0" \
    --override audit/env/tff-overrides.txt
cd audit
./run_sample.sh                                     # should end with "3 of 3 homes pass"
python env/check_tff.py                             # should end with "TFF environment OK"
```

Do not `pip install` other packages into this environment without pinning
`numpy==1.25.2`: anything that pulls in NumPy 2 breaks TensorFlow.

The sample run writes to `sample_run/` and should end with "3 of 3 homes
pass". It also shows every kind of flag the real audit can raise: the fake
data has an unmatched `end` marker, overlapping activities, a 25-hour gap, a
sensor that dies early, battery messages and an unmapped label.

## 1. Get the data

Put everything under `data/raw/` and never edit those files.

**Pilot: Zenodo release, 4 homes, 33 MB.** Start here; it downloads in
seconds.
- https://zenodo.org/records/17180309 → `new_labeled_data.zip`
- Check the download: MD5 must be `86954063e1d2099d288f59227b19a749`
  (`md5sum` on Linux, `md5` on macOS, `certutil -hashfile FILE MD5` on Windows).
- Floor plans and site information are in the companion record
  https://zenodo.org/records/15708568. You need them to give each sensor a room.
- Use Aruba (1 resident) and Milan (1 resident and a pet). Cairo and Tulum have
  two residents; profile them, but expect to exclude them.

**Main: UCI release (dataset 506), about 30 homes, 13 GB zipped.** Start the
download now; it takes a while.
- https://archive.ics.uci.edu/dataset/506/human+activity+recognition+from+continuous+ambient+sensor+data
- List the archive before extracting: `unzip -l FILE.zip | less`. You only need
  the raw annotated event files (one per home, named like `csh101.ann.txt`);
  skip the large feature CSVs. Extract by pattern, for example
  `unzip FILE.zip '*ann.txt' -d data/raw/uci`. Adjust the pattern to the names
  the listing shows.

Write `data/raw/SOURCES.md`: URL, download date, checksum, licence (CC BY 4.0)
and the citation (Cook et al., 2013).

## 2. Look before you parse

Open the first lines of one file from each release:

```bash
head -5 data/raw/uci/csh101/csh101.ann.txt
head -5 data/raw/zenodo/<home file>
```

The parser expects:
- UCI: 8 fields, `date time sensor location location message sensor_type activity`
- Zenodo/classic: `date time sensor value`, sometimes followed by `Label begin` or `Label end`

If a file looks different, stop and adjust the parser before going further.

## 3. Parse

```bash
python scripts/parse_casas.py --glob "data/raw/uci/**/*.ann.txt"
python scripts/parse_casas.py --home aruba data/raw/zenodo/<aruba file>
python scripts/parse_casas.py --home milan data/raw/zenodo/<milan file>
```

Check `reports/parse_log.csv`. Bad lines should be close to zero. In classic
files, `unmatched_end`, `unclosed_begin` and `repeated_begin` show broken
begin/end markers: a missing `end` labels everything after it until the next
`begin`, so a home with many of these needs a closer look.

## 4. Profile

```bash
python scripts/profile_homes.py
```

Read `reports/audit_profile.md` and `reports/home_summary.csv`. Then fill in
`mappings/home_metadata.csv` (residents, pets) from the dataset documentation;
the data cannot tell you this.

## 5. Build the mappings

```bash
python scripts/inventory.py
```

- **Labels.** `mappings/raw_labels.csv` lists every raw label and whether it is
  mapped. Add each UNMAPPED one to `mappings/label_map.csv`. The draft follows
  Zehtabian et al. (2021), with cooking split out of chores. `exclude` drops a
  label; `other` keeps it as "not a target activity".
- **Sensors.** `mappings/sensor_inventory.csv` has a `room` column. For UCI
  homes it is pre-filled from the location fields; for Zenodo homes, fill it
  from the floor plans. Set `keep` to `no` for sensors you drop (dead,
  irrelevant), with a note.

Run `inventory.py` again until nothing is unmapped.

## 6. Check feasibility

```bash
python scripts/feasibility.py
python scripts/feasibility.py --drop-other     # the same without the 'other' class
```

`reports/feasibility.md` proposes which classes to keep (present in enough
homes' test periods) and which homes pass. Classes and homes depend on each
other: if you drop homes, run it again, since a class may then fall below
the threshold.

## 7. Decide and write it up

Fill in `reports/AUDIT_REPORT_TEMPLATE.md`: the homes you keep and exclude
(with reasons), the shared sensor schema, the shared label set, how you treat
'Other' and unlabelled time, and open questions. That document is the
phase 1 deliverable, and section 5 of it goes straight into the methods
chapter of the report.

## TFF environment (also a phase 1 milestone)

The audit scripts run anywhere. TensorFlow Federated does not:

- The current release, **0.87.0, only installs on Linux x86_64 with Python
  3.9 to 3.11**. On macOS, Windows or Python 3.12+, `pip` silently falls back
  to version 0.33.0 from 2022, which is useless.
- It pins `jax`/`jaxlib` 0.4.14, which has been **removed from PyPI**, so a
  plain `pip install tensorflow-federated` fails even on Linux.

The setup in step 0 handles both problems (about 2.5 GB). `check_tff.py`
prints "Hello, World!" and five FedAvg rounds when it works.

- **Windows:** use WSL2 (Ubuntu), then the recipe above.
- **macOS:** use a Linux machine (a DSV lab computer or a cloud VM), or
  Docker with `env/Dockerfile` (untested; slow under emulation on Apple Silicon).
- After the script ends, TFF can leave a `worker_binary` process behind that
  holds the terminal open. If a command seems to hang after finishing, kill it.

## Rules worth keeping

- Fix the thresholds in `config.py` before you profile; record every later
  change and why. Otherwise the home selection gets tuned to the results.
- Never edit raw files. Every correction lives in a mapping file or in code.
- Keep `data/` out of Git; commit code, mappings and reports. The
  `.gitignore` belongs at the repository root (move it there from `audit/`);
  its patterns apply to every subfolder.
