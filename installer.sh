#!/bin/sh
#
# Abertis Auto Switcher PRO - installer
#
#   wget https://raw.githubusercontent.com/prof-abdo/Abertis-Auto-Switcher-PRO/main/installer.sh -O - | /bin/sh
#
# Downloads the latest release of the plugin and installs it with dpkg.
#
# The installer is deliberately conservative:
#   * it never reboots and never restarts Enigma2
#   * it never touches /etc/astra/astra.conf, /etc/astra/scripts/abertis or
#     the softcam keys (the package only extends them, with a backup)
#   * it keeps a copy of the package and of the working configuration in
#     /root/abetris-backup
#
set -e

REPO="prof-abdo/Abertis-Auto-Switcher-PRO"
RELEASE="v1.9.12"
PKG="enigma2-plugin-extensions-abertisautoswitcher"
BACKUP_DIR="/root/abetris-backup"
TMP="/tmp/abertisautoswitcher-install.$$"
PKG_DIR=""

say()  { echo "[abertis-auto-switcher] $*"; }
die()  { echo "[abertis-auto-switcher] ERROR: $*" >&2; exit 1; }

cleanup() { rm -f "$TMP"; rm -rf "$PKG_DIR"; }
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------- checks
[ "$(id -u)" = "0" ] || die "please run this as root"
command -v dpkg >/dev/null 2>&1 || die "dpkg not found - this is not a Debian based system"
[ -d /usr/lib/enigma2/python/Plugins/Extensions ] || die "Enigma2 was not found on this system"

ARCH="$(uname -m)"
case "$ARCH" in
	aarch64|arm64) ;;
	*) say "WARNING: unexpected architecture '$ARCH' (expected aarch64)" ;;
esac

say "Abertis Auto Switcher PRO installer"
say "system: $ARCH, Enigma2 found"

# ------------------------------------------------------------- download
fetch() {
	# $1 = url
	if command -v wget >/dev/null 2>&1; then
		wget -q -O "$TMP" "$1" 2>/dev/null
	else
		curl -fsSL -o "$TMP" "$1" 2>/dev/null
	fi
}

IPK="${PKG}_${RELEASE#v}_all.ipk"
URL="https://github.com/${REPO}/releases/download/${RELEASE}/${IPK}"

say "downloading ${IPK}"
if ! fetch "$URL" || [ ! -s "$TMP" ]; then
	# fall back to whatever the latest release provides
	say "pinned release not available, asking GitHub for the latest one"
	if command -v wget >/dev/null 2>&1; then
		JSON="$(wget -qO- "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null || true)"
	else
		JSON="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null || true)"
	fi
	URL="$(printf '%s' "$JSON" | sed -n 's/.*"browser_download_url"[ ]*:[ ]*"\([^"]*\)".*/\1/p' | head -n 1)"
	[ -n "$URL" ] || die "no release asset found for ${REPO}"
	fetch "$URL" || die "download failed: $URL"
	[ -s "$TMP" ] || die "downloaded file is empty"
	IPK="$(basename "$URL")"
fi

# keep the real file name, dpkg shows it in its output
PKG_DIR="/tmp/abertisautoswitcher-pkg.$$"
mkdir -p "$PKG_DIR"
PKG_FILE="${PKG_DIR}/${IPK}"
mv "$TMP" "$PKG_FILE"
TMP="$PKG_FILE"

# --------------------------------------------------------------- backup
mkdir -p "$BACKUP_DIR"
cp -a "$TMP" "$BACKUP_DIR/" 2>/dev/null || true
STAMP="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo manual)"
for f in /etc/astra/astra.conf /etc/astra/scripts/abertis; do
	if [ -f "$f" ]; then
		cp -a "$f" "$BACKUP_DIR/$(basename "$f").$STAMP" 2>/dev/null || true
	fi
done
say "backups kept in $BACKUP_DIR"

# -------------------------------------------------------------- install
say "installing $(basename "$TMP")"
dpkg -i "$TMP" || die "dpkg failed, see the output above"
# the plugin used to be shipped as "AbetrisAuto": make sure only one copy
# of the plugin stays on the system
rm -rf /usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto 2>/dev/null || true

INSTALLED="$(dpkg-query -W -f='${Package} ${Version}' "$PKG" 2>/dev/null || echo unknown)"
say "installed: $INSTALLED"
say "done - restart Enigma2 (or reboot the box) to load the plugin"
