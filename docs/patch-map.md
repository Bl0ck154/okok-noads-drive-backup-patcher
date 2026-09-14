# Patch map (OKOK 3.1.66 / 173 only)

The exact `classes4.dex` hash is guarded before mutation. The patch targets the app's centralized `com.chipsea.code.ad.TopOnAdManager` and no-ops the observed initialization/load/show methods for splash, banner and rewarded ads, including R8 synthetic wrappers/lambda entry points.

The manifest patch changes the existing typed boolean `android:allowBackup` value in `<application>` from false to true. No Google OAuth credentials, API keys, or user secrets are embedded.

Because these are fixed offsets for one exact binary version, upgrading OKOK requires a fresh analysis and a new guarded patch map.
