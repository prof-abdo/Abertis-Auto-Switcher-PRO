# -*- coding: utf-8 -*-
"""Automation helpers for astra-sm / oscam on DreamOS 2.6."""
import base64
import os
import re
import shutil
import stat
import subprocess
import time
from . import logger
import platform


def _get_receiver_arch():
    """Return receiver architecture (arm64/arm/mips) from platform.machine()."""
    m = platform.machine().lower()
    if "aarch64" in m or "arm64" in m:
        return "arm64"
    if "arm" in m:
        return "arm"
    if "mips" in m:
        return "mips"
    return "arm64"


ASTRA_BIN_CANDIDATES = ["/usr/bin/astra", "/usr/bin/astra-sm", "/etc/astra/astra"]
ABERTIS_SCRIPT = "/etc/astra/scripts/abertis"
BUNDLED_NATIVE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "abertis.aarch64")
ABERTIS_SCRIPT_B64 = "IyEvdXNyL2Jpbi9lbnYgcHl0aG9uCiMgLSotIGNvZGluZzogdXRmLTggLSotCiIiIkFiZXJ0aXMgVDItTUkgZGUtZW5jYXBzdWxhdG9yIChhYXJjaDY0LWZyaWVuZGx5IFB5dGhvbiByZXBsYWNlbWVudCkuCgpFeHRyYWN0cyB0aGUgTVBFRy1UUyBwYWNrZXRzIGZvciBhIGdpdmVuIFBJRCBmcm9tIHN0ZGluIGFuZCB3cml0ZXMgdGhlaXIKcGF5bG9hZCB0byBzdGRvdXQuIERyb3AtaW4gcmVwbGFjZW1lbnQgZm9yIHRoZSBhcm1oZiAnYWJlcnRpcycgYmluYXJ5IHRoYXQKZG9lcyBub3QgcnVuIG9uIDY0LWJpdCBEcmVhbU9TLgoKVXNhZ2U6ICBhYmVydGlzIDxQSUQ+CiIiIgppbXBvcnQgc3lzCgoKZGVmIF9zdHJlYW1zKCk6CiAgICB0cnk6CiAgICAgICAgcmV0dXJuIHN5cy5zdGRpbi5idWZmZXIsIHN5cy5zdGRvdXQuYnVmZmVyCiAgICBleGNlcHQgQXR0cmlidXRlRXJyb3I6CiAgICAgICAgcmV0dXJuIHN5cy5zdGRpbiwgc3lzLnN0ZG91dAoKCmRlZiBfYih4KToKICAgICIiIlJldHVybiBpbnRlZ2VyIHZhbHVlIG9mIGEgYnl0ZSwgcHkyL3B5MyBzYWZlLiIiIgogICAgaWYgaXNpbnN0YW5jZSh4LCBpbnQpOgogICAgICAgIHJldHVybiB4CiAgICByZXR1cm4gb3JkKHgpCgoKZGVmIG1haW4oKToKICAgIGlmIGxlbihzeXMuYXJndikgPCAyOgogICAgICAgIHN5cy5zdGRlcnIud3JpdGUoInVzYWdlOiBhYmVydGlzIDxQSUQ+XG4iKQogICAgICAgIHJldHVybiAyCiAgICB0cnk6CiAgICAgICAgcGlkID0gaW50KHN5cy5hcmd2WzFdKQogICAgZXhjZXB0IFZhbHVlRXJyb3I6CiAgICAgICAgc3lzLnN0ZGVyci53cml0ZSgiaW52YWxpZCBQSUQ6ICVzXG4iICUgc3lzLmFyZ3ZbMV0pCiAgICAgICAgcmV0dXJuIDIKCiAgICBpbnAsIG91dCA9IF9zdHJlYW1zKCkKICAgIFNZTkMgPSAweDQ3CiAgICB3aGlsZSBUcnVlOgogICAgICAgIGNodW5rID0gaW5wLnJlYWQoMTg4KQogICAgICAgIGlmIG5vdCBjaHVuazoKICAgICAgICAgICAgYnJlYWsKICAgICAgICBpZiBsZW4oY2h1bmspIDwgMTg4OgogICAgICAgICAgICBicmVhawogICAgICAgIGJ1ZiA9IGNodW5rCiAgICAgICAgaWYgX2IoYnVmWzBdKSAhPSBTWU5DOgogICAgICAgICAgICBpZHggPSBidWYuZmluZChjaHIoU1lOQykgaWYgbm90IGlzaW5zdGFuY2UoYnVmWzBdLCBpbnQpIGVsc2UgYnl0ZXMoW1NZTkNdKSkKICAgICAgICAgICAgIyBzaW1wbGVyOiB0cnkgYm90aAogICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICBpZHggPSBidWYuZmluZChiIlx4NDciKQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICAgICAgaWR4ID0gLTEKICAgICAgICAgICAgaWYgaWR4IDwgMDoKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICMgc2tpcCB0aGlzIG1pc2FsaWduZWQgY2h1bmsKICAgICAgICAgICAgY29udGludWUKICAgICAgICB0c3BpZCA9ICgoX2IoYnVmWzFdKSAmIDB4MUYpIDw8IDgpIHwgX2IoYnVmWzJdKQogICAgICAgIGlmIHRzcGlkICE9IHBpZDoKICAgICAgICAgICAgY29udGludWUKICAgICAgICBhZmMgPSBfYihidWZbM10pICYgMHgzMAogICAgICAgIHBheWxvYWQgPSBiIiIKICAgICAgICBpZiBhZmMgPT0gMHgxMDoKICAgICAgICAgICAgcGF5bG9hZCA9IGJ1Zls0Ol0KICAgICAgICBlbGlmIGFmYyA9PSAweDMwOgogICAgICAgICAgICBhZmwgPSBfYihidWZbNF0pCiAgICAgICAgICAgIHBheWxvYWQgPSBidWZbNSArIGFmbDpdCiAgICAgICAgIyAweDIwIGFkYXB0YXRpb24gb25seSwgMHgwMCBubyBwYXlsb2FkIC0+IGVtcHR5CiAgICAgICAgaWYgcGF5bG9hZDoKICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgb3V0LndyaXRlKHBheWxvYWQpCiAgICAgICAgICAgICAgICBvdXQuZmx1c2goKQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICAgICAgcGFzcwogICAgdHJ5OgogICAgICAgIG91dC5mbHVzaCgpCiAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgIHBhc3MKICAgIHJldHVybiAwCgoKaWYgX19uYW1lX18gPT0gIl9fbWFpbl9fIjoKICAgIHN5cy5leGl0KG1haW4oKSkK"
ASTRA_CONF = "/etc/astra/astra.conf"
ASTRA_CONF_BACKUP = ASTRA_CONF + ".abetrisauto.bak"
ASTRA_INIT = "/etc/init.d/astra-sm"
ASTRA_UNIT = "/etc/systemd/system/astra-sm.service"
ASTRA_BIN = "/usr/bin/astra"
ASTRA_SCRIPT = "/etc/astra/scripts/abertis"
OSCAM_SERVER = "/etc/tuxbox/config/oscam.server"
OSCAM_SERVICES = "/etc/tuxbox/config/oscam.services"
OSCAM_DVBAPI = "/etc/tuxbox/config/oscam.dvbapi"
OSCAM_DVBAPI_BACKUP = OSCAM_DVBAPI + ".abertisauto.bak"
OSCAM_INIT_SCRIPTS = ("/etc/init.d/oscam", "/etc/init.d/softcam")
ABERTIS_DVBAPI_A_RULE = (
    "A: ::0BD2:07EA 2600:000000:1FFF # Abertis PID 2026 F5")
