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

ASTRA_BIN_CANDIDATES = ["/usr/bin/astra", "/usr/bin/astra-sm", "/etc/astra/astra"]
ABERTIS_SCRIPT = "/etc/astra/scripts/abertis"
BUNDLED_NATIVE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "abertis.aarch64")
ABERTIS_SCRIPT_B64 = "IyEvdXNyL2Jpbi9lbnYgcHl0aG9uCiMgLSotIGNvZGluZzogdXRmLTggLSotCiIiIkFiZXJ0aXMgVDItTUkgZGUtZW5jYXBzdWxhdG9yIChhYXJjaDY0LWZyaWVuZGx5IFB5dGhvbiByZXBsYWNlbWVudCkuCgpFeHRyYWN0cyB0aGUgTVBFRy1UUyBwYWNrZXRzIGZvciBhIGdpdmVuIFBJRCBmcm9tIHN0ZGluIGFuZCB3cml0ZXMgdGhlaXIKcGF5bG9hZCB0byBzdGRvdXQuIERyb3AtaW4gcmVwbGFjZW1lbnQgZm9yIHRoZSBhcm1oZiAnYWJlcnRpcycgYmluYXJ5IHRoYXQKZG9lcyBub3QgcnVuIG9uIDY0LWJpdCBEcmVhbU9TLgoKVXNhZ2U6ICBhYmVydGlzIDxQSUQ+CiIiIgppbXBvcnQgc3lzCgoKZGVmIF9zdHJlYW1zKCk6CiAgICB0cnk6CiAgICAgICAgcmV0dXJuIHN5cy5zdGRpbi5idWZmZXIsIHN5cy5zdGRvdXQuYnVmZmVyCiAgICBleGNlcHQgQXR0cmlidXRlRXJyb3I6CiAgICAgICAgcmV0dXJuIHN5cy5zdGRpbiwgc3lzLnN0ZG91dAoKCmRlZiBfYih4KToKICAgICIiIlJldHVybiBpbnRlZ2VyIHZhbHVlIG9mIGEgYnl0ZSwgcHkyL3B5MyBzYWZlLiIiIgogICAgaWYgaXNpbnN0YW5jZSh4LCBpbnQpOgogICAgICAgIHJldHVybiB4CiAgICByZXR1cm4gb3JkKHgpCgoKZGVmIG1haW4oKToKICAgIGlmIGxlbihzeXMuYXJndikgPCAyOgogICAgICAgIHN5cy5zdGRlcnIud3JpdGUoInVzYWdlOiBhYmVydGlzIDxQSUQ+XG4iKQogICAgICAgIHJldHVybiAyCiAgICB0cnk6CiAgICAgICAgcGlkID0gaW50KHN5cy5hcmd2WzFdKQogICAgZXhjZXB0IFZhbHVlRXJyb3I6CiAgICAgICAgc3lzLnN0ZGVyci53cml0ZSgiaW52YWxpZCBQSUQ6ICVzXG4iICUgc3lzLmFyZ3ZbMV0pCiAgICAgICAgcmV0dXJuIDIKCiAgICBpbnAsIG91dCA9IF9zdHJlYW1zKCkKICAgIFNZTkMgPSAweDQ3CiAgICB3aGlsZSBUcnVlOgogICAgICAgIGNodW5rID0gaW5wLnJlYWQoMTg4KQogICAgICAgIGlmIG5vdCBjaHVuazoKICAgICAgICAgICAgYnJlYWsKICAgICAgICBpZiBsZW4oY2h1bmspIDwgMTg4OgogICAgICAgICAgICBicmVhawogICAgICAgIGJ1ZiA9IGNodW5rCiAgICAgICAgaWYgX2IoYnVmWzBdKSAhPSBTWU5DOgogICAgICAgICAgICBpZHggPSBidWYuZmluZChjaHIoU1lOQykgaWYgbm90IGlzaW5zdGFuY2UoYnVmWzBdLCBpbnQpIGVsc2UgYnl0ZXMoW1NZTkNdKSkKICAgICAgICAgICAgIyBzaW1wbGVyOiB0cnkgYm90aAogICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICBpZHggPSBidWYuZmluZChiIlx4NDciKQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICAgICAgaWR4ID0gLTEKICAgICAgICAgICAgaWYgaWR4IDwgMDoKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICMgc2tpcCB0aGlzIG1pc2FsaWduZWQgY2h1bmsKICAgICAgICAgICAgY29udGludWUKICAgICAgICB0c3BpZCA9ICgoX2IoYnVmWzFdKSAmIDB4MUYpIDw8IDgpIHwgX2IoYnVmWzJdKQogICAgICAgIGlmIHRzcGlkICE9IHBpZDoKICAgICAgICAgICAgY29udGludWUKICAgICAgICBhZmMgPSBfYihidWZbM10pICYgMHgzMAogICAgICAgIHBheWxvYWQgPSBiIiIKICAgICAgICBpZiBhZmMgPT0gMHgxMDoKICAgICAgICAgICAgcGF5bG9hZCA9IGJ1Zls0Ol0KICAgICAgICBlbGlmIGFmYyA9PSAweDMwOgogICAgICAgICAgICBhZmwgPSBfYihidWZbNF0pCiAgICAgICAgICAgIHBheWxvYWQgPSBidWZbNSArIGFmbDpdCiAgICAgICAgIyAweDIwIGFkYXB0YXRpb24gb25seSwgMHgwMCBubyBwYXlsb2FkIC0+IGVtcHR5CiAgICAgICAgaWYgcGF5bG9hZDoKICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgb3V0LndyaXRlKHBheWxvYWQpCiAgICAgICAgICAgICAgICBvdXQuZmx1c2goKQogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICAgICAgcGFzcwogICAgdHJ5OgogICAgICAgIG91dC5mbHVzaCgpCiAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgIHBhc3MKICAgIHJldHVybiAwCgoKaWYgX19uYW1lX18gPT0gIl9fbWFpbl9fIjoKICAgIHN5cy5leGl0KG1haW4oKSkK"
ASTRA_CONF = "/etc/astra/astra.conf"
ASTRA_CONF_BACKUP = ASTRA_CONF + ".abetrisauto.bak"
ASTRA_INIT = "/etc/init.d/astra-sm"
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
-- Adjust the input transponder and output UDP port to your setup.
-- Hispasat 30.0W Abertis example (T2-MI PLP). Update frequency/symbol rate as needed.
log file /tmp/astra.log
log debug

