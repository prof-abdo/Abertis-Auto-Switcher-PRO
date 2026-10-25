# -*- coding: utf-8 -*-
"""Build enigma2-plugin-extensions-abertisautoswitcher_<version>_all.deb.

Produces a standard Debian .deb (ar archive):
  debian-binary (2.0)
  control.tar.gz  (control + postinst + prerm)
  data.tar.gz     (plugin files incl. arch/<arch> binaries, etc/init.d/astra,
                   and the *.dist Abertis key files for fresh installs)

Everything else is identical to build_ipk.py: the working astra.conf,
SoftCam.Key and OSCam files are never owned by the package itself.
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
    with open(os.path.join(DEBIAN, "control"), "r", encoding="utf-8") as f:
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
        entries.append((PLUGIN_REL + "/abertis.aarch64", native, 0o755))

    # Loose aarch64 tools (kept for backwards compatibility with the .ipk
    # layout; ensure_astra_tools() prefers arch/arm64/ over these)
    for tool in ("astra", "t2mi_decap", "spammer"):
        path = os.path.join(PLUGIN_DIR, tool)
        if os.path.exists(path):
            entries.append((PLUGIN_REL + "/" + tool, path, 0o755))

    # Shared libraries the shipped astra tools need (deployed into
    # /usr/lib by setup.py when the image lacks them)
    for lib in ("libcrypto.so.3", "libdvbcsa.so.1"):
        path = os.path.join(PLUGIN_DIR, lib)
        if os.path.exists(path):
            entries.append((PLUGIN_REL + "/" + lib, path, 0o644))

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

    # init script of astra
    init = os.path.join(PKG, "etc", "init.d", "astra")
    if os.path.exists(init):
        entries.append(("etc/init.d/astra", init, 0o755))

    # The Abertis BISS key files as *.dist copies (see build_ipk.py): dpkg
    # owns only the .dist names, the postinst copies them under their real
    # names on a fresh install.  The repo keeps the lowercase live copy
    # under softcam.key ("SoftCam.Key" cannot coexist with it on Windows).
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


def _build_data_tar(entries):
    # dpkg cannot create a missing leaf directory on its own
    # ("...dpkg-new: No such file or directory"), so every parent
    # directory of a data entry gets an explicit dir entry.
    dirs = set()
    for name, _path, _mode in entries:
        parts = name.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]) + "/")
    dirs = sorted(dirs)

    buf = io.BytesIO()
    tar = tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT)
    for d in dirs:
        ti = tarfile.TarInfo(d)
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


def _build_control_tar():
    buf = io.BytesIO()
    tar = tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.GNU_FORMAT)
    order = [("control", 0o644), ("postinst", 0o755), ("prerm", 0o755)]
    for name, mode in order:
        path = os.path.join(DEBIAN, name)
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
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
    header = "%-16s%-12d%-6d%-6d%08d%-10d`\n" % (
        name, 0, 0, 0, 0o644, len(body))
    assert len(header) == 60, len(header)
    out = header.encode("ascii") + body
    if len(body) % 2:
        out += b"\n"
    return out


def main():
    version = _control_version()
    out_path = os.path.join(
        ROOT,
        "enigma2-plugin-extensions-abertisautoswitcher_%s_all.deb" % version,
    )

    data_entries = _gather_data_entries()
    data_tar = _build_data_tar(data_entries)
    control_tar = _build_control_tar()

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
