# -*- coding: utf-8 -*-
"""Boot-time automation for Abertis Auto.

At 12s after enigma2 start:
  1. run the idempotent setup (safe astra start, OSCam A-rules, lamedb rules)
  2. start the multi-channel automation hook (event + polling fallback)

The three managed channels (URL tags pid2026, pid2050, pid8001) use the
same OSCam-EMU A-rule path:

  F1 learning (outer PAT/PMT) -> F5 (data only) -> reload -> zap the feed
  -> sync Astra PAT/PMT -> play the selected Ciefp URL as-is
  -> verify with the native decoder info

The proxy channel must never be added to the lamedb: DreamOS 2.6 keeps the
HTTP push black when it finds a cached entry for it.  Other Abertis feeds
stay untouched.
"""
import os
import re
import threading
import time
from . import logger, setup, lamedb_fix

try:
    from enigma import eTimer, eServiceReference, iServiceInformation
except Exception:
    eTimer = None
    eServiceReference = None
    iServiceInformation = None

try:
    from NavigationInstance import NavigationInstance
except Exception:
    NavigationInstance = None

_timer = None
_timer_conn = None
_hook = None
_session = None

# The three Abertis feeds and their URL tags.  The data pid of each service
# is its decimal PID (2026=0x7EA, 2050=0x802, 8001=0x1F41).
FEED_REFS = {
    "2026": "1:0:1:BD2:EA74:1:CE42BD6:0:0:0:",
    "2050": "1:0:1:BEA:EA74:1:CE42BD6:0:0:0:",
    "8001": "1:0:1:3E9:EA62:0:CE4B157:0:0:0:",
}
FEED_REF = FEED_REFS["2026"]
FEED_TAG = "BD2:EA74"
URL_TAGS = ("pid2026", "pid2050", "pid8001")
URL_TAG = "pid2026"  # backwards-compatible alias
URL_RE = re.compile(r"/abertis/pid(\d+)", re.IGNORECASE)
# Permanently skipped feeds.  8008 is intentionally not listed: La 1 UHD,
# Clan HD, DKISS and the other channels on that feed must get the normal
# F1/F5 attempt even while the feed is currently off-air.  A failed attempt
# is remembered and is not retried by itself (see _on_service_started and
# _finish); selecting another service cancels it and starts the new one.
SKIP_PIDS = frozenset()
# Service id used by OSCam's log line for each feed (legacy fallback).
OSCAM_SIDS = {"2026": "0BD2", "2050": "0BEA", "8001": "03E9"}
FALLBACK_URL_REF = (
    "1:0:1:20C:2BD6:7EA:0:0:0:0:"
    "http%3a//localhost%3a9999/abertis/pid2026:La 1 HD La Rioja [2026]"
)

FEED_SETTLE = 8.0       # seconds after zapping the F5 feed before reading Astra
SIBLING_SETTLE = 3.5    # seconds between the sibling feed zap and the feed zap
CW_TIMEOUT = 12.0       # seconds to wait for the BISS key (the A-rule is fast)
CW_SETTLE = 2.0         # seconds after the key was seen before the F5 phase
OSCAM_LOGS = ("/tmp/oscam.log", "/var/log/oscam.log", "/var/log/oscam/oscam.log")
URL_SETTLE = 6.0        # seconds before verifying URL playback
VERIFY_TRIES = 4        # extra checks before a playback is called failed
VERIFY_INTERVAL = 1.5   # seconds between two playback checks
RETRY_DELAY = 2.0       # seconds before one automatic retry
FAIL_COOLDOWN = 20.0    # seconds before a failed URL can auto-trigger again
MAX_RETRIES = 1
ASTRA_SETTLE = 8.0      # seconds for astra to de-encapsulate the channel
SYNC_ATTEMPTS = 10      # tries to read the astra output (PMT pid of the channel)
SYNC_TIMEOUT = 12.0     # seconds for one read of the astra output
RELOAD_TIMEOUT = 45.0   # seconds for the webif service list reload

_WEBIF_SID = ""
_WEBIF_SID_TS = 0.0

DISABLE_MARKER = "/tmp/abetris_auto_off"


def _ref(service):
    if service is None:
        return ""
    try:
        s = service.toString()
        if s:
            return s
    except Exception:
        pass
    try:
        s = str(service)
        # getCurrentService() returns an iPlayableService proxy, not a ref.
        return s if s.startswith("1:") else ""
    except Exception:
        return ""


def _is_url(ref):
    """True for any Ciefp Abertis URL (``/abertis/pid<number>``)."""
    return bool(URL_RE.search(ref or ""))


def _skipped_pid(ref):
    """Return the PID when this URL is on the no-signal skip list."""
    match = URL_RE.search(ref or "")
    if match and match.group(1) in SKIP_PIDS:
        return match.group(1)
    return None


def _is_feed(ref):
    text = (ref or "").upper()
    return any(feed.split(":")[3].upper() in text
               for feed in FEED_REFS.values())


def _oscam_path():
    for path in OSCAM_LOGS:
        try:
            if os.path.exists(path):
                return path
        except Exception:
            pass
    return OSCAM_LOGS[0]


def _oscam_size():
    try:
        return os.path.getsize(_oscam_path())
    except Exception:
        return 0


def _read_bytes(path, pos, limit=None):
    try:
        with open(path, "rb") as f:
            if pos < 0:
                pos = 0
            f.seek(pos)
            return f.read() if limit is None else f.read(limit)
    except Exception:
        return b""


def _has_cw(data, sid="0BD2"):
    try:
        text = data.decode("latin-1", "replace").upper()
    except Exception:
        try:
            text = str(data).upper()
        except Exception:
            return False
    return sid.upper() in text and "FOUND" in text


def _oscam_cw_seen(pos, sid="0BD2"):
    """True if oscam logged the BISS key of our service after <pos>."""
    return _has_cw(_read_bytes(_oscam_path(), pos), sid)


