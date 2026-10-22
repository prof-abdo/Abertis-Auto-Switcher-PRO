# -*- coding: utf-8 -*-
"""lamedb rules for Abertis on DreamOS 2.6.

apply()/prestart writes the final F5 state for the three boot-managed feeds:

  2026: F5 + data only
  2050: F5 + data only
  8001: F5 + data only

The runtime automation handles every other feed on selection with the same
F1 learning -> F5 playback sequence.  Only the three boot-managed services
are changed by apply().

All feeds must finish in F5 with the cached data pid only.  Measured on
DreamOS 2.6: with F1 (+/- PMT) the streamserver forwards only the sections
(PAT/PMT) to astra and the T2-MI data pid never reaches the de-encapsulator,
so the channel stays black.  In F5 the streamserver hands the data pid to
astra, which unwraps the T2-MI stream.  The BISS key comes from the
OSCam-EMU A-rule, so the F1 learning phase is only a temporary step of the
runtime automation, never the final state.

Other Abertis services are left exactly as they are.
"""
import io
import os
import re
import stat

LAMEDB = "/etc/enigma2/lamedb"
BACKUP = "/etc/enigma2/lamedb.abertis.bak"
AUTO_BACKUP = "/etc/enigma2/lamedb.auto.bak"
MARKER = "/tmp/abertis_prestart_ok"

# Rules validated live on DreamOS 2.6 (2026-10-22).
#
# The final state of every managed feed is F5 + data pid only.  Validated by
# measurement:
#   F5 + data            -> the streamserver hands the data pid (2026=0x07EA,
#                           2050=0x0802, 8001=0x1F41) to astra, the T2-MI
#                           de-encapsulator (/etc/astra/scripts/abertis <pid>)
#                           unwraps the channel and astra outputs the clear TS
#   F5 + data + PMT      -> the PMT is not part of the demux filters, the
#                           de-encapsulator output is garbage
#   F1 (+/- PMT)         -> on 2050/8001 only the sections (PAT/PMT) reach
#                           astra; the data pid never arrives and the channel
#                           stays black.  This was measured on both
#                           transponders (11222H and 12631V).
# The BISS key comes from the OSCam-EMU A-rule, so the F1 learning phase is
# only a temporary runtime step; apply()/prestart always writes F5.
SERVICE_RULES = {
    "2026": {"flag": 5, "data": "0007ea", "pmt": None},
    "2050": {"flag": 5, "data": "000802", "pmt": None},
    "8001": {"flag": 5, "data": "001f41", "pmt": None},
}
PLAY_RULES = {
    "2026": {"flag": 5, "data": "0007ea", "pmt": None},
    "2050": {"flag": 5, "data": "000802", "pmt": None},
    "8001": {"flag": 5, "data": "001f41", "pmt": None},
}
# Temporary learning modes: the feed is played with the real outer PAT/PMT so
# the frontend/OSCam can see the CA program once.  Never the final state.
LEARNING_RULES = {
    "2026": {"flag": 1, "data": "0007ea", "pmt": "1b72"},
    "2050": {"flag": 1, "data": "000802", "pmt": "1b8a"},
    "8001": {"flag": 1, "data": "001f41", "pmt": "1389"},
}
# Backward-compatible aliases.
RULE_2026_PLAY = PLAY_RULES["2026"]
RULE_2026_F1 = LEARNING_RULES["2026"]
RULE_2026_F5 = PLAY_RULES["2026"]
RULE_2050_PLAY = PLAY_RULES["2050"]
RULE_2050_F1 = LEARNING_RULES["2050"]
RULE_8001_PLAY = PLAY_RULES["8001"]
RULE_8001_F1 = LEARNING_RULES["8001"]

# The three boot-managed feeds use their measured F1 learning PMT.  Every
# other feed derives its F1 PMT from the outer SID (PMT_PID_OFFSET below);
# all feeds then switch to F5 + data before astra playback.
LEARNING_PMTS = dict((pid, rule["pmt"])
                     for pid, rule in LEARNING_RULES.items())

