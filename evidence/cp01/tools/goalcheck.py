#!/usr/bin/env python3
"""goalcheck.py - CP-01 loop oracle. py -3.12, stdlib only.
Read-only against the workspace; writes only evidence/cp01/goalcheck-<n>.txt.
One line per goal:  G<n>: TRUE|FALSE  <reason>"""
import hashlib, json, re, socket, sys, zlib
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
CP = WS / "evidence" / "cp01"
AUTH = ("OPERATOR AUTHORIZATION: SWS-UI-001 ADDENDUM-01 v1.0 is issued as written; "
        "the CP-01 envelope, the two module installs, and gates 8a-8j are authorized; "
        "stage pauses waived; no provider spend authorized.")
V3 = {"bg":"#0b0e14","panel":"#151b28","sidebar":"#0d121c","input":"#1b2333",
      "border":"#232b3a","text":"#c7d1de","text-muted":"#9aa7bd","text-faint":"#3a4353",
      "accent":"#7fc8e8","accent-dim":"#2a4a5c","ok":"#9ece6a","warning":"#e0af68","danger":"#f7768e"}
STEMS = ["PROCESS_START","PORT_UNAVAILABLE","HEALTH_CHECK","IDENTITY_MISMATCH",
         "MODEL_UNAVAILABLE","PROVIDER_UNAVAILABLE","OPENCODE_UNAVAILABLE",
         "CONFIGURATION","WORKER","CONDUCTOR"]
CAPS = {"shell/src":320,"shell/static":300,"shell/modules":140,"sow-desktop":700,
        "sow-python":400,"distillery":500,"tokencenter":60}
ABS_CAP=1850
RES=[]
def rec(g,ok,why): RES.append((g,bool(ok),why))
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda: f.read(65536), b''): h.update(c)
    return h.hexdigest()
def rd(p):
    with open(p,'r',encoding='utf-8-sig',errors='replace') as f: return f.read()
def art(*p): return CP.joinpath(*p)
def piso(s):
    s=s.strip()[:-1]+'+00:00' if s.strip().endswith('Z') else s.strip()
    try: return datetime.fromisoformat(s)
    except ValueError:
        try: return datetime.fromisoformat(s.split('.')[0]+'+00:00')
        except ValueError: return None
def ledger(): return json.loads(rd(WS/'evidence'/'GATE-LEDGER.json'))
def gate_cand(key):
    try: led=ledger()
    except Exception as e: return False,'ledger unreadable: %s'%e
    g=led.get('gates',{}).get(key)
    if not isinstance(g,dict): return False,'ledger key "%s" absent'%key
    if g.get('status')!='CANDIDATE': return False,'status=%s want CANDIDATE'%g.get('status')
    if g.get('claimed_by')!='builder': return False,'claimed_by != builder'
    if g.get('evaluated_by') is not None: return False,'already evaluated'
    ev=g.get('evidence') or []
    if not ev: return False,'evidence list empty'
    for e in ev:
        p=WS/e['path']
        if not p.is_file(): return False,'missing %s'%e['path']
        if sha(p)!=str(e.get('sha256','')).lower(): return False,'hash mismatch %s'%e['path']
    return True,'CANDIDATE, %d evidence entries verified'%len(ev)
def suite_ok(path,minc):
    p=WS/path
    if not p.is_file(): return False,'%s absent'%path
    t=rd(p); m=re.search(r'Ran (\d+) tests? in',t)
    tail=[l for l in t.strip().splitlines() if l.strip()]
    last=tail[-1].strip() if tail else ''
    if not m: return False,"no 'Ran N tests' line"
    n=int(m.group(1))
    if n<minc: return False,'Ran %d < %d'%(n,minc)
    if last!='OK': return False,'last line %r != OK'%last
    return True,'Ran %d OK'%n

def bm_equal():
    p=WS/'shell'/'BUILD-MANIFEST.txt'
    if not p.is_file(): return False,'BUILD-MANIFEST.txt absent'
    bad=[]; n=0
    for line in rd(p).splitlines():
        line=line.rstrip('\r')
        if not line or line.startswith('#'): continue
        parts=line.split(None,1)
        if len(parts)!=2: continue
        h,rel=parts[0],parts[1].strip(); f=WS/'shell'/rel; n+=1
        if not f.is_file(): bad.append(rel+' missing')
        elif sha(f)!=h.lower(): bad.append(rel+' hash')
    if n==0: return False,'no entries parsed'
    if bad: return False,'%d mismatched: %s'%(len(bad),'; '.join(bad[:4]))
    return True,'%d entries equal live hashes'%n