def _webif_session(force=False):
    global _WEBIF_SID, _WEBIF_SID_TS
    now = time.time()
    if not force and _WEBIF_SID and (now - _WEBIF_SID_TS) < 30:
        return _WEBIF_SID
    try:
        import urllib2
        ua = "AbetrisAuto"
        req = urllib2.Request("http://127.0.0.1/web/session",
                              headers={"User-Agent": ua})
        data = urllib2.urlopen(req, timeout=4).read()
        m = re.search(r"<e2sessionid>\s*([^<\s]+)\s*</e2sessionid>", data)
        sid = m.group(1) if m else ""
        if sid:
            _WEBIF_SID = sid
            _WEBIF_SID_TS = now
        return sid
    except Exception:
        _WEBIF_SID = ""
        _WEBIF_SID_TS = 0
        return ""


def _webif_zap(ref):
    """Zap through local webif; works even when NavigationInstance is absent."""
    global _WEBIF_SID, _WEBIF_SID_TS
    import urllib
    import urllib2
    ua = "AbetrisAuto"
    for force in (False, True):
        sid = _webif_session(force=force)
        query = {"sRef": ref}
        if sid:
            query["sessionid"] = sid
        url = "http://127.0.0.1/web/zap?" + urllib.urlencode(query)
        # DreamOS 2.6's webif refuses state changes over GET (405 "Invalid
        # method"), so try POST first.  An empty body is enough: the
        # parameters stay in the query string.  GET stays as a fallback for
        # images whose webif only implements GET.
        last = None
        for method in ("POST", "GET"):
            try:
                data = "" if method == "POST" else None
                req = urllib2.Request(url, data, {"User-Agent": ua})
                urllib2.urlopen(req, timeout=6).read()
                return True
            except Exception as e:
                last = e
        _WEBIF_SID = ""
        _WEBIF_SID_TS = 0
        if force:
            logger.log("Abertis webif zap failed: %s" % last)
    return False


def _info_playing(info):
    """True when the decoder reports a locked picture (or real A/V pids)."""
    if not info:
        return False

    def num(key):
        value = info.get(key)
        if value is None:
            return -1
        if not isinstance(value, (int, float)):
            value = str(value).strip()
            if not value or value.upper() == "N/A":
                return -1
        try:
            return int(value)
        except (TypeError, ValueError):
            return -1

    if num("height") > 0:
        return True
    return num("vpid") > 0 and num("apid") > 0


def _unquote(text):
    try:
        if "%" not in text:
            return text
        out = []
        i = 0
        while i < len(text):
            if text[i] == "%" and i + 2 < len(text):
                try:
                    out.append(chr(int(text[i + 1:i + 3], 16)))
                    i += 3
                    continue
                except ValueError:
                    pass
            out.append(text[i])
            i += 1
        return "".join(out)
    except Exception:
        return text


def _parse_ref(ref):
    """Split a service reference into (sid, ns, tsid, onid, path, name)."""
    try:
        parts = (ref or "").split(":", 11)
        if len(parts) < 12:
            return None
        return (int(parts[3], 16), int(parts[6], 16), int(parts[4], 16),
                int(parts[5], 16), parts[10], parts[11])
    except Exception:
        return None


def _b(value):
    """Byte value of a character (py2/py3 safe)."""
    if isinstance(value, int):
        return value
    try:
        return ord(value)
    except Exception:
        return -1


def _fetch_stream(url, limit=1200000, timeout=12):
    """Read the astra output, keeping whatever arrived within the timeout.

    The output is a live stream: a single read() for the full limit can block
    until the socket timeout and would throw away the data that already
    arrived.  The PAT of the channel is repeated about every 100 ms, so a
    partial buffer is usually enough to find it.
    """
    import urllib2
    req = urllib2.Request(url, headers={"User-Agent": "AbetrisAuto"})
    resp = urllib2.urlopen(req, timeout=timeout)
    chunks = []
    total = 0
    deadline = time.time() + timeout
    while total < limit:
        try:
            chunk = resp.read(65536)
        except Exception:
            break
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if time.time() >= deadline:
            break
    try:
        resp.close()
    except Exception:
        pass
    return b"".join(chunks)


def _ts_offset(data):
    """Return the packet alignment of a TS byte stream.

    The astra output is read over HTTP, so the body does not necessarily
    start on a 188 byte packet boundary.  The offset with the most sync
    bytes (0x47) is the real alignment.
    """
    n = len(data)
    best = (0, -1)
    for off in range(0, min(188, max(0, n - 187))):
        ok = 0
        checked = 0
        i = off
        while i + 187 < n and checked < 8:
            if data[i:i + 1] == b"\x47":
                ok += 1
            checked += 1
            i += 188
        if ok > best[1]:
            best = (off, ok)
        if checked and ok == checked:
            break
    return best[0]


def _ts_sections(data, pid):
    """Return the section payloads carried on the given PID."""
    out = []
    n = len(data)
    off = _ts_offset(data)
    for i in range(off, n - 187, 188):
        p = data[i:i + 188]
        if len(p) < 188 or _b(p[0]) != 0x47:
            continue
        spid = ((_b(p[1]) & 0x1F) << 8) | _b(p[2])
        if spid != pid:
            continue
        if not (_b(p[1]) & 0x40):
            # no payload unit start indicator -> continuation, skip it
            continue
        afc = (_b(p[3]) >> 4) & 3
        if afc in (0, 2):
            continue
        idx = 4
        if afc == 3:
            idx += 1 + _b(p[4])
        payload = p[idx:]
        if not payload:
            continue
        ptr = _b(payload[0])
        sec = payload[1 + ptr:]
        if sec:
            out.append(sec)
    return out


