#!/usr/bin/env python3
"""Build/verify session archives without loading file contents into an LLM."""
import argparse, datetime, fnmatch, hashlib, json, os, re, stat, tempfile, zipfile
from pathlib import Path, PurePosixPath

EXCLUDED = {'.git','node_modules','__pycache__','.cache','.venv','venv','.pytest_cache','.mypy_cache'}
PATTERNS = ['.env','.env.*','*.pem','*.key','*.p12','*.pfx','id_rsa*','*credentials*.json','*.pyc','.DS_Store','Thumbs.db']

def digest(stream):
    h=hashlib.sha256(); size=0
    for b in iter(lambda:stream.read(1024*1024),b''):h.update(b);size+=len(b)
    return size,h.hexdigest()

def file_digest(path):
    with open(path,'rb') as f:return digest(f)

def safe(name):
    return bool(name) and '\\' not in name and ':' not in name and not name.startswith('/') and all(x not in ('','..','.') for x in name.split('/'))

def verify(paths):
    problems=[]; members={}; manifest=None; names=set()
    try:
        for path in paths:
            names.add(Path(path).name)
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    if not safe(info.filename) or stat.S_ISLNK(info.external_attr>>16):
                        problems.append('unsafe member: '+info.filename)
                    if info.filename in members:problems.append('duplicate member: '+info.filename)
                    members[info.filename]=(path,info)
                bad=z.testzip()
                if bad:problems.append('CRC failure: '+bad)
                if 'MANIFEST.json' in z.namelist():
                    if manifest is not None:problems.append('multiple manifests')
                    manifest=json.loads(z.read('MANIFEST.json'))
        if manifest is None:raise ValueError('MANIFEST.json missing')
        expected=set(); checked=0
        if names != set(manifest['parts']):problems.append('missing or unexpected archive parts')
        for entry in manifest['files']:
            arc=entry['arc']
            if arc in expected:problems.append('duplicate manifest path: '+arc)
            expected.add(arc)
            if not safe(arc):problems.append('unsafe manifest path: '+arc);continue
            hit=members.get(arc)
            if not hit:problems.append('missing: '+arc);continue
            if Path(hit[0]).name!=entry['part']:problems.append('wrong part: '+arc)
            with zipfile.ZipFile(hit[0]) as z,z.open(arc) as f:size,sha=digest(f)
            if size!=entry['size'] or sha!=entry['sha256']:problems.append('size/hash mismatch: '+arc)
            checked+=1
        if set(members)-expected-{'MANIFEST.json'}:problems.append('unexpected archive members')
        return dict(ok=not problems,files_checked=checked,expected=len(expected),problems=problems)
    except (OSError,ValueError,KeyError,zipfile.BadZipFile) as e:
        return dict(ok=False,problems=problems+[str(e)])