-- Input: satellite transponder
input {
  type = "dvb"
  adapter = 0
  delivery_system = "dvbs2"
  frequency = 11739000
  symbol_rate = 27500000
  polarization = "vertical"
  fec = "3/4"
  modulation = "8psk"
  rolloff = "0.35"
  plp = 0
}

-- Output: local UDP stream consumed by the lamedb stream-relay service
output {
  type = "udp"
  address = "127.0.0.1"
  port = 5000
}
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
    if os.path.exists(ASTRA_CONF):
        logger.log("astra.conf already exists, keeping it")
        return True
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
    """Make sure /etc/astra/scripts/abertis is the native aarch64 tool.

    The native binary (bundled with the plugin) is the Abertis T2-MI
    de-encapsulator: it turns the scrambled T2-MI PID of a feed into the
    clear transport stream of the channel.  The python fallback only
    extracts the PID payload and is therefore NOT equivalent, it is just
    there to have something that runs.
    """
    try:
        need = True
        if os.path.exists(ABERTIS_SCRIPT):
            mach = _elf_machine(ABERTIS_SCRIPT)
            if mach is None:
                # not an ELF (python/shell script) -> keep
                need = False
            elif mach == 0xB7:
                # AArch64 native -> keep the known-good binary
                need = False
            elif mach == 0x28:
                # ARM 32-bit -> replace with the aarch64 native
                need = True
            else:
                need = True
        if not need:
            logger.log("abertis script already present (native aarch64 or script)")
            return True
        _makedirs(os.path.dirname(ABERTIS_SCRIPT))
    except Exception:
        pass
    # 1) the bundled aarch64 native tool
    try:
        if os.path.exists(BUNDLED_NATIVE):
            with open(BUNDLED_NATIVE, "rb") as f:
                data = f.read()
            tmp = ABERTIS_SCRIPT + ".new"
            with open(tmp, "wb") as f:
                f.write(data)
            os.chmod(tmp, 0o755)
            try:
                os.rename(tmp, ABERTIS_SCRIPT)
            except Exception:
                os.remove(tmp)
                raise
            logger.log("installed native aarch64 abertis tool at %s" % ABERTIS_SCRIPT)
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


