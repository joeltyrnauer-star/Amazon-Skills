#!/usr/bin/env python3
"""Create and verify an immutable, manifest-backed session ZIP."""
import argparse, hashlib, json, os, tempfile, zipfile
from pathlib import Path

def digest_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('staging', type=Path); p.add_argument('output', type=Path)
    a = p.parse_args(); root = a.staging.resolve(); out = a.output.resolve()
    if not root.is_dir() or out.is_relative_to(root) or out.exists():
        p.error('Require a staging directory and a new output outside staging')
    files = []
    for f in sorted(root.rglob('*')):
        if f.is_symlink(): p.error('Symlinks are unsupported: ' + str(f))
        if f.is_file():
            rel = f.relative_to(root).as_posix()
            if rel == 'manifest.json' or '\\' in rel or ':' in rel:
                p.error('Reserved or unsafe path: ' + rel)
            files.append((f, rel, f.stat().st_size, digest_file(f)))
    if not files: p.error('Staging is empty')
    manifest = {'schema_version': 1, 'files': [dict(path=r,size=s,sha256=h) for _,r,s,h in files]}
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=out.parent, suffix='.zip'); os.close(fd)
    tmp = Path(temporary)
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
            for f, r, _, _ in files: z.write(f, r)
            z.writestr('manifest.json', json.dumps(manifest, separators=(',',':')))
        with zipfile.ZipFile(tmp) as z:
            if z.testzip(): raise ValueError('ZIP CRC verification failed')
            for _, r, size, expected in files:
                h = hashlib.sha256(); count = 0
                with z.open(r) as f:
                    for chunk in iter(lambda: f.read(1024*1024), b''):
                        h.update(chunk); count += len(chunk)
                if count != size or h.hexdigest() != expected:
                    raise ValueError('File changed or archive mismatch: ' + r)
        os.link(tmp, out)  # atomic no-overwrite publication
        print(json.dumps(dict(path=str(out),files=len(files),size=out.stat().st_size,
                              sha256=digest_file(out),verified=True)))
    finally: tmp.unlink(missing_ok=True)

if __name__ == '__main__': main()
