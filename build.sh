#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
INPUT="${1:-}"
if [[ -z "$INPUT" || ! -f "$INPUT" ]]; then
  echo "Usage: $0 '/path/to/OKOK international [3.1.66].zip'" >&2
  exit 2
fi

OUT="$ROOT/out"
PATCHED="$OUT/patched-splits"
MERGED="$OUT/OKOK-Mod-3.1.66-universal-unsigned.apk"
ALIGNED="$OUT/OKOK-Mod-3.1.66-universal-aligned.apk"
FINAL="$OUT/OKOK-BlankCore-3.1.66-full.apk"
CORE_DIR="$OUT/patched-base-arm64"
MERGED_CORE="$OUT/OKOK-BlankCore-3.1.66-base-arm64-unsigned.apk"
ALIGNED_CORE="$OUT/OKOK-BlankCore-3.1.66-base-arm64-aligned.apk"
FINAL_CORE="$OUT/OKOK-BlankCore-3.1.66-base-arm64.apk"
CACHE="$ROOT/.cache"
PRIVATE="$ROOT/.private"
mkdir -p "$PATCHED" "$CORE_DIR" "$CACHE" "$PRIVATE"
rm -rf "$PATCHED"/* "$CORE_DIR"/*
rm -f "$MERGED" "$ALIGNED" "$FINAL" "$MERGED_CORE" "$ALIGNED_CORE" "$FINAL_CORE" "$OUT/SHA256SUMS.txt"

python3 "$ROOT/patch_okok.py" "$INPUT" "$PATCHED"

APKEDITOR="$CACHE/APKEditor-1.4.9.jar"
APKEDITOR_SHA256="a9cd40df818845456be6d696de6110c89edf4b0a0580cb83438ed6b25a366e67"
if [[ ! -f "$APKEDITOR" ]]; then
  curl -L --fail --retry 3 -o "$APKEDITOR" \
    https://github.com/REAndroid/APKEditor/releases/download/V1.4.9/APKEditor-1.4.9.jar
fi
echo "$APKEDITOR_SHA256  $APKEDITOR" | sha256sum -c -

if [[ -n "${ANDROID_BUILD_TOOLS_DIR:-}" ]]; then
  APKSIGNER="$ANDROID_BUILD_TOOLS_DIR/apksigner"
  ZIPALIGN="$ANDROID_BUILD_TOOLS_DIR/zipalign"
else
  TOOLS="$CACHE/android-build-tools-36.1"
  if [[ ! -x "$TOOLS/apksigner" || ! -x "$TOOLS/zipalign" || ! -f "$TOOLS/lib64/libc++.so" ]]; then
    ZIP="$CACHE/build-tools_r36.1_linux.zip"
    [[ -f "$ZIP" ]] || curl -L --fail --retry 3 -o "$ZIP" \
      https://dl-ssl.google.com/android/repository/build-tools_r36.1_linux.zip
    rm -rf "$TOOLS.tmp" && mkdir -p "$TOOLS.tmp"
    unzip -q -o "$ZIP" -d "$TOOLS.tmp"
    APKSIGNER_SRC="$(find "$TOOLS.tmp" -type f -name apksigner | head -1)"
    ZIPALIGN_SRC="$(find "$TOOLS.tmp" -type f -name zipalign | head -1)"
    LIB_SRC="$(dirname "$APKSIGNER_SRC")/lib"
    LIB64_SRC="$(dirname "$APKSIGNER_SRC")/lib64"
    mkdir -p "$TOOLS"
    cp "$APKSIGNER_SRC" "$ZIPALIGN_SRC" "$TOOLS/"
    cp -a "$LIB_SRC" "$TOOLS/lib"
    cp -a "$LIB64_SRC" "$TOOLS/lib64"
    chmod +x "$TOOLS/apksigner" "$TOOLS/zipalign"
    rm -rf "$TOOLS.tmp"
  fi
  APKSIGNER="$TOOLS/apksigner"
  ZIPALIGN="$TOOLS/zipalign"
fi

java -Xmx4g -jar "$APKEDITOR" m -i "$PATCHED" -o "$MERGED" -f -clean-meta

# A/B diagnostic: merge only base + arm64 native split, intentionally omitting
# the density split/resources. This isolates resource-table merge failures.
cp "$PATCHED/base.apk" "$CORE_DIR/base.apk"
cp "$PATCHED/split_config.arm64_v8a.apk" "$CORE_DIR/split_config.arm64_v8a.apk"
java -Xmx4g -jar "$APKEDITOR" m -i "$CORE_DIR" -o "$MERGED_CORE" -f -clean-meta

python3 - "$MERGED" "$MERGED_CORE" <<'PY'
import sys, zipfile
old=b'com.chipsea.btcontrol.en'
new=b'com.chipsea.btcontrol.na'
old16='com.chipsea.btcontrol.en'.encode('utf-16le')
new16='com.chipsea.btcontrol.na'.encode('utf-16le')
for apk in sys.argv[1:]:
    old_hits=[]; new_hits=0
    with zipfile.ZipFile(apk) as z:
        bad=z.testzip()
        if bad:
            raise SystemExit(f'{apk}: bad ZIP member: {bad}')
        for info in z.infolist():
            if info.is_dir():
                continue
            data=z.read(info.filename)
            if old in data or old16 in data:
                old_hits.append(info.filename)
            new_hits += data.count(new) + data.count(new16)
    if old_hits:
        raise SystemExit(f'{apk}: old package remains: {old_hits[:20]}')
    if new_hits == 0:
        raise SystemExit(f'{apk}: new package not found')
    print(f'{apk}: package verification OK; new-package hits={new_hits}')
PY

"$ZIPALIGN" -P 16 -f 4 "$MERGED" "$ALIGNED"
"$ZIPALIGN" -P 16 -f 4 "$MERGED_CORE" "$ALIGNED_CORE"
"$ZIPALIGN" -P 16 -c 4 "$ALIGNED"
"$ZIPALIGN" -P 16 -c 4 "$ALIGNED_CORE"

KEYSTORE="${OKOK_KEYSTORE:-$PRIVATE/okok-mod.p12}"
PASS="${OKOK_KEYSTORE_PASS:-okokmod-local}"
ALIAS="${OKOK_KEY_ALIAS:-okokmod}"
if [[ ! -f "$KEYSTORE" ]]; then
  if [[ "${GITHUB_ACTIONS:-false}" == "true" ]]; then
    echo "GitHub build requires a signing keystore supplied by the workflow." >&2
    exit 3
  fi
  keytool -genkeypair -keystore "$KEYSTORE" -storetype PKCS12 \
    -storepass "$PASS" -keypass "$PASS" -alias "$ALIAS" \
    -keyalg RSA -keysize 3072 -validity 3650 \
    -dname 'CN=OKOK Mod Local Build,O=Personal Build,C=LT'
  echo "Generated private signing key: $KEYSTORE" >&2
  echo "Keep it private; future updates need the same key." >&2
fi

"$APKSIGNER" sign \
  --ks "$KEYSTORE" --ks-key-alias "$ALIAS" \
  --ks-pass "pass:$PASS" --key-pass "pass:$PASS" \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
  --out "$FINAL" "$ALIGNED"

"$APKSIGNER" sign \
  --ks "$KEYSTORE" --ks-key-alias "$ALIAS" \
  --ks-pass "pass:$PASS" --key-pass "pass:$PASS" \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
  --out "$FINAL_CORE" "$ALIGNED_CORE"

"$APKSIGNER" verify --verbose --print-certs "$FINAL"
"$APKSIGNER" verify --verbose --print-certs "$FINAL_CORE"
sha256sum "$FINAL" "$FINAL_CORE" | tee "$OUT/SHA256SUMS.txt"

echo
echo "Built: $FINAL"
echo "Built: $FINAL_CORE"
echo "Package: com.chipsea.btcontrol.na"
echo "Installable alongside the original com.chipsea.btcontrol.en app."