# The Abertis mux places the outer PMT of a feed 0x0FA0 above its outer
# service id (verified on 2025/2026/2027/301/8001: 0BD1->1B71, 0BD2->1B72,
# 0515->14B5, 03E9->1389).  This makes the F1 learning phase possible for
# every feed without a hardcoded per-feed table.
PMT_PID_OFFSET = 0x0FA0


def learning_pmt(pid):
    """Return the feed's outer PMT PID (measured or derived from its SID)."""
    pid = str(int(pid))
    pmt = LEARNING_PMTS.get(pid)
    if pmt:
        return pmt
    info = get_feed_info(pid)
    if info:
        return "%04x" % ((int(info["sid"]) + PMT_PID_OFFSET) & 0x1FFF)
    return None

try:
    _TEXT = unicode
except NameError:
    _TEXT = str

SERVICE_REF_RE = re.compile(r"^[0-9a-fA-F]{4}:")
NAME_RE = re.compile(r"^Abertis PID (\d+)(?: F[0-9a-fA-F]+)?$", re.IGNORECASE)

# A feed can be re-scanned on a new transponder while keeping the same
# Abertis PID/URL.  The old lamedb entry may still exist with no signal, so
# point the runtime at the newly scanned service explicitly.
# 8008: Hispasat 30W, 12583 V 16901, SID 0x3F0, scanned 2026-10-22.
FEED_REF_OVERRIDES = {
    "8008": "1:0:1:3F0:EA68:0:CE4B127:0:0:0:",
}


def _tmpdir():
    d = os.path.dirname(LAMEDB)
    return d if d else "/etc/enigma2"


def _read_lines(path):
    with io.open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        return f.readlines()


def _ref_parts(ref):
    """Return (sid, tsid, onid, ns) from an Enigma2 service reference."""
    parts = str(ref).split(":")
    if len(parts) < 7:
        return None
    try:
        return (int(parts[3], 16), int(parts[4], 16),
                int(parts[5], 16), int(parts[6], 16))
    except ValueError:
        return None


def _service_index_for_ref(lines, ref):
    """Find the lamedb service block matching an Enigma2 reference."""
    target = _ref_parts(ref)
    if target is None:
        return None
    for i in range(0, len(lines) - 2):
        if not SERVICE_REF_RE.match(lines[i].strip()):
            continue
        parts = lines[i].strip().split(":")
        if len(parts) < 4:
            continue
        try:
            # lamedb order: sid:namespace:tsid:onid
            got = (int(parts[0], 16), int(parts[2], 16),
                   int(parts[3], 16), int(parts[1], 16))
        except ValueError:
            continue
        if got == target:
            return i
    return None


def _override_feed_info(pid):
    """Load the scanned replacement feed named in FEED_REF_OVERRIDES."""
    ref = FEED_REF_OVERRIDES.get(str(pid))
    if not ref:
        return None
    try:
        lines = _read_lines(LAMEDB)
    except Exception:
        return None
    index = _service_index_for_ref(lines, ref)
    if index is None:
        return None
    parts = lines[index].strip().split(":")
    if len(parts) < 4:
        return None
    try:
        sid = int(parts[0], 16)
        ns = int(parts[1], 16)
        tsid = int(parts[2], 16)
        onid = int(parts[3], 16)
    except ValueError:
        return None
    return {
        "pid": int(pid),
        "sid": sid,
        "ns": ns,
        "tsid": tsid,
        "onid": onid,
        "name": lines[index + 1].strip(),
        "prov": lines[index + 2].strip(),
        "has_data": bool(re.search(r"c:00[0-9a-fA-F]{4}(?:,|$)",
                                   lines[index + 2])),
        "ref": ref,
    }


