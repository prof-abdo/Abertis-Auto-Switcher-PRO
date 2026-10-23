# Abertis Auto Switcher PRO 1.9.12 - all Abertis feeds on DreamOS 2.6

Automatic setup and playback for the Abertis / Ciefp `streamrelay` channels
on Hispasat 30W, written for DreamOS 2.6 (Enigma2 5.0, Python 2.7).
Based on `AbetrisFlagSwitch` by mouadhada (tunisia-sat), generalized to every
`Abertis PID <n>` feed instead of three hard-coded channels.

## What the plugin does

### One-time / boot setup (idempotent)

`setup.run_full_setup()` makes the receiver ready for every Abertis feed that
is present in the lamedb:

* keeps the Ciefp `/etc/astra/astra.conf` authoritative and appends only the
  missing `Abertis PID <n>` stream blocks;
* appends only the missing OSCam-EMU `A:` rules to
  `/etc/tuxbox/config/oscam.dvbapi`;
* keeps a native aarch64 `/etc/astra/scripts/abertis` de-encapsulator;
* restarts OSCam only when a new A-rule was actually written, and only when
  exactly one active OSCam unit exists;
* never overwrites `SoftCam.Key`, the Ciefp bouquets, or an existing Astra
  configuration.

On the live receiver this covers all 56 Abertis streams in `astra.conf` and
all 56 corresponding A-rules.  Existing files are left untouched when the
entry is already present.

### Automatic sequence (on boot and whenever a Ciefp URL is selected)

Any Ciefp URL of the form `/abertis/pid<number>` is handled, not just
2025/2026/2050/8001, provided the lamedb contains the matching
`Abertis PID <pid>` feed.  The hook polls the current service and also
listens to the Enigma2 service-change event.

```
Ciefp URL selected (/abertis/pid<pid>)
  |
  |-- 1. find "Abertis PID <pid>" in the lamedb (outer SID + data PID)
  |-- 2. learning phase: feed -> F1 + cached data PID + outer PMT PID, reload
  |       -> Enigma2 parses the CA program, OSCam-EMU answers through the
  |          A-rule and the BISS key is cached (no real ECM needed)
  |-- 3. playback phase: feed -> F5 + cached data PID, reload
  |       -> the DreamOS streamserver hands the T2-MI data PID to astra
  |-- 4. retune the feed through a sibling feed on the SAME transponder
  |       (the demux filters are rebuilt; the dish is never moved)
  |-- 5. read the astra output PAT/PMT and verify the native decoder info
  |-- 6. zap the Ciefp URL exactly as it is (field 6 / ONID untouched)
  `-- verify vpid/apid/pmtpid via iServiceInformation; retry the URL only