ABERTIS_DVBAPI_A_RULES = (
    ABERTIS_DVBAPI_A_RULE,
    "A: ::0BEA:0802 2600:000000:1FFF # Abertis PID 2050 F5",
    "A: ::03E9:1F41 2600:000000:1FFF # Abertis PID 8001 F5",
)
SOFTCAM_KEY = "/etc/tuxbox/config/softcam.key"
SOFTCAM_KEY_UPPER = "/etc/tuxbox/config/SoftCam.Key"

# BISS keys for the Abertis muxes (30.0W). Astra reads the LOWERCASE file
# /etc/tuxbox/config/softcam.key; the uppercase SoftCam.Key is for oscam-emu.
# Keep this list in sync with the sat-universe thread / oscam SoftCam.Key.
ABERTIS_KEYS = """\
F 65ADC3CF 00000000 2A1F90D961EA97E2
F B94256FC 00000000 2A1F90D961EA97E2
F F2E725ED 00000000 2A1F90D961EA97E2
F DBEC7ADB 00000000 081C62868233A75C
F 0BDB1FFF 00000000 2E4E9511A3155C14
F 0BDC1FFF 00000000 2E4E9511A3155C14
F 0BDD1FFF 00000000 2E4E9511A3155C14
F 0BDE1FFF 00000000 2E4E9511A3155C14
F BA8DF156 00000000 2A1F90D961EA97E2
F 945D7BC8 00000000 081C62868233A75C
F 11F38C69 00000000 19103C655FDC9CD7
F 5A56FF78 00000000 19103C655FDC9CD7
F 653C02A9 00000000 19103C655FDC9CD7
F 2E9971B8 00000000 19103C655FDC9CD7
F F276E48B 00000000 19103C655FDC9CD7
F 0CD11FFF 00000000 2E4E9511A3155C14
F 0CD21FFF 00000000 2E4E9511A3155C14
F 0CD31FFF 00000000 2E4E9511A3155C14
F 0CD41FFF 00000000 2E4E9511A3155C14
F 0CE51FFF 00000000 71FD58C6E72F93A9
F 42BE5305 00000000 71FD58C6E72F93A9
F 091B2014 00000000 71FD58C6E72F93A9
F B40E2E34 00000000 71FD58C6E72F93A9
F FFAB5D25 00000000 71FD58C6E72F93A9
F 2344C816 00000000 71FD58C6E72F93A9
F 68E1BB07 00000000 71FD58C6E72F93A9
F 07A02483 00000000 71FD58C6E72F93A9
F 19A625CF 00000000 EB86E152E78C6DE0
F 520356DE 00000000 EB86E152E78C6DE0
F 8EECC3ED 00000000 EB86E152E78C6DE0
F C549B0FC 00000000 EB86E152E78C6DE0
F EC42EFCA 00000000 EB86E152E78C6DE0
F 0DCB1FFF 00000000 2E4E9511A3155C14
F 0DCC1FFF 00000000 2E4E9511A3155C14
F 0DCD1FFF 00000000 2E4E9511A3155C14
F 0DCE1FFF 00000000 2E4E9511A3155C14
F 05151FFF 00000000 254AA110F3CFDB9D
F 05171FFF 00000000 254AA110F3CFDB9D
F 45A8F9BE 00000000 19103C655FDC9CD7
F 0E0D8AAF 00000000 19103C655FDC9CD7
F 99476C8D 00000000 FCF5190A9481A4B9
F 05971FFF 00000000 2E4E9511A3155C14
F 05991FFF 00000000 2E4E9511A3155C14
F 145555B0 00000000 19103C655FDC9CD7
F D86B1EF5 00000000 19103C655FDC9CD7
F 15186227 00000000 7578FAE7D3B728B2
F C9F7F714 00000000 7578FAE7D3B728B2
F 82528405 00000000 7578FAE7D3B728B2
F F541A822 00000000 FE6566C9EB28697C
F 3CDA0BE1 00000000 2E4E9511A3155C14
F E0359ED2 00000000 DBCEC36CA05806FE
F AB90EDC3 00000000 C53AF0EFB178FC25
F 829BB2F5 00000000 759EC4D7AA7F658E
F C93EC1E4 00000000 0F41A9F9FB5FAD07
F 15D154D7 00000000 C53AF0EFB178FC25
F 909ED3A6 00000000 FE6566C9EB28697C
F 11311FFF 00000000 71FD58C6E72F93A9
F 125D1FFF 00000000 71FD58C6E72F93A9
F 2EEE0144 00 19103C655FDC9CD7
F 03E80021 00 FE6566C9EB28697C
F 070A1FFF 00 0BBD824AA1116D1F
F 070A1FFF 01 0BBD824AA1116D1F
F 03F01FFF 00000000 FE6566C9EB28697C
F 50DEB036 00000000 FE6566C9EB28697C
"""

DEFAULT_ASTRA_CONF = """# Abertis Auto - astra-sm configuration template
# Pure Lua configuration for astra-sm 0.2.88.  The native astra-sm
# directives (log file / log debug / input { ... } / output { ... }) are
# rejected by the Lua parser and were removed.  The Abertis feeds are
# appended below by the plugin.

log.set({ stdout = false, debug = false, syslog = "astra", })

"""


def _run(cmd):
    try:
        return os.system(cmd)
    except Exception as e:
        logger.log("cmd failed %s: %s" % (cmd, e))
        return -1


def _makedirs(path):
    """Python 2.7-compatible makedirs (no exist_ok)."""
    if not path:
        return
    try:
        os.makedirs(path)
    except OSError:
        pass
    except Exception:
        pass


def _elf_machine(path):
    """Return the ELF e_machine (0xB7 = AArch64, 0x28 = ARM 32-bit) or None."""
    try:
        import struct
        with open(path, "rb") as f:
            h = f.read(20)
        if len(h) < 20 or h[:4] != b"\x7fELF":
            return None
        endian = h[5]
        if not isinstance(endian, int):
            endian = ord(endian)
        if endian == 1:
            return struct.unpack("<H", h[18:20])[0]
        return struct.unpack(">H", h[18:20])[0]
    except Exception:
        return None


def _normalize_key_line(line):
    line = line.split(";")[0].strip()
    return " ".join(line.split())


def _read_text(path):
    """Read a text file; return None when it cannot be read."""
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception:
        return None


def _atomic_write(path, data, mode=None):
    """Write a file through a temporary file + rename (never truncate first)."""
    tmp = path + ".abetrisauto.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    if mode is not None:
        try:
            os.chmod(tmp, mode)
        except Exception:
            pass
    os.rename(tmp, path)