def ensure_astra_tools():
    """Install the astra-sm binaries that the package ships.

    Returns (changed, messages).  The call is idempotent: a file that is
    already the shipped one is left alone, and a file that is replaced is
    backed up once.  Replacing a running binary is done with a rename, so
    the running process keeps working until it is restarted.
    """
    import shutil
    messages = []
    changed = False
    here = os.path.dirname(os.path.abspath(__file__))
    for name, target in ASTRA_TOOLS:
        src = os.path.join(here, name)
        if not os.path.isfile(src):
            messages.append("%s: not shipped, skipped" % target)
            continue
        try:
            if os.path.exists(target) and _same_file(src, target):
                messages.append("%s: already installed" % target)
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
            messages.append("%s: installed" % target)
        except Exception as e:
            messages.append("%s: %s" % (target, e))
    return changed, messages


# Runtime libraries that the shipped astra-sm binaries need on a clean
# DreamOS image (the image ships OpenSSL 1.0 and no libdvbcsa at all).
RUNTIME_LIBS = (
    ("libdvbcsa.so.1", "/usr/lib/libdvbcsa.so.1"),
    ("libcrypto.so.3", "/usr/lib/libcrypto.so.3"),
)


def ensure_runtime_libs():
    """Install the runtime libraries shipped by the package.

    A file that is missing is created, a file that differs is backed up
    once and replaced.  The call is idempotent.  Returns (changed, messages).
    """
    import shutil
    messages = []
    changed = False
    here = os.path.dirname(os.path.abspath(__file__))
    for name, target in RUNTIME_LIBS:
        src = os.path.join(here, name)
        if not os.path.isfile(src):
            messages.append("%s: not shipped, skipped" % target)
            continue
        try:
            if os.path.exists(target):
                if os.path.getsize(src) == os.path.getsize(target):
                    with open(src, "rb") as f1, open(target, "rb") as f2:
                        if f1.read() == f2.read():
                            messages.append("%s: already installed" % target)
                            continue
                backup = target + ".orig"
                if not os.path.exists(backup):
                    shutil.copy2(target, backup)
                    messages.append("%s: previous version kept as %s" % (target, backup))
            tmp = target + ".new"
            shutil.copy2(src, tmp)
            os.chmod(tmp, 0o755)
            os.rename(tmp, target)
            changed = True
            messages.append("%s: installed" % target)
        except Exception as e:
            messages.append("%s: %s" % (target, e))
    return changed, messages


def run_full_setup(restart_configs=True):
    """Prepare all Abertis feeds and fix the three validated lamedb entries.

    ``restart_configs`` is False at boot: configuration files are only
    changed when something is missing, and a pending astra restart is logged
    instead of interrupting a running stream.  The UI passes True, so its
    explicit "Run setup" action can apply a controlled restart.
    """
    logger.log("=== Abertis Auto full setup start ===")
    libs_changed, lib_messages = ensure_runtime_libs()
    for msg in lib_messages:
        logger.log(msg)
    tools_changed, tool_messages = ensure_astra_tools()
    for msg in tool_messages:
        logger.log(msg)
    ensure_abertis_script()
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
        if tools_changed or libs_changed:
            # the astra binary or one of its libraries was replaced: it
            # only takes effect with a restart
            if restart_configs:
                ok, msg = controlled_astra_restart()
                logger.log(msg)
            else:
                logger.log("astra binary or its libraries updated - a controlled astra restart is required")
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