def css_tokens():
    css=rd(WS/'shell'/'static'/'app.css')
    m=re.search(r':root\s*\{(.*?)\}',css,re.S)
    return dict(re.findall(r'--([a-z-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;',m.group(1))) if m else None
def grep_tree(relroots,needle,exclude=()):
    hits=[]; rx=re.compile(re.escape(needle)); ex=tuple(e.lower() for e in exclude)
    for rr in relroots:
        root=WS/rr
        if not root.is_dir(): continue
        for p in root.rglob('*'):
            if not p.is_file(): continue
            sp=str(p).lower()
            if any(x in sp for x in ex): continue
            if p.suffix.lower() not in ('.py','.js','.json','.html','.css','.txt','.md'): continue
            try:
                if rx.search(rd(p)): hits.append(str(p.relative_to(WS)))
            except OSError: pass
    return hits
def png_ok(p,minb=8000):
    if not p.is_file(): return False,'absent'
    raw=p.read_bytes()
    if len(raw)<minb: return False,'only %d bytes'%len(raw)
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'): return False,'not PNG'
    if b'IEND' not in raw[-16:]: return False,'truncated'
    idat=bytearray(); i=8
    while i+8<=len(raw):
        ln=int.from_bytes(raw[i:i+4],'big'); typ=raw[i+4:i+8]
        if typ==b'IDAT': idat+=raw[i+8:i+8+ln]
        if typ==b'IEND': break
        i+=12+ln
    if not idat or len(idat)>60_000_000: return False,'no/too-large IDAT'
    try: out=zlib.decompress(bytes(idat))
    except zlib.error as e: return False,'zlib %s'%e
    if len(set(out[:200000]))<8: return False,'near-uniform (blank?)'
    return True,'%d bytes decodes non-blank'%len(raw)
def before_ok():
    p=art('before','HASHES.txt')
    if not p.is_file(): return False,'before/HASHES.txt absent'
    lines=[l.rstrip('\r') for l in rd(p).splitlines() if l.strip() and not l.startswith('#')]
    if not lines: return False,'HASHES.txt empty'
    bad=[]
    for l in lines:
        parts=l.split(None,1)
        if len(parts)!=2: bad.append('unparsed '+l[:40]); continue
        h,rel=parts[0],parts[1].strip(); f=art('before',rel)
        if not f.is_file(): bad.append(rel+' missing')
        elif sha(f)!=h.lower(): bad.append(rel+' hash')
    return (False,'%d problems: %s'%(len(bad),'; '.join(bad[:4]))) if bad else (True,'%d files verified'%len(lines))
def tproof(band,name):
    fb=art(band,name+'-fails-before.txt'); pa=art(band,name+'-passes-after.txt')
    if not fb.is_file(): return False,'%s/%s-fails-before.txt absent'%(band,name)
    if not pa.is_file(): return False,'%s/%s-passes-after.txt absent'%(band,name)
    ta=[l for l in rd(pa).strip().splitlines() if l.strip()]
    if not ta or ta[-1].strip()!='OK': return False,'%s passes-after not OK'%name
    return True,'fails-before + passes-after OK'

