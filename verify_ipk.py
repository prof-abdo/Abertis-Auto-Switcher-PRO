# -*- coding: utf-8 -*-
"""Inspect the built IPK: list data.tar.gz members with sizes."""
import io
import os
import tarfile

ROOT = os.path.dirname(os.path.abspath(__file__))
ipks = [f for f in os.listdir(ROOT)
        if f.startswith("enigma2-plugin-extensions-abertisautoswitcher_") and f.endswith(".ipk")]
ipks.sort(key=lambda f: os.path.getmtime(os.path.join(ROOT, f)))
ipk = os.path.join(ROOT, ipks[-1])
blob = open(ipk, "rb").read()
assert blob.startswith(b"!<arch>\n"), "not an ar archive"
off = 8
members = {}
while off < len(blob):
    header = blob[off:off + 60]
    name = header[:16].decode("ascii").strip()
    size = int(header[48:58].decode("ascii").strip())
    body = blob[off + 60:off + 60 + size]
    members[name] = body
    off += 60 + size + (size % 2)
print("ar members:", sorted(members))
data = tarfile.open(fileobj=io.BytesIO(members["data.tar.gz"]), mode="r:gz")
for ti in data.getmembers():
    if ti.name.rstrip("/") in (
        "etc",
        "etc/tuxbox",
        "etc/tuxbox/config",
        "usr",
        "usr/lib",
    ):
        continue
    print("  %9d  %s" % (ti.size, ti.name))
