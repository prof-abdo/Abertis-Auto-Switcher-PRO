#!/bin/sh
#
# Abertis Auto Switcher PRO - installer
#
#   wget https://raw.githubusercontent.com/prof-abdo/Abertis-Auto-Switcher-PRO/main/installer.sh -O - | /bin/sh
#
# Downloads the latest release of the plugin and installs it.
#
# Works on both package systems:
#   * DreamOS / Debian images   -> dpkg  + the .deb package
#   * OpenATV / OpenPLi images  -> opkg  + the .ipk package
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
RELEASE="v1.9.13"
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
[ -d /usr/lib/enigma2/python/Plugins/Extensions ] || die "Enigma2 was not found on this system"

# DreamOS / Debian images use dpkg with the .deb package, opkg images
# (OpenATV, OpenPLi, ...) use opkg with the .ipk package.  On a Debian
# system both formats install fine (same container), the .deb is preferred.
PKG_KIND=""
PKG_EXTS=""
if command -v dpkg >/dev/null 2>&1; then
    PKG_KIND="deb"
    PKG_EXTS="deb ipk"
elif command -v opkg >/dev/null 2>&1; then
    PKG_KIND="ipk"
    PKG_EXTS="ipk"
else
    die "neither dpkg nor opkg found - unknown package system"
fi

ARCH="$(uname -m)"
case "$ARCH" in
    aarch64|arm64|arm|mips|armv7*|armel|armhf|mipsel) ;;
    *) say "WARNING: unexpected architecture '$ARCH' (supported: aarch64/arm/mips)" ;;
esac

say "Abertis Auto Switcher PRO installer"
say "system: $ARCH, package system: $PKG_KIND"

# ------------------------------------------------------------- download
fetch() {
    # $1 = url
    if command -v wget >/dev/null 2>&1; then
        wget -q -O "$TMP" "$1" 2>/dev/null
    else
        curl -fsSL -o "$TMP" "$1" 2>/dev/null
    fi
}

VER="${RELEASE#v}"
NAME=""
PKG_URL=""
for EXT in $PKG_EXTS; do
    NAME="${PKG}_${VER}_all.${EXT}"
    PKG_URL="https://github.com/${REPO}/releases/download/${RELEASE}/${NAME}"
    say "downloading ${NAME}"
    if fetch "$PKG_URL" && [ -s "$TMP" ]; then
        break
    fi
    say "${NAME} is not part of ${RELEASE}, trying the next format"
    NAME=""
    PKG_URL=""
done

if [ -z "$NAME" ]; then
    # pinned release has no matching asset: ask GitHub for the latest one
    say "pinned assets not available, asking GitHub for the latest release"
    if command -v wget >/dev/null 2>&1; then
        JSON="$(wget -qO- "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null || true)"
    else
        JSON="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null || true)"
    fi
    URLS="$(printf '%s' "$JSON" | sed -n 's/.*"browser_download_url"[ ]*:[ ]*"\([^"]*\)".*/\1/p')"
    for EXT in $PKG_EXTS; do
        PKG_URL="$(printf '%s\n' "$URLS" | grep "\.${EXT}\$" | head -n 1)"
        if [ -n "$PKG_URL" ]; then
            fetch "$PKG_URL" && [ -s "$TMP" ] && NAME="$(basename "$PKG_URL")" && break
            die "download failed: $PKG_URL"
        fi
    done
    [ -n "$NAME" ] || die "no ${PKG_EXTS} asset found for ${REPO}"
fi

# keep the real file name, the package manager shows it in its output
PKG_DIR="/tmp/abertisautoswitcher-pkg.$$"
mkdir -p "$PKG_DIR"
PKG_FILE="${PKG_DIR}/${NAME}"
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
case "$PKG_KIND" in
    deb)
        dpkg -i "$TMP" || die "dpkg failed, see the output above"
        INSTALLED="$(dpkg-query -W -f='${Package} ${Version}' "$PKG" 2>/dev/null || echo unknown)"
        ;;
    *)
        opkg install --force-reinstall --force-overwrite "$TMP" || die "opkg failed, see the output above"
        INSTALLED="$(opkg list-installed 2>/dev/null | grep "^${PKG} " | head -n 1 || echo unknown)"
        ;;
esac

# the plugin used to be shipped as "AbetrisAuto": make sure only one copy
# of the plugin stays on the system
rm -rf /usr/lib/enigma2/python/Plugins/Extensions/AbetrisAuto 2>/dev/null || true

say "installed: $INSTALLED"
say "done - restart Enigma2 (or reboot the box) to load the plugin"