def ensure_softcam_key():
    """Install/merge the Abertis BISS keys into the lowercase file astra reads."""
    try:
        keydir = os.path.dirname(SOFTCAM_KEY)
        if keydir and not os.path.isdir(keydir):
            os.makedirs(keydir)
    except Exception:
        pass
    existing = ""
    if os.path.exists(SOFTCAM_KEY):
        existing = _read_text(SOFTCAM_KEY)
        if existing is None:
            # Fail closed: a key file we cannot read must never be rewritten.
            logger.log("softcam.key exists but cannot be read - keeping it untouched")
            return False
    seeded = False
    if not existing and os.path.exists(SOFTCAM_KEY_UPPER):
        upper = _read_text(SOFTCAM_KEY_UPPER)
        if upper is None:
            logger.log("SoftCam.Key exists but cannot be read - keeping it untouched")
            return False
        if "ABERTIS" in upper.upper():
            existing = upper
            seeded = True
    # Never rewrite a working softcam.key that already holds Abertis keys.
    if os.path.exists(SOFTCAM_KEY) and existing:
        up = existing.upper()
        if "070A1FFF" in up or "0BDB1FFF" in up or "ABERTIS" in up:
            logger.log("softcam.key already contains Abertis keys - keeping untouched")
            return True
    have = set()
    for line in existing.splitlines():
        n = _normalize_key_line(line)
        if n:
            have.add(n)
    wanted = []
    for line in ABERTIS_KEYS.splitlines():
        n = _normalize_key_line(line)
        if n and n not in have and n not in wanted:
            wanted.append(n)
    if not wanted and not seeded:
        logger.log("softcam.key already contains all Abertis keys")
        return True
    try:
        content = existing
        if content and not content.endswith("\n"):
            content += "\n"
        if wanted:
            content += "\n".join(wanted) + "\n"
        if not isinstance(content, bytes):
            content = content.encode("utf-8")
        _atomic_write(SOFTCAM_KEY, content, 0o644)
        logger.log("softcam.key: installed/merged %d Abertis keys" % len(wanted))
        return True
    except Exception as e:
        logger.log("ensure_softcam_key failed: %s" % e)
        return False


def ensure_softcam_key_upper():
    """Mirror the Abertis BISS keys into the uppercase SoftCam.Key.

    astra reads the lowercase ``softcam.key`` but oscam-emu reads
    ``SoftCam.Key``.  A key that only exists in the lowercase file is
    invisible for the emulator: the ECM request fails with "Key not found"
    and the T2-MI feed stays encrypted, so the channel stays black.

    Only missing lines are appended, the user file is backed up first and
    nothing is ever removed or rewritten.  Returns ``(ok, changed)``.
    """
    if not os.path.exists(SOFTCAM_KEY_UPPER):
        return False, False
    existing = _read_text(SOFTCAM_KEY_UPPER)
    if existing is None:
        logger.log("SoftCam.Key exists but cannot be read - keeping it untouched")
        return False, False
    source = _read_text(SOFTCAM_KEY) if os.path.exists(SOFTCAM_KEY) else None
    if not source:
        return False, False
    have = set()
    for line in existing.splitlines():
        n = _normalize_key_line(line)
        if n:
            have.add(n)
    wanted = []
    for line in source.splitlines():
        if "ABERTIS" not in line.upper():
            continue
        n = _normalize_key_line(line)
        if not n or n in have or n in wanted:
            continue
        wanted.append(line.strip())
    if not wanted:
        logger.log("SoftCam.Key already contains all Abertis keys")
        return True, False
    try:
        backup = SOFTCAM_KEY_UPPER + ".abetrisauto.bak"
        if not os.path.exists(backup):
            shutil.copy2(SOFTCAM_KEY_UPPER, backup)
        content = existing
        if content and not content.endswith("\n"):
            content += "\n"
        content += "\n".join(wanted) + "\n"
        _atomic_write(SOFTCAM_KEY_UPPER, content.encode("utf-8"), 0o644)
        logger.log("SoftCam.Key: merged %d Abertis keys" % len(wanted))
        return True, True
    except Exception as e:
        logger.log("ensure_softcam_key_upper failed: %s" % e)
        return False, False


def astra_present():
    for p in ASTRA_BIN_CANDIDATES:
        if os.path.exists(p):
            return True
    # also check PATH
    try:
        r = os.system("which astra >/dev/null 2>&1")
        if r == 0:
            return True
    except Exception:
        pass
    return False


def install_astra():
    if astra_present():
        logger.log("astra-sm already present")
        return True
    logger.log("astra-sm not found, trying opkg install...")
    rc = _run("opkg update >/tmp/abetris_opkg.log 2>&1")
    rc = _run("opkg install astra-sm >>/tmp/abetris_opkg.log 2>&1")
    if astra_present():
        logger.log("astra-sm installed OK")
        return True
    logger.log("astra-sm install failed (see /tmp/abetris_opkg.log)")
    return False


def ensure_astra_conf():
    # A fresh DreamOS image ships an astra.conf in the native astra-sm
    # format (input { ... } / output { ... }).  That file is not the
    # Abertis template: appended Abertis streams would be mixed with the
    # native blocks and make astra crash.  Replace it in that case.  A
    # file that is already the Abertis template (or that has no foreign
    # blocks) is kept as is.
    if os.path.exists(ASTRA_CONF):
        try:
            with open(ASTRA_CONF, "r") as f:
                text = f.read()
            # A foreign template (the astra-sm package's default config) is
            # detected first: it mixes native input{}/output{} blocks with
            # the Abertis make_channel blocks and crashes astra 0.2.88.
            if "input {" in text and 'type = "dvb"' in text:
                logger.log("astra.conf is a foreign template - replacing it")
            elif "make_channel" in text and "http://localhost:8001" in text:
                logger.log("astra.conf already exists, keeping it")
                return True
            else:
                logger.log("astra.conf is empty or unknown - replacing it")
        except Exception:
            pass
    try:
        _makedirs(os.path.dirname(ASTRA_CONF))
    except Exception:
        pass
    try:
        with open(ASTRA_CONF, "w") as f:
            f.write(DEFAULT_ASTRA_CONF)
        logger.log("created default %s" % ASTRA_CONF)
        return True
    except Exception as e:
        logger.log("cannot create astra.conf: %s" % e)
        return False


def _upper_service_ref(ref):
    """Uppercase the four hex fields of an Enigma2 service reference."""
    parts = (ref or "").split(":")
    if len(parts) >= 7:
        for i in (3, 4, 5, 6):
            parts[i] = parts[i].upper()
    return ":".join(parts)


def astra_stream_block(pid, feed_ref):
    """Build one astra-sm make_channel block for an Abertis feed."""
    pid = str(int(pid))
    ref = _upper_service_ref(feed_ref)
    return (
        'make_channel({\n'
        '  name = "Abertis PID %s",\n'
        '  input = {\n'
        '    "http://localhost:8001/%s",\n'
        '  },\n'
        '  transform = {{\n'
        '    format = "pipe",\n'
        '    command = "/etc/astra/scripts/abertis %s",\n'
        '  }},\n'
        '  output = {\n'
        '    "http://0.0.0.0:9999/abertis/pid%s",\n'
        '  },\n'
        '})\n' % (pid, ref, pid, pid)
    )