def _write_lamedb(lines, suffix):
    """Write the lamedb through a temp file, keeping the original file mode.

    Raises on failure (the temp file is removed).
    """
    tmp = os.path.join(_tmpdir(), ".lamedb.%s.%d" % (suffix, os.getpid()))
    mode = None
    try:
        mode = stat.S_IMODE(os.stat(LAMEDB).st_mode)
    except Exception:
        mode = None
    try:
        with io.open(tmp, "w", encoding="utf-8", newline="") as f:
            # Python 2 needs unicode here: the lamedb holds non-ASCII
            # provider names (the 12583 V scan) and the rules are plain str.
            out = []
            for line in lines:
                if isinstance(line, _TEXT):
                    out.append(line)
                else:
                    out.append(line.decode("utf-8", "replace"))
            f.writelines(out)
        if mode is not None:
            os.chmod(tmp, mode)
        os.rename(tmp, LAMEDB)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


def _split_fields(prov):
    return [p.strip() for p in prov.strip().split(",") if p.strip()]


def _build_provider(prov, rule):
    """Keep p:/PCR/C:, replace the cached components and the flag."""
    fields = _split_fields(prov)
    p = None
    pcr = None
    ca = None
    for f in fields:
        low = f.lower()
        if low.startswith("p:") and p is None:
            p = f
        elif low.startswith("c:03") and pcr is None:
            pcr = f
        elif f.startswith("C:") and ca is None:
            ca = f
    if rule.get("provider"):
        p = rule["provider"]
    if p is None:
        p = "p:ABERTIS"
    if pcr is None:
        pcr = "c:031fff"
    if ca is None:
        # A freshly scanned data feed has no CA descriptor yet.  Abertis is
        # BISS-encrypted; without this descriptor Enigma2/OSCam never request
        # the ECM and the feed stays black.
        ca = "C:2600"
    out = [p, pcr]
    if rule.get("data"):
        out.append("c:" + rule["data"])
    if rule.get("pmt"):
        out.append("c:19" + rule["pmt"])
    if ca:
        out.append(ca)
    out.append("f:%x" % rule["flag"])
    return ",".join(out) + "\n"


def _fix_name(name, flag):
    core = name.strip()
    m = NAME_RE.match(core)
    if m:
        core = "Abertis PID " + m.group(1)
    return core + " F%d\n" % flag


def apply(flag=None):
    """Apply the final per-service rules to the lamedb on disk.

    The historical ``flag`` argument is accepted for compatibility but
    ignored: each service has its own validated rule now.
    Returns (known_count, details_list).
    """
    details = []
    if not os.path.exists(LAMEDB):
        return 0, ["ERROR: lamedb not found"]

    if not os.path.exists(BACKUP):
        try:
            with io.open(LAMEDB, "rb") as src:
                data = src.read()
            with io.open(BACKUP, "wb") as dst:
                dst.write(data)
            details.append("Backup created: %s" % BACKUP)
        except Exception as e:
            details.append("Backup failed: %s" % e)

    try:
        lines = _read_lines(LAMEDB)
    except Exception as e:
        return 0, ["ERROR reading lamedb: %s" % e]

    out = []
    count = 0
    changed = 0
    removed = 0
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if SERVICE_REF_RE.match(line.strip()) and i + 2 < n:
            name_line = lines[i + 1]
            prov_line = lines[i + 2]
            m = NAME_RE.match(name_line.strip())
            if m and m.group(1) in SERVICE_RULES:
                rule = SERVICE_RULES[m.group(1)]
                new_name = _fix_name(name_line, rule["flag"])
                new_prov = _build_provider(prov_line, rule)
                if new_name != name_line or new_prov != prov_line:
                    changed += 1
                    details.append("  %s -> %s" % (name_line.strip(), new_prov.strip()))
                out.append(line)
                out.append(new_name)
                out.append(new_prov)
                count += 1
                i += 3
                continue
            if prov_line.strip().upper().startswith("P:ABERTIS") and not m:
                # leftover streamrelay entry (not an "Abertis PID" feed):
                # DreamOS 2.6 keeps the proxy channel black when the entry
                # exists, because the file push of the HTTP stream fails.
                # "Abertis PID <n>" entries are real feeds (even when they
                # are not one of the three services this plugin manages) and
                # must never be removed.
                removed += 1
                changed += 1
                details.append("  removed streamrelay entry: %s"
                               % name_line.strip())
                i += 3
                continue
            out.append(line)
            out.append(name_line)
            out.append(prov_line)
            i += 3
            continue
        out.append(line)
        i += 1

    if not changed:
        details.append("lamedb already in final state (%d known services)" % count)
        return count, details

    try:
        _write_lamedb(out, "tmp")
        if removed:
            details.append("lamedb written: %d known services updated, "
                           "%d streamrelay entries removed" % (changed - removed,
                                                               removed))
        else:
            details.append("lamedb written: %d known services updated" % changed)
    except Exception as e:
        details.append("ERROR writing lamedb: %s" % e)
    return count, details


