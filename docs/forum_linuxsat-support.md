# Abertis Auto Switcher PRO v1.9.13 – Automatic T2‑MI Feed Playback Plugin (Enigma2: DreamOS **and** OpenATV)

Dear linuxsat-support community,

I am pleased to share with you my plugin **Abertis Auto Switcher PRO**, a complete
automation suite for every **Abertis feed on 30.0° W (Hispasat)**, built and
tested live on a **Dreambox Two** – under **DreamOS 2.6 (Python 2.7)** and under
**openATV 8.0.1 (Python 3.14)** – Enigma2 5.x / 7.x / 8.x images.

**GitHub:** https://github.com/prof-abdo/Abertis-Auto-Switcher-PRO

---

## What does it do?

On 30.0° W the Abertis muxes broadcast **dozens of FTA / BISS channels bundled
inside one T2‑MI multiplex**. Every feed on the Enigma2 side is a separate PIDs
mask (`Abertis PID 301 / 303 / 420 / 2025 / 2026 / 2050 / 8001 / 8008 …`).
Normally you have to re‑configure astra‑sm, oscam.dvbapi, SoftCam.Key and
lamedb for **each and every feed, by hand, every time the feed changes**.

My plugin turns all of that into **one single click** (or nothing at all, it is
automatic on every boot).

### Automatic sequence (F1 → F5)
When you zap any Ciefp streamrelay URL of the form
`http://127.0.0.1:8001/abertis/pid<NUMBER>`, the plugin:

1. Reads **/etc/enigma2/lamedb** and finds the service reference of
   `Abertis PID <number>`, with its **outer PMT PID** and **data PID c:00xxxx**.
2. **Learning phase (F1)** – switches that service to F1 mode, caches the
   data PID + outer PMT PID, then asks Enigma2 to **reload lamedb** so
   the CA program gets recognized.
3. **Playback (F5)** – switches back to F5 + cached data PID, reload again,
   and the picture plays.
4. Everything is **logged in real time**, backed up first, and
   **idempotent** – you can run it a thousand times, nothing gets duplicated
   or corrupted.

### Automatic A‑rules + BISS keys + streams
* Creates one OSCam‑EMU `A:` rule per feed in
  `/etc/tuxbox/config/oscam.dvbapi`, with a `.abetrisauto.bak` backup.
* Mirrors missing BISS keys from the lowercase `softcam.key` into
  `SoftCam.Key` (`oscam-emu` reads the upper‑case file).
* Generates every missing **astra‑sm stream block** into
  `/etc/astra/astra.conf` so that feeding a new PID works instantly.

### Automatic astra‑sm / T2‑MI toolchain
* Ships the known‑good **astra‑sm 0.2.88 (patched `t2mi` payload PID 0x90)
  + `t2mi_decap` + `spammer`** binaries **for aarch64 receivers**, and the
  native **`abertis` T2‑MI de‑encapsulator (fully static) for aarch64, arm
  (32‑bit) and mips** receivers.
* Writes the `/etc/init.d/astra` + `astra-sm.service` systemd unit so astra
  starts automatically at every cold boot (only when the image does not
  already manage astra).
* Adds the `streamrelay.socket` so that port 8001 is always up.

### Automatic lamedb fix before Enigma2 starts
A small `prestart_fix.py` runs **before** Enigma2 writes its own snapshot of
lamedb (via a systemd `ExecStartPre` drop‑in), so no in‑memory
`c:00xxxx` data PID can be lost again.

### The "ta9ti3" fix (picture cutting)
A network tuning file `/etc/sysctl.d/99-abertis.conf` (from the Ciefp
reference project) with **16 MB UDP/TCP socket buffers**, `vm.dirty*`
page‑write tuning, and `net.ipv4.tcp_tw_recycle = 0` – these prevent the
**packet loss that cuts the picture** while the high‑bitrate Abertis feeds
go through `streamproxy → astra → HTTP`.

### New in v1.9.13: both package systems, both images, true multi‑arch
* **DreamOS / Debian images (dpkg)** ← install the **`.deb`**
* **OpenATV / OpenPLi / opkg images** ← install the **`.ipk`**
* The **one‑line installer auto‑detects** the package system and picks the
  right format; no flags needed.
* **Multi‑architecture in one package**: it detects the receiver
  architecture (`uname -m`) and deploys the matching binaries:
  * **aarch64 / arm64** – full toolchain (`astra`, `t2mi_decap`, `spammer`, `abertis`)
  * **arm (32‑bit) / mips** – static native `abertis` de‑encapsulator
