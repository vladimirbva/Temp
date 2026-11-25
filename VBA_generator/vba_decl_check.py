#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vba_decl_check.py - статический анализатор VBA-конверторов (правило владельца 25.11.2026:
"прогонять всё постоянно" - при сборке КАЖДОЙ версии конвертора, без исключений).

Проверки:
1. Необъявленные идентификаторы в коде (вне строк-литералов и комментариев), с учётом
   модульных объявлений, параметров процедур, локальных Dim/Const/ReDim и меток.
2. ЗАВИСИМОСТИ ВСТАВОК от внешних (модульных) объявлений: имена, используемые внутри
   процедур с заданным префиксом (вставки), но объявленные только ВНЕ вставки.
   Именно этот класс ошибок проявляется при ручном переносе вставок владельцем
   (L9_THR_LINE, ltt/lws, di0, nP2).

Использование:
  python vba_decl_check.py file.txt [file2 ...] [--prefix L9_]
"""
import re, sys, collections

TYPES = set('long string integer double boolean variant object currency single byte decimal dbl any longptr int'.split())
BUILTIN_FUNCS = set("""
abs array asc atn attrcall cbool cbyte ccur cdate cdbl cdec chr cint clng cos csng cstr
cvar cverr date dateadd datediff datepart dateserial datevalue day dir doevents
eof err error exp filedatetime filelen fix format freefile getattr hex hour iif
input inputbox instr instrrev int isarray isdate isempty iserror ismissing isnull
isnumeric isobject join kill lbound lcase left len loc lof log ltrim lset mid minute mkdir
month msgbox name now oct pmt ppmt rate replace rgb right rmdir rnd round rtrim
rset second setattr sgn sin space spc sqr sqrt str strconv strcomp split unload curdir
switch tab tan time timer timeserial timevalue trim typename ubound ucase val vartype
weekday year randomize sendkeys prpro collection ufprogress
""".split())
VBA_KEYWORDS = set("""
true false empty null nothing and or not xor mod like is to step each next until wend end
sub function property get let set new with exit call const dim redim preserve static public
private global as byval byref optional paramarray erase open close for while do loop
select case if then else elseif resume on error goto return stop me this byval
print write input line seek lock unlock width put option explicit compare binary text
next each in step byval
""".split())
OBJS = set("""
debug application thisworkbook activeworkbook activesheet activecell activedocument
cells range rows columns worksheets sheets workbooks selection
scripting dictionary filesystemobject fso createobject
vbe vbprojects vbproject components
""".split())
VB_CONST = set("""
vbtextcompare vbbinarycompare vbusecompareoption vbcrlf vblf vbcr vbtab vbnewline
vbnullstring vbnullchar vbback vbformfeed vbverticaltab vbobjecterror vbinformation
vbcritical vbexclamation vbquestion vbokonly vbokcancel vbyesno vbyesnocancel
vbretrycancel vbabortretryignore vbok vbcancel vbabort vbretry vbignore vbyes vbno
vbdefaultbutton1 vbdefaultbutton2 vbdefaultbutton3 vbapplicationmodal vbsystemmodal
""".split())

TOKEN = re.compile(r'[A-Za-z_]\w*')
KEYWORDS = r'\b(?:Dim|Const|ReDim|Static|Public|Private|Global)\b'

def strip_code(line):
    out, i, n = [], 0, len(line)
    in_str = False
    while i < n:
        c = line[i]
        if in_str:
            if c == '"':
                if i + 1 < n and line[i+1] == '"':
                    i += 2; continue
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True; out.append(' '); i += 1; continue
        if c == "'":
            break
        out.append(c); i += 1
    s = ''.join(out)
    s = re.sub(r'&[hH][0-9A-Fa-f]+', ' HEX ', s)
    return s

LABELS = set('nextfile ixdone elseout nextpi out4 nextblock'.split())

def decl_names(code):
    names = set()
    for m in re.finditer(KEYWORDS + r'([^:\'"\n]*)', code):
        seg = m.group(1)
        for part in re.split(r'[,;=]', seg):
            part = part.strip()
            toks = re.findall(r'[A-Za-z_]\w*', part)
            if not toks:
                continue
            if toks[0].lower() in ('dim', 'const', 'redim', 'static', 'public', 'private', 'global'):
                toks = toks[1:]   # ключевое слово внутри сегмента после склейки - берём следующий токен
            if toks:
                names.add(toks[0])
    return names

def params_of(sig):
    names = set()
    mm = re.match(r'.*?\((.*)\)', sig)
    if not mm: return names
    inner = mm.group(1)
    for part in inner.split(','):
        pm = re.match(r'\s*(?:Optional\s+)?(?:ByVal\s+|ByRef\s+)?(?:ParamArray\s+)?([A-Za-z_]\w*)', part.strip())
        if pm:
            names.add(pm.group(1))
    return names

def split_procs(lines):
    """Возвращает [(start, end, name, params)] процедуры (end включительно)."""
    procs = []
    i = 0
    while i < len(lines):
        m = re.match(r'\s*(?:Public\s+|Private\s+|Friend\s+)?(Sub|Function|Property)\s+(\w+)', lines[i])
        if m:
            name = m.group(2)
            params = params_of(lines[i])
            j = i + 1
            while j < len(lines) and not re.match(r'\s*End (?:Sub|Function|Property)\b', lines[j]):
                j += 1
            procs.append((i, min(j, len(lines)-1), name, params))
            i = j + 1
        else:
            i += 1
    return procs

def glue(raw):
    lines, buf = [], ''
    for l in raw:
        st = l.rstrip()
        if st.endswith('_'):
            buf += st[:-1] + ' '
        else:
            lines.append(buf + st); buf = ''
    if buf: lines.append(buf)
    return lines

def analyze(path):
    lines = glue(open(path, encoding='utf-8-sig', errors='replace').read().splitlines())
    procs = split_procs(lines)
    module = set()
    proc_names = set()
    for st, en, nm, pm in procs:
        proc_names.add(nm)
    in_proc = [False]*len(lines)
    for st, en, nm, pm in procs:
        for j in range(st, en+1):
            in_proc[j] = True
    for i, l in enumerate(lines):
        if not in_proc[i]:
            module |= decl_names(strip_code(l))
            module |= params_of(l)   # заголовки вне процедур тоже
    problems = []
    for st, en, nm, pm in procs:
        local = set(pm)
        for j in range(st, en+1):
            local |= decl_names(strip_code(lines[j]))
        declared = module | local | proc_names
        for j in range(st, en+1):
            code = strip_code(lines[j])
            code = re.sub(r'\b(Append|Output|Input|Binary|Random)\b(?=\s*(#|As|,|$))', ' MODE', code)
            code = re.sub(r'\.\s*([A-Za-z_]\w*)', ' PROP', code)
            # метка - только в НАЧАЛЕ строки
            lm = re.match(r'\s*([A-Za-z_]\w*)\s*:', code)
            if lm: declared.add(lm.group(1))
            for m in TOKEN.finditer(code):
                w = m.group(0)
                wl = w.lower()
                if wl in BUILTIN_FUNCS or wl in VBA_KEYWORDS or wl in OBJS or wl in VB_CONST:
                    continue
                if wl in TYPES or wl.startswith('vb') or wl == 'msofiledialogfolderpicker' or wl == 'prop' or wl == 'mode' or wl in LABELS:
                    continue
                if w not in declared:
                    problems.append((j+1, w))
    return problems, procs, lines


def src_map(raw):
    """Соответствие склеенная строка -> исходная строка (для номеров в отчёте)."""
    mapping, out_i = [], 0
    for i, l in enumerate(raw):
        out_i = i
        mapping.append(out_i)
    return mapping

def block_dependency(path, prefix):
    """Имена, используемые в процедурах с префиксом (вставка), но объявленные только вне их
    (модульный уровень, другие процедуры). Считаются: локальные Dim/Const/параметры."""
    lines = glue(open(path, encoding='utf-8-sig', errors='replace').read().splitlines())
    procs = split_procs(lines)
    module = set()
    proc_names = set()
    for st, en, nm, pm in procs:
        proc_names.add(nm)
    in_proc = [False]*len(lines)
    for st, en, nm, pm in procs:
        for j in range(st, en+1):
            in_proc[j] = True
    for i, l in enumerate(lines):
        if not in_proc[i]:
            module |= decl_names(strip_code(l))
            module |= params_of(l)
    used = collections.defaultdict(list)
    for st, en, nm, pm in procs:
        if not nm.startswith(prefix):
            continue
        local = set(pm)
        for j in range(st, en+1):
            local |= decl_names(strip_code(lines[j]))
        declared = local | {n for n in proc_names if n.startswith(prefix)}
        for j in range(st, en+1):
            code = strip_code(lines[j])
            code = re.sub(r'\.\s*([A-Za-z_]\w*)', ' PROP', code)
            for m in TOKEN.finditer(code):
                w = m.group(0)
                if w in declared: continue
                wl = w.lower()
                if wl in BUILTIN_FUNCS or wl in VBA_KEYWORDS or wl in TYPES or wl in VB_CONST:
                    continue
                if wl.startswith('vb'): continue
                if w in module or w in proc_names:   # объявлено вне вставки - РИСК
                    used[w].append(j+1)
    return used

if __name__ == '__main__':
    args = sys.argv[1:]
    prefix = 'L9_'
    if '--prefix' in args:
        k = args.index('--prefix'); prefix = args[k+1]; args = args[:k]+args[k+2:]
    paths = args
    for p in paths:
        problems, procs, lines = analyze(p)
        by = collections.Counter(x[1] for x in problems)
        print(f'=== {p}: процедур {len(procs)}, необъявленных имён {len(by)} ===')
        for w, c in by.most_common(15):
            ls = sorted(set(x[0] for x in problems if x[1] == w))[:6]
            print(f'  {w}: {c}, строки {ls}')
        dep = block_dependency(p, prefix)
        print(f'  вставка {prefix}: имена, объявленные ТОЛЬКО вне вставки (риск потери при переносе): {len(dep)}')
        for w, ls in sorted(dep.items()):
            print(f'    {w}: строки {sorted(set(ls))[:6]}')