def set_feed_mode(pid, mode):
    """Switch only the feed of the given Abertis PID.

    ``play``/``f5``: flag 5 + the cached data PID only.  This is the final
    state astra needs to receive the T2-MI payload through the streamserver.
    ``f1``: flag 1 + the cached data PID.  This is the temporary learning
    phase of the runtime automation; when the outer PMT PID of the feed is
    known it is cached too, otherwise Enigma2 discovers it from the
    transponder PAT.

    Returns (changed, message).  Never touches any other service.
    """
    try:
        pid = str(int(pid))
    except (TypeError, ValueError):
        return False, "ERROR: invalid Abertis PID %s" % pid
    mode = str(mode).lower()
    if mode in ("play", "astra", "5", "f5"):
        rule = {"flag": 5, "data": "%06x" % int(pid), "pmt": None}
    elif mode in ("1", "f1"):
        # F1 is the temporary key-learning phase.  The three validated feeds
        # have a measured outer PMT PID; every other feed derives it from the
        # mux rule (SID + 0x0FA0).  Caching both the data and PMT PID is what
        # makes Enigma2/OSCam see the CA program and cache the BISS key.
        pmt = learning_pmt(pid)
        data = "%06x" % int(pid)
        rule = {"flag": 1, "data": data, "pmt": pmt}
    else:
        return False, "ERROR: unknown mode %s" % mode
    if not os.path.exists(LAMEDB):
        return False, "ERROR: lamedb not found"
    try:
        lines = _read_lines(LAMEDB)
    except Exception as e:
        return False, "ERROR reading lamedb: %s" % e

    override_ref = FEED_REF_OVERRIDES.get(pid)
    target = _service_index_for_ref(lines, override_ref) if override_ref else None
    if target is None:
        for i in range(0, len(lines) - 2):
            if not SERVICE_REF_RE.match(lines[i].strip()):
                continue
            m = NAME_RE.match(lines[i + 1].strip())
            if m and m.group(1) == pid:
                target = i
                break
    if target is None:
        return False, "ERROR: Abertis PID %s not found" % pid

    if override_ref and not NAME_RE.match(lines[target + 1].strip()):
        # Adopt the freshly scanned feed ("12583V SID 0x3f0") into the normal
        # Abertis naming so later lookups and logs are unambiguous.
        rule = dict(rule)
        rule["provider"] = u"p:ABERTIS"
        new_name = u"Abertis PID %s F%d\n" % (pid, rule["flag"])
    else:
        new_name = _fix_name(lines[target + 1], rule["flag"])
    new_prov = _build_provider(lines[target + 2], rule)
    if new_name == lines[target + 1] and new_prov == lines[target + 2]:
        return False, "Abertis PID %s already F%d" % (pid, rule["flag"])

    try:
        if not os.path.exists(AUTO_BACKUP):
            with io.open(LAMEDB, "rb") as src:
                data = src.read()
            with io.open(AUTO_BACKUP, "wb") as dst:
                dst.write(data)
    except Exception as e:
        return False, "ERROR creating auto backup: %s" % e

    lines[target + 1] = new_name
    lines[target + 2] = new_prov
    try:
        _write_lamedb(lines, "%s.tmp" % pid)
    except Exception as e:
        return False, "ERROR writing lamedb: %s" % e
    return True, "Abertis PID %s -> F%d (%s)" % (
        pid, rule["flag"], new_prov.strip())


