#!/usr/bin/python
# -*- coding: utf-8 -*-
"""systemd ExecStartPre: fix /etc/enigma2/lamedb before enigma2 loads it.

Runs before enigma2 so the in-memory database is built from the final
per-service rules.  Never fails the boot: always exits 0.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import lamedb_fix
    count, details = lamedb_fix.apply()
    try:
        with open("/tmp/abertis_prestart_ok", "w") as f:
            f.write("count=%d\n" % count)
            for d in details:
                f.write("%s\n" % d)
    except Exception:
        pass
except Exception as e:
    try:
        with open("/tmp/abertis_prestart_err", "w") as f:
            f.write("%s\n" % e)
    except Exception:
        pass

sys.exit(0)