def ensure_astra_streams(config_path=None, backup_path=None, feeds=None):
    """Add the missing Abertis feeds to astra.conf without touching the rest.

    Existing make_channel blocks (the three live-validated streams) are kept
    byte-for-byte.  A one-time backup is created before the first append.
    Returns ``(ok, changed, message)``.
    """
    config_path = config_path or ASTRA_CONF
    backup_path = backup_path or ASTRA_CONF_BACKUP
    if not os.path.exists(config_path):
        return False, False, "ERROR: astra.conf not found: %s" % config_path
    try:
        with open(config_path, "rb") as f:
            original = f.read()
        text = original.decode("latin-1", "replace")
    except Exception as e:
        return False, False, "ERROR reading astra.conf: %s" % e

    existing = set(int(x) for x in
                   re.findall(r"/abertis/pid(\d+)", text, re.I))
    if feeds is None:
        from . import lamedb_fix
        feeds = lamedb_fix.get_all_feeds()

    missing = []
    invalid = []
    for feed in feeds:
        try:
            pid = int(feed["pid"])
        except (KeyError, TypeError, ValueError):
            continue
        if pid in existing:
            continue
        ref = feed.get("ref") or ""
        if not ref.startswith("1:0:1:"):
            invalid.append(pid)
            continue
        missing.append((pid, ref))
        existing.add(pid)

    if not missing:
        message = "astra.conf already has %d Abertis streams" % len(existing)
        if invalid:
            message += " (no feed ref for: %s)" % ", ".join(
                str(p) for p in sorted(invalid))
        return True, False, message

    if not os.path.exists(backup_path):
        try:
            shutil.copy2(config_path, backup_path)
        except Exception as e:
            return False, False, "ERROR creating astra.conf backup: %s" % e

    content = text
    if content and not content.endswith("\n"):
        content += "\n"
    content += "\n"
    for pid, ref in missing:
        content += astra_stream_block(pid, ref) + "\n"
    try:
        mode = stat.S_IMODE(os.stat(config_path).st_mode)
    except Exception:
        mode = 0o644
    try:
        _atomic_write(config_path, content.encode("latin-1"), mode)
    except Exception as e:
        return False, False, "ERROR writing astra.conf: %s" % e
    return True, True, "astra.conf: added %d Abertis streams (%s)" % (
        len(missing), ", ".join(str(p) for p, _ in missing))


def ensure_astra_feed_refs(config_path=None, backup_path=None):
    """Point the astra input of a re-scanned feed at its new transponder.

    astra pulls the T2-MI stream of a feed from the Enigma2 streamrelay
    using the service reference of that feed.  When the feed moved to a new
    transponder (8008 -> 12583 V) the old reference in astra.conf returns
    no data and the proxied channel stays black, even though the feed itself
    is fine.

    Only the input reference of the affected blocks is rewritten; the rest
    of the Ciefp configuration stays byte-for-byte.  Returns
    ``(ok, changed, message)``.
    """
    config_path = config_path or ASTRA_CONF
    backup_path = backup_path or ASTRA_CONF_BACKUP
    from . import lamedb_fix
    overrides = lamedb_fix.FEED_REF_OVERRIDES
    if not overrides:
        return True, False, "no feed reference overrides"
    if not os.path.exists(config_path):
        return False, False, "ERROR: astra.conf not found: %s" % config_path
    try:
        with open(config_path, "rb") as f:
            original = f.read()
        content = original.decode("latin-1", "replace")
    except Exception as e:
        return False, False, "ERROR reading astra.conf: %s" % e

    changed = []
    for pid in sorted(overrides):
        target = overrides[pid]
        pattern = re.compile(
            r'(name\s*=\s*"Abertis PID %s"[\s\S]{0,800}?8001/)([^"]+)' % pid)
        match = pattern.search(content)
        if not match:
            continue
        current = match.group(2).strip()
        if current.upper() == target.upper():
            continue
        content = (content[:match.start(2)] + target + content[match.end(2):])
        changed.append("%s: %s -> %s" % (pid, current, target))

    if not changed:
        return True, False, "astra.conf feed references are up to date"

    try:
        if not os.path.exists(backup_path):
            shutil.copy2(config_path, backup_path)
        mode = stat.S_IMODE(os.stat(config_path).st_mode)
    except Exception as e:
        return False, False, "ERROR preparing astra.conf: %s" % e
    try:
        _atomic_write(config_path, content.encode("latin-1"), mode)
    except Exception as e:
        return False, False, "ERROR writing astra.conf: %s" % e
    return True, True, "astra.conf feed references updated: %s" % "; ".join(changed)


def astra_pids():
    """Return the PIDs of the running astra processes."""
    try:
        output = subprocess.check_output(["pidof", "astra"],
                                         stderr=subprocess.STDOUT)
    except Exception:
        return []
    if not isinstance(output, str):
        output = output.decode("ascii", "replace")
    return output.split()


ASTRA_PORT = 9999


def _tcp_listen_inodes(port):
    """Inode numbers of sockets listening on <port> (from /proc/net/tcp*)."""
    inodes = []
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path) as f:
                lines = f.read().splitlines()
        except Exception:
            continue
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 10:
                continue
            try:
                if int(parts[1].split(":")[1], 16) != port:
                    continue
                if parts[3] == "0A":  # TCP_LISTEN
                    inodes.append(parts[9])
            except Exception:
                continue
    return inodes


def _socket_inode_users(inode):
    """[(pid, command name)] of the processes holding a socket inode."""
    users = []
    try:
        names = os.listdir("/proc")
    except Exception:
        return users
    for name in names:
        if not name.isdigit():
            continue
        fddir = "/proc/%s/fd" % name
        try:
            fds = os.listdir(fddir)
        except Exception:
            continue
        for fd in fds:
            try:
                link = os.readlink(os.path.join(fddir, fd))
            except Exception:
                link = ""
            if link == "socket:[%s]" % inode:
                cmd = ""
                try:
                    with open("/proc/%s/comm" % name) as f:
                        cmd = f.read().strip()
                except Exception:
                    pass
                users.append((int(name), cmd))
                break
    return users


def astra_port_owner(port=ASTRA_PORT):
    """Describe who owns the astra output port.

    Returns ("free", "free"), ("astra", "astra (pid N)") when one of our
    processes is listening, ("busy", "<cmd> (pid N), ...") when a foreign
    service has bound the port, or ("unknown", ...) when /proc cannot be
    read (development systems).
    """
    pids = {}
    try:
        for inode in _tcp_listen_inodes(port):
            for pid, cmd in _socket_inode_users(inode):
                pids.setdefault(pid, cmd)
    except Exception as e:
        return "unknown", "status unknown (%s)" % e
    if not pids:
        return "free", "free"
    owners = ", ".join("%s (pid %d)" % (cmd or "?", pid)
                       for pid, cmd in sorted(pids.items()))
    if all("astra" in (cmd or "").lower() for cmd in pids.values()):
        return "astra", owners
    return "busy", owners


# Provisioning of the astra-sm init script + systemd unit, mirroring the
# postinst heredocs.  postinst can only create them when /usr/bin/astra
# already exists at package-install time; on a fresh receiver the plugin
# deploys the binary later (ensure_astra_tools), so the plugin provisions
# the service itself at setup time.  Only-if-missing: an image-owned
# script or unit is never touched.
ASTRA_INIT_SH = """#!/bin/sh
### BEGIN INIT INFO
# Provides:          astra-sm
# Required-Start:    $local_fs $network
# Required-Stop:     $local_fs $network
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: astra-sm streaming (Abertis T2-MI de-encapsulation)
### END INIT INFO

DAEMON=/usr/bin/astra
CONF=/etc/astra/astra.conf
PIDFILE=/var/run/astra.pid
LOGFILE=/tmp/astra.log

is_running() {
    pidof astra >/dev/null 2>&1
}

case "$1" in
    start)
        if is_running; then
            echo "astra-sm already running"
            exit 0
        fi
        [ -x "$DAEMON" ] || { echo "astra binary missing"; exit 1; }
        [ -f "$CONF" ] || { echo "astra.conf missing"; exit 1; }
        rm -f "$PIDFILE"
        nohup "$DAEMON" --pid "$PIDFILE" --log "$LOGFILE" "$CONF" >/dev/null 2>&1 &
        sleep 1
        if is_running; then
            echo "astra-sm started"
            exit 0
        fi
        echo "astra-sm failed to start"
        exit 1
        ;;
    stop)
        if [ -f "$PIDFILE" ]; then
            kill "$(cat "$PIDFILE")" 2>/dev/null
        fi
        for p in $(pidof astra); do
            kill "$p" 2>/dev/null
        done
        rm -f "$PIDFILE"
        echo "astra-sm stopped"
        ;;
    restart)
        "$0" stop
        sleep 1
        "$0" start
        ;;
    status)
        if is_running; then
            echo "astra-sm running (pid $(pidof astra))"
            exit 0
        fi
        echo "astra-sm stopped"
        exit 3
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
exit 0
"""

