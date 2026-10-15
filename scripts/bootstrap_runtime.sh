#!/bin/sh
# Agent-only inert extraction when no Python is available. Native approval/source verification comes first.
set -eu
umask 077
[ "$#" = 4 ] && [ "$1" = '--approved' ] || { echo RUNTIME_PERMISSION_REQUIRED; exit 1; }
archive=$2
digest=$3
target=$4
case "$digest" in *[!0-9a-f]*|'') echo RUNTIME_HASH_INVALID; exit 1;; esac
[ "${#digest}" = 64 ] && [ -f "$archive" ] && [ ! -L "$archive" ] && [ ! -e "$target" ] || exit 1
parent=$(cd -- "$(dirname -- "$target")" && pwd -P)
target="$parent/$(basename -- "$target")"
package=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
case "$target/" in "$package/"*) echo RUNTIME_PATH_BLOCKED; exit 1;; esac
case "$package/" in "$target/"*) echo RUNTIME_PATH_BLOCKED; exit 1;; esac
stage=$(mktemp -d "$parent/.report-kit-core-XXXXXXXX")
trap 'rm -f -- "$stage/core.tar" "$stage/names" "$stage/types"; rmdir -- "$stage"' EXIT HUP INT TERM
cp -- "$archive" "$stage/core.tar"
actual=$(/usr/bin/shasum -a 256 "$stage/core.tar")
[ "${actual%% *}" = "$digest" ] || { echo RUNTIME_CHECKSUM_FAILED; exit 1; }
/usr/bin/tar -tf "$stage/core.tar" > "$stage/names"
/usr/bin/tar -tvf "$stage/core.tar" > "$stage/types"
if LC_ALL=C /usr/bin/grep -v '^-' "$stage/types" >/dev/null; then echo RUNTIME_LINK_BLOCKED; exit 1; fi
if LC_ALL=C /usr/bin/grep -E '(^/|(^|/)\.\.(/|$)|\\|[[:cntrl:]])' "$stage/names" >/dev/null; then echo RUNTIME_PATH_BLOCKED; exit 1; fi
if /usr/bin/grep -v -E '^(python/|site/|manifests/core\.json$|runtime-receipt\.json$)' "$stage/names" >/dev/null; then echo RUNTIME_LAYER_BLOCKED; exit 1; fi
mkdir -m 700 -- "$target"
/usr/bin/tar -xf "$stage/core.tar" -C "$target" --no-same-owner --no-same-permissions
# Keep it inert. The agent must verify inventory and request execution permission before running the interpreter.
/usr/bin/find "$target" -type f -exec /bin/chmod 600 {} +
printf '%s\n' 'RUNTIME_CORE_EXTRACTED_NOT_ACTIVATED'