```

The final feed state is always **F5 + data PID** (no PMT PID).  The F1 state
is only a temporary learning step.  On this receiver the old F5-only shortcut
does not create an OSCam demux/key, and F1 without the outer PMT also fails;
that is why every feed uses the F1 learning phase first.

The outer PMT is derived from the mux rule:

```
outer PMT PID = (outer SID + 0x0FA0) & 0x1FFF
```

Measured examples: `2025: 0x0BD1 -> 0x1B71`, `2026: 0x0BD2 -> 0x1B72`,
`2027: 0x0BD3 -> 0x1B73`, `301: 0x0515 -> 0x14B5`,
`8001: 0x03E9 -> 0x1389`, `8008: 0x03F0 -> 0x1390`.

### Why the Ciefp URL is not patched

DreamOS 2.6 reads the PMT from the pushed HTTP stream.  The Ciefp reference
already carries the data PID in field 6, and the astra output supplies the
real PMT on its own PID.  Writing the PMT PID (or the ONID) into field 6 makes
the frontend wait for a PMT it never finds and the channel stays black.
The plugin therefore plays the Ciefp URL unchanged and verifies it with the
native `iServiceInformation`, not with a blocking webif call.

### 8008 on the new transponder (12583 V 16901)

`8008` - including `La 1 UHD (8008)`, `Clan HD (8008)`, `DKISS (8008)` and
the other channels sharing that feed - is **not** in `SKIP_PIDS` (the set is
empty).  Selecting any of them runs the normal F1 learning and F5 playback
sequence, exactly like the other feeds.

The feed moved: the Abertis mux for PID 8008 is now on **Hispasat 30W,
12583 V 16901, SID 0x3F0** (service reference
`1:0:1:3F0:EA68:0:CE4B127:0:0:0:`).  The old entry
(`1:0:1:3F0:EA68:0:CE4AF34:0:0:0:`, 12084 V) is still in the lamedb but has
no signal, so the plugin uses an explicit override:

```
FEED_REF_OVERRIDES = {
    "8008": "1:0:1:3F0:EA68:0:CE4B127:0:0:0:",
}
```

`lamedb_fix.get_feed_info()` returns the scanned service, `set_feed_mode()`
rewrites that service (it adopts the scanned name `12583V SID 0x3f0` into
`Abertis PID 8008 F5` and adds the missing `C:2600` CA descriptor), and
`setup.ensure_astra_feed_refs()` rewrites the **input reference of the
`Abertis PID 8008` block in `astra.conf`** to the new namespace.  astra pulls
the T2-MI stream of one exact service reference, so an outdated input
reference means "no data" and a black channel even when the feed is fine.

The BISS key of the new feed is in the lowercase `softcam.key`
(`F 03F01FFF 00000000 FE6566C9EB28697C ;ABERTIS 8008 (30.0W/12583)`), but
oscam-emu reads the uppercase `SoftCam.Key`.  `setup.ensure_softcam_key_upper()`
mirrors the missing Abertis lines into that file (backup first, only appends,
never rewrites an existing line) and the runtime restarts OSCam once when it
had to add something.  Without the key the ECM request fails with
`Key not found` and the T2-MI stays encrypted - the picture would be black.

A failed attempt is not retried by itself: `_finish(False)` remembers the
current URL and `_on_service_started` ignores repeated events for that same
URL.  If another Abertis URL is selected while an attempt is still running,
the old sequence is cancelled immediately and the new URL is started, so a
dead feed cannot block the next channel.  Service references are compared
case-insensitively: the lamedb feeds are written in lower case while Enigma2
reports them in upper case, and both describe the same service.

`801` (Ciefp `A7`/`A8`) has no `Abertis PID 801` feed in the live lamedb or
in `astra.conf`; the plugin logs `no feed in lamedb - cannot automate` and
does not invent a feed definition.  `8009` is radio-only and also has no feed
entry.  `802` and `2301` have no Ciefp 30W Abertis bouquet entry.

## OSCam-EMU A-rule

Every feed gets one line in `/etc/tuxbox/config/oscam.dvbapi`:

```
A: ::0BD1:07E9 2600:000000:1FFF # Abertis PID 2025 F5
```

`A:` maps the service SID + data PID to a fake ECM PID (`1FFF`).  OSCam-EMU
answers the BISS request from `SoftCam.Key`; the receiver does not need a
separate key-learning channel.  The rules are added idempotently, the original
file is backed up once to `oscam.dvbapi.abetrisauto.bak`, and the OSCam binary
is never replaced.

## Backups and rollback

The plugin creates these files before changing anything:

* `/etc/enigma2/lamedb.abertis.bak` - first original lamedb
* `/etc/enigma2/lamedb.auto.bak` - lamedb before the first runtime mode switch
* `/etc/astra/astra.conf.abetrisauto.bak` - first original astra.conf
* `/etc/tuxbox/config/oscam.dvbapi.abetrisauto.bak` - first original dvbapi

Existing backups are never replaced.  The UI's Yellow button restores the
lamedb backup; the Astra/OSCam backups can be restored with `cp` if needed.

On this receiver the rollback packages are preserved under
`/root/abetris-backup/`:

* `abetris_1.9.4.ipk` - current release (native-eLabel UI, transparent text)
* `abetris_1.9.3.ipk` - previous release (native-eLabel UI, 8008 on 12583 V)
* `abetris_1.9.2.ipk` - previous release (Python widget UI)
* `abetris_1.9.1.ipk` - 8008 on 12583 V, but with the reference case bug
* `abetris_1.8.ipk` - 8008 on 12583 V, first version of the new transponder
* `abetris_1.7.ipk` - 8008 automated, still on the old (dead) transponder
* `abetris_1.6_skip8008.ipk` - previous release (8008 skipped)
* `abetris_1.5.ipk` - earlier all-feed release
* `1.6-before/`, `1.6-pre-8008-skip/`, `1.7-before/`, `1.8-before-12583/`,
  `1.9-before-casefix/`, `1.9.1-before/` - file snapshots

To roll back to the previous 8008-skip behaviour:

```sh
dpkg -i /root/abetris-backup/abetris_1.6_skip8008.ipk
systemctl restart enigma2.service
```

A full reboot is not required; a controlled Enigma2 restart is enough.  The
plugin never runs `init 4`, never moves the dish and never restarts
Astra/Enigma2 on its own.

## Install

```sh
dpkg -i enigma2-plugin-extensions-abertisautoswitcher_1.9.4_all.ipk
systemctl restart enigma2.service
```

On DreamOS the package manager may be exposed as `opkg`, but this build is a
Debian-format package and installs with `dpkg -i`.  The postinst message says
"Reboot to activate"; a controlled Enigma2 service restart is sufficient and
is what was validated here.

## UI (Extensions menu -> "Abertis Auto Pro")

The screen is only informative - the engine does everything by itself, there
is no F1/F5 button to press. The 1.9.5 UI uses plain Enigma2 `<widget>` elements
with opaque colours (no transparency tricks), including coloured buttons and
static labels. It does not bind Python Label components or pixmaps to this
receiver's skin.

* **RED - Exit** - close the screen
* **GREEN - Update** - compares the installed version with the packages kept
  in `/root/abetris-backup/` and shows how to install a newer one
* **YELLOW - Refresh** - re-checks the automation status
* **BLUE - Diagnostics** - shows the running processes, the number of
  Abertis feeds, the 8008 feed reference, the oscam-emu key state and the
  log tail
* **OK - About** - version, author and credits

The author of this build is **Kingcs / Prof-abdo**, with special thanks to
**mouadhada** (the original AbetrisFlagSwitch) and **Saber Hisham SH**.

DreamOS 2.6 details worth keeping in mind when changing the screen:

* the inline `<screen name="...">` has to be the **class name** of the Screen
  object, otherwise Enigma2 does not find the screen and shows a green
  screen;
* a Python `Label` only takes a **byte string** (`eLabel.setText()`); unicode
  text or assigning a pixmap to it can raise a SWIG exception during skin
  creation.  The 1.9.5 screen uses `Label()` with encoded byte strings only.

## Files

```
usr/lib/enigma2/python/Plugins/Extensions/AbertisAutoSwitcher/
  __init__.py
  plugin.py          UI and autostart registration
  lamedb_fix.py      feed catalog, F1/F5 rules, computed PMT, A-rules,
                     FEED_REF_OVERRIDES for re-scanned feeds
  setup.py           idempotent Astra/OSCam setup, backup and restart guards,
                     key mirroring (softcam.key -> SoftCam.Key) and the
                     astra.conf feed reference sync
  autostart.py       runtime state machine + optional skip list
  prestart_fix.py    systemd ExecStartPre lamedb fix
  logger.py
  abertis.aarch64    native Abertis T2-MI de-encapsulator
