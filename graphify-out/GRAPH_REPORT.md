# Graph Report - AbetrisFlagSwitch  (2026-10-21)

## Corpus Check
- Corpus is ~10,370 words - fits in a single context window. You may not need a graph.

## Summary
- 279 nodes · 455 edges · 22 communities (15 shown, 7 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 4 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output
- Token-usage caveat: the semantic extraction agent did not expose usage counts; 0/0 are placeholders, not measured totals.

## Community Hubs (Navigation)
- 2026 Automation State Machine
- Abertis System Overview
- TS Parsing and Webif Utilities
- lamedb Rules and Reload
- Plugin Startup and Services
- 2026 PID and Service Rules
- Astra T2-MI Packaging
- Plugin Control UI
- Legacy Flag-Switch UI
- Abertis Stream Tool
- Oscam and BISS Acquisition
- IPK Builder
- Graphify OpenCode Hook
- Package Postinstall
- Package Removal Script
- Plugin Menu Actions
- Plugin Logging
- Setup Automation

## God Nodes (most connected - your core abstractions)
1. `_Auto2026` - 34 edges
2. `log()` - 15 edges
3. `AbetrisAutoScreen` - 11 edges
4. `Abertis Auto v1.2` - 11 edges
5. `apply()` - 9 edges
6. `run_full_setup()` - 9 edges
7. `set_streamrelay_service()` - 8 edges
8. `Automatic F1-to-F5 streamrelay switching state machine` - 8 edges
9. `_is_url()` - 7 edges
10. `_oscam_found()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `_webif_zap()` --calls--> `log()`  [EXTRACTED]
  AbetrisAuto/usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto/autostart.py → AbetrisAuto/usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto/logger.py
- `_streamrelay_pids()` --calls--> `set_streamrelay_service()`  [EXTRACTED]
  AbetrisAuto/usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto/autostart.py → AbetrisAuto/usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto/lamedb_fix.py
- `reload_edvbdb()` --calls--> `log()`  [EXTRACTED]
  AbetrisAuto/usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto/lamedb_fix.py → AbetrisAuto/usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto/logger.py
- `run_full_setup()` --calls--> `fix_all()`  [EXTRACTED]
  AbetrisAuto/usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto/setup.py → AbetrisAuto/usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto/lamedb_fix.py
- `_run()` --calls--> `log()`  [EXTRACTED]
  AbetrisAuto/usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto/autostart.py → AbetrisAuto/usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto/logger.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Abertis Services Managed by the Prestart Fix** — abetrisauto_readme_prestart_fix_py, abetrisauto_readme_service_8001, abetrisauto_readme_service_2026, abetrisauto_readme_service_2050 [EXTRACTED 1.00]
- **Automatic F1-to-F5 Playback Sequence** — abetrisauto_readme_automatic_switching_sequence, abetrisauto_readme_sequence_step_1_feed_f1, abetrisauto_readme_sequence_step_2_zap_feed, abetrisauto_readme_sequence_step_3_stop_feed, abetrisauto_readme_sequence_step_4_restore_f5, abetrisauto_readme_sequence_step_5_read_astra_pmt, abetrisauto_readme_sequence_step_6_zap_streamrelay [EXTRACTED 1.00]
- **One-Time Manual Prerequisites** — abetrisauto_readme_manual_prerequisites, abetrisauto_readme_astra_sm, abetrisauto_readme_astra_conf, abetrisauto_readme_softcam_key, abetrisauto_readme_oscam_dvbapi_streamrelay_config, abetrisauto_readme_abertis_channel_list_provider [EXTRACTED 1.00]

## Communities (22 total, 7 thin omitted)

### Community 0 - "2026 Automation State Machine"
Cohesion: 0.10
Nodes (14): _Auto2026, _info_playing(), _is_url(), Key of a service reference: only the url part. The plugin zaps the channel with…, Fast path. Polling remains the reliable fallback., Reload the service list without freezing the user interface. The webif…, Stop the feed playback (only used to release the timeshift). Playing a DVB…, All feeds back to F5 (cached pids) and reload. In F5 the streamserver (astra's… (+6 more)

### Community 1 - "Abertis System Overview"
Cohesion: 0.07
Nodes (40): Abertis Auto v1.2, Abertis channel list in lamedb with provider ABERTIS, AbetrisFlagSwitch, Working /etc/astra/astra.conf, Astra output as a normal single-program transport stream, astra-sm prerequisite, Automatic F1-to-F5 streamrelay switching state machine, autostart.py (+32 more)

### Community 2 - "TS Parsing and Webif Utilities"
Cohesion: 0.07
Nodes (34): _b(), _has_cw(), _oscam_cw_cached(), _oscam_found(), _oscam_path(), _oscam_size(), _parse_pat(), _parse_pmt() (+26 more)

### Community 3 - "lamedb Rules and Reload"
Cohesion: 0.09
Nodes (34): apply(), _build_provider(), ensure_cached_pids(), fix_all(), fix_disk(), _fix_name(), get_feed_ref(), _parse_sid_line() (+26 more)

### Community 4 - "Plugin Startup and Services"
Cohesion: 0.12
Nodes (27): autostart(), WHERE_SESSIONSTART variant: guarantees a real session/nav object., _run(), sessionstart(), log(), main(), Plugins(), sessionstart() (+19 more)

### Community 5 - "2026 PID and Service Rules"
Cohesion: 0.11
Nodes (22): Abertis PID 2026 feed, Astra log /var/log/messages; search for Abertis PID 2026, Cached PMT PID used in the F1 step, Abertis feed data PID, F1 feed state, /etc/enigma2/lamedb, /etc/enigma2/lamedb.2026_auto.bak, state before the first F1 step, /etc/enigma2/lamedb.abertis.bak, original lamedb backup created once (+14 more)

### Community 6 - "Astra T2-MI Packaging"
Cohesion: 0.18
Nodes (11): Abertis T2-MI de-encapsulator at /etc/astra/scripts/abertis, armhf Abertis binary, Astra streamserver input, Keep an existing aarch64 binary; install the bundled binary when the tool is missing or is an armhf binary, Bundled aarch64 binary abertis.aarch64, Clear transport stream of the channel, DEBIAN control, postinst, and prerm, enigma2-plugin-extensions-abertisauto_1.2_all.ipk (+3 more)

### Community 8 - "Legacy Flag-Switch UI"
Cohesion: 0.39
Nodes (6): AbetrisFlagScreen, log(), main(), Plugins(), Screen, reload_http()

### Community 9 - "Abertis Stream Tool"
Cohesion: 0.60
Nodes (4): _b(), main(), Return integer value of a byte, py2/py3 safe., _streams()

### Community 10 - "Oscam and BISS Acquisition"
Cohesion: 0.40
Nodes (5): BD2 feed transponder at 11222H, Current Abertis BISS key, oscam, CW evidence log /tmp/oscam.log; search for 0BD2 and found, Step 2: zap the feed at BD2 11222H so oscam requests the BISS key

### Community 11 - "IPK Builder"
Cohesion: 0.83
Nodes (3): _ar_member(), main(), _tar_gz()

## Knowledge Gaps
- **37 isolated node(s):** `Dreambox Two 4K`, `Enigma2 5.0`, `Enigma2 7.x`, `Hispasat 30W / 11222H`, `systemd ExecStartPre` (+32 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_Auto2026` connect `2026 Automation State Machine` to `TS Parsing and Webif Utilities`?**
  _High betweenness centrality (0.104) - this node is a cross-community bridge._
- **Why does `AbetrisAutoScreen` connect `Plugin Control UI` to `Plugin Startup and Services`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Why does `Abertis Auto v1.2` connect `Abertis System Overview` to `Astra T2-MI Packaging`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **What connects `Dreambox Two 4K`, `Enigma2 5.0`, `Enigma2 7.x` to the rest of the system?**
  _37 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `2026 Automation State Machine` be split into smaller, more focused modules?**
  _Cohesion score 0.09523809523809523 - nodes in this community are weakly interconnected._
- **Should `Abertis System Overview` be split into smaller, more focused modules?**
  _Cohesion score 0.06666666666666667 - nodes in this community are weakly interconnected._
- **Should `TS Parsing and Webif Utilities` be split into smaller, more focused modules?**
  _Cohesion score 0.07307692307692308 - nodes in this community are weakly interconnected._
