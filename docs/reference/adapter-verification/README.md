# Adapter verification records

One file per `nautilus_trader` version whose **attended order-semantics pass** actually ran against the live Kraken account, named for the exact version string the interpreter reports.

The series is a maintenance obligation rather than a phase's research: every bump owes one, indefinitely, long after the phase that introduced the requirement is history. That is why these live under `reference/` and carry no phase prefix or serial.

**`cli/engine/order-semantics-verified.json` is the index.** It maps each version to its record here, and it is the file both arming guards read — the engine Ansible role refuses a converge rendering `exec_armed=true` on a version absent from it, and `cli.engine.execgate` refuses the gate at runtime when the running interpreter's version is absent. Keeping the mapping there rather than repeating it here is deliberate: one file, two readers, no second list to drift.

The procedure that produces a record is `infra/runbooks/order-semantics-verification.md`; the harness it drives is `infra/scripts/kraken-order-semantics-probe.py`.