ASTRA_UNIT_SH = """[Unit]
Description=Astra SM (Abertis T2-MI de-encapsulation)
After=network.target enigma2.service

[Service]
Type=forking
PIDFile=/var/run/astra.pid
ExecStart=/etc/init.d/astra-sm start
ExecStop=/etc/init.d/astra-sm stop
TimeoutStartSec=30
Restart=on-failure
RestartSec=10

[Install]
WantedBy=graphical.target
"""


def _ensure_astra_init(messages):
    """Create /etc/init.d/astra-sm and its systemd unit when they are absent.

    Calls are idempotent and never overwrite the image's own astra-sm:
    nothing is written when the files already exist.
    """
    if not os.path.exists(ASTRA_BIN):
        return False, "no %s - init script not created" % ASTRA_BIN
    changed = False
    if not os.path.exists(ASTRA_INIT):
        try:
            with open(ASTRA_INIT, "w") as f:
                f.write(ASTRA_INIT_SH)
            os.chmod(ASTRA_INIT, 0o755)
            messages.append("created %s (was missing)" % ASTRA_INIT)
            changed = True
        except Exception as e:
            return False, "could not create %s: %s" % (ASTRA_INIT, e)
    if not os.path.exists(ASTRA_UNIT):
        try:
            with open(ASTRA_UNIT, "w") as f:
                f.write(ASTRA_UNIT_SH)
            os.chmod(ASTRA_UNIT, 0o644)
            messages.append("created %s" % ASTRA_UNIT)
            try:
                subprocess.call(("systemctl", "daemon-reload"))
                subprocess.call(("systemctl", "enable", "astra-sm.service"))
            except Exception:
                pass
        except Exception as e:
            messages.append("could not create %s: %s" % (ASTRA_UNIT, e))
    return True, ("astra init script provisioned" if changed
                  else "astra init script already present")


def controlled_astra_restart():
    """Restart astra only when exactly one instance is running.

    This is deliberately not a blind restart: a second/ambiguous astra
    process is reported and left alone, because it can mean a stale pidfile
    or a second instance fighting for :9999.
    """
    pids = astra_pids()
    if len(pids) > 1:
        return False, "refusing astra restart: %d processes (%s)" % (
            len(pids), ", ".join(pids))
    if not os.path.exists(ASTRA_INIT):
        return False, "refusing astra restart: %s not found" % ASTRA_INIT
    state, owner_txt = astra_port_owner()
    if state == "busy":
        return False, ("refusing astra restart: TCP port %d is held by "
                       "%s - stop or disable that service first"
                       % (ASTRA_PORT, owner_txt))
    try:
        rc = subprocess.call([ASTRA_INIT, "restart"])
    except Exception as e:
        return False, "astra restart failed: %s" % e
    if rc != 0:
        return False, "astra init restart returned %s" % rc
    deadline = time.time() + 15
    while time.time() < deadline:
        pids = astra_pids()
        if len(pids) == 1:
            return True, "astra restarted (pid %s)" % pids[0]
        if len(pids) > 1:
            return False, "astra restart left %d processes (%s)" % (
                len(pids), ", ".join(pids))
        time.sleep(0.5)
    state, owner_txt = astra_port_owner()
    if state != "free":
        return False, "astra did not start within 15s (port %d: %s)" % (
            ASTRA_PORT, owner_txt)
    return False, "astra did not start within 15s"


def restart_astra():
    """Start astra only if it is not running.

    DreamOS's /etc/init.d/astra-sm uses /var/run/astra.pid, which can be
    stale (a failed second instance overwrites it before binding :9999).
    A blind restart then kills the wrong pid, starts a second astra that
    cannot bind :9999 and exits, and systemctl kills the cgroup.  Never
    restart a running astra: just verify it and start it once if absent.
    """
    try:
        if os.system("pidof astra >/dev/null 2>&1") == 0:
            logger.log("astra already running - no restart")
            return True
    except Exception as e:
        logger.log("astra pid check failed: %s" % e)
    state, owner_txt = astra_port_owner()
    if state == "busy":
        logger.log("port %d held by %s - skipping astra start"
                   % (ASTRA_PORT, owner_txt))
        return True
    try:
        if os.path.exists("/var/run/astra.pid"):
            os.remove("/var/run/astra.pid")
    except Exception as e:
        logger.log("astra stale pid remove failed: %s" % e)
    rc = _run("/etc/init.d/astra-sm start >/tmp/abetris_astra.log 2>&1")
    logger.log("astra start tried once (rc=%s)" % rc)
    return True


def ensure_oscam_abertis():
    """Best-effort: append an Abertis reader + services if not present."""
    changed = False
    try:
        if os.path.exists(OSCAM_SERVER):
            txt = open(OSCAM_SERVER).read()
        else:
            txt = ""
        if "AbertisAuto" not in txt:
            block = """
[reader]
label = AbertisAuto
protocol = emu
device = /etc/tuxbox/config/softcam.key
caid = 2600
group = 1
"""
            with open(OSCAM_SERVER, "a") as f:
                f.write(block)
            changed = True
            logger.log("appended Abertis reader to oscam.server")
    except Exception as e:
        logger.log("oscam.server update failed: %s" % e)

    try:
        if not os.path.exists(OSCAM_SERVICES):
            open(OSCAM_SERVICES, "w").close()
        txt = open(OSCAM_SERVICES).read()
        if "AbertisAuto" not in txt:
            with open(OSCAM_SERVICES, "a") as f:
                f.write("[AbertisAuto]\ncaid = 2600\ngroup = 1\n")
            changed = True
            logger.log("appended Abertis services entry")
    except Exception as e:
        logger.log("oscam.services update failed: %s" % e)
    return changed


def _dvbapi_rule_key(line):
    """Normalize an OSCam dvbapi directive without its trailing comment."""
    line = line.split("#", 1)[0].split(";", 1)[0]
    return " ".join(line.strip().split()).lower()