def _parse_pat(data, sid):
    """Return the PMT PID of the given service id (None if not found)."""
    for sec in _ts_sections(data, 0):
        if not sec or _b(sec[0]) != 0x00:
            continue
        slen = ((_b(sec[1]) & 0x0F) << 8) | _b(sec[2])
        if slen > 1020:
            continue
        body = sec[8:8 + slen - 4]
        i = 0
        while i + 4 <= len(body):
            prog = (_b(body[i]) << 8) | _b(body[i + 1])
            pmt = ((_b(body[i + 2]) & 0x1F) << 8) | _b(body[i + 3])
            if prog == sid:
                return pmt
            i += 4
    return None


_VIDEO_TYPES = (0x02, 0x10, 0x1B, 0x1E, 0x24, 0x25, 0x26, 0x27, 0x51)
_AUDIO_TYPES = {
    0x03: lamedb_fix.CACHE_MPEG_AUDIO,
    0x04: lamedb_fix.CACHE_AC3_AUDIO,
    0x0F: lamedb_fix.CACHE_AAC_AUDIO,
    0x11: lamedb_fix.CACHE_AC3_AUDIO,
    0x81: lamedb_fix.CACHE_AC3_AUDIO,
    0x82: lamedb_fix.CACHE_DTS_AUDIO,
    0x87: lamedb_fix.CACHE_EAC3_AUDIO,
}


def _parse_pmt(data, pmtpid):
    """Return (vpid, apid, apid_cache, pcrpid) of the PMT."""
    best = (-1, -1, lamedb_fix.CACHE_AC3_AUDIO, -1)
    for sec in _ts_sections(data, pmtpid):
        if not sec or _b(sec[0]) != 0x02:
            continue
        slen = ((_b(sec[1]) & 0x0F) << 8) | _b(sec[2])
        if slen > 1020 or len(sec) < 13:
            continue
        pcr = ((_b(sec[8]) & 0x1F) << 8) | _b(sec[9])
        pil = ((_b(sec[10]) & 0x0F) << 8) | _b(sec[11])
        rest = sec[12 + pil:3 + slen]
        vpid = -1
        apid = -1
        acache = lamedb_fix.CACHE_AC3_AUDIO
        i = 0
        while i + 4 < len(rest):
            st = _b(rest[i])
            epid = ((_b(rest[i + 1]) & 0x1F) << 8) | _b(rest[i + 2])
            esil = ((_b(rest[i + 3]) & 0x0F) << 8) | _b(rest[i + 4])
            info = rest[i + 5:i + 5 + esil]
            if st in _VIDEO_TYPES and vpid < 0:
                vpid = epid
            elif st in _AUDIO_TYPES and apid < 0:
                apid = epid
                acache = _AUDIO_TYPES[st]
            elif st == 0x06 and apid < 0:
                # private PES with an AC3/EAC3 registration
                apid = epid
                acache = lamedb_fix.CACHE_AC3_AUDIO
                if b"EAC3" in info:
                    acache = lamedb_fix.CACHE_EAC3_AUDIO
            i += 5 + esil
        if vpid >= 0:
            return vpid, apid, acache, pcr
        if best[0] < 0:
            best = (vpid, apid, acache, pcr)
    return best


def _streamrelay_pids(data, ref):
    """Return the PIDs of a streamrelay channel (from the astra output).

    Only the astra output is parsed.  The proxy channel must *not* be added
    to the lamedb: on DreamOS 2.6 an entry with cached pids makes the file
    push of the HTTP stream fail (DMX_SET_INPUT) and the channel stays
    black.  The URL reference is played as-is and the frontend discovers
    the PAT/PMT of the astra output itself.

    Returns (need_reload, pmtpid, message); need_reload is always False, it
    is kept for the historical call sites.
    """
    info = _parse_ref(ref)
    if not info:
        return None, None, "cannot parse reference"
    sid, ns, tsid, onid, path, name = info
    pmtpid = _parse_pat(data, sid)
    if pmtpid is None:
        return None, None, "service %04x not in PAT" % sid
    vpid, apid, acache, pcrpid = _parse_pmt(data, pmtpid)
    if vpid < 0:
        return None, None, "no video pid in PMT %04x" % pmtpid
    return False, pmtpid, "PAT/PMT ok: pmt=%d vpid=%d apid=%d" % (
        pmtpid, vpid, apid)


def _ref_with_pmtpid(ref, pmtpid):
    """Put the real PMT PID into the service reference (field 6)."""
    try:
        parts = (ref or "").split(":", 11)
        if len(parts) < 12 or pmtpid is None:
            return ref
        parts[5] = "%x" % pmtpid
        return ":".join(parts)
    except Exception:
        return ref


def _ref_key(ref):
    """Key of a service reference: the url part plus the channel name.

    The plugin zaps the channel with the real PMT PID in the reference, so
    the reference changes while the channel stays the same - the polling
    must not start a second sequence because of that.

    The name has to be part of the key: all channels of one PID share the
    same url (``/abertis/pid8008``), so La 1 UHD, Clan HD and DKISS would
    otherwise look like the same channel and only the first one would be
    automated.

    References without a URL are compared case-insensitively: the lamedb
    feeds are written in lower case while Enigma2 reports them in upper
    case, and both describe the same service.
    """
    try:
        parts = (ref or "").split(":", 11)
        if len(parts) >= 11 and parts[10].startswith("http"):
            if len(parts) > 11 and parts[11]:
                return parts[10] + "|" + parts[11]
            return parts[10]
    except Exception:
        pass
    return (ref or "").upper()



def _webif_current():
    """Query webif for the current service / decoder PIDs (best effort)."""
    global _WEBIF_SID, _WEBIF_SID_TS
    try:
        import urllib2
        ua = "AbetrisAuto"
        sid = _webif_session()
        url = "http://127.0.0.1/web/getcurrent"
        if sid:
            url += "?sessionid=" + sid
        req = urllib2.Request(url, headers={"User-Agent": ua})
        data = urllib2.urlopen(req, timeout=4).read()

        def tag(name):
            mm = re.search(r"<%s>\s*([^<]*?)\s*</%s>" % (name, name), data)
            return mm.group(1) if mm else None

        return {
            "ref": tag("e2servicereference"),
            "name": tag("e2servicename"),
            "vpid": tag("e2vpid"),
            "apid": tag("e2apid"),
            "pmtpid": tag("e2pmtpid"),
        }
    except Exception:
        _WEBIF_SID = ""
        _WEBIF_SID_TS = 0
        return None


