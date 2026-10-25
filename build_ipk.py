# -*- coding: utf-8 -*-
"""Build enigma2-plugin-extensions-abertisautoswitcher_1.9.13_all.ipk.

Only the plugin python files are packaged.  /etc/astra/astra.conf and
/etc/astra/scripts/abertis are deliberately excluded: they are the user's
known-good working files.  The postinst only appends missing Abertis
streams/A-rules after backing them up.

The Abertis BISS key files are shipped as /etc/tuxbox/config/*.dist copies;
the postinst installs them under their real names only when no key file
exists yet, so a receiver's working keys are never overwritten.
"""
import io
import os
import tarfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(ROOT, "AbertisAutoSwitcher")
PLUGIN_REL = "usr/lib/enigma2/python/Plugins/Extensions/AbertisAutoSwitcher"
PLUGIN_DIR = os.path.join(PKG, PLUGIN_REL)
DEBIAN = os.path.join(PKG, "DEBIAN")
OUT = os.path.join(ROOT, "enigma2-plugin-extensions-abertisautoswitcher_1.9.13_all.ipk")


def _tar_gz(entries, dirs=()):
    buf = io.BytesIO()
    tar = tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT)
    # Directory entries first: on a clean image the plugin directory does
    # not exist yet and dpkg cannot create the file's parent on its own
    # (it fails with "...dpkg-new: No such file or directory").
    for name in dirs:
        ti = tarfile.TarInfo(name)
        ti.type = tarfile.DIRTYPE
        ti.mode = 0o755
        ti.uid = 0
        ti.gid = 0
        ti.uname = "root"
        ti.gname = "root"
        ti.mtime = int(time.time())
        tar.addfile(ti)
    for name, path, mode in entries:
        data = open(path, "rb").read()
        ti = tarfile.TarInfo(name)
        ti.size = len(data)
        ti.mode = mode
        ti.uid = 0
        ti.gid = 0
        ti.uname = "root"
        ti.gname = "root"
        ti.mtime = int(time.time())
        tar.addfile(ti, io.BytesIO(data))
    tar.close()
    return buf.getvalue()


def _ar_member(name, body):
    # ipkg-build writes the member names without a trailing slash; opkg
    # matches them exactly.
    header = "%-16s%-12d%-6d%-6d%-8s%-10d`\n" % (name, 0, 0, 0, "100644", len(body))
    assert len(header) == 60, len(header)
    out = header.encode("ascii") + body
    if len(body) % 2:
        out += b"\n"
    return out


def _control_version():
    """Read the Version: field of DEBIAN/control."""
    with io.open(os.path.join(DEBIAN, "control"), "r", encoding="utf-8") as f:
        for line in f:
            if line.lower().startswith("version:"):
                return line.split(":", 1)[1].strip()
    return ""


def main():
    plugin_files = sorted(f for f in os.listdir(PLUGIN_DIR) if f.endswith(".py"))
    data_entries = []
    for f in plugin_files:
        data_entries.append((PLUGIN_REL + "/" + f, os.path.join(PLUGIN_DIR, f), 0o644))
    # the native aarch64 Abertis de-encapsulator is bundled as a fallback;
    # the plugin only installs it when /etc/astra/scripts/abertis is not
    # already an aarch64 binary.
    native = os.path.join(PLUGIN_DIR, "abertis.aarch64")
    if os.path.exists(native):
        data_entries.append((PLUGIN_REL + "/abertis.aarch64", native, 0o755))
    # the astra-sm binaries: astra itself, the T2-MI de-encapsulator and the
    # test tool.  The plugin deploys them into /usr/bin (with a backup of the
    # file it replaces), so they are shipped inside the plugin directory.
    for tool in ("astra", "t2mi_decap", "spammer"):
        path = os.path.join(PLUGIN_DIR, tool)
        if os.path.exists(path):
            data_entries.append((PLUGIN_REL + "/" + tool, path, 0o755))
    # The init script of astra.  Nothing else owns /etc/init.d/astra, so dpkg
    # can install it directly; the working astra.conf, SoftCam.Key and the
    # OSCam files stay untouched by dpkg itself.
    init_script = os.path.join(ROOT, "AbertisAutoSwitcher", "etc", "init.d", "astra")
    if os.path.exists(init_script):
        data_entries.append(("etc/init.d/astra", init_script, 0o755))
    # The Abertis BISS key files (astra reads the lowercase softcam.key,
    # oscam-emu the uppercase SoftCam.Key).  They are shipped as *.dist so
    # dpkg never overwrites a receiver's working keys: the postinst copies
    # them into place only when the real file does not exist yet.  The repo
    # keeps the uppercase copy under "SoftCam.Key.dist" because a Windows
    # checkout cannot hold two file names that differ only in case.
    key_entries = (
        ("etc/tuxbox/config/softcam.key.dist",
         os.path.join(PKG, "etc", "tuxbox", "config", "softcam.key")),
        ("etc/tuxbox/config/SoftCam.Key.dist",
         os.path.join(PKG, "etc", "tuxbox", "config", "SoftCam.Key.dist")),
    )
    for name, path in key_entries:
        if os.path.exists(path):
            data_entries.append((name, path, 0o644))
    for name, _path, _mode in data_entries:
        assert (name.startswith(PLUGIN_REL + "/") or name == "etc/init.d/astra"
                or name.startswith("etc/tuxbox/config/")), name
    version = _control_version()
    assert version in OUT, "output file %s does not match control version %s" % (
        os.path.basename(OUT), version)
    control_entries = [
        ("control", os.path.join(DEBIAN, "control"), 0o644),
        ("postinst", os.path.join(DEBIAN, "postinst"), 0o755),
        ("prerm", os.path.join(DEBIAN, "prerm"), 0o755),
    ]
    control_tar = _tar_gz(control_entries)
    # Include the plugin directory itself in the data tar so a clean DreamOS
    # image (no AbertisAutoSwitcher directory yet) can install it: dpkg cannot create
    # a missing leaf directory on its own ("...dpkg-new: No such file or
    # directory").  The parent directories exist on every Enigma2 image.
    plugin_dirs = [PLUGIN_REL + "/", "etc/tuxbox/config/"]
    data_tar = _tar_gz(data_entries, plugin_dirs)
    out = b"!<arch>\n"
    out += _ar_member("debian-binary", b"2.0\n")
    out += _ar_member("control.tar.gz", control_tar)
    out += _ar_member("data.tar.gz", data_tar)
    with open(OUT, "wb") as f:
        f.write(out)
    print("built %s (%d bytes)" % (OUT, len(out)))
    for name, _, _ in data_entries:
        print("  data:", name)


if __name__ == "__main__":
    main()
