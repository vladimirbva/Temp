# -*- coding: utf-8 -*-
# Пост-резчик (перенос механики Ф32а/Ф32б LH3 v24 на уровень файла).
# Пороги: часть > 5000 строк -> резать; монолит-блок/цикл > 4000 -> Ф32а/Ф32б.
# Прототип Python-версии для последующего 1:1 переноса в VBS (L9_-имена).
import re

MARK_H1 = 'LH1 v25'
MARK_H2 = 'LH2 v39'

def strip_comments(s):
    out, q, i = [], False, 0
    while i < len(s):
        c = s[i]
        if c == "'":
            q = not q
        elif c == '/' and not q and i+1 < len(s) and s[i+1] == '/':
            break
        else:
            out.append(c)
        i += 1
    return ''.join(out)

def delta(s):
    t = strip_comments(s).lower()
    if not any(w in t for w in ('begin','end','try','repeat','until','case')):
        return 0
    d = 0
    for w in re.findall(r'[a-z0-9_]+', t):
        if w in ('begin','try','repeat','case'): d += 1
        elif w in ('end','until'): d -= 1
    return d

def cut_candidates(body):
    cand, dd = [], 0
    for k in range(len(body)):
        dd += delta(body[k])
        if dd == 0:
            t = body[k].strip().lower()
            if t.startswith('//'):
                cand.append(k+1)
            elif t.endswith(';') and not t.startswith('end') and not t.startswith('else'):
                jn = k+1
                while jn < len(body) and not body[jn].strip():
                    jn += 1
                nx = body[jn].strip().lower()[:4] if jn < len(body) else ''
                if not nx.startswith(('else','end','unti','+','-','and','or','.')):
                    cand.append(k+1)
    return cand

def mono_strip(s):
    r, q, i = [], False, 0
    while i < len(s):
        c = s[i]
        if c == "'":
            q = not q
        elif c == '/' and not q and i+1 < len(s) and s[i+1] == '/':
            break
        elif not q:
            r.append(c)
        i += 1
    return ''.join(r)

def mono_words(s):
    return re.findall(r'[a-z0-9_]+', mono_strip(s).lower())

