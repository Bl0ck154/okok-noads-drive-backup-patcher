#!/usr/bin/env python3
import argparse
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
    for off, insns_size in AD_CODE_ITEMS.items():
        actual = struct.unpack_from('<I', x, off + 12)[0]
        if actual != insns_size:
            raise ValueError(f'code_item size mismatch at {off:#x}: {actual} != {insns_size}')
        # First instruction: return-void (0x000e), remaining instructions: nop.
        struct.pack_into('<H', x, off + 16, 0x000E)
        x[off + 18:off + 16 + 2 * insns_size] = b'\0' * (2 * (insns_size - 1))
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
    if is_base and name == 'AndroidManifest.xml':
        data = patch_manifest(data)

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


def build(input_zip: str, outdir: str):
    os.makedirs(outdir, exist_ok=True)
    with zipfile.ZipFile(input_zip) as bundle:
        names = set(bundle.namelist())
        required = {'base.apk', 'split_config.arm64_v8a.apk', 'split_config.xxxhdpi.apk'}
        if not required.issubset(names):
            raise ValueError(f'expected split APK set missing: {sorted(required - names)}')

        tmp = tempfile.mkdtemp(prefix='okok-', dir=outdir)
        try:
            for name in required:
                with open(os.path.join(tmp, name), 'wb') as f:
                    f.write(bundle.read(name))

            base = os.path.join(tmp, 'base.apk')
            if sha(open(base, 'rb').read()) != BASE_SHA:
                raise ValueError('base.apk hash mismatch; expected the analyzed OKOK International 3.1.66 build')

            total_package_hits = 0
            total_label_hits = 0
            outputs = []
            for name in ('base.apk', 'split_config.arm64_v8a.apk', 'split_config.xxxhdpi.apk'):
                src = os.path.join(tmp, name)
                dst = os.path.join(outdir, name)
                p_hits, l_hits = repack(src, dst, is_base=(name == 'base.apk'))
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
