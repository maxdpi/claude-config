#!/usr/bin/env bash
# Sync this repo's config directories into ~/.claude, replacing what's there.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HOME}/.claude"

mkdir -p "$DEST"

for dir in "$SRC"/*/; do
  name="$(basename "$dir")"
  echo "Syncing $name -> $DEST/$name"
  rsync -a --delete "$dir" "$DEST/$name/"
done

echo "Done."