def ensure_oscam_dvbapi_a_rule(config_path=None, backup_path=None):
    """Add the verified PID 2026 F5 A-rule without replacing user config.

    The original config is copied once before the first edit.  Returns
    ``(ok, changed, message)`` so callers can restart OSCam only when a new
    directive actually had to be written.
    """
    config_path = config_path or OSCAM_DVBAPI
    backup_path = backup_path or OSCAM_DVBAPI_BACKUP
    target = _dvbapi_rule_key(ABERTIS_DVBAPI_A_RULE)
    try:
        exists = os.path.exists(config_path)
        shadow = []
        if exists:
            with open(config_path, "rb") as f:
                original = f.read()
            for line in original.splitlines():
                text = line.decode("ascii", "ignore")
                key = _dvbapi_rule_key(text)
                if not key:
                    continue
                if key == target:
                    message = "OSCam A-rule already present; config kept"
                    logger.log(message)
                    return True, False, message
                if "0bd2" in key:
                    # an earlier directive for the same service would win
                    shadow.append(text.strip())
        else:
            original = b""

        config_dir = os.path.dirname(config_path)
        if config_dir and not os.path.isdir(config_dir):
            _makedirs(config_dir)

        if exists and not os.path.exists(backup_path):
            backup_dir = os.path.dirname(backup_path)
            if backup_dir and not os.path.isdir(backup_dir):
                _makedirs(backup_dir)
            shutil.copy2(config_path, backup_path)

        content = original
        if content and not content.endswith((b"\n", b"\r")):
            content += b"\n"
        content += ABERTIS_DVBAPI_A_RULE.encode("ascii") + b"\n"
        _atomic_write(config_path, content)
        message = "OSCam A-rule added to %s" % config_path
        if shadow:
            message += ("; WARNING: an existing directive for 0BD2 may shadow it: %s"
                        % " | ".join(shadow))
        logger.log(message)
        return True, True, message
    except Exception as e:
        message = "ERROR: OSCam A-rule install failed: %s" % e
        logger.log(message)
        return False, False, message


def ensure_oscam_dvbapi_a_rules(config_path=None, backup_path=None, rules=None):
    """Add the A-rules without replacing the user config.

    ``rules`` defaults to the three live-validated feeds; callers can pass the
    complete catalog (``lamedb_fix.build_a_rules()``).  The original file is
    copied once before the first edit.  Returns ``(ok, changed, message)``;
    changed is True only when at least one directive was actually appended.
    """
    config_path = config_path or OSCAM_DVBAPI
    backup_path = backup_path or OSCAM_DVBAPI_BACKUP
    if rules is None:
        rules = ABERTIS_DVBAPI_A_RULES
    rules = tuple(rules)
    try:
        exists = os.path.exists(config_path)
        original = b""
        if exists:
            with open(config_path, "rb") as f:
                original = f.read()
        lines = [line.decode("ascii", "ignore")
                 for line in original.splitlines()]
        existing_keys = set()
        for text in lines:
            key = _dvbapi_rule_key(text)
            if key:
                existing_keys.add(key)
        missing = []
        shadows = []
        for rule in rules:
            target = _dvbapi_rule_key(rule)
            if target in existing_keys:
                continue
            missing.append(rule)
            # A different directive for the same service can shadow the
            # A-rule (e.g. D: 2600:000000:0BD2 1000).
            token = target.split()[1] if len(target.split()) > 1 else ""
            sid = token.split(":")[2][:4] if token.startswith("::") else ""
            if sid:
                for text in lines:
                    key = _dvbapi_rule_key(text)
                    if key and key != target and sid in key:
                        shadows.append(text.strip())
        if not missing:
            message = "OSCam A-rules already present; config kept"
            logger.log(message)
            return True, False, message

        config_dir = os.path.dirname(config_path)
        if config_dir and not os.path.isdir(config_dir):
            _makedirs(config_dir)
        if exists and not os.path.exists(backup_path):
            backup_dir = os.path.dirname(backup_path)
            if backup_dir and not os.path.isdir(backup_dir):
                _makedirs(backup_dir)
            shutil.copy2(config_path, backup_path)

        content = original
        if content and not content.endswith((b"\n", b"\r")):
            content += b"\n"
        for rule in missing:
            content += rule.encode("ascii") + b"\n"
        _atomic_write(config_path, content)
        added = ", ".join("PID " + rule.split("::")[1].split(":")[0]
                          for rule in missing)
        message = "OSCam A-rules added to %s: %s" % (config_path, added)
        if shadows:
            message += ("; WARNING: an existing directive may shadow one: %s"
                        % " | ".join(shadows))
        logger.log(message)
        return True, True, message
    except Exception as e:
        message = "ERROR: OSCam A-rules install failed: %s" % e
        logger.log(message)
        return False, False, message


def _existing_init_script():
    """Return an OSCam init script that exists on this box (or None)."""
    for path in OSCAM_INIT_SCRIPTS:
        try:
            if os.path.exists(path):
                return path
        except Exception:
            pass
    return None


def restart_oscam():
    """Restart OSCam: one active systemd unit, else the OSCam init script."""
    list_cmd = ["systemctl", "list-units", "--type=service", "--state=active",
                "--no-legend", "--no-pager"]
    try:
        output = subprocess.check_output(list_cmd, stderr=subprocess.STDOUT)
    except Exception as e:
        logger.log("OSCam restart skipped (cannot list active units): %s" % e)
        return _restart_oscam_init_script()
    if not isinstance(output, str):
        output = output.decode("utf-8", "replace")

    units = []
    for line in output.splitlines():
        fields = line.split()
        if not fields:
            continue
        unit = fields[0]
        low = unit.lower()
        if not low.endswith(".service"):
            continue
        # only a unit that is really named after oscam, not "backup-oscam"
        if not low.startswith("oscam"):
            continue
        if unit not in units:
            units.append(unit)
    if len(units) > 1:
        logger.log("OSCam restart skipped (%d active OSCam units; expected one)" %
                   len(units))
        return False
    if not units:
        logger.log("OSCam restart: no active OSCam systemd unit found")
        return _restart_oscam_init_script()

    unit = units[0]
    try:
        rc = subprocess.call(["systemctl", "restart", unit])
        if rc != 0:
            logger.log("OSCam restart failed for %s (rc=%s)" % (unit, rc))
            return False
        state = subprocess.check_output(["systemctl", "is-active", unit],
                                        stderr=subprocess.STDOUT).strip()
        if not isinstance(state, str):
            state = state.decode("utf-8", "replace")
        if state != "active":
            logger.log("OSCam restart did not return %s to active (state=%s)" %
                       (unit, state))
            return False
        logger.log("OSCam service restarted: %s" % unit)
        return True
    except Exception as e:
        logger.log("OSCam restart failed for %s: %s" % (unit, e))
        return False


def _restart_oscam_init_script():
    """Restart OSCam through its init script (boxes without a systemd unit)."""
    script = _existing_init_script()
    if not script:
        logger.log("OSCam restart skipped (no OSCam systemd unit and no init script)")
        return False
    try:
        rc = subprocess.call([script, "restart"])
        if rc != 0:
            logger.log("OSCam restart via %s failed (rc=%s)" % (script, rc))
            return False
        logger.log("OSCam restarted via %s" % script)
        return True
    except Exception as e:
        logger.log("OSCam restart via %s failed: %s" % (script, e))
        return False


