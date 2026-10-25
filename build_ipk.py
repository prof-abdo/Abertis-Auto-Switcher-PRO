# -*- coding: utf-8 -*-
"""Build enigma2-plugin-extensions-abertisautoswitcher_<version>_all.ipk.

For opkg images (OpenATV / OpenPLi / ...).  The layout is the standard ipk
ar container (debian-binary + control.tar.gz + data.tar.gz) - the same one
opkg and dpkg both consume.

Contents are identical to build_deb.py: the working astra.conf and the
OSCam files are never owned by the package; the Abertis BISS key files are
shipped as /etc/tuxbox/config/*.dist copies that the postinst installs
under their real names only when no key file exists yet.
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


def _control_version():
    """Read the Version: field of DEBIAN/control."""
    with io.open(os.path.join(DEBIAN, "control"), "r", encoding="utf-8") as f:
        for line in f:
            if line.lower().startswith("version:"):
                return line.split(":", 1)[1].strip()
    return ""


def _gather_data_entries():
    entries = []

    # Plugin .py files
    for f in sorted(os.listdir(PLUGIN_DIR)):
        if f.endswith(".py"):
            entries.append((PLUGIN_REL + "/" + f,
                            os.path.join(PLUGIN_DIR, f),
                            0o644))

    # Native aarch64 Abertis de-encapsulator (arm64 fallback)
    native = os.path.join(PLUGIN_DIR, "abertis.aarch64")
    if os.path.exists(native):
        entries.append((PLUGIN_REL + "/abertis.aarch64",
                        native, 0o755))

    # Loose aarch64 tools (backwards compatible layout; the plugin prefers
    # the per-arch copies under arch/<arch>/)
    for tool in ("astra", "t2mi_decap", "spammer"):
        path = os.path.join(PLUGIN_DIR, tool)
        if os.path.exists(path):
            entries.append((PLUGIN_REL + "/" + tool, path, 0o755))

    # Per-arch binaries under arch/arm64/, arch/arm/, arch/mips/
    arch_dir = os.path.join(PLUGIN_DIR, "arch")
    if os.path.isdir(arch_dir):
        for arch in sorted(os.listdir(arch_dir)):
            d = os.path.join(arch_dir, arch)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                p = os.path.join(d, f)
                if os.path.isfile(p):
                    entries.append(
                        (PLUGIN_REL + "/arch/" + arch + "/" + f, p, 0o755))

    # The init script of astra.  Nothing else owns /etc/init.d/astra, so the
    # package can install it directly; the working astra.conf, SoftCam.Key
    # and the OSCam files stay untouched by the package manager itself.
    init_script = os.path.join(PKG, "etc", "init.d", "astra")
    if os.path.exists(init_script):
        entries.append(("etc/init.d/astra", init_script, 0o755))

    # The Abertis BISS key files (astra reads the lowercase softcam.key,
    # oscam-emu the uppercase SoftCam.Key).  They are shipped as *.dist so
    # the package never overwrites a receiver's working keys.  The repo
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
            entries.append((name, path, 0o644))

    for name, _path, _mode in entries:
        assert (name.startswith(PLUGIN_REL + "/") or name == "etc/init.d/astra"
                or name.startswith("etc/tuxbox/config/")), name
    return entries


def _tar_gz(entries, dirs=()):
    buf = io.BytesIO()
    tar = tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT)
    # Directory entries first: on a clean image the plugin directory does
    # not exist yet and the package manager cannot create the file's parent
    # on its own ("...dpkg-new: No such file or directory").
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


def _dir_names(entries):
    dirs = set()
    for name, _path, _mode in entries:
        parts = name.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]) + "/")
    return sorted(dirs)


def _ar_member(name, body):
    header = "%-16s%-12d%-6d%-6d%-8s%-10d`\n" % (name, 0, 0, 0, "100644", len(body))
    assert len(header) == 60, len(header)
    out = header.encode("ascii") + body
    if len(body) % 2:
        out += b"\n"
    return out


def main():
    version = _control_version()
    out_path = os.path.join(
        ROOT,
        "enigma2-plugin-extensions-abertisautoswitcher_%s_all.ipk" % version,
    )

    data_entries = _gather_data_entries()
    control_entries = [
        ("control", os.path.join(DEBIAN, "control"), 0o644),
        ("postinst", os.path.join(DEBIAN, "postinst"), 0o755),
        ("prerm", os.path.join(DEBIAN, "prerm"), 0o755),
    ]
    control_tar = _tar_gz(control_entries)
    data_tar = _tar_gz(data_entries, _dir_names(data_entries))

    out = b"!<arch>\n"
    out += _ar_member("debian-binary", b"2.0\n")
    out += _ar_member("control.tar.gz", control_tar)
    out += _ar_member("data.tar.gz", data_tar)
    with open(out_path, "wb") as f:
        f.write(out)

    print("built %s (%d bytes)" % (out_path, len(out)))
    for name, _, _ in data_entries:
        print("  data:", name)


if __name__ == "__main__":
    main()
