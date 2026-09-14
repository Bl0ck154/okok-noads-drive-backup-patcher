# OKOK Mod 3.1.66 — no ads + side-by-side universal APK

Reproducible **binary patch/build tooling** for the analyzed OKOK International `3.1.66 (173)` split-APK bundle.

This repository does **not** contain the proprietary original OKOK APK/XAPK, decompiled application source, assets, or a private signing key. Supply your own copy of the supported bundle. The patcher checks the analyzed `base.apk`, DEX and manifest hashes before modifying anything.

## What the patch does

1. **Disables app-driven ads/popups.** The known `com.chipsea.code.ad.TopOnAdManager` initialization/loading/showing entry points (splash, banner and rewarded paths) are replaced with DEX `return-void` bodies.
2. **Makes the mod a separate app.** The package is renamed from `com.chipsea.btcontrol.en` to `com.chipsea.btcontrol.na`, including matching binary package/provider references, so it can be installed alongside the original OKOK app. The launcher label is changed to `OKOK·Modded Build!`.
3. **Enables Android Auto Backup** by changing `android:allowBackup` from `false` to `true`. Eligible app files, SharedPreferences and SQLite databases may participate in Android's private cloud backup/restore flow, subject to Android policy and quota.
4. Recomputes DEX SHA-1/Adler32 values and strips stale APK signatures.
5. Merges `base.apk` + ARM64 + xxxhdpi resource splits into **one universal APK**, applies 16 KiB-compatible native-library alignment and signs/verifies it with Android `apksigner`.

## Important Google Drive distinction

The current patch **does not add an in-app Google Drive screen, Google OAuth login button, visible My Drive file, or real-time/two-way Drive synchronization**. `allowBackup=true` only enables Android's system-managed Auto Backup path. A proper user-visible Drive sync feature is separate work and should use a real Google OAuth client and UI integrated into the app.

## Supported input

Expected bundle entries:

- `base.apk`
- `split_config.arm64_v8a.apk`
- `split_config.xxxhdpi.apk`

Exact analyzed `base.apk` SHA-256:

`638c2f8d7a5ceb44cb622545d795921a0a929488b7ecf01aa59123c2373ab353`

Original package: `com.chipsea.btcontrol.en`  
Mod package: `com.chipsea.btcontrol.na`

## Local build

Requirements: Python 3, Java/keytool, curl and unzip. APKEditor 1.4.9 and Android Build Tools 36.1 are downloaded automatically and pinned/verified by the scripts.

```bash
export OKOK_KEYSTORE_PASS='your-private-password'
./build.sh '/path/to/OKOK international [3.1.66].zip'
```

Output:

`out/OKOK-Mod-3.1.66-universal.apk`

The first local build can create `.private/okok-mod.p12`. Keep it private and backed up: Android updates to an already-installed mod build must be signed with the same key.

## GitHub Actions build

The workflow **Build OKOK Mod** is committed in `.github/workflows/build.yml`.

- Every push/PR validates the Python and shell build scripts.
- **Run workflow** accepts a direct URL to your own original 3.1.66 bundle and an optional source SHA-256.
- The manual workflow builds one signed `OKOK-Mod-3.1.66-universal.apk` and uploads it as a GitHub Actions artifact.
- `publish_release=true` additionally publishes that APK and its SHA-256 file as a GitHub Release.

For stable update-compatible signing, configure these repository Actions secrets (never commit the private key):

- `OKOK_KEYSTORE_B64` — base64 of the PKCS#12 signing keystore
- `OKOK_KEYSTORE_PASS` — keystore/key password
- `OKOK_KEY_ALIAS` — signing alias

The original proprietary bundle is intentionally not stored in this public repository.

## Install

Install `OKOK-Mod-3.1.66-universal.apk` normally. Because its package is `com.chipsea.btcontrol.na`, it is a separate application and does **not** replace `com.chipsea.btcontrol.en`.

The two apps have separate Android sandboxes/databases. Existing private data from the original app is therefore not automatically copied into the mod simply by installing it side-by-side.

## Legal / provenance

This repo contains original patch/build tooling and patch metadata only. It is not affiliated with Shenzhen Careyou Health Science and Technology Co / OKOK Technology. Use it with software you are authorized to modify.
