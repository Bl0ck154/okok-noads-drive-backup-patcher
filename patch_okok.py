#!/usr/bin/env python3
import argparse, hashlib, os, shutil, struct, tempfile, zipfile, zlib

BASE_SHA='638c2f8d7a5ceb44cb622545d795921a0a929488b7ecf01aa59123c2373ab353'
DEX_SHA='9dabbbb48656730c10e4269655862008a2daca880d323d94e425c7d428520700'
MANIFEST_SHA='8ecc89cd9088ec4d98073c5c67022842535e94d74cbd2b11364961a8d6c395f0'
# code_item offsets in classes4.dex for com.chipsea.code.ad.TopOnAdManager methods.
AD_CODE_ITEMS={
    0x23b380:4,   # r8 lambda
    0x23b398:4,   # nest confirmInit
    0x23b3b0:4,   # nest showSplashAd
    0x23b3c8:4,   # nest toLoadAd
    0x23b438:16,  # confirmInit
    0x23b468:27,  # initAd
    0x23b4b0:54,  # lambda$confirmInit$0
    0x23b52c:40,  # loadBannerAd
    0x23b58c:30,  # loadRewardAd
    0x23b5d8:78,  # loadSplashAd
    0x23b71c:100, # showBannerAd
    0x23b7f4:49,  # showRewardAd
    0x23b868:31,  # showSplashAd
    0x23b8b8:56,  # toLoadAd
}
ALLOW_BACKUP_DATA_OFF=0xdd14

def sha(b): return hashlib.sha256(b).hexdigest()

def patch_dex(b):
    if sha(b)!=DEX_SHA: raise ValueError('classes4.dex hash mismatch; this patcher supports OKOK 3.1.66 only')
    x=bytearray(b)
    for off,insns_size in AD_CODE_ITEMS.items():
        actual=struct.unpack_from('<I',x,off+12)[0]
        if actual!=insns_size: raise ValueError(f'code_item size mismatch at {off:#x}: {actual} != {insns_size}')
        # first instruction: return-void (0x000e), rest: nop (0x0000)
        struct.pack_into('<H',x,off+16,0x000e)
        x[off+18:off+16+2*insns_size]=b'\0'*(2*(insns_size-1))
    # DEX signature and checksum must be recomputed after any mutation.
    x[12:32]=hashlib.sha1(x[32:]).digest()
    struct.pack_into('<I',x,8,zlib.adler32(x[12:]) & 0xffffffff)
    return bytes(x)

def patch_manifest(b):
    if sha(b)!=MANIFEST_SHA: raise ValueError('AndroidManifest.xml hash mismatch; this patcher supports OKOK 3.1.66 only')
    x=bytearray(b)
    # android:allowBackup typed boolean data in <application>: false (0) -> true (-1)
    if struct.unpack_from('<I',x,ALLOW_BACKUP_DATA_OFF)[0]!=0:
        raise ValueError('unexpected allowBackup value')
    struct.pack_into('<I',x,ALLOW_BACKUP_DATA_OFF,0xffffffff)
    return bytes(x)

def is_old_sig(name):
    u=name.upper()
    if not u.startswith('META-INF/'): return False
    base=u.rsplit('/',1)[-1]
    return base=='MANIFEST.MF' or base.endswith(('.SF','.RSA','.DSA','.EC'))

def alignment_extra(existing, data_offset_without_new_extra, align):
    if align<=1: return existing
    pad=(-data_offset_without_new_extra)%align
    if pad and pad<4: pad+=align
    if not pad: return existing
    # Unknown ZIP extra-field ID used solely as deterministic padding.
    return existing+struct.pack('<HH',0xD935,pad-4)+b'\0'*(pad-4)

def clone_info(zi):
    n=zipfile.ZipInfo(zi.filename, date_time=zi.date_time)
    for a in ('compress_type','comment','create_system','create_version','extract_version','flag_bits','internal_attr','external_attr','volume'):
        if hasattr(zi,a): setattr(n,a,getattr(zi,a))
    n.extra=zi.extra or b''
    return n

def repack(src,dst,replacements=None):
    replacements=replacements or {}
    with zipfile.ZipFile(src,'r') as zin, zipfile.ZipFile(dst,'w',allowZip64=True) as zout:
        for zi in zin.infolist():
            if is_old_sig(zi.filename): continue
            data=replacements.get(zi.filename)
            if data is None: data=zin.read(zi.filename)
            nz=clone_info(zi)
            # Re-align uncompressed entries after repacking. Native libs use 16 KiB page alignment.
            if zi.compress_type==zipfile.ZIP_STORED:
                align=16384 if zi.filename.endswith('.so') else 4
                nameb=zi.filename.encode('utf-8')
                base=zout.fp.tell()+30+len(nameb)+len(nz.extra)
                nz.extra=alignment_extra(nz.extra,base,align)
            zout.writestr(nz,data,compress_type=zi.compress_type)

def build(input_zip,outdir):
    os.makedirs(outdir,exist_ok=True)
    with zipfile.ZipFile(input_zip) as bundle:
        names=set(bundle.namelist())
        need={'base.apk','split_config.arm64_v8a.apk','split_config.xxxhdpi.apk'}
        if not need.issubset(names): raise ValueError(f'expected split APK set missing: {sorted(need-names)}')
        tmp=tempfile.mkdtemp(prefix='okok-',dir=outdir)
        try:
            for n in need:
                open(os.path.join(tmp,n),'wb').write(bundle.read(n))
            base=os.path.join(tmp,'base.apk')
            if sha(open(base,'rb').read())!=BASE_SHA: raise ValueError('base.apk hash mismatch; expected OKOK International 3.1.66')
            with zipfile.ZipFile(base) as z:
                repl={'classes4.dex':patch_dex(z.read('classes4.dex')),
                      'AndroidManifest.xml':patch_manifest(z.read('AndroidManifest.xml'))}
            repack(base,os.path.join(outdir,'base-patched-unsigned.apk'),repl)
            repack(os.path.join(tmp,'split_config.arm64_v8a.apk'),os.path.join(outdir,'split_config.arm64_v8a-patched-unsigned.apk'))
            repack(os.path.join(tmp,'split_config.xxxhdpi.apk'),os.path.join(outdir,'split_config.xxxhdpi-patched-unsigned.apk'))
        finally:
            shutil.rmtree(tmp,ignore_errors=True)
    return [os.path.join(outdir,x) for x in ('base-patched-unsigned.apk','split_config.arm64_v8a-patched-unsigned.apk','split_config.xxxhdpi-patched-unsigned.apk')]

if __name__=='__main__':
    ap=argparse.ArgumentParser(description='Patch OKOK International 3.1.66 split APK set')
    ap.add_argument('input_zip'); ap.add_argument('output_dir')
    a=ap.parse_args(); print('\n'.join(build(a.input_zip,a.output_dir)))