def g0():
    p=art('session-start.txt')
    if not p.is_file(): return rec('G0',False,'session-start.txt absent')
    t=rd(p); pr=[]
    if '# utc:' not in t: pr.append('no utc header')
    if '# producer: ox-alpha CP-01' not in t: pr.append('no producer header')
    if 'bash_tool_shell:' not in t: pr.append('shell not recorded')
    for rel,rx in [('docs/DECISIONS.md',r'sha256_docs_DECISIONS_md:\s*([0-9a-f]{64}'),
                   ('AGENTS.md',r'sha256_AGENTS_md:\s*([0-9a-f]{64}'),
                   ('CLAUDE.md',r'sha256_CLAUDE_md:\s*([0-9a-f]{64}'),
                   ('docs/SWS-UI-001-v1.2-ADDENDUM-01.md',r'sha256_ADDENDUM_01:\s*([0-9a-f]{64}'),
                   ('docs/OX-ALPHA-DIRECTIVE-CP-01.md',r'sha256_CP01_directive:\s*([0-9a-f]{64}')]:
        m=re.search(rx+r')',t)
        if not m: pr.append(rel+' hash line missing'); continue
        live=sha(WS/rel)
        if m.group(1)!=live: pr.append('%s stale (%s vs %s)'%(rel,m.group(1)[:8],live[:8]))
    ma=re.search(r'sha256_AGENTS_md:\s*([0-9a-f]{64})',t); mc=re.search(r'sha256_CLAUDE_md:\s*([0-9a-f]{64})',t)
    if ma and mc and ma.group(1)!=mc.group(1): pr.append('AGENTS != CLAUDE')
    for port in (5175,8700,8765,5180):
        if ('port %d:'%port) not in t: pr.append('port %d missing'%port)
    if 'module processes under' not in t: pr.append('module-process section missing')
    lp=WS/'evidence'/'OPERATOR-INSTRUCTIONS.log'
    if not lp.is_file() or AUTH not in rd(lp): pr.append('auth sentence not in op-log')
    if not art('tools','goalcheck.py').is_file(): pr.append('oracle absent')
    rec('G0',not pr,'session-start verified' if not pr else '; '.join(pr))
def g01():
    names=['product-software','multi-model-terminal-app','sovereign-distillery','sov-1','token-piggy-bank']
    tool=WS/'evidence'/'tools'/'manifest.py'
    if not tool.is_file(): return rec('G0.1',False,'manifest tool absent')
    th=sha(tool); pr=[]
    try: want=ledger()['manifest_tool_sha256'].lower()
    except Exception as e: return rec('G0.1',False,'ledger unreadable %s'%e)
    if th!=want: pr.append('tool %s != ledger %s'%(th[:10],want[:10]))
    for nm in names:
        mf=art('manifests','manifest-cp01-before-%s.txt'%nm)
        if not mf.is_file(): pr.append('before-%s absent'%nm); continue
        m=re.search(r'# tool-sha256:\s*([0-9a-f]{64})',rd(mf)[:800])
        if not m: pr.append(nm+' header lacks tool-sha256')
        elif m.group(1)!=th: pr.append(nm+' tool-sha mismatch')
    q1,q2=art('sow-git-inspect-1.txt'),art('sow-git-inspect-2.txt')
    if not (q1.is_file() and q2.is_file()): pr.append('quiescence pair incomplete')
    else:
        t1,t2=rd(q1),rd(q2)
        m1,m2=re.search(r'# utc:\s*(\S+)',t1),re.search(r'# utc:\s*(\S+)',t2)
        b1=[l for l in t1.splitlines() if l.strip() and not l.startswith('#')]
        b2=[l for l in t2.splitlines() if l.strip() and not l.startswith('#')]
        d1,d2=(piso(m1.group(1)) if m1 else None),(piso(m2.group(1)) if m2 else None)
        if b1!=b2: pr.append('SOW git bodies differ')
        if not(d1 and d2): pr.append('quiescence utc unparsable')
        elif abs((d2-d1).total_seconds())<60: pr.append('<60s apart')
    rec('G0.1',not pr,'five manifests + quiescence verified' if not pr else '; '.join(pr))
def g02():
    pr=[]
    ok,why=before_ok()
    if not ok: pr.append(why)
    tb=art('test-run-before.txt')
    if not tb.is_file(): pr.append('test-run-before.txt absent')
    else:
        ok,why=suite_ok(str(tb.relative_to(WS)),122)
        if not ok: pr.append('before-suite: '+why)
    ok,why=bm_equal()
    if not ok: pr.append('BUILD-MANIFEST '+why)
    toks=css_tokens()
    if toks is None: pr.append(':root unparsable')
    else:
        for k,v in V3.items():
            if toks.get(k,'').lower()!=v: pr.append('css --%s=%s want %s'%(k,toks.get(k),v))
    rec('G0.2',not pr,'baseline verified' if not pr else '; '.join(pr))