def ensure_abertis_script():
    """Make sure /etc/astra/scripts/abertis is a native tool of the
    receiver architecture.

    The native binary (bundled with the plugin) is the Abertis T2-MI
    de-encapsulator: it turns the scrambled T2-MI PID of a feed into the
    clear transport stream of the channel.  The python fallback only
    extracts the PID payload and is therefore NOT equivalent, it is just
    there to have something that runs.
    """
    # Per-architecture binary selection: prefer arch/<arch>/abertis.  When
    # the package ships no binary for this receiver (e.g. the astra tools
    # only exist as arm64, the abertis tool only for arm64/arm/mips), an
    # aarch64 binary must NEVER overwrite a working one on a mips or 32-bit
    # arm box: keep the installed one or fall back to the python script.
    arch = _get_receiver_arch()
    here = os.path.dirname(os.path.abspath(__file__))
    arch_binary = os.path.join(here, "arch", arch, "abertis")
    native_src = None
    if os.path.isfile(arch_binary):
        native_src = arch_binary
    elif arch == "arm64":
        # the tool shipped loose in the plugin directory is aarch64 too
        native_src = BUNDLED_NATIVE
    try:
        need = True
        if os.path.exists(ABERTIS_SCRIPT):
            mach = _elf_machine(ABERTIS_SCRIPT)
            if mach is None:
                # not an ELF (python/shell script) -> keep
                need = False
            elif native_src is None:
                # nothing native for this receiver architecture: never
                # touch a binary that is already installed
                logger.log("no native abertis tool for arch %s - "
                           "keeping the installed binary" % arch)
                need = False
            else:
                target_mach = _elf_machine(native_src)
                # keep the binary when it matches what we would install
                if mach == target_mach:
                    need = False
        if not need:
            logger.log("abertis script already present (arch=%s)" % arch)
            return True
        if native_src is None:
            raise IOError("no native abertis tool for arch %s" % arch)
        _makedirs(os.path.dirname(ABERTIS_SCRIPT))
    except Exception:
        pass
    # 1) the native tool for the receiver architecture
    try:
        if native_src is not None and os.path.exists(native_src):
            with open(native_src, "rb") as f:
                data = f.read()
            tmp = ABERTIS_SCRIPT + ".new"
            with open(tmp, "wb") as f:
                f.write(data)
            os.chmod(tmp, 0o755)
            try:
                backup = ABERTIS_SCRIPT + ".orig"
                if not os.path.exists(backup):
                    shutil.copy2(ABERTIS_SCRIPT, backup)
                    logger.log("previous abertis tool kept as %s" % backup)
                os.rename(tmp, ABERTIS_SCRIPT)
            except Exception:
                os.remove(tmp)
                raise
            logger.log("installed native abertis tool (arch=%s) at %s" % (arch, ABERTIS_SCRIPT))
            return True
    except Exception as e:
        logger.log("native abertis install failed: %s" % e)
    # 2) the portable python fallback
    try:
        data = base64.b64decode(ABERTIS_SCRIPT_B64)
        with open(ABERTIS_SCRIPT, "wb") as f:
            f.write(data)
        os.chmod(ABERTIS_SCRIPT, 0o755)
        logger.log("installed python abertis script at %s" % ABERTIS_SCRIPT)
        return True
    except Exception as e:
        logger.log("ensure_abertis_script failed: %s" % e)
        return False


def apply_all_feeds(restart=True):
    """Install the A-rules and astra streams of every Abertis feed.

    Both files are backed up once and only missing entries are appended, so
    the operation is idempotent.  When ``restart`` is true, astra and OSCam
    are restarted only when their file actually changed; astra's restart is
    guarded by ``controlled_astra_restart()``.
    """
    from . import lamedb_fix
    feeds = lamedb_fix.get_all_feeds()
    rules = lamedb_fix.build_a_rules(feeds)
    messages = []

    ensure_astra_conf()
    astra_ok, astra_changed, astra_msg = ensure_astra_streams(feeds=feeds)
    messages.append(astra_msg)
    logger.log(astra_msg)
    if astra_ok and astra_changed and restart:
        ok, msg = controlled_astra_restart()
        messages.append(msg)
        logger.log(msg)

    oscam_ok, oscam_changed, oscam_msg = ensure_oscam_dvbapi_a_rules(rules=rules)
    messages.append(oscam_msg)
    logger.log(oscam_msg)
    if oscam_ok and oscam_changed and restart:
        restart_oscam()

    return bool(astra_ok and oscam_ok), messages


# The astra-sm binaries that the package ships.  They are installed into
# /usr/bin by ensure_astra_tools(); a file that is replaced is backed up
# once as <file>.orig and the working astra.conf is never touched.
ASTRA_TOOLS = (
    ("astra", "/usr/bin/astra"),
    ("t2mi_decap", "/usr/bin/t2mi_decap"),
    ("spammer", "/usr/bin/spammer"),
)


def _same_file(left, right):
    try:
        if os.path.getsize(left) != os.path.getsize(right):
            return False
        import filecmp
        return filecmp.cmp(left, right, shallow=False)
    except Exception:
        return False


# Libraries the patched astra tools are dynamically linked against.  Some
# images (e.g. openATV 8) ship libdvbcsa but not OpenSSL 3, third-party
# DreamOS images (e.g. DreamELite) ship neither: a needed library the
# package carries inside the plugin directory is deployed into /usr/lib as
# a NEW file - an existing system library is never touched.  When neither
# the image nor the package provides a library, the image package manager
# (apt-get / opkg) is tried once before keeping the installed binary.
TOOL_SHARED_LIBS = {
    "astra": ("libcrypto.so.3", "libdvbcsa.so.1"),
    "t2mi_decap": ("libcrypto.so.3", "libdvbcsa.so.1"),
    "spammer": (),
}


