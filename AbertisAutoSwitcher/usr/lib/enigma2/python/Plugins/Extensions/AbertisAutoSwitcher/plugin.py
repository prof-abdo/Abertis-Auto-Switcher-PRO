# -*- coding: utf-8 -*-
"""Abertis Auto Pro - UI and autostart registration.

The engine itself lives in ``autostart.py`` / ``lamedb_fix.py`` /
``setup.py``; this module only draws the screen and starts the automation.
"""
import os
import re
import subprocess
import threading

from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label

from . import logger, setup, lamedb_fix, autostart

LAMEDB = "/etc/enigma2/lamedb"
BACKUP_DIR = "/root/abetris-backup"
PKG = "enigma2-plugin-extensions-abertisautoswitcher"
VERSION = "1.9.15"
AUTHOR = "Kingcs / Prof-abdo"
THANKS = "mouadhada (AbetrisFlagSwitch) and Saber Hisham SH"

try:
    _TEXT = unicode           # Python 2
except NameError:
    _TEXT = str               # Python 3


def _to_str(value):
    """eLabel.setText() only accepts a byte string."""
    if isinstance(value, _TEXT):
        try:
            return value.encode("utf-8")
        except Exception:
            return value
    return value


def _installed_version():
    try:
        out = subprocess.check_output(
            ["dpkg-query", "-W", "-f=${Version}", PKG], stderr=subprocess.STDOUT)
        value = out.decode("utf-8", "replace").strip()
        if value:
            return _to_str(value)
    except Exception:
        pass
    return VERSION


def _version_tuple(value):
    parts = []
    for chunk in re.split(r"[.\-_+]", str(value).strip()):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _local_packages():
    found = []
    try:
        names = os.listdir(BACKUP_DIR)
    except Exception:
        return found
    for name in names:
        if not name.endswith(".ipk"):
            continue
        match = (re.search(r"abertisautoswitcher_([0-9][0-9._]*)_all\.ipk$", name)
                 or re.search(r"abetris_([0-9][0-9._]*)\.ipk$", name))
        if match:
            found.append((match.group(1), name))
    return sorted(found, key=lambda item: _version_tuple(item[0]))