def band_a():
    mp=WS/'docs'/'CP-MAP-01.md'
    if not mp.is_file():
        rec('G1',False,'docs/CP-MAP-01.md absent'); rec('G2',False,'absent map'); rec('G3',False,'absent map')
    else:
        t=rd(mp)
        topics=['launch','browser','pty','conductor','registry','token center','distillery','opencode','runtime']
        low=t.lower(); miss=[x for x in topics if x not in low]
        nf=len(re.findall(r'FACT\[[^\]]+:[0-9]+\]',t))
        rec('G1',(not miss) and nf>=20,'topics complete, %d FACT[path:line]'%nf if not miss else 'missing topics: %s'%','.join(miss))
        need={'R-%02d'%i for i in range(1,16)}; have=set(re.findall(r'R-\d\d',t))
        rec('G2',need<=have and nf>=15,'R-01..R-15 cited' if need<=have else 'rows missing: %s'%','.join(sorted(need-have)))
        div=bool(re.search(r'DIVERGENCE',t))
        pd=art('premise-divergence.txt'); sr=WS/'docs'/'STOP-REPORT-CP-01.md'
        if not div: rec('G3',True,'no divergence flagged')
        else: rec('G3',pd.is_file() and sr.is_file(),'divergence recorded + STOP report' if pd.is_file() and sr.is_file() else 'divergence flagged but artifacts missing')
    ok,why=gate_cand('8a'); rec('G3.1',ok,why)
def band_b():
    cold=art('8b','cold-start.txt')
    if not cold.is_file(): rec('G4',False,'8b/cold-start.txt absent')
    else:
        t=rd(cold); oktxt=('/api/state' in t) and ('serve_forever' in t or 'cold start' in t.lower())
        pf=tproof('8b','test-cold-start-starts-nothing')
        rec('G4',oktxt and pf[0],'artifact + test proofs' if oktxt and pf[0] else 'artifact:%s proof:%s'%(oktxt,pf[1]))
    dom,h9=art('8b','external-dom.txt'),art('8b','h9-noninterference.txt')
    ok=dom.is_file() and h9.is_file(); why='external-dom + H-9 present' if ok else 'dom:%s h9:%s'%(dom.is_file(),h9.is_file())
    if ok:
        tt=rd(dom); ok=('EXTERNAL' in tt) and ('dump' in tt.lower() or '<' in tt)
        why='EXTERNAL legible in DOM' if ok else 'external-dom lacks marker'
    rec('G5',ok,why)
    sj=WS/'shell'/'modules'/'sow.json'
    if not sj.is_file(): rec('G6',False,'sow.json absent')
    else:
        try: a=json.loads(rd(sj))
        except Exception as e: a=None; rec('G6',False,'sow.json unparsable %s'%e)
        if isinstance(a,dict):
            rk=a.get('readiness',{}).get('kind')
            srd,stp=art('8b','sow-readiness.txt'),art('8b','stop-evidence.txt')
            ok=(rk in ('http','receipt_file')) and srd.is_file() and stp.is_file()
            rec('G6',ok,'readiness.kind=%s + evidence'%rk if ok else 'kind=%s rd:%s stop:%s'%(rk,srd.is_file(),stp.is_file()))
    h18=WS/'evidence'/'hardening'/'h18-failure-classes.txt'; pr=[]
    if not h18.is_file(): pr.append('h18 absent')
    else:
        th=rd(h18).upper(); miss=[s for s in STEMS if s not in th]
        if miss: pr.append('classes missing: %s'%','.join(miss))
    for nm in ('test_failure_classes','test_port_conflict_is_its_own_class'):
        p2=tproof('8b',nm)
        if not p2[0]: pr.append(nm+': '+p2[1])
    rec('G7',not pr,'10 classes + 2 proofs' if not pr else '; '.join(pr))
    bl=art('8b','browser-lifecycle.txt'); p3=tproof('8b','test_browser_handle_map')
    rec('G7.1',bl.is_file() and p3[0],'lifecycle artifact + map-test proof' if bl.is_file() and p3[0] else 'artifact:%s proof:%s'%(bl.is_file(),p3[1]))
    ok,why=gate_cand('8b'); tr=suite_ok('evidence/test-run.txt',122); lc=art('linecount.txt').is_file()
    rec('G7.2',ok and tr[0] and lc,'ledger 8b + suite + linecount' if ok and tr[0] and lc else 'ledger:%s suite:%s lc:%s'%(why,tr[1],lc))