def mono_split(base, thr=4000):
    bA = be = 0; dd = 0
    for i in range(len(base)):
        pv, dd = dd, dd + delta(base[i])
        if pv == 0 and dd > 0: bA = i + 1
        if dd == 0 and pv > 0 and bA > 0:
            if (i + 1 - bA - 1) > thr:
                be = i + 1; break
            else:
                bA = be = 0
    if bA == 0: return None, 'нет монолит-блока'
    blen = be - bA - 1
    ifStart = bA
    for i in range(bA-1, 0, -1):
        t = base[i-1].strip().lower()
        if len(t) == 0:
            ifStart = i
        elif t.startswith('if ') or t.startswith('if(') or t.startswith('elseif'):
            ifStart = i; break
        else:
            ifStart = bA; break
    cvars = []
    for i in range(ifStart, bA+1):
        for w in mono_words(base[i-1]):
            if w and w not in ('if','then','begin','and','or','not','elseif','end','=') and not w[0].isdigit():
                cvars.append(w)
    oneSided = cycFlag = 0; badCond = False
    for i in range(bA+1, be):
        tt = mono_strip(base[i-1]).lower()
        ws = mono_words(tt)
        hasB = any(w in ('begin','repeat') for w in ws)
        hasE = any(w in ('end','until') for w in ws)
        hasC = any(w in ('for','while','case') for w in ws)
        if hasC and not hasB and not hasE: oneSided += 1
        if hasC and hasB and not hasE: cycFlag = 1
        if (not badCond) and cvars:
            for v in cvars:
                if (v + ':=') in tt or (v + ' :=' ) in tt:
                    badCond = True; break
    if oneSided: return None, f'НЕ РЕЗАН: одностороних цикл-строк {oneSided}'
    if badCond: return None, 'НЕ РЕЗАН: переменная условия присваивается внутри блока'
    if cycFlag: return None, 'НЕ РЕЗАН: блок содержит многострочный цикл - путь Ф32б'
    cand = []; dd = 0
    for i in range(bA+1, be):
        pv, dd = dd, dd + delta(base[i-1])
        if dd == 0 and pv == 0:
            t = base[i-1].strip().lower()
            if t.startswith('//'):
                cand.append(i - bA)
            elif t.endswith(';') and not t.startswith('end') and not t.startswith('else'):
                jn = i
                while jn < be-1 and not base[jn].strip():
                    jn += 1
                nx = base[jn].strip().lower()[:4] if jn < be-1 else ''
                if not nx.startswith(('else','end','unti','+','-','and','or','.')):
                    cand.append(i - bA)
    if not cand: return None, 'НЕ РЕЗАН: точек реза нет'
    np_ = max(2, (blen + thr - 1)//thr)
    cts, lastc = [0], 0
    for k in range(1, np_):
        tg = k*blen//np_
        bs = 0
        for c in cand:
            if c > lastc and (bs == 0 or abs(c-tg) < abs(bs-tg)): bs = c
        if bs == 0: bs = blen-1
        if bs >= blen: bs = blen-1
        if bs <= lastc: bs = lastc+1
        cts.append(bs); lastc = bs
    cts.append(blen)
    out2 = []
    joints = []
    for i in range(1, bA+1): out2.append(base[i-1])
    for k in range(1, np_+1):
        for i in range(bA + cts[k-1] + 1, bA + cts[k]): out2.append(base[i-1])
        if k < np_:
            pe2 = base[be-1].find(';')
            out2.append(base[be-1][:pe2] if pe2 > 0 else base[be-1])
            joints.append(len(out2))
            for i in range(ifStart, bA+1): out2.append(base[i-1])
    for i in range(be, len(base)+1): out2.append(base[i-1])
    return dict(new=out2, parts=np_, blen=blen, sizes=[cts[k]-cts[k-1] for k in range(1, np_+1)], joints=joints), 'OK'

def find_loop(body, thr=4000):
    lbA = lbE = 0; dd = 0
    for i in range(len(body)):
        pv, dd = dd, dd + delta(body[i])
        if lbA == 0:
            lt = mono_strip(body[i]).lower()
            if ('for ' in lt or 'while ' in lt) and ('begin' in lt) and 'end' not in lt and 'until' not in lt:
                d2 = dd; jj = None
                for j in range(i+1, len(body)):
                    d2 += delta(body[j])
                    if d2 == pv:
                        jj = j; break
                if jj is not None and (jj - i - 1) > thr:
                    lbA, lbE = i, jj
                    break
    return lbA, lbE

def rename_word(s, old, new):
    out, q, i = [], False, 0
    while i < len(s):
        c = s[i]
        if c == "'":
            q = not q
            out.append(c); i += 1; continue
        if not q and (c.isalpha() or c == '_'):
            j = i
            while j < len(s) and (s[j].isalnum() or s[j] == '_'):
                j += 1
            w = s[i:j]
            if w == old and (j >= len(s) or not (s[j].isalnum() or s[j] == '_')):
                out.append(new); i = j; continue
            out.append(w); i = j; continue
        if c == '/' and not q and i+1 < len(s) and s[i+1] == '/':
            out.append(s[i:]); break
        out.append(c); i += 1
    return ''.join(out)

def suf(k):
    a = ord('a') - 1
    n = k
    while n > 26:
        n -= 26
        a += 1
    return (chr(a) if a > ord('a')-1 else '') + chr(ord('a') + n - 1)

def find_decl(L, nm):
    for i, l in enumerate(L):
        t = l.strip()
        if t.startswith('procedure ') and (t[len('procedure '):].split('(')[0].split(' ')[0].split(';')[0] == nm):
            return i
    return None

def build_cut(L, cls, procname, thr_line=5000, thr_inner=4000, marker='L9'):
    hdr = next((i for i, l in enumerate(L) if l.strip().startswith('procedure ' + cls + '.' + procname + ';')), None)
    if hdr is None: return None, None, None, None, None, 'нет процедуры'
    decl_i = find_decl(L, procname)
    if decl_i is None: return None, None, None, None, None, 'нет декларации'
    bi = next((j for j in range(hdr+1, len(L)) if L[j].strip() == 'begin'), None)
    if bi is None: return None, None, None, None, None, 'нет begin'
    dd = 1; ei = None
    for j in range(bi+1, len(L)):
        dd += delta(L[j])
        if dd <= 0: ei = j; break
    bL = L[bi+1:ei]
    dd = 0; idxExc = None
    for k in range(len(bL)):
        t = strip_comments(bL[k]).strip().lower()
        if dd == 1 and (t == 'except' or t.startswith('except ')):
            idxExc = k; break
        dd += delta(bL[k])
    inner = bL[:idxExc] if idxExc is not None else bL
    exc = bL[idxExc:] if idxExc is not None else []
    td1 = 1 if strip_comments(inner[0]).strip() == 'try' else 0
    base = inner[1:] if td1 else inner[:]
    varlines = [(j, L[j].strip()) for j in range(hdr+1, bi) if L[j].strip() and L[j].strip().lower() != 'var' and not L[j].strip().startswith('//')]
    flds = []
    for jj, t in varlines:
        pp = t.find(':')
        if pp > 1:
            lhs = t[:pp].strip(); tp = t[pp+1:].rstrip(';').strip()
            for vn in lhs.split(','):
                vn = vn.strip()
                if vn and re.match(r'^[A-Za-z_]\w*$', vn):
                    flds.append((procname + '_' + vn, vn, tp))
    for fld, vn, tp in flds:
        base = [rename_word(l, vn, fld) for l in base]
        exc = [rename_word(l, vn, fld) for l in exc]
    lbA, lbE = find_loop(base, thr_inner)
    if lbA:
        llen = lbE - lbA - 1
        tbody = base[lbA+1:lbE]
        tcand = cut_candidates(tbody)
        lnP2 = max(2, (llen + thr_inner - 1)//thr_inner)
        cts, last = [0], 0
        for k in range(1, lnP2):
            tg = k*llen//lnP2
            bs = 0
            for c in tcand:
                if c > last and (bs == 0 or abs(c-tg) < abs(bs-tg)): bs = c
            if bs == 0: bs = llen-1
            if bs >= llen: bs = llen-1
            if bs <= last: bs = last+1
            cts.append(bs); last = bs
        cts.append(llen)
        names = [procname + suf(k) for k in range(1, lnP2+1)]
        inner2 = []
        inner2.extend(base[:lbA+1])
        for k in range(1, lnP2+1):
            inner2.append('    ' + names[k-1] + ';  // ' + marker + ': часть ' + str(k) + ' из ' + str(lnP2) + ' цикла ' + procname)
        inner2.extend(base[lbE:])
        pi = dict(inner=inner2, names=names, bodies=[tbody[cts[k-1]:cts[k]] for k in range(1, lnP2+1)],
                  note='Ф32б: цикл ' + str(llen) + ' -> ' + str(lnP2) + ' частей', decl_note='цикла',
                  maxp=max(cts[k]-cts[k-1] for k in range(1, len(cts))))
        return base, exc, pi, flds, dict(hdr=hdr, bi=bi, ei=ei, td1=td1), 'OK'
    r, msg = mono_split(base, thr_inner)
    joints = []
    if r:
        base = r['new']; joints = r['joints']
        cand = set(cut_candidates(base))
        for jj in joints: cand.add(jj)
    else:
        cand = set(cut_candidates(base))
    n = len(base)
    np1 = max(2, (n + thr_line - 1)//thr_line) if n > thr_line else 1
    cand = sorted(cand)
    cts, last = [0], 0
    for k in range(1, np1):
        tg = k*n//np1
        bs = 0
        for c in cand:
            if c > last and (bs == 0 or abs(c-tg) < abs(bs-tg)): bs = c
        if bs == 0: bs = n-1
        if bs >= n: bs = n-1
        if bs <= last: bs = last+1
        cts.append(bs); last = bs
    cts.append(n)
    names = [procname + suf(k) for k in range(1, np1+1)]
    sizes = [cts[k]-cts[k-1] for k in range(1, len(cts))]
    pi = dict(inner=None, names=names, bodies=[base[cts[k-1]:cts[k]] for k in range(1, len(cts))],
              note=('Ф32а+' if r else '') + 'N-резка: ' + str(sizes), decl_note='процедуры', maxp=max(sizes))
    return base, exc, pi, flds, dict(hdr=hdr, bi=bi, ei=ei, td1=td1), 'OK'

def apply_cut_file(path, cls, procname, marker, max_iter=3, thr_line=5000, thr_inner=4000, write_enc='utf-8-sig'):
    total = []
    for it in range(max_iter):
        L = open(path, encoding='utf-8-sig', errors='replace').read().splitlines()
        base, exc, pi, flds, sp, msg = build_cut(L, cls, procname, thr_line, thr_inner, marker)
        if pi is None:
            if it == 0: return None
            break
        names = pi['names']; bodies = pi['bodies']
        out = []
        out.extend(L[:sp['bi']+1])
        if sp['td1']: out.append('  try')
        if pi['inner'] is not None:
            out.extend(pi['inner'])
        else:
            for nm in names:
                out.append('    ' + nm + ';  // ' + marker + ': часть 1 из ' + str(len(names)) + ' процедуры ' + procname)
        out.extend(exc)
        out.append('end;')
        out.extend(L[sp['ei']+1:])
        decl_i = find_decl(out, procname)
        decls = ['    procedure ' + nm + ';      // ' + marker + ': часть ' + str(k) + ' из ' + str(len(names)) + ' ' + pi['decl_note'] + ' ' + procname
                 for k, nm in enumerate(names, 1)]
        out = out[:decl_i+1] + decls + out[decl_i+1:]
        if flds:
            cls_i = next(i for i, l in enumerate(out) if '=class(' in l.lower())
            field_block = ['    ' + fld + ': ' + tp + ';  // ' + marker + ': локал процедуры ' + procname for fld, vn, tp in flds]
            out = out[:cls_i+1] + field_block + out[cls_i+1:]
        hdr2 = next(i for i, l in enumerate(out) if l.strip().startswith('procedure ' + cls + '.' + procname + ';'))
        beg2 = next(j for j in range(hdr2+1, len(out)) if out[j].strip() == 'begin')
        dd = 1; ei2 = None
        for j in range(beg2+1, len(out)):
            dd += delta(out[j])
            if dd <= 0: ei2 = j; break
        parts_out = []
        for k in range(1, len(names)+1):
            pq = bodies[k-1]
            parts_out.append('')
            parts_out.append('procedure ' + cls + '.' + names[k-1] + ';')
            parts_out.append('begin')
            parts_out.extend(pq)
            parts_out.append('    Miss_comm:=1; // ' + marker + ': расчёт дошёл до конца части')
            parts_out.append('end;')
        out = out[:ei2+1] + parts_out + out[ei2+1:]
        open(path, 'w', encoding=write_enc).write('\n'.join(out) + '\n')
        total.append((procname, it+1, pi['note']))
        if pi['maxp'] <= thr_line:
            break
    return total

def cut_file(path, marker, thr_line=5000, thr_inner=4000, write_enc='utf-8-sig'):
    """Скан всех процедур файла и резка > порога. Возвращает список [proc, note]."""
    res = []
    for it in range(200):
        L = open(path, encoding='utf-8-sig', errors='replace').read().splitlines()
        # найти первую процедуру с телом > thr_line
        prs = []
        for i, l in enumerate(L):
            if l.strip().startswith('procedure '):
                prs.append(i)
        target = None
        for k, i in enumerate(prs):
            end = prs[k+1] if k+1 < len(prs) else len(L)
            if end - i > thr_line:
                t = L[i].strip()
                m = re.match(r'procedure\s+([A-Za-z0-9_.]+)', t)
                if m:
                    target = (i, m.group(1).rstrip(';'))
                break
        if target is None:
            return res
        nm = target[1]
        cls = nm.split('.')[0] if '.' in nm else ''
        pn = nm.split('.')[-1] if '.' in nm else nm
        r = apply_cut_file(path, cls, pn, marker, thr_line=thr_line, thr_inner=thr_inner, write_enc=write_enc)
        if r is None:
            # не режем (нет декларации/начала) — помечаем и пропускаем процедуру
            res.append((pn, 'SKIP'))
            if len(res) > 200: break
            continue
        res.extend(r)
    return res