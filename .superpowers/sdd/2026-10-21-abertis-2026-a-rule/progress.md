# SDD ledger — plan: docs/superpowers/plans/2026-10-21-abertis-2026-a-rule.md

Ruling: Execute in the provided workspace — the environment reports that `D:\AbetrisFlagSwitch` is not a Git repository, so a Git worktree, BASE commits, and commit-range task scripts are unavailable; changes remain local and no commits/deployment will be attempted — cost if wrong: work is not isolated by Git and must be reviewed carefully against pre-existing user files.

Pre-flight: Task 1 produces `setup.ensure_oscam_dvbapi_a_rule()` and guarded `setup.restart_oscam()` consumed by `setup.run_full_setup()`; Task 2 consumes `lamedb_fix.set_2026_mode("f5")` and changes only the 2026 state machine; Task 3 tests the PMT parser/reference behavior in the same `autostart.py`. No cross-task interface mismatch found.

Task 1: complete (tests: `python -m unittest discover -s tests -v` → 9/9 pass; RED observed first; no Git commit possible in this non-repository workspace).

Task 2: complete (tests: `python -m unittest discover -s tests -v` → 14/14 pass; RED observed first for every new test).

Task 2: Ruling: remove automatic restoration to `previous_ref` on failure — the receiver uses a manual motor and a previous service may be at another orbital position; avoiding an automatic zap enforces the rotor-safety constraint — cost if wrong: after a failed playback attempt, the receiver may remain on the 2026 URL/feed until the user manually selects another service.

Task 3: complete (tests: `python -m unittest discover -s tests -v` → 18/18 pass; `python build_ipk.py` → enigma2-plugin-extensions-abertisauto_1.3_all.ipk, data.tar.gz contains only the plugin python files + abertis.aarch64, no astra.conf / softcam.key / OSCam binary).

Task 3: Ruling: the PAT/PMT parser now uses the existing `_b()` byte helper instead of `ord()` so the same code works on DreamOS Python 2.7 and on Python 3 (where the local tests run) — cost if wrong: none; the decoded values are identical on Python 2.

Task 3: Ruling: the package installs the A-rule from `DEBIAN/postinst` as well as from the boot-time setup, both through `setup.ensure_oscam_dvbapi_a_rule()`; the postinst call is wrapped in `|| true` so a failed OSCam restart can never fail the package installation — cost if wrong: the rule may be installed slightly later than the plugin boot sequence on a box where the postinst python invocation fails silently.

Final review: fresh reviewer subagent (whole-change review, no git diff available — it read the current files, the plan, this ledger and the built IPK). Findings and dispositions:

Fixed (each with a failing test first, RED->GREEN, suite 31/31 green):
- Critical C-1 sync-failure branch looped forever (the re-zap reset the attempt counter) and left `busy` set: added `sync_cycles`, a `_sync_failed()` helper and `_give_up()`; the sequence now ends instead of looping.
- Important I-1 `_go_f5` ignored a failed lamedb write: an "ERROR ..." message now aborts the sequence with `_finish(False)`.
- Important I-2 the TS parser assumed a 188-byte aligned HTTP body: `_ts_offset()` finds the packet alignment first.
- Important I-3 `ensure_softcam_key` truncated the user's key file when the read failed: it now fails closed (`_read_text`) and writes atomically.
- Important I-4 an installed A-rule was never reloaded when OSCam is not a systemd unit: `restart_oscam()` falls back to `/etc/init.d/oscam|softcam`.
- Important I-5 the OSCam unit match was a loose substring ("backup-oscam.service" matched): only units whose name starts with "oscam" are considered.
- Important I-6 a pre-existing directive for 0BD2 would shadow the new rule: the installer reports it in the log/message.
- Important I-7 the dvbapi append was not atomic: the file is now written through a temp file + rename.
- Important I-8 `_verify` reported success when the webif was unreachable: it now requires a real measurement.
- Important I-9 `nav.playService()` ran inside a worker thread: the navigation fallback moved to the main thread (`_nav_zap` called from `_tick`).
- Test quality T-1/T-2/T-3: the three weak tests now assert the real behaviour (state sequence, `set_2026_mode("f5")`, `_zap_async`/`_webif_zap` not called) instead of mocking names that no longer exist.
- Minors M-1/M-2/M-3/M-5/M-6/M-13/M-14/M-15/M-17/M-18 and the README wording M-9/M-10: duplicate methods removed, dead state removed, uninitialised attributes initialised, the disable marker now makes `run_now()` a no-op, the UI title says v1.3, the postinst heredoc is guarded, the IPK builder refuses entries outside the plugin dir and checks the control version, the lamedb rewrite keeps the original file mode, the service-name regex is case-insensitive, the README no longer over-claims.

Final: minor (deferred): `_parse_ref` maps reference field 6 to `onid` although the Ciefp list puts the data PID there (pre-existing; the streamrelay lamedb entry keeps that value — playback is sid driven).
Final: minor (deferred): `ensure_oscam_abertis()` is dead code (never called); the oscam-emu reader for caid 2600 is documented as a manual prerequisite instead of being created automatically (creating a second reader could break the working configuration).
Final: minor (deferred): `ensure_abertis_script` replaces an armhf binary with the aarch64 one (pre-existing behaviour, the target box is aarch64).
Final: minor (deferred): `DEFAULT_ASTRA_CONF` describes a 11739 MHz transponder while the feed is BD2 @ 11222H (only used when astra.conf is missing, which is not the case on the target box).
Final: minor (deferred): the plugin UI updates widgets from a worker thread (pre-existing Enigma2 pattern).

Verification on the target (read-only, no deployment): the new plugin files were copied to /tmp on the Dreambox, `python -m py_compile` passed under Python 2.7.13, and `ensure_oscam_dvbapi_a_rule()` returned `(True, False, 'OSCam A-rule already present; config kept')` — the live `oscam.dvbapi` (md5 ad18802f6f36e2c19eba89ab5ed1e9e1) was not modified, no OSCam restart was triggered, and the /tmp copy was removed afterwards.