def band_c():
    es,pf=art('8c','empty-session.json'),tproof('8c','test_new_session_spawns_no_process')
    rec('G8',es.is_file() and pf[0],'record + proof' if es.is_file() and pf[0] else 'artifact:%s proof:%s'%(es.is_file(),pf[1]))
    sf=art('8c','selection-flow.txt')
    ok=sf.is_file() and all(k in rd(sf).lower() for k in ('create','select','initialize','use'))
    rec('G9',ok,'Create->Select->Initialize->Use recorded' if ok else 'selection-flow absent/incomplete')
    gr=tproof('8c','test_governed_replacement')
    hits=grep_tree(['modules/sow'],'already holds a live session',exclude=('test','fixture'))
    rec('G10',gr[0] and not hits,'governed replacement; refusal gone' if gr[0] and not hits else 'proof:%s hits:%s'%(gr[1],hits[:3]))
    pnd=art('8c','powershell-not-default.txt')
    rec('G11',pnd.is_file(),'grep-proof present' if pnd.is_file() else 'powershell-not-default.txt absent')
    ok,why=gate_cand('8c')
    ss=art('8c','sow-suite-ok.txt'); sok=ss.is_file() and suite_ok(str(ss.relative_to(WS)),1)[0]
    lc=art('linecount.txt').is_file()
    rec('G11.1',ok and sok and lc,'ledger 8c + SOW suite + linecount' if ok and sok and lc else 'ledger:%s suite:%s lc:%s'%(why,sok,lc))
def band_d():
    dom=art('8d','conductor-dom.txt')
    if dom.is_file():
        t=rd(dom).lower()
        ok=(('<input' in t) or ('<textarea' in t) or ('contenteditable' in t)) and (('submit' in t) or ('send' in t)) and ('turn' in t)
        why='input + submit + turns in DOM'
    else: ok,why=False,'8d/conductor-dom.txt absent'
    rec('G12',ok,why)
    rt=art('8d','conductor-roundtrip.txt')
    if rt.is_file():
        t=rd(rt)
        ok=('directive' in t.lower()) and ('response' in t.lower()) and (('UNSUPPORTED' in t) or ('context' in t.lower()) or ('follow-up' in t.lower()))
        why='round-trip legs recorded'
    else: ok,why=False,'conductor-roundtrip.txt absent'
    rec('G13',ok,why)
    ok,why=gate_cand('8d'); rec('G13.1',ok,why)
def band_e():
    wr=art('8e','worker-registry.json'); ok=False; why='worker-registry.json absent'
    if wr.is_file():
        try:
            data=json.loads(rd(wr)); workers=data if isinstance(data,list) else data.get('workers',[])
            def hf(w):
                f=json.dumps(w).lower()
                return all(k in f for k in ('session_id','provider_id','model_id','backend','state','created_utc'))
            ok=isinstance(workers,list) and len(workers)>=2 and all(hf(w) for w in workers[:10])
            why='%d workers, fields incl created_utc'%len(workers) if ok else 'workers=%d/fields missing'%(len(workers) if isinstance(workers,list) else -1)
        except Exception as e: ok,why=False,'registry unparsable %s'%e
    pf=tproof('8e','test_registry_fields_projected')
    rec('G14',ok and pf[0],why+'; test:%s'%pf[0])
    dd=art('8e','directive-delivery.txt')
    ok=dd.is_file() and 'session_id' in rd(dd)
    rec('G15',ok,'delivery with target session' if ok else 'directive-delivery absent/no session_id')
    wf,syn=art('8e','worker-failure.txt'),art('8e','synthesis.txt')
    owed=grep_tree(['modules/sow/control_plane','modules/sow/apps/desktop'],'LIVE_WORKERS_OWED',exclude=('test','node_modules'))
    mlbl=grep_tree(['modules/sow/apps/desktop/renderer'],'mock',exclude=('node_modules',))
    ok=wf.is_file() and syn.is_file() and ((not owed) or bool(mlbl))
    rec('G16',ok,'failure + synthesis + honest feed' if ok else 'wf:%s syn:%s owed:%s'%(wf.is_file(),syn.is_file(),owed[:2]))
    ok,why=gate_cand('8e')
    blob=json.dumps(ledger().get('gates',{}).get('8e',{}))
    note=ok and (('NOT_RUN' in blob) or ('live' in blob.lower()))
    rec('G16.1',note,'ledger 8e with live/NOT_RUN statement' if note else why)