def set_2026_mode(mode):
    """Backward-compatible wrapper for the 2026 feed."""
    return set_feed_mode("2026", mode)


def fix_disk():
    """Disk-only apply, used by prestart_fix.py before enigma2 starts."""
    return apply()


def ensure_cached_pids():
    """Compatibility alias for older callers."""
    return apply()[0]


def restore():
    if not os.path.exists(BACKUP):
        return False, "No backup found"
    try:
        with io.open(BACKUP, "rb") as src:
            data = src.read()
        with io.open(LAMEDB, "wb") as dst:
            dst.write(data)
        return True, "Restored from %s" % BACKUP
    except Exception as e:
        return False, "Restore failed: %s" % e


def reload_bouquets():
    """Reload the lamedb in memory via webif, with the same UA + session.

    DreamOS webif requires a session id (extended_security) and the very same
    User-Agent for the reload request.  Falls back to eDVBDB if webif fails.
    """
    try:
        import urllib2
        ua = "AbetrisAuto"
        req = urllib2.Request("http://127.0.0.1/web/session",
                              headers={"User-Agent": ua})
        data = urllib2.urlopen(req, timeout=10).read()
        m = re.search(r"<e2sessionid>\s*([^<\s]+)\s*</e2sessionid>", data)
        if not m:
            raise RuntimeError("no session id")
        sid = m.group(1)
        url = "http://127.0.0.1/web/servicelistreload?mode=0&sessionid=" + sid
        # DreamOS 2.6's webif only accepts POST for servicelistreload
        # (a GET answers 405 "Invalid method").  An empty body is enough;
        # the parameters stay in the query string.
        req = urllib2.Request(url, data="", headers={"User-Agent": ua})
        urllib2.urlopen(req, timeout=40).read()
        return True
    except Exception:
        return False


def reload_edvbdb():
    """Reload the service list inside Enigma2 (fast, main thread only)."""
    try:
        from enigma import eDVBDB
        db = eDVBDB.getInstance()
        try:
            db.reloadServicelist()
        except Exception as e:
            try:
                from . import logger
                logger.log("reloadServicelist failed: %s" % e)
            except Exception:
                pass
        try:
            db.reloadBouquets()
        except Exception:
            pass
        return True
    except Exception as e:
        try:
            from . import logger
            logger.log("eDVBDB unavailable: %s" % e)
        except Exception:
            pass
        return False


def reload_db():
    """Reload lamedb/bouquets inside the running Enigma2 process.

    On DreamOS 2.6 eDVBDB.reloadServicelist() re-reads the file but does
    *not* update the flags/pids of the already existing service objects, so
    the webif reload (servicelistreload) is the method that really works -
    it is also the method used by the original AbetrisFlagSwitch plugin.
    """
    ok = reload_edvbdb()
    webif_ok = reload_bouquets()
    return bool(ok or webif_ok)


# --- streamrelay (proxy) channels ------------------------------------------
#
# The astra output of a channel is a clean single program TS, but its PAT is
# not on the PID DreamOS 2.6 expects, so Enigma2 never finds the program
# ("no PAT entry found", "timeout 0012!") and the channel stays black.
#
# The fix is the same trick the AbetrisFlagSwitch tool uses: play the channel
# in F5 mode (dxNoDVB -> "use cached pids") and store the PIDs of the astra
# output in the lamedb.  The plugin writes/refreshes those entries when the
# user selects a streamrelay channel.

SR_PROVIDER = "ABERTIS"

