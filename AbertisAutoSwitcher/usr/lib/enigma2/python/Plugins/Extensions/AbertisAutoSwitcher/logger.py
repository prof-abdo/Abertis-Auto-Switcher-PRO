# -*- coding: utf-8 -*-
import time
import os

LOGFILE = "/tmp/abetris_auto.log"
MAX_LINES = 500


def log(msg):
    try:
        line = "[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
        with open(LOGFILE, "a") as f:
            f.write(line)
        # trim
        try:
            with open(LOGFILE, "r") as f:
                lines = f.readlines()
            if len(lines) > MAX_LINES:
                with open(LOGFILE, "w") as f:
                    f.writelines(lines[-MAX_LINES:])
        except Exception:
            pass
    except Exception:
        pass


def tail(n=20):
    try:
        with open(LOGFILE, "r") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except Exception:
        return ""


def clear():
    try:
        open(LOGFILE, "w").close()
    except Exception:
        pass
