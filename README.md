# OKOK International 3.1.66 — no-ads + cloud-backup patcher

Reproducible **binary patch/build tooling** for the exact OKOK International `3.1.66 (173)` split-APK bundle used to create this project.

This repository does **not** contain the proprietary OKOK APK, decompiled application source, assets, or a signing private key. You provide your own copy of the original bundle. The patcher refuses unknown `base.apk` / DEX / manifest hashes rather than patching a different version blindly.

## What the patch does

1. **Disables app-driven ads/popups.** The known `com.chipsea.code.ad.TopOnAdManager` initialization/loading/showing entry points (splash, banner and rewarded paths) are replaced with DEX `return-void` bodies. Adapter/SDK bytecode can remain physically present, but the app-level mediation paths are inactive.
2. **Enables Android Auto Backup** by changing `android:allowBackup` from `false` to `true`. On supported Android devices this lets eligible app files, SharedPreferences and SQLite databases participate in the user's private Android/Google Drive cloud backup, subject to Android backup policy and quota. This is backup/restore, **not** a user-visible Drive file or real-time two-way Drive synchronization.
3. Recomputes the DEX SHA-1 + Adler32 header values, strips stale signatures, preserves split APKs, and re-aligns stored files/native libraries.
4. `build.sh` downloads official Android Build Tools 36.1 when needed, runs `zipalign`, then signs/verifies all split APKs with `apksigner` (v1/v2/v3).

## Supported input

Expected bundle entries:

- `base.apk`
- `split_config.arm64_v8a.apk`
- `split_config.xxxhdpi.apk`

Exact `base.apk` SHA-256:

`638c2f8d7a5ceb44cb622545d795921a0a929488b7ecf01aa59123c2373ab353`

Package: `com.chipsea.btcontrol.en`

## Build

Requirements: Python 3, Java `keytool`, `curl`, `unzip`. Android Build Tools are fetched automatically unless `ANDROID_BUILD_TOOLS_DIR` is set.

```bash
export OKOK_KEYSTORE_PASS='choose-a-private-password'
./build.sh '/path/to/OKOK international [3.1.66].zip'
```

Output:

`out/OKOK-International-3.1.66-noads-drivebackup.apks`

The first build creates `.private/okok-mod.p12`. **Keep that file private and backed up.** Android updates require the same signing key.

## Install

The developer's original private signing key is unavailable, so a modified build cannot update the Play Store/original installation in-place. Preserve/sync any data you need from the original app, uninstall it, then install all three generated split APKs together (for example with a split-APK installer or `adb install-multiple`).

## Google Drive note

Android Auto Backup stores its dataset in the user's private backup storage; it is managed by Android rather than exposed as a normal file in My Drive. Android currently documents a 25 MB per-app Auto Backup limit. If explicit on-demand, two-way Google Drive synchronization is needed, that should be implemented as a separate feature with a proper Google OAuth client rather than embedding credentials into a binary patch.

## Legal / provenance

This repo contains only original patch/build tooling and patch metadata. It is not affiliated with Shenzhen Careyou Health Science and Technology Co / OKOK Technology. Use it with software you are authorized to modify.
