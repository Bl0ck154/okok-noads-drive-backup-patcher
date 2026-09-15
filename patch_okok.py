#!/usr/bin/env python3
import argparse
import base64
import hashlib
import os
import shutil
import struct
import tempfile
import zipfile
import zlib

BASE_SHA = '638c2f8d7a5ceb44cb622545d795921a0a929488b7ecf01aa59123c2373ab353'
DEX_SHA = '9dabbbb48656730c10e4269655862008a2daca880d323d94e425c7d428520700'
MANIFEST_SHA = '8ecc89cd9088ec4d98073c5c67022842535e94d74cbd2b11364961a8d6c395f0'

OLD_PACKAGE = 'com.chipsea.btcontrol.en'
NEW_PACKAGE = 'com.chipsea.btcontrol.na'
OLD_LABEL = 'OKOK·International'
# Same UTF-8 byte length and same UTF-16 code-unit length as OLD_LABEL, so it
# can be replaced safely inside Android binary string pools without rebuilding
# resources.arsc.
NEW_LABEL = 'OKOK·Modded Build!'

# Lite build placeholders: keep resource IDs/files valid while dropping heavy
# decorative/media payload. The MP3 is ~0.15 s of silence; the PNG is a 1x1
# transparent pixel.
SILENT_MP3 = base64.b64decode(
    'SUQzBAAAAAAAIlRTU0UAAAAOAAADTGF2ZjYxLjcuMTAzAAAAAAAAAAAAAAD/4zjAAAAAAAAAAAAASW5mbwAAAA8AAAAFAAACQACA'
    'gICAgICAgICAgICAgICAgICAoKCgoKCgoKCgoKCgoKCgoKCgoKDAwMDAwMDAwMDAwMDAwMDAwMDAwODg4ODg4ODg4ODg4ODg4ODg'
    '4ODg//////////////////////////8AAAAATGF2YzYxLjE5AAAAAAAAAAAAAAAAJARQAAAAAAAAAkC9954TAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/4xjEAAAAA0gAAAAATEFNRTMuMTAwVVVVVVVVVVVVVVVVVVVVVVVV'
    'VVVVVVVVVVVVVVVVVUxBTUUzLjEwMFVVVVVVVVVVVVX/4xjEOwAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV'
    'VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/4xjEdgAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV'
    'VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/4xjEsQAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV'
    'VVVVVVVVVVVVVVVVVVVVVVVVVVVVVVX/4xjExAAAA0gAAAAAVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV'
    'VVVVVVVVVVVVVVVVVVVVVVVVVVU='
)
TRANSPARENT_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+Z9erAAAAAElFTkSuQmCC'
)
LITE_IMAGE_THRESHOLD = 100_000

# code_item offsets in classes4.dex for com.chipsea.code.ad.TopOnAdManager methods.
AD_CODE_ITEMS = {
    0x23B380: 4,   # r8 lambda
    0x23B398: 4,   # nest confirmInit
    0x23B3B0: 4,   # nest showSplashAd
    0x23B3C8: 4,   # nest toLoadAd
    0x23B438: 16,  # confirmInit
    0x23B468: 27,  # initAd
    0x23B4B0: 54,  # lambda$confirmInit$0
    0x23B52C: 40,  # loadBannerAd
    0x23B58C: 30,  # loadRewardAd
    0x23B5D8: 78,  # loadSplashAd
    0x23B71C: 100, # showBannerAd
    0x23B7F4: 49,  # showRewardAd
    0x23B868: 31,  # showSplashAd
    0x23B8B8: 56,  # toLoadAd
}

# Advertising SDK ContentProviders run before Application.onCreate(). The
# original no-ads patch disabled the app-level TopOn manager, but these
# providers could still initialize third-party ad SDKs during process startup.
# For this exact hash-guarded OKOK 3.1.66 build, their onCreate() methods are
# replaced with `return true` while keeping each code item the same size.
AD_PROVIDER_CODE_ITEMS = {
    'classes5.dex': {
        0x2185D8: 13,  # Facebook AudienceNetworkContentProvider.onCreate
        0x365468: 2,   # Google MobileAdsInitProvider.onCreate
        0x57CB5C: 28,  # MBridge MBComponentLifecycleProvider.onCreate
    },
    'classes6.dex': {
        0x56E6F8: 40,  # SmartDigi SDMInitializationProvider.onCreate
    },
    'classes7.dex': {
        0x3336FC: 28,  # SecMtp ATInitializationProvider.onCreate
    },
    'classes8.dex': {
        0x222534: 15,  # TraminiContentProvider.onCreate
        0x284FBC: 13,  # VungleProvider.onCreate
    },
    'classes9.dex': {
        0x185AEC: 18,  # Yandex MobileAdsInitializeProvider.onCreate
    },
    'classes10.dex': {
        0x325A30: 24,  # BigoAdsProvider.onCreate
    },
}