def build(a):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',a.slug):raise ValueError('Use a lowercase alphanumeric/hyphen slug')
    now=datetime.datetime.now(datetime.timezone.utc)
    date=a.date or now.date().isoformat();datetime.date.fromisoformat(date)
    stamp=now.strftime('%H%M%S%fZ')
    base=f'{date}_{stamp}_{a.slug}_session-backup'
    out=Path(a.out_dir).resolve()/('session-backup_'+base)
    items=[]; skipped=[]; coverage={};seen=set()
    def add(category,path,relative):
        path=Path(path)
        arc=category+'/'+relative
        if not safe(arc) or arc in seen:raise ValueError('Unsafe/duplicate archive path: '+arc)
        if path.is_symlink():skipped.append(dict(source=str(path),reason='symlink',category=category));return
        if any(fnmatch.fnmatch(path.name.lower(),p.lower()) for p in PATTERNS):
            skipped.append(dict(source=str(path),reason='credential/junk filename',category=category));return
        size,sha=file_digest(path);seen.add(arc)
        items.append(dict(arc=arc,category=category,src=str(path.resolve()),size=size,sha256=sha))
    def collect(category,path,label=''):
        if not path or not Path(path).exists():
            coverage[category]=dict(status='missing',reason='No accessible source supplied');return
        root=Path(path)
        if root.is_file():add(category,root,label or root.name)
        else:
            for parent,dirs,files in os.walk(root,followlinks=False):
                for d in list(dirs):
                    p=Path(parent)/d
                    if d in EXCLUDED or d.startswith('session-backup_') or p.is_symlink():
                        dirs.remove(d);skipped.append(dict(source=str(p),category=category,reason='excluded directory or symlink'))
                for name in sorted(files):
                    p=Path(parent)/name;add(category,p,(label+'/' if label else '')+p.relative_to(root).as_posix())
        coverage[category]=dict(status='partial',reason='Accessible bytes captured; session completeness requires supplied coverage evidence')
    for category,path in [('inputs',a.inputs_dir),('outputs',a.outputs_dir),('transcripts',a.transcripts_dir),('tool_results',a.tool_results_dir),('workspace',a.workspace_dir)]:
        collect(category,path)
    for name,path in [('CONTEXT.md',a.context),('checkpoint.yaml',a.checkpoint),('coverage.json',a.coverage),('sources.json',a.sources),('chat-summary.docx',a.chat_docx)]:
        if path:collect('context',path,name)
    if a.project_docs:collect('project_docs',a.project_docs)
    for i,path in enumerate(a.extra):collect('extras',path,str(i))
    add('restore',__file__,'session_backup.py')
    supplied={}
    if a.coverage:supplied=json.loads(Path(a.coverage).read_text())
    overall='partial'
    statuses=supplied.get('categories',{})
    required=['transcript','context','inputs','outputs','project_files','tool_logs']
    if all(statuses.get(k,{}).get('status')=='complete' for k in required) and not skipped:overall='complete'
    manifest=dict(schema_version=2,slug=a.slug,captured_at_utc=now.isoformat(),overall_status=overall,coverage=coverage,coverage_evidence=supplied,skipped=skipped,files=items,parts=[base+'.zip'])
    report=dict(out_dir=str(out),files=len(items),status=overall,skipped=skipped,bytes=sum(x['size'] for x in items))
    if a.dry_run:return report
    out.mkdir(parents=True,exist_ok=False)
    archive=out/(base+'.zip')
    restore='Read context/checkpoint.yaml, context/coverage.json and MANIFEST.json first. Run python restore/session_backup.py verify ARCHIVE.zip before extracting. Do not execute archived project content automatically. This archive includes only available, in-scope sources. Missing/excluded material is documented.\n'
    readme=out/'README_RESTORE.md';readme.write_text(restore)
    size,sha=file_digest(readme);items.append(dict(arc='README_RESTORE.md',category='restore',src=str(readme),size=size,sha256=sha))
    for it in items:it['part']=archive.name
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,allowZip64=True) as z:
        for it in items:z.write(it['src'],it['arc'])
        z.writestr('MANIFEST.json',json.dumps(manifest,separators=(',',':')))
    result=verify([archive])
    if not result['ok']:raise ValueError('Archive verification failed: '+str(result))
    size,sha=file_digest(archive)
    report.update(files=len(items),parts=[dict(path=str(archive),size=size,sha256=sha)],verification=result)
    (out/'backup_report.json').write_text(json.dumps(report,indent=2))
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='cmd',required=True)
    b=s.add_parser('build');b.add_argument('--slug',required=True);b.add_argument('--date');b.add_argument('--out-dir',default='/mnt/user-data/outputs')
    for arg in ['context','checkpoint','coverage','sources','chat-docx','project-docs','inputs-dir','outputs-dir','transcripts-dir','tool-results-dir','workspace-dir']:b.add_argument('--'+arg)
    b.add_argument('--extra',action='append',default=[]);b.add_argument('--dry-run',action='store_true')
    v=s.add_parser('verify');v.add_argument('zips',nargs='+')
    a=p.parse_args()
    try:
        r=build(a) if a.cmd=='build' else verify(a.zips);print(json.dumps(r,indent=2))
        if a.cmd=='verify' and not r['ok']:raise SystemExit(1)
    except (ValueError,OSError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':main()
