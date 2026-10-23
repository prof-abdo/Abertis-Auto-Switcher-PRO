# -*- coding: utf-8 -*-

from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
import os
import re
import time
import threading

LAMEDB = "/etc/enigma2/lamedb"
BACKUP = "/etc/enigma2/lamedb.bak"
TMPFILE = "/tmp/lamedb_mod"
PACKAGE = "ABERTIS"
LOGFILE = "/tmp/abetris_flag.log"

def log(msg):
    with open(LOGFILE, "a") as f:
        f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))

def reload_http():
    log("Reloading bouquets (thread)...")
    os.system('wget -q -O - "http://127.0.0.1/web/servicelistreload?mode=0"')
    os.system('wget -q -O - "http://127.0.0.1/web/servicelistreload?mode=1"')
    log("Reload HTTP done")

class AbetrisFlagScreen(Screen):
    skin = """
    <screen name="AbetrisFlagSwitch" position="center,center" size="700,250" title="ABERTIS Flag Switch v0.a1 alpha">
        <widget name="status" position="20,20" size="660,60" font="Regular;27"/>
        <widget name="info" position="20,120" size="660,50" font="Regular;23"/>
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self["status"] = Label("Choose a flag to apply:")
        self["info"] = Label("Red = F1, Green = F5, Cancel = back")
        self["actions"] = ActionMap(
            ["ColorActions", "OkCancelActions"],
            {
                "red": lambda: self.change_flag("1"),
                "green": lambda: self.change_flag("5"),
                "cancel": self.close
            }, -1
        )
        log("Plugin opened")

    def change_flag(self, flag):
        log("Starting apply_flag %s" % flag)
        self["status"].setText("Applying F%s..." % flag)
        time.sleep(0.1)  # UI timeout

        if not os.path.exists(LAMEDB):
            self.session.open(MessageBox, "Error: lamedb not found", MessageBox.TYPE_ERROR)
            log("LAMEDB not found")
            return

        # Backup
        os.system("cp '%s' '%s'" % (LAMEDB, BACKUP))
        log("Backup created")

        # Lecture et modification
        with open(LAMEDB, "r") as f:
            lines = f.readlines()
        log("LAMEDB read OK")

        out = []
        count = 0
        i = 0
        while i < len(lines):
            line = lines[i]
            out.append(line)
            if re.match(r"^[0-9a-f]{4}:", line.strip()):
                if i + 2 < len(lines):
                    name_line = lines[i + 1]
                    flags_line = lines[i + 2]
                    if flags_line.strip().upper().startswith("P:%s" % PACKAGE):
                        name_core = name_line.strip()
                        if name_core.endswith(" F1") or name_core.endswith(" F5"):
                            name_core = name_core[:-3]
                        new_name = name_core + " F" + flag + "\n"
                        new_flags = re.sub(r"f:\d+", "f:%s" % flag, flags_line)
                        out.append(new_name)
                        out.append(new_flags)
                        count += 1
                        i += 3
                        continue
                    else:
                        out.append(name_line)
                        out.append(flags_line)
                        i += 3
                        continue
            i += 1

        with open(TMPFILE, "w") as f:
            f.writelines(out)
        log("LAMEDB written OK (%d services)" % count)

        os.system("cp '%s' '%s'" % (TMPFILE, LAMEDB))
        log("LAMEDB replaced")

        # Reload HTTP in a separate thread
        t = threading.Thread(target=reload_http)
        t.start()

        self["status"].setText("F%s applied (%d services)" % (flag, count))
        log("Flag applied successfully")
        time.sleep(0.1)  # UI timeout

def main(session, **kwargs):
    session.open(AbetrisFlagScreen)

def Plugins(**kwargs):
    return [PluginDescriptor(name="ABERTIS Flag Switch v0.a1 alpha",
                             description="Change F1/F5 for ABERTIS",
                             where=PluginDescriptor.WHERE_EXTENSIONSMENU,
                             fnc=main)]