# Startup simplification in classes4.dex.
SHELL_ONCREATE = (0x2E1AA8, 189)
SHELL_SUPER_ONCREATE_METHOD_IDX = 1559
APPENTRY_WELCOME_METHOD_IDX = 1555
ACTIVITY_FINISH_METHOD_IDX = 28
UMENG_CODE_ITEMS = {
    0x29644C: 4,   # onPageEnd
    0x296464: 4,   # onPageStart
    0x29647C: 4,   # onPause
    0x296494: 4,   # onResume
    0x2964AC: 27,  # umconfigInit
    0x2964F4: 8,   # umconfigPreinit
}
# AppMetrica preload provider (analytics, not app core).
AD_PROVIDER_CODE_ITEMS.setdefault('classes9.dex', {})[0x3B53F8] = 64

ALLOW_BACKUP_DATA_OFF = 0xDD14


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fixed_pairs():
    pairs = []
    for old, new in ((OLD_PACKAGE, NEW_PACKAGE), (OLD_LABEL, NEW_LABEL)):
        old8, new8 = old.encode('utf-8'), new.encode('utf-8')
        old16, new16 = old.encode('utf-16le'), new.encode('utf-16le')
        if len(old8) != len(new8) or len(old16) != len(new16):
            raise RuntimeError(f'fixed-size replacement length mismatch: {old!r} -> {new!r}')
        pairs.extend(((old8, new8), (old16, new16)))
    return pairs


FIXED_PAIRS = _fixed_pairs()
OLD_PACKAGE_BYTES = OLD_PACKAGE.encode('utf-8')
OLD_PACKAGE_UTF16 = OLD_PACKAGE.encode('utf-16le')


def replace_fixed_strings(data: bytes):
    package_hits = 0
    label_hits = 0
    out = data
    for index, (old, new) in enumerate(FIXED_PAIRS):
        hits = out.count(old)
        if hits:
            out = out.replace(old, new)
            if index < 2:
                package_hits += hits
            else:
                label_hits += hits
    return out, package_hits, label_hits


def refresh_dex(data: bytes) -> bytes:
    if not data.startswith(b'dex\n'):
        return data
    x = bytearray(data)
    x[12:32] = hashlib.sha1(x[32:]).digest()
    struct.pack_into('<I', x, 8, zlib.adler32(x[12:]) & 0xFFFFFFFF)
    return bytes(x)


def patch_ad_dex(data: bytes) -> bytes:
    if sha(data) != DEX_SHA:
        raise ValueError('classes4.dex hash mismatch; this patcher supports OKOK 3.1.66 only')
    x = bytearray(data)

    # Disable the app-level ad manager.
    for off, insns_size in AD_CODE_ITEMS.items():
        actual = struct.unpack_from('<I', x, off + 12)[0]
        if actual != insns_size:
            raise ValueError(f'code_item size mismatch at {off:#x}: {actual} != {insns_size}')
        struct.pack_into('<H', x, off + 16, 0x000E)  # return-void
        x[off + 18:off + 16 + 2 * insns_size] = b'\0' * (2 * (insns_size - 1))

    # Disable Umeng analytics hooks, including the pre-init called directly
    # from CSApplication.onCreate().
    for off, insns_size in UMENG_CODE_ITEMS.items():
        actual = struct.unpack_from('<I', x, off + 12)[0]
        if actual != insns_size:
            raise ValueError(f'Umeng code_item size mismatch at {off:#x}: {actual} != {insns_size}')
        struct.pack_into('<H', x, off + 16, 0x000E)
        x[off + 18:off + 16 + 2 * insns_size] = b'\0' * (2 * (insns_size - 1))

    # Bypass com.chipsea.shell.MainActivity (privacy/VIP/app-open-ad wrapper).
    # Keep the normal Activity lifecycle contract: call direct superclass
    # onCreate(Bundle), launch AppEntry.welcome() -> InitActivity, finish shell.
    off, insns_size = SHELL_ONCREATE
    actual = struct.unpack_from('<I', x, off + 12)[0]
    if actual != insns_size:
        raise ValueError(f'shell onCreate size mismatch: {actual} != {insns_size}')
    body = [
        0x0275, SHELL_SUPER_ONCREATE_METHOD_IDX, 0x0001,  # invoke-super/range {v1..v2}
        0x0177, APPENTRY_WELCOME_METHOD_IDX, 0x0001,     # invoke-static/range {v1}
        0x0174, ACTIVITY_FINISH_METHOD_IDX, 0x0001,      # invoke-virtual/range {v1}
        0x000E,                                           # return-void
    ]
    for i, code_unit in enumerate(body):
        struct.pack_into('<H', x, off + 16 + 2 * i, code_unit)
    x[off + 16 + 2 * len(body):off + 16 + 2 * insns_size] = b'\0' * (2 * (insns_size - len(body)))
    return bytes(x)


