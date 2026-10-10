# Bookkeeping runbooks — Kraken's statements and the tax tool's import file

You are here to run a month's bookkeeping, or because the daily pass's report listed the bookkeeping reminder as **OWED** under `## Reminders`. Nothing is wrong and nothing fired. Blockpit, the tax tool, takes the account's history from a manual-import file that `zcrypto tax blockpit` writes from Kraken's own ledger and trades exports; the exports, the file and its provenance are archived on the NAS as the audit trail.

`README.md` beside this file states what belongs in a runbook at all; a reminder names a section by file and anchor, and a procedure is found by its file and heading.

______________________________________________________________________

<a name="kraken-monthly-bookkeeping"></a>

## kraken-monthly-bookkeeping — PROCEDURE

### What you are seeing

A month has closed, and its Kraken activity is not yet in the Blockpit manual integration that holds the account's history. Each window is one directory on the NAS, `/volume1/ZhaoCrypto/kraken-statements/<start>_<end>/`, named by its UTC start date and its exclusive UTC end date; the first window runs from 2026-07-01 to 2026-11-01, and each later window is the calendar month after the newest archived one, so a month missed is run as its own window before the month after it.

### What it means

Blockpit computes FIFO per integration, so the manual integration carries the whole history and each window extends it without a gap or an overlap. One export spans the whole window — Kraken's export article states no maximum period.

### What to do

From the workstation at the repository root; `<W>` is the window's directory name and `<P>` the newest archived window's, the last name `ls /mnt/zhao-crypto/kraken-statements/` prints — for a re-run of `<W>` (step 5's last sentence), the last name it prints before `<W>`, the window before `<W>` or that window's newest sibling.

1. **Request the two exports**: `kraken export-report --report ledgers --starttm <start epoch> --endtm <end epoch>` and the same with `--report trades`, each epoch the UTC midnight of its date (`date -u -d <date> +%s`); each prints a report id.
2. **Fetch and test them** once `kraken export-status --report ledgers` and `--report trades` read each report `Processed`, before its `expiretm`: `mkdir -p data/kraken-statements/<W>`, then `kraken export-retrieve --output-file data/kraken-statements/<W>/ledgers.zip <the ledgers id>` and the same with `trades.zip` and the trades id. Test each zip with `uv run python -I -c 'import sys, zipfile; print(zipfile.ZipFile(sys.argv[1]).testzip())' <the zip>`, which checks its member's CRC and prints `None`; then `unzip` each zip there, and the directory holds two zips and two CSVs. A zip that fails its test is refused: run its retrieve again.
3. **Read the CSVs**: each CSV's data rows (`tail -n +2 <the CSV> | wc -l`) equal the `count` that `kraken ledgers -o json` and `kraken trades-history -o json` print with `--start <start epoch>` and `--end <end epoch>`, the API's start bound exclusive and its end inclusive, and its times carry a fraction of a second, so these bounds read the window's rows unless one is stamped exactly on its start or end second; and the ledger's first and last `time` lie inside the window (`head -2` and `tail -1` of each CSV). A CSV whose rows differ from the count refuses its zip: run that retrieve again.
4. **Write the import file**: `uv run zcrypto tax blockpit --ledgers data/kraken-statements/<W>/<the ledgers CSV> --trades data/kraken-statements/<W>/<the trades CSV> --out data/kraken-statements/<W>/blockpit-<W>.csv --after /mnt/zhao-crypto/kraken-statements/<P>/blockpit-<P>.csv.provenance.json` — the first window takes no `--after`. Exit 0 prints the rows per label and the closing balances. Exit 1 prints each refusal and writes nothing: a row type the mapping has not met, or an opening balance the previous window's closing does not match, is a decision for the owner, and the window waits for it.
5. **Archive the window**: `ssh nas 'mkdir -p /volume1/ZhaoCrypto/kraken-statements && mkdir /volume1/ZhaoCrypto/kraken-statements/<W>'` — a window already archived fails the second `mkdir` and stops here, an archived file being replaced by a sibling and not written over ([`nas.md#nas-file-transfer`](nas.md#nas-file-transfer) step 3) — then `scp data/kraken-statements/<W>/* nas:/ZhaoCrypto/kraken-statements/<W>/`, the path without `/volume1`, then `ssh nas 'sudo bash -s /volume1/ZhaoCrypto/kraken-statements' < infra/nas/normalize-archive-perms.sh`, so the mount's readers can open the tree, then `sha256sum /mnt/zhao-crypto/kraken-statements/<W>/*`, read through the mount: the two CSVs' and the import file's hashes equal the three `jq -r '.inputs.ledgers.sha256, .inputs.trades.sha256, .output.sha256'` prints over the provenance, and the two zips' and the provenance's equal `sha256sum data/kraken-statements/<W>/*`'s. A copy or a hash read that fails is completed in place, not removed ([`nas.md#zcrypto-nas-disk-low`](nas.md#zcrypto-nas-disk-low) step 3): run this step again from its `scp`, then the perms normalisation and the hash read — the second `mkdir` is skipped, the directory this run made, `<W>` or `<W>-r2` on a re-run, already existing, and `scp` writes over the partial files this run left. Until the copy completes, a copy interrupted after the provenance file landed reads to the daily pass as archived, and the reminder clears over the partial copy, which is why the recovery runs at once. A window run again, once step 6 or 7 stopped it and the owner ruled the change, is the sibling `<W>-r2` (then `-r3`): its directory under `data/kraken-statements/` takes the window's two zips and two Kraken CSVs, step 4 writes `blockpit-<W>-r2.csv` there, and this step archives it as `<W>-r2/`, which the next window's `<P>` then names.
6. **Import into Blockpit**: Integrations → the manual integration → the upload icon beside Sync → the Blockpit Template tab → `blockpit-<W>.csv`, once; a second upload of one file duplicates its rows, so a re-import follows the deletion of that file's rows in Blockpit, and an upload the tab refuses stops the month. Blockpit values a `Deposit` row, a crypto deposit, at market until it is labelled: label it in Blockpit from what you know of its origin, such as a Transfer from the wallet it left, which carries the acquisition date and cost.
7. **Read the balances**: in Blockpit's Ledger view of the manual integration, each asset's balance at the window's end equals the provenance's `closing` value for it (`jq .closing` on the provenance file). A difference stops the month: read that asset's transactions in the window against the import file before anything else is imported.

### Retire when

`cli/tax/blockpit.py` is absent from the repo — the transform this procedure runs.

______________________________________________________________________

<a name="kraken-bookkeeping-due"></a>

## kraken-bookkeeping-due — SCHEDULED REMINDER

### What you are seeing

The daily pass's report (`ops-daily.py report`) names `kraken bookkeeping` under `## Reminders` — `due in N days` or `OVERDUE by N days`, with the newest archived window's end date, or `no window archived yet`. The **OWED** marker in front of it, set from the due day onward, is the trigger. It is not an alert: nothing is wrong.

### What it means

The pass reads the newest `<start>_<end>` directory under `/mnt/zhao-crypto/kraken-statements/` that holds a provenance file; the next window is due on the 2nd of the month after that window's end month, and the first on 2026-11-02.

### What to do

Run [`kraken-monthly-bookkeeping`](#kraken-monthly-bookkeeping) for the owed window. The reminder clears at the next pass once the window's directory on the NAS holds its provenance file.

### Retire when

`BOOKKEEPING_RUNBOOK` is absent from `infra/scripts/ops_daily.py` — the reminder that sends you here.
