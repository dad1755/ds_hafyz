# S12 evidence — Docker hardening and recovery

Every file here is a verbatim command transcript, captured on `ridergami2` against the live
`aihubcampus` Compose project. Nothing is retyped from memory. Where a check is a *negative*
(the restore guard refusing the live volume), the refusal itself is the evidence.

| File | What it is | Reproduce with |
|---|---|---|
| `build.txt` | the hardened image building from a digest-pinned base | `docker compose build web` |
| `restart.txt` | before/after of a real `--force-recreate`: same row counts, same artifact sha256, hardening now applied | `bash evidence/s12/restart.sh` |
| `backup.txt` | a backup of the live **hardened** stack: snapshot, streamed out and checksum-verified, self-verification of its own tarball | `scripts/backup.sh` |
| `roundtrip.txt` | live DB → volume copy → backup → restore into a disposable volume and a directory; three-way row-count compare; the three refusals of the live volume | see the section headings inside |
| `smoke_test.txt` | the 15 checks against the running container | `scripts/smoke_test.sh` |
| `secrets.txt` | the secret-pattern scan over the tree | `python3 scripts/check_no_secrets.py` |
| `fresh_clone.txt` | a fresh `git clone` of the branch + CSV + `.env` → build → run → health 200 | `bash evidence/s12/fresh_clone.sh` |
| `release_gate.txt` | `scripts/verify_release.sh` verdict table | `scripts/verify_release.sh --build` |
| `restart.sh` | the script that produced `restart.txt` | — |
| `fresh_clone.sh` | the script that produced `fresh_clone.txt` | — |

## What each acceptance item maps to

| Acceptance (issue) | Where |
|---|---|
| fresh-checkout build+run quoted (image id, health 200) | `fresh_clone.txt` |
| restart persistence proven with before/after row counts | `restart.txt` |
| restore round-trip proven with a checksum compare on the disposable copy | `roundtrip.txt` |
| zero host ports published | `smoke_test.txt` (`docker port` empty, `PortBindings={}`), `restart.txt` |
| every script the runbook references exists | `release_gate.txt` (`docs name real files`) |

## Notes on method

- The **fresh clone** is built and run as its own container with `--network none` and a
  throwaway volume: it cannot collide with the live stack's network, volume or port, and it
  publishes nothing. The health probe therefore runs *inside* that container. Building a second
  Compose project on this host would be a stream-isolation violation, so the fresh clone is
  built with `docker build` and run with `docker run`.
- The **restore** never targets `aihubcampus_app_storage`. It targets
  `aihubcampus-s12-restored` (a fresh disposable volume) and `/tmp/restore-check` (a directory).
  The live database's sha256 is printed before and after the attempts to show it did not move.
- The **backup** is taken while the service is running and healthy — the snapshot is one read
  transaction, so no downtime is needed and none was taken.