def band_f():
    det=art('8f','opencode-detect.txt')
    if not det.is_file():
        rec('G17',False,'opencode-detect.txt absent'); rec('G18',False,'no detect artifact'); rec('G19',False,'no detect artifact')
    else:
        t=rd(det); ab='ABSENT' in t.upper()
        rec('G17',True,'detection recorded (%s)'%('absent on host' if ab else 'present'))
        direct,dele,un=art('8f','opencode-direct.txt'),art('8f','opencode-delegation.txt'),art('8f','opencode-unavailable.txt')
        ok18=(direct.is_file() and un.is_file() and 'NOT_RUN' in rd(direct).upper()) if ab else direct.is_file()
        ok19=(dele.is_file() and 'NOT_RUN' in rd(dele).upper()) if ab else dele.is_file()
        rec('G18',ok18,'direct access (or truthful NOT_RUN)' if ok18 else 'opencode-direct missing/insufficient')
        rec('G19',ok19,'delegation chain (or truthful NOT_RUN)' if ok19 else 'opencode-delegation missing/insufficient')
    bnm=art('8f','backend-not-model.txt'); mh=[]
    for rr in ('modules/sow/control_plane/nodes','modules/sow/adapters'):
        root=WS/rr
        if not root.is_dir(): continue
        for p in root.rglob('*.py'):
            try: txt=rd(p)
            except OSError: continue
            for m in re.finditer(r"model_id['\"]?\s*[:=]\s*['\"]([^'\"]+)",txt):
                if 'opencode' in m.group(1).lower(): mh.append(p.name+': '+m.group(1))
    rec('G19.1',bnm.is_file() and not mh,'backend-not-model proven' if bnm.is_file() and not mh else 'artifact:%s rows:%s'%(bnm.is_file(),mh[:3]))
    ok,why=gate_cand('8f'); rec('G19.2',ok,why)

def band_g():
    rdj,da=art('8g','registry-dump.json'),art('8g','duplication-audit.txt')
    ok=rdj.is_file() and da.is_file()
    if ok:
        try: json.loads(rd(rdj))
        except Exception: ok=False
    rec('G20',ok,'registry dump + duplication audit' if ok else 'dump:%s audit:%s'%(rdj.is_file(),da.is_file()))
    pf=tproof('8g','test_incompatible_selection_refused')
    rec('G21',pf[0],'incompatibility refusal proven' if pf[0] else pf[1])
    dv=art('8g','discovery.txt')
    ok=dv.is_file() and 'ollama' in rd(dv).lower()
    rec('G22',ok,'per-source discovery recorded' if ok else 'discovery.txt absent/no ollama source')
    gs=art('8g','grok-status.txt')
    rec('G22.0',gs.is_file(),'grok status recorded' if gs.is_file() else 'grok-status.txt absent')
    ok,why=gate_cand('8g'); rec('G22.1',ok,why)
def band_h():
    prov=WS/'modules'/'distillery'/'INSTALL-PROVENANCE.json'
    bc=art('8h','distillery-baseline-clean.txt')
    ok=prov.is_file() and bc.is_file() and ('no differences' in rd(bc).lower())
    rec('G23',ok,'Option-A install + protected unchanged' if ok else 'prov:%s baseline:%s'%(prov.is_file(),bc.is_file()))
    dj=WS/'shell'/'modules'/'distillery.json'; okj=False; whyj='distillery.json absent'
    if dj.is_file():
        try:
            a=json.loads(rd(dj))
            okj=(a.get('state_class')=='runnable') and ('launch' in a) and (a.get('readiness',{}).get('kind')=='http') and (a.get('identity',{}).get('kind')=='http_json') and (a.get('stop',{}).get('kind')=='job_object') and isinstance(a.get('runtime_writes'),list)
            whyj='real lifecycle declared' if okj else 'adapter incomplete'
        except Exception as e: whyj='unparsable %s'%e
    st,sp=art('8h','distillery-start.txt'),art('8h','distillery-stop.txt')
    rec('G24',okj and st.is_file() and sp.is_file(),whyj+'; start:%s stop:%s'%(st.is_file(),sp.is_file()))
    dom=art('8h','distillery-dom.txt')
    if dom.is_file():
        t=rd(dom); tl=t.lower()
        need=['runtime status','student model','pipeline state','queue','logs']
        miss=[x for x in need if x not in tl]; nobare='D:/' not in t
        ok=(not miss) and nobare
        why='console surfaces, no bare D:/' if ok else 'missing:%s barepath:%s'%(','.join(miss),not nobare)
    else: ok,why=False,'distillery-dom.txt absent'
    rec('G25',ok,why)
    na,pf=art('8h','no-autocompute.txt'),tproof('8h','test_start_invokes_no_pipeline')
    rec('G25.1',na.is_file() and pf[0],'no-compute window + start-path test' if na.is_file() and pf[0] else 'artifact:%s proof:%s'%(na.is_file(),pf[1]))
    ok,why=gate_cand('8h'); rec('G25.2',ok,why)