* **Wrong‑architecture binaries are never deployed**: on arm/mips the
  plugin keeps your already‑installed binaries untouched and only ships
  the `abertis` tool for that architecture (the action and the decision
  are logged, e.g. `astra: no mips binary shipped, leaving the installed
  one untouched`).
* **Images without OpenSSL 3 cannot receive a broken astra**: the patched
  astra is linked against `libcrypto.so.3`. When the image lacks it
  (e.g. openATV 8.0.1 only ships libcrypto.so.4 / 1.0.2), the library the
  package carries is deployed into `/usr/lib` **only when missing** and
  `ldconfig` is refreshed – if a needed library can neither be found nor
  shipped, our binary is not installed and **your working binary stays**.
  Every replaced file is kept once as `*.orig`.
* The postinst message no longer asks for a reboot: **the plugin loads at
  the next Enigma2 start of your choice**.

### Never overwrites anything
`/etc/astra/astra.conf`, `/etc/astra/scripts/abertis`, the OSCam files and
the working softcam keys are **never overwritten**: only **missing entries
are appended**, everything is backed up first (`.orig` / `.abetrisauto.bak`
/ `/root/abetris-backup`). The Abertis key files are shipped as `*.dist` so
a receiver's existing keys stay untouched; a fresh image gets them
installed automatically.

---

## Installation (one line, works on both image families)

On a **root** shell of the receiver:

```
wget https://raw.githubusercontent.com/prof-abdo/Abertis-Auto-Switcher-PRO/main/installer.sh -O - | /bin/sh
```

**Or install manually:**

```
# DreamOS / Debian images (dpkg):
cd /tmp
wget -O abertis-pro.deb https://github.com/prof-abdo/Abertis-Auto-Switcher-PRO/releases/download/v1.9.13/enigma2-plugin-extensions-abertisautoswitcher_1.9.13_all.deb
dpkg -i abertis-pro.deb

# OpenATV / OpenPLi / opkg images:
cd /tmp
wget -O abertis-pro.ipk https://github.com/prof-abdo/Abertis-Auto-Switcher-PRO/releases/download/v1.9.13/enigma2-plugin-extensions-abertisautoswitcher_1.9.13_all.ipk
opkg install --force-reinstall --force-overwrite abertis-pro.ipk
```

(the old `.ipk` versions v1.0 → v1.9.12 are still on GitHub for older
images, and the installer upgrades cleanly from them).

## Plugin Menu
`Menu → Extensions → AbertisAutoSwitcher`

You can trigger the whole sequence manually with a single "Run setup" – the
auto‑sequence runs on every boot and on every Ciefp URL zap.

## What you need

* An **Enigma2 image with dpkg (DreamOS 2.6) or opkg (OpenATV 8 / OpenPLi)**.
* A dish pointed at **30.0° W** and one **free tuner** for the Abertis
  muxes (Hispasat 12583 V, T2‑MI multiplexed).
* One installed **OSCam with oscam‑emu** (BISS‑capable).
* The **Ciefp streams/bouquets** for the `/abertis/pid<n>` URLs
  (his T2‑MI Abertis settings are the reference).

## Screenshots

*(attach here: abetris_osd_1.png – OSD banner during the F1 learning phase,
abetris_osd_2.png – settings screen, abetris_osd_3.png – log view)*

## Credits & Thanks

* **Ciefp** – for his reference project CiefpSettingsT2miAbertis with the
  original astra‑sm binaries, the per‑architecture `abertis` tools, the
  T2‑MI sysctl tuning and the reference astra config.
* **MOHAMED_OS / Levi45** – for keeping the Abertis BISS keys up to date.
* **linuxsat-support** – for the knowledge base.

## Source / support

* GitHub: https://github.com/prof-abdo/Abertis-Auto-Switcher-PRO
* Releases: v1.9.13 (`.deb` for DreamOS, `.ipk` for OpenATV/OpenPLi)
* Pull‑requests, test feedback on other receivers and bug reports are very
  welcome – especially welcome: reports from **arm (32‑bit) / mips** owners.

---

*Tested & working on: Dreambox Two 4K under DreamOS 2.6 (dpkg) and openATV
8.0.1 / opkg with Python 3.14 (dpkg‑less image, patched astra running with
shipped libcrypto.so.3). All Abertis feeds auto‑configured, FTA + BISS +
F1 learning phase; PID 8008 verified at 100 % TS‑sync on DreamOS.*

Enjoy ! 🙂
— Prof‑Abdo (Kingcs)