class _Auto2026(object):
    def __init__(self, session=None):
        self.session = session
        self.nav = NavigationInstance.instance if NavigationInstance is not None else None
        if self.nav is None and session is not None:
            self.nav = getattr(session, "nav", None)
        self.busy = False
        self.state = "idle"
        self.pending_ref = None
        self.pending_url = None
        self.pending_pmtpid = None
        self.attempt = 0
        self.deadline = 0
        self.retry_until = 0
        self.last_seen_ref = ""
        # Refs the plugin itself selected during the current sequence.  Any
        # other ref seen while busy is a user/timer change and cancels it.
        self.internal_refs = set()
        self.sync_attempts = 0
        self.sync_cycles = 0
        self.verify_tries = 0
        self.sync_thread = None
        self.sync_data = []
        self.sync_error = None
        self.reload_thread = None
        self.reload_next = None
        self.zap_thread = None
        self.zap_ok = False
        self.zap_nav_pending = False
        self.zap_callback = None
        self.zap_label = ""
        self.zap_ref = ""
        self.disabled = False
        self.feed_mode = "f1"
        self.direct_f5 = False
        self.oscam_pos = 0

        if os.path.exists(DISABLE_MARKER):
            logger.log("Abertis auto hook disabled (%s)" % DISABLE_MARKER)
            self.disabled = True
            return

        self.step_timer = eTimer()
        self._step_conn = self.step_timer.timeout.connect(self._tick)
        self.poll_timer = eTimer()
        self._poll_conn = self.poll_timer.timeout.connect(self._poll)
        self.debug_timer = eTimer()
        self._debug_conn = self.debug_timer.timeout.connect(self._debug)

        if self.nav is not None:
            try:
                self.nav.serviceStarted.append(self._on_service_started)
            except Exception:
                pass

        self.poll_timer.start(1500)
        self.debug_timer.start(2500, True)
        logger.log("Abertis auto hook ready (nav=%s session=%s feed=%s)" % (
            self.nav is not None, self.session is not None, FEED_REF))

    def _current_ref(self):
        # nav first: getCurrentService() returns an iPlayableService proxy,
        # the service *reference* comes from getCurrentServiceReference().
        if self.nav is not None:
            for meth in ("getCurrentServiceReference",
                         "getCurrentlyPlayingServiceReference"):
                try:
                    ref = _ref(getattr(self.nav, meth)())
                    if ref:
                        return ref
                except Exception:
                    pass
        info = _webif_current()
        if info:
            return info.get("ref") or ""
        return ""

    def _debug(self):
        current = self._current_ref()
        logger.log("Abertis debug: nav=%s session=%s current=%s busy=%s state=%s" % (
            self.nav is not None, self.session is not None,
            current, self.busy, self.state))

    def _is_external_ref(self, ref):
        """True when ref is not one of the services the plugin zapped itself."""
        if not ref or not self.pending_ref:
            return False
        key = _ref_key(ref)
        if not key:
            return False
        if key == _ref_key(self.pending_ref):
            return False
        if key in self.internal_refs:
            return False
        # The feed of the pending PID belongs to the sequence too, even when
        # it was not zapped by this run (the user can select it directly).
        try:
            pid = self._feed_pid()
            if pid:
                feed_ref = lamedb_fix.get_feed_ref(pid)
                if feed_ref and _ref_key(feed_ref) == key:
                    return False
        except Exception:
            pass
        return True

    def _on_service_started(self, *args):
        """Fast path.  Polling remains the reliable fallback."""
        service = args[0] if args else None
        ref = _ref(service)
        if not ref:
            ref = self._current_ref()
        cancelled = False
        if self.busy:
            # A user selecting another service must not wait for a dead 8008
            # feed to exhaust its sync retries.  The plugin's own feed/URL
            # zaps are in internal_refs and are ignored here.
            if self._is_external_ref(ref):
                logger.log("Abertis service changed while busy - cancelling "
                           "the current sequence")
                self._cancel()
                cancelled = True
            else:
                return
        key = _ref_key(ref)
        if key and key == self.last_seen_ref and not cancelled:
            # The same URL is already selected/failed.  Do not restart it on
            # every serviceStarted event; a real change of service updates
            # last_seen_ref and is handled normally.
            return
        if key:
            self.last_seen_ref = key
        if _is_url(ref) and time.time() >= self.retry_until:
            skip = _skipped_pid(ref)
            if skip:
                logger.log("Abertis URL pid %s skipped (no signal)" % skip)
                return
            logger.log("Abertis URL selected (serviceStarted)")
            self.start(ref)

    def _poll(self):
        ref = self._current_ref()
        if not ref:
            return
        cancelled = False
        if self.busy:
            if self._is_external_ref(ref):
                logger.log("Abertis service changed while busy (poll) - "
                           "cancelling the current sequence")
                self._cancel()
                cancelled = True
            else:
                return
        key = _ref_key(ref)
        if not key or (key == self.last_seen_ref and not cancelled):
            return
        self.last_seen_ref = key
        logger.log("Abertis poll new current=%s" % ref)
        if _is_url(ref) and time.time() >= self.retry_until:
            skip = _skipped_pid(ref)
            if skip:
                logger.log("Abertis URL pid %s skipped (no signal)" % skip)
                return
            logger.log("Abertis URL selected (poll)")
            self.start(ref)

    def start(self, url_ref=None):
        if self.disabled or self.busy or eServiceReference is None:
            return False
        current = self._current_ref()
        if not url_ref:
            url_ref = current if _is_url(current) else FALLBACK_URL_REF
        if not _is_url(url_ref):
            url_ref = FALLBACK_URL_REF
        skip = _skipped_pid(url_ref)
        if skip:
            self.last_seen_ref = _ref_key(url_ref)
            logger.log("Abertis URL pid %s skipped (no signal)" % skip)
            return False
        try:
            self.pending_url = eServiceReference(url_ref)
        except Exception as e:
            logger.log("Abertis URL ref invalid: %s" % e)
            return False
        self.pending_ref = url_ref
        self.pending_pmtpid = None
        self.internal_refs = set([_ref_key(url_ref)])
        # Leftovers of older versions: a streamrelay entry in the lamedb
        # keeps the proxy channel black on DreamOS 2.6.  The removal is
        # picked up by the reload of the F5 phase, no extra reload needed.
        try:
            removed, msg = lamedb_fix.remove_streamrelay_services()
            if removed:
                logger.log("Abertis streamrelay cleanup: %s" % msg)
        except Exception as e:
            logger.log("Abertis streamrelay cleanup failed: %s" % e)
        pid = self._feed_pid()
        if not pid:
            logger.log("Abertis URL has no pid tag: %s" % url_ref)
            return False
        if pid not in FEED_REFS and lamedb_fix.get_feed_info(pid) is None:
            logger.log("Abertis PID %s: no feed in lamedb - cannot automate"
                       % pid)
            return False
        self._prepare_runtime(pid)
        # Every feed needs the same short F1 learning phase: with only the
        # data PID cached (F5) Enigma2/OSCam never see the outer service and
        # therefore never request the BISS key.  F1 makes OSCam cache it;
        # the following F5 phase hands the clear T2-MI payload to astra.
        self.direct_f5 = False
        self.busy = True
        self.attempt = 0
        self.retry_until = 0
        self.sync_attempts = 0
        self.sync_cycles = 0
        self.verify_tries = 0
        self.feed_mode = "f1"
        self.oscam_pos = _oscam_size()
        logger.log("Abertis A-rule automation starts for pid %s (learning "
                   "phase F1, the OSCam-EMU A-rule provides the BISS key)"
                   % pid)
        self._go_f5()
        return True

    def _prepare_runtime(self, pid):
        """Make sure oscam and astra can serve this feed before F1/F5.

        Two things can be out of date after a feed moved to a new
        transponder: the BISS key of the new feed (oscam-emu reads the
        uppercase SoftCam.Key) and the astra input reference of the feed
        (astra pulls the T2-MI stream of that exact service reference).
        Both are repaired here, with a backup and a controlled restart.
        """
        try:
            key_ok, key_changed = setup.ensure_softcam_key_upper()
        except Exception as e:
            key_changed = False
            logger.log("Abertis key check failed: %s" % e)
        if key_changed:
            logger.log("Abertis: oscam-emu was missing the Abertis keys - "
                       "restarting OSCam")
            try:
                setup.restart_oscam()
            except Exception as e:
                logger.log("Abertis OSCam restart failed: %s" % e)
        try:
            ref_ok, ref_changed, ref_message = setup.ensure_astra_feed_refs()
        except Exception as e:
            ref_changed = False
            ref_message = "ERROR: %s" % e
        if ref_changed:
            logger.log("Abertis: %s - restarting astra" % ref_message)
            try:
                ok, message = setup.controlled_astra_restart()
                logger.log(message)
            except Exception as e:
                logger.log("Abertis astra restart failed: %s" % e)

    def _reload_async(self, tag, callback):
        """Reload the service list without freezing the user interface.

        The webif servicelistreload is the method that really updates the
        flags on DreamOS 2.6 (the same one the AbetrisFlagSwitch plugin
        uses).  It needs a few seconds to re-read 13000 services and all
        the bouquets, so it runs in a background thread.
        """
        self.reload_thread = threading.Thread(target=self._reload_worker)
        self.reload_thread.daemon = True
        self.reload_thread.start()
        self.reload_next = callback
        self.state = "reload"
        self.deadline = time.time() + RELOAD_TIMEOUT
        self.step_timer.start(300, True)

    def _reload_worker(self):
        try:
            ok = lamedb_fix.reload_bouquets()
            logger.log("Abertis webif reload done: %s" % ok)
        except Exception as e:
            logger.log("Abertis webif reload failed: %s" % e)

    def _apply_feed_mode(self, pid, mode):
        """Set the feed mode, keeping the 2026 helper for compatibility."""
        if pid == "2026":
            return lamedb_fix.set_2026_mode(mode)
        return lamedb_fix.set_feed_mode(pid, mode)

    def _go_f5(self):
        """Switch the selected feed to the given mode and reload.

        "f1" (learning phase): the feed is played with the real PAT/PMT, so
        the frontend asks the CA to descramble and oscam learns the program
        and the BISS key (the A-rule provides the key immediately).
        "f5" (playback phase): the feed is played with the cached data pid
        only, so the streamserver hands the payload to astra, which unwraps
        the T2-MI stream into the clear channel TS.
        """
        self.state = "f5"
        pid = self._feed_pid()
        logger.log("Abertis A-rule path: PID %s %s, reload" % (pid, self.feed_mode))
        try:
            changed, msg = self._apply_feed_mode(pid, self.feed_mode)
        except Exception as e:
            logger.log("Abertis PID %s feed setup error: %s" % (pid, e))
            self._finish(False)
            return
        logger.log("Abertis PID %s lamedb: %s" % (pid, msg))
        if msg.startswith("ERROR"):
            # without the feed record the whole A-rule path cannot work
            logger.log("Abertis PID %s feed setup failed: %s" % (pid, msg))
            self._finish(False)
            return
        self._reload_async("F5", self._after_reload_f5)

    def _after_reload_f5(self):
        if self.feed_mode == "f1":
            # learning phase: zap the feed so oscam sees the program and
            # the BISS key (the A-rule answers immediately)
            self.state = "f1wait"
            self.deadline = time.time() + 0.7
        else:
            self.state = "f5wait"
            self.deadline = time.time() + 0.5
        self.step_timer.start(250, True)

    def _feed_pid(self):
        """The Abertis PID of the selected streamrelay channel."""
        info = _parse_ref(getattr(self, "pending_ref", None))
        if info:
            m = URL_RE.search(info[4] or "")
            if m:
                return m.group(1)
        return ""

    def _feed_ref(self):
        """The feed that belongs to the selected streamrelay channel."""
        pid = self._feed_pid()
        ref = lamedb_fix.get_feed_ref(pid)
        if ref:
            logger.log("Abertis feed for pid %s: %s" % (pid, ref))
            return ref
        fallback = FEED_REFS.get(pid)
        if fallback:
            logger.log("Abertis feed for pid %s not found - using %s" % (
                pid, fallback))
            return fallback
        logger.log("Abertis feed for pid %s not found in lamedb" % pid)
        return ""

    def _feed_sid(self):
        """Feed SID used by OSCam's ``cw`` log line."""
        pid = self._feed_pid()
        info = lamedb_fix.get_feed_info(pid)
        if info:
            return "%04X" % int(info["sid"])
        parsed = _parse_ref(self._feed_ref())
        if parsed:
            return "%04X" % parsed[0]
        return ""

    def _after_zap_feed_f1(self, ok):
        if not ok:
            self._finish(False)
            return
        self.state = "cw"
        self.deadline = time.time() + CW_TIMEOUT
        self.step_timer.start(350, True)

    def _go_playback(self):
        """Second phase: the feed in F5, so astra gets the clear payload."""
        self.feed_mode = "f5"
        self.oscam_pos = _oscam_size()
        self._go_f5()

    def _zap_feed_f5(self):
        """Rebuild the demux filters, then zap the feed.

        The streamserver only hands the demux filters to astra.  If the feed
        is already playing with stale filters, astra gets the wrong pids and
        the T2-MI de-encapsulator produces garbage.  Zapping a sibling feed
        of the same transponder and back rebuilds the filters without moving
        the tuner (the dish is never touched).
        """
        self.sync_attempts = 0
        pid = self._feed_pid()
        sibling = lamedb_fix.get_sibling_feed_ref(pid)
        if sibling and sibling != self._feed_ref():
            logger.log("Abertis re-tune the feed via a sibling feed on the same "
                       "transponder: %s" % sibling)
            self._zap_async(sibling, "sibling", self._after_zap_sibling)
            return
        self._zap_async(self._feed_ref(), "feed", self._after_zap_feed_f5)

    def _after_zap_sibling(self, ok):
        if not ok:
            logger.log("Abertis sibling feed zap failed - zapping the feed directly")
            self._zap_async(self._feed_ref(), "feed", self._after_zap_feed_f5)
            return
        # the frontend needs a moment to really switch before the feed is
        # zapped again, otherwise the demux keeps the stale filters
        self.state = "siblingwait"
        self.deadline = time.time() + SIBLING_SETTLE
        self.step_timer.start(250, True)

    def _after_zap_feed_f5(self, ok):
        if not ok:
            self._finish(False)
            return
        self.state = "feed5"
        self.deadline = time.time() + FEED_SETTLE
        self.step_timer.start(400, True)

    def _sync_and_f5(self):
        self.state = "sync"
        self.deadline = time.time() + 0.2
        self.step_timer.start(200, True)

    def _start_sync(self):
        """Read the astra output in the background (it can take seconds)."""
        self.sync_attempts += 1
        self.sync_data = []
        self.sync_error = None
        url = ""
        info = _parse_ref(self.pending_ref)
        if info:
            url = _unquote(info[4])
            # The Ciefp refs use 0.0.0.0/localhost; the astra listener is
            # local.  Normalize only the sync read, never the played ref.
            url = url.replace("//0.0.0.0:", "//127.0.0.1:")
            url = url.replace("//localhost:", "//127.0.0.1:")

        def worker():
            try:
                self.sync_data.append(_fetch_stream(url))
            except Exception as e:
                self.sync_error = e

        self.sync_thread = threading.Thread(target=worker)
        self.sync_thread.daemon = True
        self.sync_thread.start()
        self.state = "syncwait"
        self.deadline = time.time() + SYNC_TIMEOUT
        self.step_timer.start(300, True)

    def _give_up(self):
        """No PMT PID could be discovered: playing without it stays black."""
        logger.log("Abertis no PMT PID discovered - not playing (the channel "
                   "would stay black on DreamOS 2.6)")
        self._finish(False)

    def _sync_failed(self, msg):
        """Count a failed astra read; give up instead of looping forever."""
        self.sync_cycles += 1
        if self.sync_cycles >= 2:
            logger.log("Abertis streamrelay sync failed again (%s) - giving up" % msg)
            self._give_up()
            return False
        logger.log("Abertis streamrelay sync failed (%s) - re-reading the astra output"
                   % msg)
        self._zap_feed_f5()
        return True

    def _after_reload_sr(self):
        self.state = "srwait"
        self.deadline = time.time() + 0.5
        self.step_timer.start(250, True)

    def _play_url(self):
        # The Ciefp reference keeps the data pid (0x7EA) in field 6 and the
        # frontend reads the real PMT from the pushed stream.  Patching the
        # reference with the PMT pid makes the frontend wait for a PMT it
        # never finds ("timeout 0012!") and the picture stays black.
        logger.log("Abertis streamrelay ref: %s" % self.pending_ref)
        self._zap_async(self.pending_ref, "URL", self._after_zap_url)

    def _after_zap_url(self, ok):
        if not ok:
            self._finish(False)
            return
        self.state = "urlwait"
        self.deadline = time.time() + URL_SETTLE
        self.step_timer.start(300, True)

    def _zap_async(self, ref, label, callback):
        """Zap a channel using a background thread (no deadlock)."""
        if not ref:
            logger.log("Abertis %s zap: empty ref" % label)
            callback(False)
            return
        key = _ref_key(ref)
        if key:
            self.internal_refs.add(key)
        self.zap_thread = threading.Thread(target=self._zap_worker,
                                           args=(ref, label))
        self.zap_thread.daemon = True
        self.zap_thread.start()
        self.zap_label = label
        self.zap_ref = ref
        self.zap_callback = callback
        self.state = "zapwait"
        self.deadline = time.time() + 12
        self.step_timer.start(200, True)

    def _zap_worker(self, ref, label):
        self.zap_ok = _webif_zap(ref)
        if self.zap_ok:
            self.zap_nav_pending = False
            return
        # The webif failed: the navigation fallback is done by _tick() on the
        # main thread (nav.playService() must not run inside a worker thread).
        self.zap_nav_pending = True

    def _nav_zap(self, ref):
        """Play a service through the navigation (main thread only)."""
        if self.nav is None or not ref:
            return False
        try:
            if getattr(self.nav, "immediatePlay", True):
                self.nav.playService(eServiceReference(ref))
                logger.log("Abertis nav zap: %s" % ref)
                return True
        except Exception as e:
            logger.log("Abertis nav zap failed: %s" % e)
        return False

    def _tick(self):
        now = time.time()
        if self.state == "f5wait":
            if now >= self.deadline:
                self._zap_feed_f5()
                return
            self.step_timer.start(250, True)
            return

        if self.state == "f1wait":
            if now >= self.deadline:
                self._zap_async(self._feed_ref(), "feed", self._after_zap_feed_f1)
                return
            self.step_timer.start(250, True)
            return

        if self.state == "cw":
            sid = self._feed_sid() or OSCAM_SIDS.get(self._feed_pid(), "0BD2")
            if _oscam_cw_seen(self.oscam_pos, sid):
                logger.log("Abertis PID %s: oscam has the BISS key (A-rule)"
                           % self._feed_pid())
                self.state = "cwsettle"
                self.deadline = time.time() + CW_SETTLE
                self.step_timer.start(400, True)
                return
            if now >= self.deadline:
                logger.log("Abertis PID %s: no BISS key in the oscam log - "
                           "continuing with the F5 phase anyway"
                           % self._feed_pid())
                self._go_playback()
                return
            self.step_timer.start(400, True)
            return

        if self.state == "cwsettle":
            if now >= self.deadline:
                self._go_playback()
                return
            self.step_timer.start(400, True)
            return

        if self.state == "siblingwait":
            if now >= self.deadline:
                self._zap_async(self._feed_ref(), "feed", self._after_zap_feed_f5)
                return
            self.step_timer.start(250, True)
            return

        if self.state == "feed5":
            if now >= self.deadline:
                self._sync_and_f5()
                return
            self.step_timer.start(400, True)
            return

        if self.state == "zapwait":
            if self.zap_thread is None or not self.zap_thread.is_alive():
                if not self.zap_ok and self.zap_nav_pending:
                    # the webif zap failed: retry through the navigation, here
                    # on the main thread
                    self.zap_nav_pending = False
                    self.zap_ok = self._nav_zap(self.zap_ref)
                if self.zap_ok:
                    logger.log("Abertis %s zap: %s" % (self.zap_label, self.zap_ref))
                else:
                    logger.log("Abertis %s zap failed" % self.zap_label)
                cb = self.zap_callback
                self.zap_callback = None
                if cb:
                    cb(self.zap_ok)
            elif now >= self.deadline:
                logger.log("Abertis %s zap timeout" % (self.zap_label,))
                cb = self.zap_callback
                self.zap_callback = None
                if cb:
                    cb(False)
            else:
                self.step_timer.start(200, True)
            return

        if self.state == "feed5":
            if now >= self.deadline:
                self._sync_and_f5()
                return
            self.step_timer.start(400, True)
            return

        if self.state == "sync":
            if now >= self.deadline:
                self._start_sync()
            else:
                self.step_timer.start(250, True)
            return

        if self.state == "syncwait":
            if self.sync_thread is not None and not self.sync_thread.is_alive():
                data = self.sync_data[0] if self.sync_data else None
                need = None
                pmtpid = None
                msg = "no data"
                if data:
                    try:
                        need, pmtpid, msg = _streamrelay_pids(data, self.pending_ref)
                        logger.log("Abertis streamrelay: %s" % msg)
                    except Exception as e:
                        need, pmtpid, msg = None, None, "error: %s" % e
                else:
                    msg = "fetch failed: %s" % (self.sync_error,)
                if need is True:
                    # the lamedb changed (streamrelay channel now F5) -> reload
                    self.pending_pmtpid = pmtpid
                    self._reload_async("SR", self._after_reload_sr)
                    return
                if need is False:
                    self.pending_pmtpid = pmtpid
                    self._play_url()
                    return
                if self.sync_attempts >= SYNC_ATTEMPTS:
                    self._sync_failed(msg)
                    return
                logger.log("Abertis streamrelay sync retry %d (%s)" % (
                    self.sync_attempts, msg))
                self.state = "sync"
                self.deadline = time.time() + 2.0
                self.step_timer.start(600, True)
            elif now >= self.deadline:
                logger.log("Abertis streamrelay sync timeout")
                if self.sync_attempts >= SYNC_ATTEMPTS:
                    self._sync_failed("timeout")
                    return
                self.state = "sync"
                self.deadline = time.time() + 1.5
                self.step_timer.start(500, True)
            else:
                self.step_timer.start(300, True)
            return

        if self.state == "reload":
            if self.reload_thread is None or not self.reload_thread.is_alive():
                callback = self.reload_next
                self.reload_next = None
                if callback:
                    callback()
            elif now >= self.deadline:
                logger.log("Abertis reload timeout - continuing")
                callback = self.reload_next
                self.reload_next = None
                if callback:
                    callback()
            else:
                self.step_timer.start(300, True)
            return

        if self.state == "srwait":
            if now >= self.deadline:
                self._play_url()
                return
            self.step_timer.start(250, True)
            return

        if self.state == "urlwait":
            if now >= self.deadline:
                self._verify()
                return
            self.step_timer.start(300, True)
            return

        if self.state == "urlretry":
            if now >= self.deadline:
                self.verify_tries = 0
                logger.log("Abertis retry %d/%d: re-zapping only the URL (astra "
                           "is left alone)" % (self.attempt, MAX_RETRIES))
                self._play_url()
                return
            self.step_timer.start(250, True)
            return

        if self.state == "retry":
            if now >= self.deadline:
                logger.log("Abertis retry %d/%d" % (self.attempt, MAX_RETRIES))
                self.feed_mode = "f5" if getattr(self, "direct_f5", False) else "f1"
                self._go_f5()
                return
            self.step_timer.start(250, True)

    def _native_info(self):
        """Decoder info straight from Enigma2 (no webif round trip).

        Calling the webif from the Enigma2 main thread can block and return
        a false negative, which used to re-run the whole feed sequence and
        break a working astra pipeline.  getInfo() on the current service
        is the same source the webif uses.
        """
        try:
            nav = getattr(self, "nav", None)
            if nav is None or iServiceInformation is None:
                return None
            service = nav.getCurrentService()
            if service is None:
                return None
            info = service.info()
            if info is None:
                return None

            def val(name):
                try:
                    const = getattr(iServiceInformation, name, None)
                    if const is None:
                        return -1
                    return info.getInfo(const)
                except Exception:
                    return -1

            return {
                "ref": self._current_ref(),
                "vpid": val("sVideoPID"),
                "apid": val("sAudioPID"),
                "pmtpid": val("sPMTPID"),
                "height": val("sVideoHeight"),
            }
        except Exception:
            return None

    def _verify(self):
        current = self._current_ref()
        info = self._native_info()
        playing = _info_playing(info)
        if info is None:
            logger.log("Abertis verify: current=%s native info unavailable" % current)
        else:
            logger.log("Abertis verify: current=%s vpid=%s apid=%s pmtpid=%s "
                       "height=%s playing=%s" % (
                           current, info.get("vpid"), info.get("apid"),
                           info.get("pmtpid"), info.get("height"), playing))
        if _is_url(current) and playing:
            self._finish(True)
            return
        if self.verify_tries < VERIFY_TRIES:
            self.verify_tries += 1
            self.state = "urlwait"
            self.deadline = time.time() + VERIFY_INTERVAL
            logger.log("Abertis playback not confirmed yet - check %d/%d" % (
                self.verify_tries, VERIFY_TRIES))
            self.step_timer.start(300, True)
            return
        self._retry()

    def _retry(self):
        if self.attempt < MAX_RETRIES:
            self.attempt += 1
            self.state = "urlretry"
            self.deadline = time.time() + RETRY_DELAY
            logger.log("Abertis playback verify failed - re-zapping the URL only")
            self.step_timer.start(250, True)
        else:
            self._finish(False)

    def _cancel(self):
        """Abort the current sequence because the user chose another URL."""
        try:
            self.step_timer.stop()
        except Exception:
            pass
        self.busy = False
        self.state = "idle"
        self.pending_ref = None
        self.pending_url = None
        self.pending_pmtpid = None
        self.zap_ref = ""
        self.zap_callback = None
        self.retry_until = 0
        self.internal_refs = set()
        logger.log("Abertis sequence cancelled")

    def _finish(self, ok):
        try:
            self.step_timer.stop()
        except Exception:
            pass
        self.busy = False
        self.state = "idle"
        self.verify_tries = 0
        if ok:
            self.last_seen_ref = _ref_key(self.pending_ref)
            logger.log("Abertis auto OK")
        else:
            self.retry_until = time.time() + FAIL_COOLDOWN
            current = self._current_ref()
            if _is_url(current):
                # do not re-trigger the sequence on every poll while the URL
                # is selected; a new user selection still triggers it
                self.last_seen_ref = _ref_key(current)
            logger.log("Abertis auto FAILED; previous service not restored automatically "
                       "(manual motor safety)")
        self.pending_ref = None
        self.pending_url = None
        self.internal_refs = set()

    def run_now(self):
        current = self._current_ref()
        target = current if _is_url(current) else FALLBACK_URL_REF
        return self.start(target)