CACHE_VIDEO = 0         # cVPID
CACHE_MPEG_AUDIO = 1    # cMPEGAPID
CACHE_PCR = 3           # cPCRPID
CACHE_AC3_AUDIO = 4     # cAC3PID
CACHE_EAC3_AUDIO = 12   # cAACHEAPID
CACHE_DTS_AUDIO = 14    # cDTSPID
CACHE_AAC_AUDIO = 15    # cAACAPID
CACHE_PMT = 19          # cPMTPID


def _sr_provider_line(vpid, apid, apid_cache, pcrpid, pmtpid):
    fields = [u"p:%s" % SR_PROVIDER]
    if vpid is not None and vpid >= 0:
        fields.append(u"c:%02d%04x" % (CACHE_VIDEO, vpid))
    if apid is not None and apid >= 0:
        fields.append(u"c:%02d%04x" % (apid_cache, apid))
    if pcrpid is not None and pcrpid >= 0:
        fields.append(u"c:%02d%04x" % (CACHE_PCR, pcrpid))
    if pmtpid is not None and pmtpid >= 0:
        fields.append(u"c:%02d%04x" % (CACHE_PMT, pmtpid))
    fields.append(u"f:5")
    return u",".join(fields) + u"\n"


def _sr_sid_line(sid, ns, tsid, onid, service_type=1):
    return u"%04x:%08x:%04x:%04x:%d:%d\n" % (sid, ns, tsid, onid,
                                             service_type, 0)


def _parse_sid_line(line):
    """Return (sid, ns, tsid, onid) of a lamedb service line or None."""
    parts = line.strip().split(":")
    if len(parts) < 4:
        return None
    try:
        return (int(parts[0], 16), int(parts[1], 16), int(parts[2], 16),
                int(parts[3], 16))
    except ValueError:
        return None


def set_all_mode(mode):
    """Legacy helper to apply F1 or F5 to every ABERTIS service.

    This is what the original AbetrisFlagSwitch plugin does: the name gets
    the " F1"/" F5" suffix and the flags field is switched, the cached pids
    are kept.  The Abertis PID 2026 service uses the validated rules (it
    needs the cached data pid / pmt pid).  The 2026 automatic path does not
    call this function because it must leave 8001/2050 and other services
    untouched.

    Returns (changed, message).
    """
    flag = 1 if str(mode).lower() in ("1", "f1") else 5
    if not os.path.exists(LAMEDB):
        return False, "ERROR: lamedb not found"
    try:
        lines = _read_lines(LAMEDB)
    except Exception as e:
        return False, "ERROR reading lamedb: %s" % e

    rule = RULE_2026_F1 if flag == 1 else RULE_2026_F5
    out = []
    count = 0
    changed = 0
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        out.append(line)
        if SERVICE_REF_RE.match(line.strip()) and i + 2 < n:
            name_line = lines[i + 1]
            prov_line = lines[i + 2]
            if prov_line.strip().upper().startswith("P:ABERTIS"):
                m = NAME_RE.match(name_line.strip())
                if m and m.group(1) == "2026":
                    new_name = _fix_name(name_line, flag)
                    new_prov = _build_provider(prov_line, rule)
                else:
                    new_name = name_line.strip() + "\n"
                    new_prov = re.sub(r"f:[0-9a-fA-F]+", "f:%x" % flag, prov_line)
                if new_name != name_line or new_prov != prov_line:
                    changed += 1
                out.append(new_name)
                out.append(new_prov)
                count += 1
                i += 3
                continue
            out.append(name_line)
            out.append(prov_line)
            i += 3
            continue
        i += 1

    if not changed:
        return False, "all ABERTIS services already F%d (%d)" % (flag, count)

    try:
        _write_lamedb(out, "all")
    except Exception as e:
        return False, "ERROR writing lamedb: %s" % e
    return True, "%d ABERTIS services set to F%d" % (count, flag)