class AbertisAutoSwitcherScreen(Screen):
    skin = """
    <screen name="AbertisAutoSwitcherScreen" position="center,center" size="960,580" title="Abertis Auto Switcher PRO" backgroundColor="#00141e2b">
        <widget name="brand" position="40,30" size="880,55" font="Regular;38" foregroundColor="#00ffffff" backgroundColor="#00141e2b"/>
        <widget name="tagline" position="40,90" size="880,32" font="Regular;22" foregroundColor="#009bb7d0" backgroundColor="#00141e2b"/>
        <widget name="status" position="40,155" size="880,58" font="Regular;28" foregroundColor="#0096e6c5" backgroundColor="#001c3040" valign="center"/>
        <widget name="log" position="40,240" size="880,120" font="Regular;23" foregroundColor="#00e3eaf0" backgroundColor="#00141e2b"/>
        <widget name="btn_red" position="40,405" size="200,52" font="Regular;22" foregroundColor="#00ffffff" backgroundColor="#00a32c3e" halign="center" valign="center"/>
        <widget name="btn_green" position="265,405" size="200,52" font="Regular;22" foregroundColor="#00ffffff" backgroundColor="#00246b47" halign="center" valign="center"/>
        <widget name="btn_yellow" position="490,405" size="200,52" font="Regular;22" foregroundColor="#00141e2b" backgroundColor="#00e6bf48" halign="center" valign="center"/>
        <widget name="btn_blue" position="715,405" size="200,52" font="Regular;22" foregroundColor="#00ffffff" backgroundColor="#002d60a0" halign="center" valign="center"/>
        <widget name="btn_ok" position="40,482" size="200,40" font="Regular;22" foregroundColor="#00ffffff" backgroundColor="#0034465b" halign="center" valign="center"/>
        <widget name="footer" position="265,482" size="650,58" font="Regular;20" foregroundColor="#009bb7d0" backgroundColor="#00141e2b"/>
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        labels = {
            "brand": "ABERTIS AUTO SWITCHER PRO",
            "tagline": "Professional Abertis / Ciefp Stream Engine  |  DreamOS 2.6",
            "status": "System Ready — Automation Active",
            "log": "Select any Abertis feed from the bouquet.  Automatic F1 -> F5 playback handles the rest.",
            "btn_red": "Exit",
            "btn_green": "Check update",
            "btn_yellow": "Refresh status",
            "btn_blue": "Diagnostics",
            "btn_ok": "OK  About",
            "footer": "Abertis Auto Switcher PRO  v1.9.15  |  Kingcs / Prof-abdo  |  mouadhada + Saber Hisham SH",
        }
        for name, text in labels.items():
            self[name] = Label(_to_str(text))
        self["actions"] = ActionMap(
            ["ColorActions", "OkCancelActions", "InfobarActions"],
            {
                "red": self.close,
                "green": self.check_update,
                "yellow": self.refresh,
                "blue": self.show_diagnostics,
                "ok": self.show_about,
                "cancel": self.close,
            }, -1)
        self._busy = False
        self.onLayoutFinish.append(self._on_skin_ready)
        self.refresh()
        logger.log("Abertis Auto Switcher PRO UI opened")

    # ------------------------------------------------------------------ utils
    def _on_skin_ready(self):
        logger.log("Abertis Auto Switcher PRO UI layout ready (opaque colors)")

    def _message(self, title, text):
        self.session.open(MessageBox, _to_str(text), type=MessageBox.TYPE_INFO,
                          timeout=-1, title=_to_str(title))

    # ---------------------------------------------------------------- actions
    def refresh(self):
        hook = getattr(autostart, "_hook", None)
        if hook is None:
            status = "Automation is starting"
        elif getattr(hook, "disabled", False):
            status = "Automation is disabled"
        elif getattr(hook, "busy", False):
            status = "Preparing your channel..."
        else:
            status = "Automation ready"
        self["status"].setText(_to_str(status))

    def run_setup(self):
        """Re-apply the whole configuration (idempotent, backed up)."""
        if self._busy:
            return
        self._busy = True
        logger.log("UI requested full setup")

        def worker():
            try:
                count = setup.run_full_setup(restart_configs=True)
                lamedb_fix.reload_bouquets()
                logger.log("UI setup done: %d feeds active" % count)
            except Exception as e:
                logger.log("setup error: %s" % e)
            finally:
                self._busy = False

        threading.Thread(target=worker).start()

    def check_update(self):
        """Compare the installed version with the packages kept on the box."""
        current = _installed_version()
        packages = _local_packages()
        lines = ["Installed version: %s" % current, ""]
        newer = None
        if packages:
            lines.append("Packages found in %s:" % BACKUP_DIR)
            for version, name in packages:
                flag = ""
                if _version_tuple(version) > _version_tuple(current):
                    flag = "   <-- newer"
                    newer = (version, name)
                lines.append("   %-10s %s%s" % (version, name, flag))
        else:
            lines.append("No package archive found in %s." % BACKUP_DIR)
        lines.append("")
        if newer:
            lines.append("Update available: %s" % newer[0])
            lines.append("")
            lines.append("dpkg -i %s/%s" % (BACKUP_DIR, newer[1]))
            lines.append("systemctl restart enigma2.service")
        else:
            lines.append("Abertis Auto Switcher PRO %s is up to date." % current)
        self._message("Abertis Auto Switcher PRO - update", "\n".join(lines))
        logger.log("UI update check completed for version %s" % current)

    def show_diagnostics(self):
        """Show what the engine is doing right now."""
        lines = []
        try:
            lines.append("version      : %s" % _installed_version())
            for name, cmd in (("enigma2", ["pidof", "enigma2"]),
                              ("astra", ["pidof", "astra"]),
                              ("oscam", ["pidof", "OSCam_11964-803"])):
                try:
                    pids = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
                    pids = pids.decode("utf-8", "replace").strip() or "not running"
                except Exception:
                    pids = "not running"
                lines.append("%-12s: %s" % (name, pids))
        except Exception as e:
            lines.append("process check failed: %s" % e)
        try:
            feeds = lamedb_fix.get_all_feeds()
            lines.append("feeds        : %d (%s)" % (
                len(feeds),
                ", ".join(str(f["pid"]) for f in feeds[:12]) +
                (" ..." if len(feeds) > 12 else "")))
            info = lamedb_fix.get_feed_info("8008")
            if info:
                lines.append("8008 feed    : %s" % info["ref"])
        except Exception as e:
            lines.append("feed check failed: %s" % e)
        try:
            upper = setup.SOFTCAM_KEY_UPPER
            text = open(upper).read() if os.path.exists(upper) else ""
            lines.append("oscam keys   : %d Abertis lines in %s" % (
                text.upper().count("ABERTIS"), os.path.basename(upper)))
        except Exception as e:
            lines.append("key check failed: %s" % e)
        lines.append("")
        lines.append(logger.tail(10))
        self._message("Abertis Auto Switcher PRO - diagnostics", "\n".join(lines))

    def show_about(self):
        msg = (
            "\n" + "=" * 48 + "\n"
            + "  ABERTIS AUTO SWITCHER PRO  v" + _installed_version() + "\n"
            + "  Professional Abertis / Ciefp Engine  |  DreamOS 2.6\n"
            + "=" * 48 + "\n\n"
            + "  AUTHOR  :  %s\n" % AUTHOR
            + "  CREDITS :  %s\n" % THANKS
            + "  BASED ON:  AbetrisFlagSwitch (mouadhada / tunisia-sat)\n\n"
            + "-" * 48 + "\n"
            + "  HOW IT WORKS\n"
            + "-" * 48 + "\n"
            + "  1. F1 Learning  ->  OSCam-EMU A-rule + BISS key\n"
            + "  2. F5 Playback  ->  Astra de-encapsulates T2-MI\n"
            + "  3. Ciefp URL played unchanged  (no patch)\n"
            + "  4. Verified via native iServiceInformation\n\n"
            + "=" * 48 + "\n"
            + "  FEEDS COVERED :  All 34 Abertis feeds (8008 included)\n"
            + "  TRANSPONDER  :  Hispasat 30W (e.g. 12583 V 16901)\n"
            + "  BACKUP PATH  :  /root/abetris-backup/\n"
            + "=" * 48 + "\n"
        )
        self._message(
            "\n  Abertis Auto Switcher PRO  -  About  \n",
            msg)


def main(session, **kwargs):
    session.open(AbertisAutoSwitcherScreen)


def sessionstart(session=None, **kwargs):
    autostart.sessionstart(session=session)


def Plugins(**kwargs):
    res = [PluginDescriptor(
        name="Abertis Auto Switcher PRO",
        description="Professional Abertis / Ciefp streamrelay engine for DreamOS 2.6",
        where=PluginDescriptor.WHERE_EXTENSIONSMENU,
        fnc=main)]
    # autostart on boot and on session start (session variant supplies nav)
    try:
        res.append(PluginDescriptor(
            name="Abertis Auto Switcher PRO",
            description="Abertis Auto Switcher PRO autostart",
            where=PluginDescriptor.WHERE_AUTOSTART,
            fnc=autostart.autostart))
        res.append(PluginDescriptor(
            name="Abertis Auto Switcher PRO",
            description="Abertis Auto Switcher PRO session start",
            where=PluginDescriptor.WHERE_SESSIONSTART,
            fnc=sessionstart))
    except Exception:
        pass
    return res