def band_i():
    prov=WS/'modules'/'tokencenter'/'INSTALL-PROVENANCE.json'
    bc=art('8i','tokenpiggy-baseline-clean.txt'); c7=tproof('8i','test_tokencenter_loopback_and_csrf')
    ok=prov.is_file() and c7[0] and bc.is_file() and ('no differences' in rd(bc).lower())
    rec('G26',ok,'copy installed; original untouched; C-7 fixed in copy' if ok else 'prov:%s baseline:%s c7:%s'%(prov.is_file(),bc.is_file(),c7[1]))
    tj=WS/'shell'/'modules'/'tokencenter.json'; okj=False; whyj='tokencenter.json absent'
    if tj.is_file():
        try:
            a=json.loads(rd(tj)); r=a.get('readiness',{})
            okj=(r.get('kind')=='http') and str(r.get('url','')).endswith('/healthz') and (r.get('expect_status')==200) and (a.get('identity',{}).get('kind')=='http_json') and bool(a.get('identity',{}).get('required_keys')) and (a.get('stop',{}).get('kind')=='job_object')
            whyj='module like any other' if okj else 'adapter incomplete'
        except Exception as e: whyj='unparsable %s'%e
    sta,stp=art('8i','tokencenter-start.txt'),art('8i','tokencenter-stop.txt')
    rec('G27',okj and sta.is_file() and stp.is_file(),whyj+'; start:%s stop:%s'%(sta.is_file(),stp.is_file()))
    dom=art('8i','main-ui-dom.txt')
    pngs=sorted((CP/'8i').glob('main-ui-*.png')) if (CP/'8i').is_dir() else []
    th={}
    for p in pngs:
        n=p.name.lower(); k='dark' if 'dark' in n else ('light' if 'light' in n else None)
        if k: g,_=png_ok(p); th[k]=th.get(k,False) or g
    central=False
    if dom.is_file():
        t=rd(dom).lower(); central=('token center' in t) and all(k in t for k in ('sovereign','debate table','distillery'))
    ok=dom.is_file() and len(th)>=2 and all(th.values()) and central
    rec('G28',ok,'central placement + themed non-blank captures' if ok else 'dom:%s themes:%s central:%s'%(dom.is_file(),sorted(th),central))
    h19=WS/'evidence'/'hardening'/'h19-tokencenter-contract.txt'
    rec('G29',h19.is_file(),'contract artifact present' if h19.is_file() else 'h19-tokencenter-contract.txt absent')
    nc=art('8i','no-credentials.txt')
    rec('G29.1',nc.is_file(),'absence-of-credential-surface proof' if nc.is_file() else 'no-credentials.txt absent')
    ok,why=gate_cand('8i'); rec('G29.2',ok,why)
def popen(port):
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); s.settimeout(0.4)
    try: return s.connect_ex(('127.0.0.1',port))==0
    finally: s.close()