DEBIAN/ control postinst prerm
```

## Logs and verification

* Plugin log: `/tmp/abetris_auto.log`
* OSCam log: `/tmp/oscam.log` (search `found`, the feed SID and `1FFF`)
* Astra log: `/tmp/astra.log`
* Native playback: `e2vpid`, `e2apid`, `e2pmtpid`, `e2videoheight` from
  `/web/getcurrent` after `Abertis auto OK`
* The plugin uses the webif user agent `AbertisAutoSwitcher` with a `sessionid`;
  `/web/zap` and `/web/servicelistreload` are POST requests.

## Live validation (2026-10-22, DreamOS 2.6)

The all-feed runtime was tested feed by feed with real Ciefp bouquet URLs.
The native `vpid`/`apid`/`pmtpid` were checked after `Abertis auto OK`.

* **Passed (34 feed-backed PIDs):** 301, 303, 420, 421, 423, 701, 702, 703,
  2025, 2026, 2027, 2028, 2050, 2060, 2270, 2271, 2272, 2273, 2274, 2302,
  2303, 2305, 2308, 2520, 2521, 2522, 2523, 2524, 8001, 8002, 8003, 8004,
  8005, 8006.
* **Failed / unavailable:** `2306` and `8000`.  Both reached F5, but the
  astra output PAT did not contain the Ciefp URL's service SID (`service 0001
  not in PAT` for 2306); no configuration was changed.  They are most likely
  off-air or broadcasting a different service at test time.
* **No feed entry, cannot automate:** `801` (Ciefp `A7`/`A8`) and `8009`
  (radio-only).  The plugin logs `no feed in lamedb - cannot automate`.
* **8008:** automated in 1.9.5 and **working** on the new transponder.
  `La 1 UHD (8008)`, `Clan HD (8008)` and `DKISS (8008)` were verified live on
  12583 V 16901 with `Abertis auto OK` and native decoder info
  (La 1 UHD: `pmtpid=4000 vpid=4001 apid=4002`, 2160p; DKISS: `pmtpid=1000
  vpid=1001 apid=1002`, 1080p; Clan HD: `pmtpid=2500 vpid=2501 apid=2502`,
  1080p).  The feed reference, the astra input reference and the oscam-emu
  key were the three parts that had to follow the new frequency.
* `8001` and `2025`/`2026` were re-verified after the 1.9.1 fix (the reference
  comparison is now case-insensitive, so the F1 -> F5 sequence is no longer
  cancelled half way and the channels no longer stall in F1).
* The reference key contains the channel name as well: all channels of one PID
  share the same url (`/abertis/pid8008`), so La 1 UHD, Clan HD and DKISS would
  otherwise look like the same channel and only the first one would be
  automated.  With 1.9.2 every one of them gets its own F1/F5 sequence.
* The 1.9.4 UI is composed directly from Enigma2-native `<eLabel>` elements;
  text-only labels use `transparent="1"` to avoid opaque black rectangles.
* A cold reboot was verified on 2026-10-22: the setup is idempotent, the
  astra/OSCam configuration is kept and the runtime automates the restored
  channel without any manual action.

## Notes

* DreamOS 2.6 uses Python 2.7.  `.pyo` files are not shipped; Enigma2 compiles
  the modules on first load.
* On failure the plugin does **not** restore the previous service and does
  **not** re-run the full feed/Astra sequence.  A playback verification
  failure retries only the URL; an Astra sync failure may re-zap the same F5
  feed once before giving up.  This is deliberate, so a manual dish motor can
  never be moved by the automation.
* To skip another dead feed, add its PID to `SKIP_PIDS` in `autostart.py`,
  rebuild the IPK and reinstall.  Do not remove it from the Ciefp bouquet or
  overwrite Ciefp/OSCam configuration.
* When a feed moves to a new transponder, three things have to follow it: the
  feed reference used by the runtime (`FEED_REF_OVERRIDES` in
  `lamedb_fix.py`), the input reference of the matching `make_channel` block
  in `astra.conf` (`setup.ensure_astra_feed_refs()`) and the BISS key of the
  new namespace in the uppercase `SoftCam.Key`
  (`setup.ensure_softcam_key_upper()`).  Only the first one is enough to tune
  the feed; without the other two the channel stays black.