def _feed_from_lines(lines, index):
    """Build the feed dict for the lamedb service at <index>."""
    if index < 0 or index + 2 >= len(lines):
        return None
    if not SERVICE_REF_RE.match(lines[index].strip()):
        return None
    m = NAME_RE.match(lines[index + 1].strip())
    if not m:
        return None
    parts = lines[index].strip().split(":")
    if len(parts) < 4:
        return None
    try:
        sid = int(parts[0], 16)
        ns = int(parts[1], 16)
        tsid = int(parts[2], 16)
        onid = int(parts[3], 16)
    except ValueError:
        return None
    prov = lines[index + 2].strip()
    return {
        "pid": int(m.group(1)),
        "sid": sid,
        "ns": ns,
        "tsid": tsid,
        "onid": onid,
        "name": lines[index + 1].strip(),
        "prov": prov,
        "has_data": bool(re.search(r"c:00[0-9a-fA-F]{4}(?:,|$)", prov)),
        "ref": "1:0:1:%x:%x:%x:%x:0:0:0:" % (sid, tsid, onid, ns),
    }


def get_feed_info(pid):
    """Return the catalog entry of an "Abertis PID <pid>" feed or None."""
    try:
        target = str(int(pid))
    except (TypeError, ValueError):
        return None
    override = _override_feed_info(target)
    if override is not None:
        return override
    try:
        lines = _read_lines(LAMEDB)
    except Exception:
        return None
    for i in range(0, len(lines) - 2):
        if not SERVICE_REF_RE.match(lines[i].strip()):
            continue
        m = NAME_RE.match(lines[i + 1].strip())
        if not m or m.group(1) != target:
            continue
        return _feed_from_lines(lines, i)
    return None


def get_all_feeds():
    """Return every "Abertis PID <n>" feed, sorted by PID."""
    try:
        lines = _read_lines(LAMEDB)
    except Exception:
        return []
    feeds = {}
    for i in range(0, len(lines) - 2):
        if not SERVICE_REF_RE.match(lines[i].strip()):
            continue
        info = _feed_from_lines(lines, i)
        if info is not None and info["pid"] not in feeds:
            feeds[info["pid"]] = info
    for pid in FEED_REF_OVERRIDES:
        info = get_feed_info(pid)
        if info is not None:
            feeds[int(pid)] = info
    return [feeds[pid] for pid in sorted(feeds)]


def build_a_rule(feed):
    """Build the OSCam-EMU A-rule of one feed (SID : data PID)."""
    pid = int(feed["pid"])
    return "A: ::%04X:%04X 2600:000000:1FFF # Abertis PID %d F5" % (
        int(feed["sid"]), pid, pid)


def build_a_rules(feeds=None):
    """Build the A-rules of every Abertis feed (or the supplied list)."""
    if feeds is None:
        feeds = get_all_feeds()
    return [build_a_rule(feed) for feed in feeds]


def get_feed_ref(pid):
    """Return the service reference of the "Abertis PID <pid>" feed."""
    info = get_feed_info(pid)
    return info["ref"] if info else None


def get_sibling_feed_ref(pid):
    """Return another Abertis feed on the SAME transponder as <pid>.

    Zapping that feed and back rebuilds the demux filters (the streamserver
    only hands the demux filters to astra).  The transponder is the same, so
    the tuner never moves the dish.

    Only feeds with a cached data pid (``c:00xxxx``) are used: a feed
    without one would open an empty demux and the astra input would stay
    broken.
    """
    info = get_feed_info(pid)
    if info is None:
        return None
    target_sid = int(info["sid"])
    target_ns = int(info["ns"])
    target_tsid = int(info["tsid"])
    try:
        lines = _read_lines(LAMEDB)
    except Exception:
        return None
    for i in range(0, len(lines) - 2):
        if not SERVICE_REF_RE.match(lines[i].strip()):
            continue
        if not NAME_RE.match(lines[i + 1].strip()):
            continue
        parts = lines[i].strip().split(":")
        if len(parts) < 4:
            continue
        try:
            sid = int(parts[0], 16)
            ns = int(parts[1], 16)
            tsid = int(parts[2], 16)
            onid = int(parts[3], 16)
        except ValueError:
            continue
        if (ns == target_ns and tsid == target_tsid
                and sid != target_sid
                and "c:00" in lines[i + 2].lower()):
            return "1:0:1:%x:%x:%x:%x:0:0:0:" % (sid, tsid, onid, ns)
    return None


