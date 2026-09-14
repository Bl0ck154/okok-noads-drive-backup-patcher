#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
INPUT="${1:-}"
if [[ -z "$INPUT" || ! -f "$INPUT" ]]; then
  echo "Usage: $0 '/path/to/OKOK international [3.1.66].zip'" >&2
  exit 2
fi

OUT="$ROOT/out"
UNSIGNED="$OUT/unsigned"
ALIGNED="$OUT/aligned"
FINAL="$OUT/final"
CACHE="$ROOT/.cache"
PRIVATE="$ROOT/.private"
mkdir -p "$UNSIGNED" "$ALIGNED" "$FINAL" "$CACHE" "$PRIVATE"
rm -f "$UNSIGNED"/*.apk "$ALIGNED"/*.apk "$FINAL"/*.apk 2>/dev/null || true

python3 "$ROOT/patch_okok.py" "$INPUT" "$UNSIGNED"

if [[ -n "${ANDROID_BUILD_TOOLS_DIR:-}" ]]; then
  APKSIGNER="$ANDROID_BUILD_TOOLS_DIR/apksigner"
  ZIPALIGN="$ANDROID_BUILD_TOOLS_DIR/zipalign"
else
  TOOLS="$CACHE/android-build-tools-36.1"
  if [[ ! -x "$TOOLS/apksigner" || ! -x "$TOOLS/zipalign" ]]; then
    ZIP="$CACHE/build-tools_r36.1_linux.zip"
    [[ -f "$ZIP" ]] || curl -L --fail --retry 2 -o "$ZIP" \
      https://dl-ssl.google.com/android/repository/build-tools_r36.1_linux.zip
    rm -rf "$TOOLS.tmp" && mkdir -p "$TOOLS.tmp"
    unzip -q -o "$ZIP" -d "$TOOLS.tmp"
    APKSIGNER_SRC="$(find "$TOOLS.tmp" -type f -name apksigner | head -1)"
    ZIPALIGN_SRC="$(find "$TOOLS.tmp" -type f -name zipalign | head -1)"
    LIB_SRC="$(dirname "$APKSIGNER_SRC")/lib"
    mkdir -p "$TOOLS"
    cp "$APKSIGNER_SRC" "$ZIPALIGN_SRC" "$TOOLS/"
    cp -a "$LIB_SRC" "$TOOLS/lib"
    chmod +x "$TOOLS/apksigner" "$TOOLS/zipalign"
    rm -rf "$TOOLS.tmp"
  fi
  APKSIGNER="$TOOLS/apksigner"
  ZIPALIGN="$TOOLS/zipalign"
fi

KEYSTORE="${OKOK_KEYSTORE:-$PRIVATE/okok-mod.p12}"
PASS="${OKOK_KEYSTORE_PASS:-okokmod-local}"
ALIAS="${OKOK_KEY_ALIAS:-okokmod}"
if [[ ! -f "$KEYSTORE" ]]; then
  keytool -genkeypair -keystore "$KEYSTORE" -storetype PKCS12 \
    -storepass "$PASS" -keypass "$PASS" -alias "$ALIAS" \
    -keyalg RSA -keysize 3072 -validity 3650 \
    -dname 'CN=OKOK Mod Local Build,O=Personal Build,C=LT'
  echo "Generated private signing key: $KEYSTORE" >&2
  echo "Keep it private; future updates need the same key." >&2
fi

for src in "$UNSIGNED"/*-patched-unsigned.apk; do
  name="$(basename "$src" -patched-unsigned.apk)"
  aligned="$ALIGNED/$name.apk"
  signed="$FINAL/$name.apk"
  "$ZIPALIGN" -P 16 -f 4 "$src" "$aligned"
  "$APKSIGNER" sign \
    --ks "$KEYSTORE" --ks-key-alias "$ALIAS" \
    --ks-pass "pass:$PASS" --key-pass "pass:$PASS" \
    --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
    --out "$signed" "$aligned"
  "$APKSIGNER" verify --verbose --print-certs "$signed"
done

python3 - "$FINAL" "$OUT/OKOK-International-3.1.66-noads-drivebackup.apks" <<'PY'
import pathlib,sys,zipfile,hashlib
src=pathlib.Path(sys.argv[1]); dst=pathlib.Path(sys.argv[2])
apks=sorted(src.glob('*.apk'))
with zipfile.ZipFile(dst,'w',allowZip64=True) as z:
    for p in apks: z.write(p,p.name,compress_type=zipfile.ZIP_STORED)
    sums=''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in apks)
    z.writestr('SHA256SUMS.txt',sums)
print(dst)
PY