def band_j():
    steps=['state-after-coldstart.json','stepB-debate.txt','stepC-workspace.txt','stepD-conductor.txt','stepE-opencode.txt','stepF-models.txt','stepG-distillery.txt','stepH-tokencenter.txt']
    missing=[s for s in steps if not art('8j',s).is_file()]
    rec('G30',not missing,'scenario A-H artifacts present' if not missing else 'missing: %s'%','.join(missing))
    pc=art('8j','proof-chain.txt'); ok=pc.is_file() and ('Human' in rd(pc))
    rec('G31',ok,'proof-chain recorded' if ok else 'proof-chain absent')
    pr=[]
    tr=suite_ok('evidence/test-run.txt',122)
    if not tr[0]: pr.append('suite '+tr[1])
    bm=bm_equal()
    if not bm[0]: pr.append('build-manifest '+bm[1])
    pmc=art('8j','protected-manifests-clean.txt')
    if not pmc.is_file() or rd(pmc).lower().count('no differences')<5: pr.append('protected-manifest clean artifact incomplete')
    toks=css_tokens()
    if toks is None or any(toks.get(k,'').lower()!=v for k,v in V3.items()): pr.append(':root drifted from v3')
    fw=art('8j','fs-watch-cp01.txt')
    if not fw.is_file() or 'events: 0' not in rd(fw): pr.append('fs-watch events!=0/absent')
    rec('G32',not pr,'regression clean' if not pr else '; '.join(pr))
    lc=art('linecount.txt'); ok=False; why='linecount.txt absent'
    if lc.is_file():
        tot=None; ok=True
        for line in rd(lc).splitlines():
            line=line.strip()
            if not line or line.startswith('#'): continue
            parts=[x.strip() for x in re.split(r'[|\t]',line) if x.strip()]
            if len(parts)<3: continue
            area,u,c=parts[0],parts[1],parts[2]
            try: ui,ci=int(u),int(c)
            except ValueError: ok=False; why='bad row %s'%line[:40]; break
            if ci==ABS_CAP: tot=ui; continue
            if ui>CAPS.get(area,10**9): ok=False; why='%s over cap %d>%d'%(area,ui,ci); break
        if ok:
            if tot is None: ok,why=False,'no absolute-total row'
            elif tot>ABS_CAP: ok,why=False,'total %d>%d'%(tot,ABS_CAP)
            else: why='within caps, total %d/%d'%(tot,ABS_CAP)
    rec('G33',ok,why)
    oc=art('8j','orphans-after.txt')
    busy=[p for p in (5175,8700,5180) if popen(p)]
    e5=popen(8765); octx=rd(oc).lower() if oc.is_file() else ''
    ok=oc.is_file() and (not busy) and ((not e5) or ('8765' in octx and 'external' in octx))
    rec('G34',ok,'builder processes stopped; ports clear'+(' (8765 external documented)' if e5 else '') if ok else 'busy:%s oc:%s'%(busy or 'none',oc.is_file()))
    ok,why=gate_cand('8j'); rec('G35',ok,why)
    rp=WS/'docs'/'CP-01-REPORT.md'
    if rp.is_file():
        t=rd(rp); rows=set(re.findall(r'R-(?:0?[1-9]|1[0-5])\b',t))
        need={'R-%d'%i for i in range(1,16)}
        claim='BUILDER CLAIM:' in t; tags=t.count('FACT[')
        ok=(need<=rows) and claim and tags>=15
        rec('G36',ok,'report complete + tagged + claim line' if ok else 'rows:%d claim:%s tags:%d'%(len(need&rows),claim,tags))
    else: rec('G36',False,'docs/CP-01-REPORT.md absent')
def main():
    seq=1
    others=list(CP.glob('goalcheck-*.txt'))
    if others: seq=max(int(re.findall(r'(\d+)',p.stem)[0]) for p in others)+1
    for fn in (g0,g01,g02,band_a,band_b,band_c,band_d,band_e,band_f,band_g,band_h,band_i,band_j):
        try: fn()
        except Exception as e: RES.append(('ORACLE-ERROR',False,'%s: %r'%(fn.__name__,e)))
    nt=sum(1 for _,o,_ in RES if o)
    lines=['# utc: '+datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]+'Z','# producer: ox-alpha CP-01 oracle','']
    for g,o,w in RES: lines.append('%s: %s  %s'%(g,'TRUE' if o else 'FALSE',w))
    lines += ['','summary: %d/%d TRUE'%(nt,len(RES))]
    out=art('goalcheck-%d.txt'%seq)
    out.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines)); return 0
if __name__=='__main__': sys.exit(main())