def remove_streamrelay_services():
    """Remove lamedb entries of streamrelay (proxy) channels.

    DreamOS 2.6 must not find those services in the lamedb: with a lamedb
    entry the file push of the proxy stream fails (DMX_SET_INPUT) and the
    channel stays black.  The Abertis feeds keep their entry, only the
    streamrelay channels (the ones with a channel name instead of
    "Abertis PID ...") are removed.
    """
    if not os.path.exists(LAMEDB):
        return False, "ERROR: lamedb not found"
    try:
        lines = _read_lines(LAMEDB)
    except Exception as e:
        return False, "ERROR reading lamedb: %s" % e

    out = []
    removed = 0
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if SERVICE_REF_RE.match(line.strip()) and i + 2 < n:
            name_line = lines[i + 1].strip()
            prov_line = lines[i + 2]
            if prov_line.strip().upper().startswith("P:ABERTIS") \
                    and not NAME_RE.match(name_line):
                removed += 1
                i += 3
                continue
            out.append(line)
            out.append(lines[i + 1])
            out.append(lines[i + 2])
            i += 3
            continue
        out.append(line)
        i += 1

    if not removed:
        return False, "no streamrelay entries"

    try:
        _write_lamedb(out, "sr")
    except Exception as e:
        return False, "ERROR writing lamedb: %s" % e
    return True, "%d streamrelay entries removed" % removed


def set_streamrelay_service(sid, ns, tsid, onid, name, vpid, apid,
                            apid_cache, pcrpid, pmtpid, service_type=1):
    """Insert or update the lamedb entry of a streamrelay (proxy) channel.

    The entry is written in F5 mode with the cached PIDs of the astra output
    so that DreamOS 2.6 plays the channel without looking for a PAT.
    Returns (changed, message).
    """
    if not os.path.exists(LAMEDB):
        return False, "ERROR: lamedb not found"
    try:
        lines = _read_lines(LAMEDB)
    except Exception as e:
        return False, "ERROR reading lamedb: %s" % e

    sid_line = _sr_sid_line(sid, ns, tsid, onid, service_type)
    prov_line = _sr_provider_line(vpid, apid, apid_cache, pcrpid, pmtpid)
    name_line = u"%s\n" % (name or u"Streamrelay")

    # look for an existing entry with the same sid/tsid/onid/namespace
    want = (sid, ns, tsid, onid)
    found = []
    for i in range(0, len(lines) - 2):
        got = _parse_sid_line(lines[i])
        if got == want:
            found.append(i)
    if found:
        keep = found[0]
        if lines[keep + 1] == name_line and lines[keep + 2] == prov_line:
            return False, "streamrelay %04x already up to date" % sid
        lines[keep + 1] = name_line
        lines[keep + 2] = prov_line
        # drop duplicated entries of the same service
        for idx in reversed(found[1:]):
            del lines[idx:idx + 3]
    else:
        # new entry: insert in front of the "end" of the services section
        end_idx = None
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == "end":
                end_idx = i
                break
        if end_idx is None:
            end_idx = len(lines)
        lines[end_idx:end_idx] = [sid_line, name_line, prov_line]

    try:
        _write_lamedb(lines, "sr")
    except Exception as e:
        return False, "ERROR writing lamedb: %s" % e
    return True, "streamrelay %04x: %s" % (sid, prov_line.strip())



def fix_all():
    """Apply the rules and refresh the in-memory database when needed."""
    count, details = apply()
    if os.path.exists(MARKER):
        details.append("prestart marker present - in-memory DB already loaded from fixed lamedb")
    else:
        if reload_bouquets():
            details.append("in-memory lamedb reloaded")
        else:
            details.append("WARNING: in-memory reload failed")
    return count, details