def _start_hook():
    global _hook
    if _hook is None and eTimer is not None:
        _hook = _Auto2026(_session)


def run_now():
    """Manual trigger used by the plugin UI / console."""
    _start_hook()
    if _hook is None:
        return False
    return _hook.run_now()


def _run():
    logger.log("Autostart triggered")
    try:
        setup.run_full_setup(restart_configs=False)
    except Exception as e:
        logger.log("Autostart setup error: %s" % e)
    try:
        _start_hook()
    except Exception as e:
        logger.log("Autostart hook error: %s" % e)


def sessionstart(session=None, **kwargs):
    """WHERE_SESSIONSTART variant: guarantees a real session/nav object."""
    global _session
    if session is not None:
        _session = session
    logger.log("Abertis Auto sessionstart (session=%s)" % (session is not None))
    autostart(session=session)


def autostart(**kwargs):
    global _timer, _timer_conn, _session
    if kwargs.get("session") is not None:
        _session = kwargs.get("session")
    if _timer is not None:
        logger.log("Abertis Auto autostart already registered")
        return
    try:
        logger.log("Abertis Auto autostart registered (session=%s)" % (_session is not None))
        if eTimer is None:
            logger.log("eTimer unavailable - autostart skipped")
            return
        _timer = eTimer()

        def _cb():
            _run()
            try:
                _timer.stop()
            except Exception:
                pass

        _timer_conn = _timer.timeout.connect(_cb)
        _timer.start(12000, True)
    except Exception as e:
        logger.log("autostart registration error: %s" % e)