def _lib_on_image(name):
    """True when the dynamic loader can find <name> on this image."""
    for path in ("/usr/lib/" + name, "/usr/lib64/" + name,
                 "/lib/" + name, "/lib64/" + name):
        if os.path.exists(path):
            return True
    try:
        p = subprocess.Popen(("ldconfig", "-p"),
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        try:
            out = p.communicate()[0]
        except Exception:
            out = ""
        if name in out.decode("utf-8", "ignore"):
            return True
    except Exception:
        pass
    return False


# Missing libraries that can still be provided by the image's own package
# manager (offline receivers simply keep their installed binary - nothing
# is ever removed or overwritten).
TOOL_LIB_PACKAGES = {
    "libdvbcsa.so.1": ("libdvbcsa1", "libdvbcsa"),
}


def _pm_install_library(lib, messages):
    """Best-effort package-manager install of a missing shared library.

    Only used when the library is missing on the image and the package
    does not ship it: opkg on opkg images, apt-get on dpkg images.  One
    attempt per boot (marker file in /tmp keeps an offline receiver from
    retrying a slow lookup over and over).
    """
    names = TOOL_LIB_PACKAGES.get(lib)
    if not names:
        return False
    marker = "/tmp/.abetris_pm_" + lib.replace(".", "_")
    if os.path.exists(marker):
        return False
    log = "/tmp/abetris_lib.log"
    for pkg in names:
        try:
            if os.path.exists("/usr/bin/opkg"):
                cmd = ("/usr/bin/opkg", "install", pkg)
            elif os.path.exists("/usr/bin/apt-get"):
                cmd = ("/usr/bin/apt-get", "install", "-y", pkg)
            else:
                return False
            with open(log, "ab") as out:
                rc = subprocess.call(cmd, stdout=out,
                                     stderr=subprocess.STDOUT)
        except Exception as e:
            messages.append("%s: package-manager install failed: %s"
                            % (lib, e))
            return False
        finally:
            try:
                open(marker, "w").close()
            except Exception:
                pass
        if rc == 0 and _lib_on_image(lib):
            messages.append("%s: installed from the image feed (%s)"
                            % (lib, pkg))
            return True
    messages.append("%s: the image package manager did not provide it "
                    "(on DreamOS try manually: apt-get update && "
                    "apt-get install -y libdvbcsa1)" % lib)
    return False


def _ensure_tool_shared_libs(tool, here, messages):
    """Make sure the shared libraries the shipped tool needs exist.

    Returns True when the shipped binary can be loaded by the image,
    False when a required library is neither present nor shipped - in
    that case the installed binary is kept (never brick a working setup).
    """
    ok = True
    for lib in TOOL_SHARED_LIBS.get(tool, ()):
        if _lib_on_image(lib):
            continue
        src = os.path.join(here, lib)
        if not os.path.isfile(src):
            if _pm_install_library(lib, messages):
                continue
            messages.append("%s: this image lacks %s and the package "
                            "does not ship it - keeping the installed "
                            "binary" % (tool, lib))
            ok = False
            continue
        target = "/usr/lib/" + lib
        try:
            shutil.copy2(src, target)
            os.chmod(target, 0o644)
            messages.append("deployed %s into /usr/lib (image lacked it)" % lib)
            try:
                subprocess.call(("ldconfig",))
            except Exception:
                pass
        except Exception as e:
            messages.append("%s: could not deploy %s: %s" % (tool, lib, e))
            ok = False
    return ok


def ensure_astra_tools():
    """Install the astra-sm binaries that the package ships.

    Per-architecture: checks for arch/<arch>/{astra,t2mi_decap,spammer} first
    (the package ships the full set for aarch64).  The loose binaries in the
    plugin directory are aarch64 too, so they are only used as a fallback on
    arch64 receivers - a wrong-architecture binary is never deployed.

    Returns (changed, messages).  The call is idempotent: a file that is
    already the shipped one is left alone, and a file that is replaced is
    backed up once.  Replacing a running binary is done with a rename, so
    the running process keeps working until it is restarted.
    """
    import shutil
    messages = []
    changed = False
    here = os.path.dirname(os.path.abspath(__file__))
    arch = _get_receiver_arch()
    arch_dir = os.path.join(here, "arch", arch)
    for name, target in ASTRA_TOOLS:
        src = os.path.join(arch_dir, name)
        if not os.path.isfile(src) and arch == "arm64":
            # the binaries shipped loose in the plugin directory are aarch64
            src = os.path.join(here, name)
        if not os.path.isfile(src):
            # astra/t2mi_decap/spammer are only shipped for arm64; on other
            # architectures keep whatever the image or the user installed
            messages.append("%s: no %s binary shipped, leaving the "
                            "installed one untouched" % (target, arch))
            if target.endswith("/astra") and os.path.exists(target) \
                    and not _lib_on_image("libdvbcsa.so.1"):
                # the image's own astra needs libdvbcsa too on some images
                _pm_install_library("libdvbcsa.so.1", messages)
            continue
        try:
            if os.path.exists(target) and _same_file(src, target):
                # libs are re-checked even when the binary is already in
                # place: some images (DreamELite on Dream One) lack
                # libdvbcsa.so.1 although astra was installed before
                _ensure_tool_shared_libs(name, here, messages)
                messages.append("%s: already installed" % target)
                continue
            if not _ensure_tool_shared_libs(name, here, messages):
                continue
            if os.path.exists(target):
                backup = target + ".orig"
                if not os.path.exists(backup):
                    shutil.copy2(target, backup)
                    messages.append("%s: previous version kept as %s" % (target, backup))
            tmp = target + ".new"
            shutil.copy2(src, tmp)
            os.chmod(tmp, 0o755)
            os.rename(tmp, target)
            changed = True
            messages.append("%s: installed (arch=%s)" % (target, arch))
        except Exception as e:
            messages.append("%s: %s" % (target, e))
    return changed, messages


def ensure_oscam_abertis():
    """Start the Abertis-capable OSCam binary if it is not running.

    DreamOS 2.6 ships oscam_2.service (running /usr/bin/oscam_2) which does
    not have the Abertis BISS keys.  The DEB ships OSCam_11964-803, which
    does.  If it is not running, start it directly; the plugin never
    stops or reconfigures an already running OSCam.
    """
    bin_path = "/usr/bin/OSCam_11964-803"
    if not os.path.exists(bin_path):
        return False, "oscam binary not found"
    try:
        if _run("pidof OSCam_11964-803").strip():
            return True, "oscam already running"
    except Exception:
        pass
    try:
        _run("%s -b >>/tmp/abetris_oscam.log 2>&1" % bin_path)
        import time
        time.sleep(0.5)
        if _run("pidof OSCam_11964-803").strip():
            return True, "oscam started"
        return False, "oscam start failed (see /tmp/abetris_oscam.log)"
    except Exception as e:
        return False, "oscam start failed: %s" % e


def run_full_setup(restart_configs=True):
    """Prepare all Abertis feeds and fix the three validated lamedb entries.

    ``restart_configs`` is False at boot: configuration files are only
    changed when something is missing, and a pending astra restart is logged
    instead of interrupting a running stream.  The UI passes True, so its
    explicit "Run setup" action can apply a controlled restart.
    """
    logger.log("=== Abertis Auto full setup start ===")
    tools_changed, tool_messages = ensure_astra_tools()
    for msg in tool_messages:
        logger.log(msg)
    ensure_abertis_script()
    oscam_ok, oscam_msg = ensure_oscam_abertis()
    logger.log(oscam_msg)
    ensure_softcam_key()
    key_ok, key_changed = ensure_softcam_key_upper()
    if key_changed:
        if restart_configs:
            restart_oscam()
        else:
            logger.log("SoftCam.Key updated - OSCam restart required")
    from . import lamedb_fix
    feeds = lamedb_fix.get_all_feeds()
    rules = lamedb_fix.build_a_rules(feeds)
    oscam_ok, oscam_changed, oscam_message = ensure_oscam_dvbapi_a_rules(rules=rules)
    logger.log(oscam_message)
    if oscam_ok and oscam_changed:
        if restart_configs:
            restart_oscam()
        else:
            logger.log("oscam.dvbapi updated - OSCam restart required")
    if not astra_present():
        logger.log("astra binary NOT found - skipping astra steps (install astra-sm manually)")
    else:
        state, owner_txt = astra_port_owner()
        logger.log("port %d: %s" % (ASTRA_PORT, owner_txt))
        init_ok, init_msg = _ensure_astra_init([])
        logger.log(init_msg)
        ensure_astra_conf()
        astra_ok, astra_changed, astra_message = ensure_astra_streams(feeds=feeds)
        logger.log(astra_message)
        ref_ok, ref_changed, ref_message = ensure_astra_feed_refs()
        logger.log(ref_message)
        if ref_changed:
            astra_changed = True
        if astra_changed:
            if restart_configs:
                ok, msg = controlled_astra_restart()
                logger.log(msg)
            else:
                logger.log("astra.conf updated - a controlled astra restart is required")
        elif tools_changed or oscam_ok:
            # the astra binary or oscam was (re)started: make sure astra
            # itself is up as well
            if restart_configs:
                ok, msg = controlled_astra_restart()
                logger.log(msg)
            else:
                logger.log("astra restart required")
        restart_astra()
    # Keep the OSCam binary and every existing config directive untouched apart
    # from the backed-up A-rules above.
    try:
        import os
        if os.path.exists("/usr/bin/OSCam_11964-803") or os.path.exists("/usr/bin/oscam"):
            logger.log("oscam present - leaving config untouched, reloading bouquets")
        else:
            logger.log("oscam binary not found")
    except Exception:
        pass
    count, details = lamedb_fix.fix_all()
    for d in details:
        logger.log(d)
    logger.log("=== Abertis Auto full setup done (%d services, %d feeds) ===" % (
        count, len(feeds)))
    return len(feeds) if feeds else count
