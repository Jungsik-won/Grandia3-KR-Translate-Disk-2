# Build cleanup — 2026-08-25

## Result

- Before cleanup: approximately 123 GB under `build/`.
- Moved out of the project: approximately 111 GB in 47 obsolete or superseded build directories.
- Remaining under `build/`: approximately 12 GB.
- Recovery location: `/Users/j.swon/.Trash/Grandia3_KR_build_cleanup_20260825/`
- Removal method: same-volume move to Trash; no permanent deletion was performed.

## Preserved active/evidence directories

- `central-runtime-cumulative-v8`
- `central-runtime-relocation-v8`
- `investigation`
- `npc_dialogue`
- `runtime-audit-20260825`
- `scenario`
- `movie-overlay-safe-probe`
- `movie-overlay-test`
- `font-proof-free`
- `font-system-fixed-20260823-audit`
- `item-codec-research`
- `runtime-tests`

`central-runtime-cumulative-v8/replacement-plan.json` was checked after cleanup:
all 350 replacement paths exist, and its `scenario` link still resolves to
`central-runtime-relocation-v8`.

## Moved build generations

- Superseded central font scaffold/audit/integration directories (`central-font-base32-v1-*`, `central-font-final-v1-*`)
- Superseded integration/runtime generations (`central-integration-v1`, `central-runtime-base32-v1`, `central-runtime-full-v1`, `central-runtime-npc-final-v1`)
- Superseded cumulative generations v5-v7
- Superseded fix/recovery/repair generations
- Relocation generations v1-v7, including aborted, partial, pre-priority-fix, and overflow experiments
- `final-test-scenario-v1`
- `font-proof-all` and its historical ISO candidates
- `system-menu-spacing`

The moved data remains recoverable until the macOS Trash is emptied. Disk space is
not fully reclaimed while the recovery directory remains in Trash.