def patch_ad_provider_dex(name: str, data: bytes) -> bytes:
    items = AD_PROVIDER_CODE_ITEMS.get(name)
    if not items:
        return data
    x = bytearray(data)
    for off, insns_size in items.items():
        actual = struct.unpack_from('<I', x, off + 12)[0]
        if actual != insns_size:
            raise ValueError(
                f'ad provider code_item size mismatch in {name} at {off:#x}: '
                f'{actual} != {insns_size}'
            )
        registers_size = struct.unpack_from('<H', x, off)[0]
        if registers_size < 1:
            raise ValueError(f'ad provider {name} at {off:#x} has no v0 register')
        # const/4 v0, #1 ; return v0 ; nop ...
        struct.pack_into('<H', x, off + 16, 0x1012)
        struct.pack_into('<H', x, off + 18, 0x000F)
        if insns_size > 2:
            x[off + 20:off + 16 + 2 * insns_size] = b'\0' * (2 * (insns_size - 2))
    return bytes(x)


def patch_manifest(data: bytes) -> bytes:
    if sha(data) != MANIFEST_SHA:
        raise ValueError('AndroidManifest.xml hash mismatch; this patcher supports OKOK 3.1.66 only')
    x = bytearray(data)
    # android:allowBackup typed boolean data in <application>: false (0) -> true (-1)
    if struct.unpack_from('<I', x, ALLOW_BACKUP_DATA_OFF)[0] != 0:
        raise ValueError('unexpected allowBackup value')
    struct.pack_into('<I', x, ALLOW_BACKUP_DATA_OFF, 0xFFFFFFFF)
    return bytes(x)


def is_old_sig(name: str) -> bool:
    upper = name.upper()
    if not upper.startswith('META-INF/'):
        return False
    base = upper.rsplit('/', 1)[-1]
    return base == 'MANIFEST.MF' or base.endswith(('.SF', '.RSA', '.DSA', '.EC'))


def alignment_extra(existing: bytes, data_offset_without_new_extra: int, align: int) -> bytes:
    if align <= 1:
        return existing
    pad = (-data_offset_without_new_extra) % align
    if pad and pad < 4:
        pad += align
    if not pad:
        return existing
    # Unknown ZIP extra-field ID used only as deterministic padding.
    return existing + struct.pack('<HH', 0xD935, pad - 4) + b'\0' * (pad - 4)


def clone_info(zi: zipfile.ZipInfo) -> zipfile.ZipInfo:
    out = zipfile.ZipInfo(zi.filename, date_time=zi.date_time)
    for attr in (
        'compress_type', 'comment', 'create_system', 'create_version',
        'extract_version', 'flag_bits', 'internal_attr', 'external_attr', 'volume'
    ):
        if hasattr(zi, attr):
            setattr(out, attr, getattr(zi, attr))
    out.extra = zi.extra or b''
    return out


def mutate_entry(name: str, data: bytes, is_base: bool):
    original = data
    if is_base and name == 'classes4.dex':
        data = patch_ad_dex(data)
    if is_base and name in AD_PROVIDER_CODE_ITEMS:
        data = patch_ad_provider_dex(name, data)
    if is_base and name == 'AndroidManifest.xml':
        data = patch_manifest(data)

    # Lite payload: preserve resource names/IDs but replace heavyweight media.
    if is_base and name.startswith('res/raw/music') and name.endswith('.mp3'):
        data = SILENT_MP3
    if (
        is_base
        and name.startswith(('res/mipmap', 'res/drawable'))
        and name.endswith('.png')
        and not name.endswith('.9.png')
        and len(data) >= LITE_IMAGE_THRESHOLD
    ):
        data = TRANSPARENT_PNG

    data, package_hits, label_hits = replace_fixed_strings(data)
    if name.endswith('.dex') and data != original:
        data = refresh_dex(data)
    return data, package_hits, label_hits


