# Graph Report - AbetrisFlagSwitch  (2026-10-25)

## Corpus Check
- Corpus is ~30,672 words - fits in a single context window. You may not need a graph.

## Summary
- 482 nodes · 809 edges · 32 communities (23 shown, 9 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 18 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Feed Automation State Machine
- Abertis Feed Catalog & A-Rules
- Lamedb Rules & Mode Switching
- Automated Switching Test Suite
- Feed Catalog & TS Test Harness
- Stream Relay & Webif TS Parsing
- Plugin Logging & UI Setup
- Native C De-encapsulator
- OSCam DVBAPI Rule Installer Tests
- Enigma2 UI Skin & Widget Tests
- Abertis Architecture & Concepts
- Legacy Flag Screen UI
- Rescanned 8008 Feed Unit Tests
- Lamedb Rule & Boot Fix Tests
- Rescanned Feed Runtime Tests
- Debian Package (.deb) Builder
- IPK Package Builder
- Automated Shell Installer
- Graphify Plugin Hook
- Astra Stream Script
- SDD Plan & Constraints
- Astra Daemon Control Service
- Graphify Agent Guidelines
- Debian Postinstall Script
- Debian Pre-removal Script
- Streamrelay Channel Rules

## God Nodes (most connected - your core abstractions)
1. `_Auto2026` - 41 edges
2. `log()` - 20 edges
3. `run_full_setup()` - 20 edges
4. `autostart()` - 15 edges
5. `AutomationRobustnessTests` - 13 edges
6. `UiSkinTests` - 13 edges
7. `F5OnlyAutomationTests` - 12 edges
8. `AllFeedAutomationTests` - 11 edges
9. `_read_lines()` - 10 edges
10. `AbertisAutoSwitcherScreen` - 10 edges

## Surprising Connections (you probably didn't know these)
- `install_rule()` --indirect_call--> `ensure_oscam_dvbapi_a_rule()`  [INFERRED]
  tests/test_abertis_auto.py → AbertisAutoSwitcher/usr/lib/enigma2/python/Plugins/Extensions/AbertisAutoSwitcher/setup.py
- `install_rules()` --indirect_call--> `ensure_oscam_dvbapi_a_rules()`  [INFERRED]
  tests/test_abertis_auto.py → AbertisAutoSwitcher/usr/lib/enigma2/python/Plugins/Extensions/AbertisAutoSwitcher/setup.py
- `PID 2026 F5 Automation Plan` --references--> `SDD Implementation Ledger`  [EXTRACTED]
  docs/superpowers/plans/2026-10-21-abertis-2026-a-rule.md → .superpowers/sdd/2026-10-21-abertis-2026-a-rule/progress.md
- `_webif_zap()` --calls--> `log()`  [EXTRACTED]
  AbertisAutoSwitcher/usr/lib/enigma2/python/Plugins/Extensions/AbertisAutoSwitcher/autostart.py → AbertisAutoSwitcher/usr/lib/enigma2/python/Plugins/Extensions/AbertisAutoSwitcher/logger.py
- `sessionstart()` --calls--> `log()`  [EXTRACTED]
  AbertisAutoSwitcher/usr/lib/enigma2/python/Plugins/Extensions/AbertisAutoSwitcher/autostart.py → AbertisAutoSwitcher/usr/lib/enigma2/python/Plugins/Extensions/AbertisAutoSwitcher/logger.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Abertis Switching Pipeline Flow** — abertisautoswitcher_readme_abertis_auto_switcher_pro, abertisautoswitcher_readme_f1_learning_phase, abertisautoswitcher_readme_f5_playback_phase [EXTRACTED 1.00]

## Communities (32 total, 9 thin omitted)

### Community 0 - "Feed Automation State Machine"
Cohesion: 0.06
Nodes (32): _Auto2026, _is_url(), _parse_ref(), object, Zap a channel using a background thread (no deadlock)., Play a service through the navigation (main thread only)., True for any Ciefp Abertis URL (``/abertis/pid<number>``)., Return the PID when this URL is on the no-signal skip list. (+24 more)

### Community 1 - "Abertis Feed Catalog & A-Rules"
Cohesion: 0.06
Nodes (63): _run(), build_a_rules(), get_all_feeds(), Return every "Abertis PID <n>" feed, sorted by PID., Build the A-rules of every Abertis feed (or the supplied list)., log(), apply_all_feeds(), astra_pids() (+55 more)

### Community 2 - "Lamedb Rules & Mode Switching"
Cohesion: 0.06
Nodes (54): apply(), build_a_rule(), _build_provider(), ensure_cached_pids(), _feed_from_lines(), fix_all(), fix_disk(), _fix_name() (+46 more)

### Community 3 - "Automated Switching Test Suite"
Cohesion: 0.06
Nodes (11): autostart(), AllFeedAutomationTests, AutomationRobustnessTests, _DeadThread, F5OnlyAutomationTests, _FakeTimer, object, The learning phase plays the feed with the real PAT/PMT. (+3 more)

### Community 4 - "Feed Catalog & TS Test Harness"
Cohesion: 0.07
Nodes (13): _abertis_ts(), AllFeedCatalogTests, AllOscamRulesInstallerTests, AstraConfigGeneratorTests, install_rules(), OscamRestartTests, _pat_section(), _pmt_section() (+5 more)

### Community 5 - "Stream Relay & Webif TS Parsing"
Cohesion: 0.08
Nodes (32): _b(), _fetch_stream(), _has_cw(), _info_playing(), _oscam_cw_seen(), _oscam_path(), _oscam_size(), _parse_pat() (+24 more)

### Community 6 - "Plugin Logging & UI Setup"
Cohesion: 0.13
Nodes (13): AbertisAutoSwitcherScreen, _installed_version(), _local_packages(), main(), Plugins(), Screen, Re-apply the whole configuration (idempotent, backed up)., Compare the installed version with the packages kept on the box. (+5 more)

### Community 7 - "Native C De-encapsulator"
Cohesion: 0.26
Nodes (14): main(), complete_split_pes(), fix_pes_timestamps(), flush_held(), get_ts(), handle_pcr(), keep_add(), keep_has() (+6 more)

### Community 8 - "OSCam DVBAPI Rule Installer Tests"
Cohesion: 0.16
Nodes (3): install_rule(), OscamRuleInstallerTests, OscamSetupHardeningTests

### Community 10 - "Abertis Architecture & Concepts"
Cohesion: 0.25
Nodes (9): Abertis Auto Switcher PRO, Astra T2-MI De-encapsulator, F1 Learning Phase, F5 Playback Phase, Feed Reference Overrides, SoftCam Key Mirroring, OSCam-EMU A-Rule, Outer PMT PID Derivation (+1 more)

### Community 11 - "Legacy Flag Screen UI"
Cohesion: 0.39
Nodes (6): AbetrisFlagScreen, log(), main(), Plugins(), Screen, reload_http()

### Community 15 - "Debian Package (.deb) Builder"
Cohesion: 0.52
Nodes (6): _ar_member(), _build_control_tar(), _build_data_tar(), _control_version(), _gather_data_entries(), main()

### Community 16 - "IPK Package Builder"
Cohesion: 0.53
Nodes (5): _ar_member(), _control_version(), main(), Read the Version: field of DEBIAN/control., _tar_gz()

### Community 17 - "Automated Shell Installer"
Cohesion: 0.53
Nodes (4): die(), fetch(), say(), installer.sh script

### Community 18 - "Graphify Plugin Hook"
Cohesion: 0.47
Nodes (5): hasGraph(), location, IMPORTANT: keep the reminder string free of backticks and $(...) constructs., server(), setup()

### Community 19 - "Astra Stream Script"
Cohesion: 0.60
Nodes (4): main(), _b(), Return integer value of a byte, py2/py3 safe., _streams()

### Community 20 - "SDD Plan & Constraints"
Cohesion: 0.67
Nodes (3): SDD Implementation Ledger, PID 2026 F5 Automation Plan, Rotor Safety Constraint

## Knowledge Gaps
- **8 isolated node(s):** `location`, `Streamrelay Channels`, `Astra T2-MI De-encapsulator`, `Feed Reference Overrides`, `SoftCam Key Mirroring` (+3 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_Auto2026` connect `Feed Automation State Machine` to `Stream Relay & Webif TS Parsing`?**
  _High betweenness centrality (0.135) - this node is a cross-community bridge._
- **Why does `autostart()` connect `Automated Switching Test Suite` to `Abertis Feed Catalog & A-Rules`, `Stream Relay & Webif TS Parsing`, `Plugin Logging & UI Setup`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `UiSkinTests` connect `Enigma2 UI Skin & Widget Tests` to `Feed Catalog & TS Test Harness`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 12 inferred relationships involving `autostart()` (e.g. with `.refresh()` and `.test_2025_url_starts_with_f1_learning_and_its_own_feed()`) actually correct?**
  _`autostart()` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `location`, `Streamrelay Channels`, `Astra T2-MI De-encapsulator` to the rest of the system?**
  _8 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Feed Automation State Machine` be split into smaller, more focused modules?**
  _Cohesion score 0.06010230179028133 - nodes in this community are weakly interconnected._
- **Should `Abertis Feed Catalog & A-Rules` be split into smaller, more focused modules?**
  _Cohesion score 0.06349206349206349 - nodes in this community are weakly interconnected._