def repack(src: str, dst: str, is_base: bool = False):
    package_hits = 0
    label_hits = 0
    with zipfile.ZipFile(src, 'r') as zin, zipfile.ZipFile(dst, 'w', allowZip64=True) as zout:
        for zi in zin.infolist():
            if is_old_sig(zi.filename):
                continue
            if is_base and zi.filename == 'assets/audience_network/classes2.dex':
                continue
            data = zin.read(zi.filename)
            data, p_hits, l_hits = mutate_entry(zi.filename, data, is_base)
            package_hits += p_hits
            label_hits += l_hits

            nz = clone_info(zi)
            # Re-align uncompressed entries after repacking. Android 15+ devices
            # may require 16 KiB native library alignment.
            if zi.compress_type == zipfile.ZIP_STORED:
                align = 16384 if zi.filename.endswith('.so') else 4
                name_bytes = zi.filename.encode('utf-8')
                base = zout.fp.tell() + 30 + len(name_bytes) + len(nz.extra)
                nz.extra = alignment_extra(nz.extra, base, align)
            zout.writestr(nz, data, compress_type=zi.compress_type)

    return package_hits, label_hits


def verify_no_old_package(apk_path: str):
    leftovers = []
    with zipfile.ZipFile(apk_path, 'r') as z:
        for zi in z.infolist():
            if zi.is_dir():
                continue
            data = z.read(zi.filename)
            if OLD_PACKAGE_BYTES in data or OLD_PACKAGE_UTF16 in data:
                leftovers.append(zi.filename)
    if leftovers:
        raise ValueError(f'old package name remains in {apk_path}: {leftovers[:20]}')


def _pick_bundle_entry(names, candidates, label):
    for candidate in candidates:
        if candidate in names:
            return candidate
    raise ValueError(f'could not find {label}; tried: {candidates}')


def build(input_zip: str, outdir: str):
    os.makedirs(outdir, exist_ok=True)
    with zipfile.ZipFile(input_zip) as bundle:
        names = set(bundle.namelist())

        # Support both the user's split bundle naming and common XAPK naming
        # used by APKPure mirrors. The base APK hash guard below is authoritative.
        base_entry = _pick_bundle_entry(
            names,
            ('base.apk', f'{OLD_PACKAGE}.apk'),
            'base APK',
        )
        arm64_entry = _pick_bundle_entry(
            names,
            ('split_config.arm64_v8a.apk', 'config.arm64_v8a.apk'),
            'arm64-v8a split',
        )
        density_entry = _pick_bundle_entry(
            names,
            (
                'split_config.xxxhdpi.apk', 'config.xxxhdpi.apk',
                'split_config.xxhdpi.apk', 'config.xxhdpi.apk',
                'split_config.xhdpi.apk', 'config.xhdpi.apk',
                'split_config.hdpi.apk', 'config.hdpi.apk',
                'split_config.mdpi.apk', 'config.mdpi.apk',
            ),
            'density split',
        )

        selected = (
            (base_entry, 'base.apk', True),
            (arm64_entry, 'split_config.arm64_v8a.apk', False),
            (density_entry, 'split_config.density.apk', False),
        )

        tmp = tempfile.mkdtemp(prefix='okok-', dir=outdir)
        try:
            for source_name, canonical_name, _ in selected:
                with open(os.path.join(tmp, canonical_name), 'wb') as f:
                    f.write(bundle.read(source_name))

            base = os.path.join(tmp, 'base.apk')
            actual_base_sha = sha(open(base, 'rb').read())
            if actual_base_sha != BASE_SHA:
                raise ValueError(
                    'base.apk hash mismatch; expected the analyzed OKOK International '
                    f'3.1.66 build {BASE_SHA}, got {actual_base_sha}'
                )

            print(f'input base entry: {base_entry}')
            print(f'input arm64 entry: {arm64_entry}')
            print(f'input density entry: {density_entry}')
            print(f'base SHA-256 verified: {actual_base_sha}')

            total_package_hits = 0
            total_label_hits = 0
            outputs = []
            for _, canonical_name, is_base in selected:
                src = os.path.join(tmp, canonical_name)
                dst = os.path.join(outdir, canonical_name)
                p_hits, l_hits = repack(src, dst, is_base=is_base)
                total_package_hits += p_hits
                total_label_hits += l_hits
                verify_no_old_package(dst)
                outputs.append(dst)

            if total_package_hits == 0:
                raise ValueError('package rename produced zero replacements')
            print(f'package replacements: {total_package_hits}')
            print(f'label replacements: {total_label_hits}')
            print(f'new package: {NEW_PACKAGE}')
            return outputs
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Patch OKOK International 3.1.66 split APK set')
    parser.add_argument('input_zip')
    parser.add_argument('output_dir')
    args = parser.parse_args()
    print('\n'.join(build(args.input_zip, args.output_dir)))
