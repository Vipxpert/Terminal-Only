#!/usr/bin/env python3
# /llm_harness/harness.py
# llm_harness: declarative patch / probe / undo / git harness for LLM-driven edits.
# Stdlib only, OS-agnostic, pure-ASCII source. Reads one payload from stdin per run.
# Install: save next to workflow_commands.txt in one folder (e.g. ~/.llm_harness), then run:
#   python harness.py --workspace "<project folder>"
import os, sys, re, json, glob, time, zlib, base64, fnmatch, hashlib, shutil, contextlib, subprocess, warnings

VERSION = "3.15"
WORKSPACE_NOTES_DIR = ".llm_harness"
MODE = "git"
HARNESS_DIR = os.path.join(".git", "llm_harness")
SHARED_DIR, GIT_DIR = HARNESS_DIR, ".git"
HISTORY_DIR = os.path.join(HARNESS_DIR, "history")
STATE_PATH = os.path.join(HARNESS_DIR, "state.json")
CONFIG_PATH = os.path.join(HARNESS_DIR, "config.json")
GRAPH_PATH = os.path.join(HARNESS_DIR, "graph.json")
WORKSPACE_NOTES_PATH = os.path.join(WORKSPACE_NOTES_DIR, "notes.md")
GOAL_PATH = os.path.join(WORKSPACE_NOTES_DIR, "goal.md")
SELF_PATH = os.path.abspath(__file__)
SELF_DIR = os.path.dirname(SELF_PATH)
RULES_PATH = os.path.join(SELF_DIR, "workflow_commands.txt")
TREE_MASTER = "docs/trees/tree_master.txt"
MAX_HISTORY, PROBE_CAP, XREF_CAP, LIST_CAP = 50, 500, 80, 400
GREP_CAP, RUN_HEAD, RUN_TAIL, RUN_TIMEOUT = 150, 40, 120, 300
SKIP_DIRS = {".git", ".llm_harness", "venv", ".venv", "node_modules", "__pycache__", "dist", "build", "target", ".next"}
BT3 = chr(96) * 3
SENT_BT3 = "@@" + "BT3" + "@@"
T_MID = chr(0x251c) + chr(0x2500) * 2 + " "
T_END = chr(0x2514) + chr(0x2500) * 2 + " "
T_BAR = chr(0x2502)
OLD_M, NEW_M, END_M = "--- [OLD CODE] ---", "+++ [NEW CODE] +++", "=== [END HUNK] ==="
TXT_OLD, TXT_NEW, TXT_END = "--- [OLD TEXT] ---", "+++ [NEW TEXT] +++", "=== [END TEXT] ==="
TEXT_MIN = 12
LINE_M = "+++ [LINE EDITS] +++"

def apply_line_edits(old, edits):
    """New lines from a hunk's verified OLD CODE plus 'N: text' (replace), 'N-' (delete) and 'N+ text' (insert after N; 0 = before line 1). -> (lines, error)"""
    repl, dels, ins = {}, set(), {}
    for raw in edits:
        if not raw.strip():
            continue
        m = re.match(r"^(\d+)([:+-])(.*)$", raw)
        if not m:
            return None, "line edit '%s' is not 'N: text', 'N-' or 'N+ text'" % raw.strip()
        k, op, rest = int(m.group(1)), m.group(2), m.group(3)
        rest = rest[1:] if rest.startswith(" ") else rest
        if not (0 if op == "+" else 1) <= k <= len(old):
            return None, "line %d is outside the %d recited OLD CODE lines" % (k, len(old))
        if op == "+":
            ins.setdefault(k, []).append(rest)
        elif k in repl or k in dels:
            return None, "line %d is edited twice" % k
        elif op == "-":
            if rest.strip():
                return None, "'%d-' deletes the line and takes no text" % k
            dels.add(k)
        else:
            repl[k] = rest
    if not (repl or dels or ins):
        return None, "no line edits under %s" % LINE_M
    out = list(ins.get(0, []))
    for n_, line in enumerate(old, 1):
        if n_ not in dels:
            out.append(repl.get(n_, line))
        out.extend(ins.get(n_, []))
    return out, None

# ---------------------------------------------------------------- Stage: IO helpers

def norm_nl(s):
    return s.replace("\r\n", "\n").replace("\r", "\n")

def load_json(path, default):
    for attempt in range(6):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (OSError, ValueError):
            # Comment (constraint): on Windows a reader's open() is refused for a moment while another chat replaces the file, and returning the default then read a live sessions.json as "no scope"; try again a few times before giving up
            if attempt == 5:
                return default
            time.sleep(0.01 * (attempt + 1))
    return default

def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Comment (invariant): other chats read these files without the state lock, so a file must never be seen half-written (an empty sessions.json read as "no scope" refused a chat its own change); write a temp file and replace the target in one step
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=True, indent=1)
    for _ in range(60):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            # Comment (workaround): on Windows the replace fails while a reader has the file open; wait for it to finish
            time.sleep(0.05)
    # Comment (workaround): after about three seconds of a reader holding the file open, an in-place write beats crashing the run; the half-written window is then back, but only under that much contention
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=True, indent=1)
    try:
        os.remove(tmp)
    except OSError:
        pass

def decode_bytes(raw):
    """Bytes -> (LF text, meta). Meta keeps EOL style and BOM so untouched lines round-trip byte-exact."""
    text = raw.decode("utf-8", "surrogateescape")
    bom = text.startswith("\ufeff")
    if bom:
        text = text[1:]
    crlf = text.count("\r\n")
    eol = "\r\n" if crlf and crlf * 2 >= text.count("\n") else "\n"
    return norm_nl(text), {"eol": eol, "bom": bom}

def encode_text(text, meta):
    body = text.rstrip("\n") + "\n"
    if meta["eol"] != "\n":
        body = body.replace("\n", meta["eol"])
    if meta["bom"]:
        body = "\ufeff" + body
    return body.encode("utf-8", "surrogateescape")

def default_meta(rel):
    return {"eol": "\r\n" if rel.lower().endswith((".bat", ".cmd")) else "\n", "bom": False}

def read_bytes(rel):
    with open(rel, "rb") as f:
        return f.read()

def write_bytes(rel, data):
    os.makedirs(os.path.dirname(rel) or ".", exist_ok=True)
    with open(rel, "wb") as f:
        f.write(data)

def read_text(rel):
    return decode_bytes(read_bytes(rel))[0]

def sha_bytes(data):
    return None if data is None else hashlib.sha1(data).hexdigest()

def sha_of(rel):
    return sha_bytes(read_bytes(rel)) if os.path.isfile(rel) else None

def pack(data):
    return None if data is None else base64.b64encode(zlib.compress(data, 9)).decode("ascii")

def unpack(s):
    return None if s is None else zlib.decompress(base64.b64decode(s))

def safe_rel(p, allow_root=False):
    """Normalize a payload path to a workspace-relative path; None when it escapes the workspace or targets git or harness internals."""
    p = p.strip().replace("\\", "/").lstrip("/")
    root = os.path.realpath(os.path.abspath("."))
    full = os.path.realpath(os.path.join(root, p or "."))
    try:
        if os.path.commonpath((root, full)) != root:
            return None
    except ValueError:
        return None
    if full == root:
        return "." if allow_root else None
    rel = os.path.relpath(full, root).replace("\\", "/")
    if rel in (".git", WORKSPACE_NOTES_DIR) or rel.startswith((".git/", WORKSPACE_NOTES_DIR + "/")):
        return None
    return rel

def decode_payload(raw):
    """Stdin bytes -> payload text: UTF-8 (BOM tolerated), LF, NBSP -> space, UI-safe sentinels decoded."""
    txt = norm_nl(raw.decode("utf-8-sig", "replace")).replace("\u00a0", " ")
    txt = re.sub(r"([A-Za-z][A-Za-z0-9+.\-]*)@@://", r"\1://", txt)
    return txt.replace(SENT_BT3, BT3)

# ---------------------------------------------------------------- Stage: Line-1 header and tree glyphs

# Comment (decision): this table is how the harness learns a language's comment syntax: a line marker ('// ', '# ', '-- ') or, for formats that only have block comments (HTML, XML, CSS), an opening marker plus a closing suffix; the first-line header, its repair and its placement all read it, so a new language is one more entry here
HDR_PREFIX = {".py": "# ", ".sh": "# ", ".txt": "# ", ".yaml": "# ", ".yml": "# ", ".toml": "# ", ".ps1": "# ",
              ".go": "// ", ".js": "// ", ".mjs": "// ", ".cjs": "// ", ".jsx": "// ", ".ts": "// ", ".tsx": "// ",
              ".c": "// ", ".h": "// ", ".cpp": "// ", ".cc": "// ", ".cxx": "// ", ".hpp": "// ", ".hh": "// ",
              ".cs": "// ", ".java": "// ", ".kt": "// ", ".kts": "// ", ".rs": "// ", ".swift": "// ", ".dart": "// ", ".scala": "// ", ".php": "// ",
              ".sql": "-- ", ".lua": "-- ",
              ".vue": "<!-- ", ".html": "<!-- ", ".htm": "<!-- ", ".xml": "<!-- ", ".css": "/* ", ".scss": "/* ",
              ".cmd": ":: # ", ".bat": ":: # "}
HDR_SUFFIX = {".vue": " -->", ".html": " -->", ".htm": " -->", ".xml": " -->", ".css": " */", ".scss": " */"}
HDR_LIKE = re.compile(r"^(?:# |// |-- |:: # )/\S+$|^<!-- /\S+ -->$|^/\* /\S+ \*/$")
CODING_RE = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")
_PROJECT = []

def project_name():
    if not _PROJECT:
        _PROJECT.append(load_json(CONFIG_PATH, {}).get("project") or os.path.basename(os.path.abspath(".")))
    return _PROJECT[0]

def ensure_line1_header(rel, text):
    """Keep the '/<project>/<path>' comment as the first line, below a shebang or coding cookie when present."""
    ext = os.path.splitext(rel)[1].lower()
    if ext not in HDR_PREFIX or os.path.abspath(".") == SELF_DIR:
        return text, "N/A"
    lines = text.split("\n")
    hdr = HDR_PREFIX[ext] + "/" + project_name() + "/" + rel + HDR_SUFFIX.get(ext, "")
    status = "Valid"
    if len(lines) > 1 and HDR_LIKE.match(lines[0]) and lines[1].startswith("#!"):
        lines[0], lines[1] = lines[1], lines[0]
        status = "Auto-Repaired"
    idx = 1 if lines[0].startswith("#!") else 0
    if ext == ".py" and idx < len(lines) and CODING_RE.match(lines[idx]):
        idx += 1
    # Comment (constraint): some formats must open with their own line, so the header goes below it: an HTML doctype (a comment above it puts old browsers into quirks mode), an XML declaration (it must be the very first thing in the file), and PHP's opening tag (a PHP file that starts with plain text is left alone, because a comment above the tag would be sent to the browser as text)
    if idx < len(lines) and ((ext in (".html", ".htm") and lines[idx].lstrip().lower().startswith("<!doctype")) or (ext == ".xml" and lines[idx].startswith("<?xml")) or (ext == ".php" and lines[idx].startswith("<?php"))):
        idx += 1
    if ext == ".php" and not (idx > 0 and lines[idx - 1].startswith("<?php")):
        return "\n".join(lines), "N/A"
    if idx < len(lines) and lines[idx] == hdr:
        return "\n".join(lines), status
    if idx < len(lines) and HDR_LIKE.match(lines[idx]):
        lines[idx] = hdr
    else:
        lines.insert(idx, hdr)
    return "\n".join(lines), "Auto-Repaired"

def is_tree_file(rel):
    return rel.startswith("docs/trees/") and rel.endswith(".txt")

def sanitize_tree(rel, text):
    """Tree files only: ASCII connectors -> box glyphs, vertical guide bars -> spaces."""
    if not is_tree_file(rel):
        return text
    t = re.sub(r"(?m)^( *)\|-- +", lambda m: m.group(1) + T_MID, text)
    t = re.sub(r"(?m)^( *)[\\" + chr(96) + r"]-- +", lambda m: m.group(1) + T_END, t)
    return t.replace(T_BAR + "   ", "    ")

# ---------------------------------------------------------------- Stage: Scope resolution

_MOD = r"(?:(?:export|default|public|private|protected|internal|static|abstract|async|final|sealed|partial|virtual|readonly|extern|override|unsafe|open|data|inline|suspend|inner|companion|mutating|synchronized|native|constexpr|operator|infix|tailrec|external|lateinit|pub(?:\([^)]*\))?)\s+)*"
DEF_KW = re.compile(r"^\s*" + _MOD + r"(class|def|func|function|fn|type|interface|struct|enum|trait|impl|namespace)\b\*?\s*(?:\(([^)]*)\)\s*)?([A-Za-z_$][\w$]*)?")
JS_METHOD = re.compile(r"^\s*" + _MOD + r"(?:get\s+|set\s+)?(?!(?:if|for|while|switch|catch|return|else|do|try|with|function|await|new|throw|typeof)\b)(?!(?:synchronized|using|lock|foreach|fixed|checked|unchecked)\s+\()([A-Za-z_$][\w$]*)\s*\([^()]*\)\s*(?::\s*[^={;]+)?\{\s*$")
JS_ASSIGN = re.compile(r"^\s*" + _MOD + r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:function\b|\([^()]*\)\s*(?::[^=]+)?=>|[A-Za-z_$][\w$]*\s*=>)")
JS_PROP = re.compile(r"^\s*([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?(?:function\b|\([^()]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)")
VUE_OPT = re.compile(r"^\s*(methods|computed|watch|props|emits|components)\s*:\s*[\{\[]")
SFC_BLOCK = re.compile(r"^<(template|script|style)\b")
# Comment (decision): harness.py's own stage comments carry a run of dashes ("# ----- Stage: IO helpers") and workflow_commands.txt sections are "#* Heading" lines; the plain pattern never matched either, so every tree node for them read as stale
ANCHOR_RE = re.compile(r"^\s*(?:(?:#|//|<!--|--|;|::)\s*#?\s*[-=*]*\s*(?:Stage|Step)\b|#\*\s+\S)")
TOC_EXTRA = re.compile(r"^\s*@\w|\b(?:HandleFunc|Handle|GET|POST|PUT|PATCH|DELETE)\(|\b(?:app|router)\.(?:get|post|put|patch|delete|use)\(")
IDENT = re.compile(r"^[A-Za-z_$][\w$]*(?:\(\))?$")
DOTTED = re.compile(r"^[A-Za-z_$][\w$]*(?:(?:\.|::)[A-Za-z_$][\w$]*)+(?:\(\))?$")
SKIPPABLE = ("#", "//", "/*", "*/", "<!--")
CLOSERS = ("}", ")", "]", "</")
# Comment (decision): Java, C#, Kotlin, Swift, C and C++ declare methods as '[modifiers] ReturnType name(args)', which the keyword patterns above cannot see; a line counts as such a definition only with a modifier (constructors too), or with a type-shaped return type and a parameter list shaped like 'Type name' (so Unity's 'void Start()' with the brace on the next line is found), and never when it begins with a control-flow word or reads like prose, so calls, conditions and Python or JS statements are not mistaken for definitions
BRACE_TYPE = re.compile(r"^\s*" + _MOD + r"(?:record|object|protocol|extension|mod|actor)\s+(?:<[^>]*>\s*)?([A-Za-z_]\w*)((?:\s*<[^<>]*>)?(?:\s*\([^()]*\))?(?:\s*:[^{;]*)?(?:\s+where\s+[^{;]+)?\s*[{;]?\s*)$")

def brace_type(line):
    """(name, None) for 'object Config {', 'record Point(int x)', 'mod tests;' and similar; a lowercase name needs a '{' or ';' after it, so prose that starts with 'object' or 'record' is not a definition."""
    m = BRACE_TYPE.match(re.sub(r"\s+//.*$", "", line))
    if m and (m.group(1)[0].isupper() or re.search(r"[{;]", m.group(2))):
        return m.group(1), None
    return None
KOTLIN_FUN = re.compile(r"^\s*" + _MOD + r"fun\s+(?:<[^>]*>\s*)?(?:[\w<>?,]+\.)*([A-Za-z_]\w*)\s*\(")
_NOT_WORD = r"(?!(?:return|new|await|throw|yield|else|case|using|lock|foreach|for|while|if|switch|catch|do|assert|print|del|raise|elif|import|from|with|global|nonlocal|goto|delete|typeof|sizeof|var|let|const|in|is|as|not|and|or|go|defer|select|func|type|chan|range|package|map|def|class|fn|fun|struct|enum|interface|try|finally|except|lambda|pass|break|continue|extends|implements|where|match|loop|when|unless|until|elsif|None|True|False|null|nil|true|false|this|self|super|base)\b)"
BRACE_METHOD = re.compile(r"^(\s*)(" + _MOD + r")((?:" + _NOT_WORD + r"(?=\S*\w)[\w<>\[\],.?*&:]+\s+)*)(?:[\w$]+::)*" + _NOT_WORD + r"([A-Za-z_]\w*)\s*(?:<[^>()]*>)?\s*\(((?:[^;{}()]|\([^()]*\))*)\)(?:\s+(?:const|noexcept|override|final|volatile))*(?:\s+throws\s+[\w.,\s]+)?(?:\s+where\s+[^{;=]+)?(?:\s*:[^;{=]*)?\s*(?:=>[^;]*;?|\{\s*)?$")
ATTR_LINE = re.compile(r"^\[[A-Za-z_][\w.]*(?:\(.*\))?(?:\s*,\s*[A-Za-z_][\w.]*(?:\(.*\))?)*\]$")

_TYPE_SHAPE = re.compile(r"^(?:void|int|long|short|byte|char|float|double|bool|boolean|string|decimal|object|var|auto|unsigned|signed|\w+_t|[A-Z][\w.]*(?:<[^<>]*>)?(?:\[\])*\??\*?|\w+<[^<>]*>\??|\w+\*+|\w+\[\])$")
_PARAM_ITEM = re.compile(r"^\s*(?:\[[^\]]*\]\s*|@\w+(?:\([^)]*\))?\s+)*(?:(?:ref|out|in|params|final|const|this)\s+)*[\w.?*&:]+(?:<[^<>]*>)?(?:\[\])*\??\*?\s+[A-Za-z_]\w*\s*(?:=\s*.*)?$")

def params_ok(args):
    """True for an empty parameter list or one whose items all read 'Type name' (with optional attributes, ref/out and a default value)."""
    if not args.strip():
        return True
    items, depth, cur = [], 0, ""
    for ch in args:
        depth += (ch in "<([") - (ch in ">)]")
        if ch == "," and depth <= 0:
            items.append(cur)
            cur = ""
        else:
            cur += ch
    items.append(cur)
    return all(_PARAM_ITEM.match(i) for i in items)

def brace_def(line):
    """(name, None) for a Java/C#/Kotlin/C/C++ style method or constructor line, else None."""
    code = re.sub(r"\s+//.*$", "", line)
    m = BRACE_METHOD.match(code)
    if not m:
        return None
    mods, types, name, args = m.group(2), m.group(3), m.group(4), m.group(5)
    if not params_ok(args):
        return None
    if re.sub(r"\b(?:export|default)\b", "", mods).strip():
        return name, None
    toks = types.split()
    if 1 <= len(toks) <= 2 and len(code.strip()) <= 140 and "  " not in code.strip() and _TYPE_SHAPE.match(toks[-1]):
        return name, None
    return None

def def_info(line):
    """(defined_name, receiver_type) when the line opens a class/function/method/SFC block, else None."""
    m = SFC_BLOCK.match(line)
    if m:
        return m.group(1), None
    m = DEF_KW.match(line)
    if m:
        if not m.group(3):
            return None
        recv = None
        if m.group(2):
            ids = re.findall(r"[A-Za-z_]\w*", re.sub(r"\[.*?\]", "", m.group(2)))
            recv = ids[-1] if ids else None
        return m.group(3), recv
    for rx in (JS_METHOD, JS_ASSIGN, JS_PROP, VUE_OPT, KOTLIN_FUN):
        m = rx.match(line)
        if m:
            return m.group(1), None
    return brace_type(line) or brace_def(line)

def is_toc_line(line):
    return bool(def_info(line) or ANCHOR_RE.match(line) or TOC_EXTRA.search(line))

def indent_of(line):
    return len(line) - len(line.lstrip())

def norm_ws(s):
    return " ".join(s.split())

_CODE_STRIP = re.compile(r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|/\*.*?\*/|//.*$)")
_CODE_STRIP_HASH = re.compile(r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|/\*.*?\*/|#.*$|//.*$)")

def code_only(ln, hash_comments=True):
    """A line without its strings and comments (escaped quotes, backtick strings and one-line /* */ handled), so names and braces inside them are not counted."""
    return (_CODE_STRIP_HASH if hash_comments else _CODE_STRIP).sub(" ", ln)

def brace_block_end(lines, i):
    """For a brace-language definition (its header reaches a line ending in an opening or closing brace within 8 lines, with no line ending in ':' or ';' before it) the line after its matching closing brace; None for anything else (Python, or braces that never balance), so the indentation rule decides there."""
    n, opened = len(lines), False
    for j in range(i, min(i + 8, n)):
        s = code_only(lines[j], False).rstrip()
        if s.endswith(("{", "}")):
            opened = True
            break
        if s.endswith((":", ";")):
            return None
    if not opened:
        return None
    depth, seen = 0, False
    for j in range(i, n):
        for ch in code_only(lines[j], False):
            if ch == "{":
                depth, seen = depth + 1, True
            elif ch == "}":
                depth -= 1
        if seen and depth <= 0:
            return j + 1
    return None

def block_bounds(lines, i, anchor):
    """Line range [start, end) of the block opened at line i (a definition, or a '# Stage' style anchor)."""
    n, base = len(lines), indent_of(lines[i])
    m = SFC_BLOCK.match(lines[i])
    if m:
        for j in range(i + 1, n):
            if lines[j].startswith("</" + m.group(1)):
                return i, j + 1
        return i, n
    end = n
    # Comment (decision): in a brace language a line at the definition's own indent can continue its header (a C# where clause) or sit in its body (a C label), so the indentation rule ended the block too early; the matching closing brace decides there, and the indentation rule stays for Python and for braces that never balance
    braced = None if anchor else brace_block_end(lines, i)
    if braced:
        end = braced
    for j in range(i + 1, i + 1 if braced else n):
        s = lines[j].strip()
        if not s:
            continue
        ind = indent_of(lines[j])
        if anchor:
            if (ind <= base and ANCHOR_RE.match(lines[j])) or (ind < base and not s.startswith(SKIPPABLE)):
                end = j
                break
        elif not s.startswith(SKIPPABLE) and (ind < base or (ind == base and not (s.startswith(CLOSERS) or s == "{"))):
            end = j
            break
    start = i
    if not anchor:
        while not braced and end - 1 > i and (not lines[end - 1].strip() or (indent_of(lines[end - 1]) <= base and (lines[end - 1].strip().startswith(SKIPPABLE + ("@",)) or ATTR_LINE.match(lines[end - 1].strip())))):
            end -= 1
        while start > 0 and (lines[start - 1].strip().startswith(SKIPPABLE + ("@", "*")) or ATTR_LINE.match(lines[start - 1].strip())) and 0 <= indent_of(lines[start - 1]) - base <= 1:
            start -= 1
    else:
        while end - 1 > i and not lines[end - 1].strip():
            end -= 1
    return start, end

def split_scope(scope):
    segs = []
    for part in scope.split(" > "):
        part = part.strip()
        if not part:
            continue
        if DOTTED.match(part):
            segs.extend(x for x in re.split(r"\.|::", re.sub(r"\(\)$", "", part)) if x)
        else:
            segs.append(part)
    return segs

def resolve_code_scope(lines, scope):
    """Scope path -> (start, end, note). note is None when every segment resolved to exactly one block."""
    if scope.strip().lower() in ("<top>", "top"):
        return 0, len(lines), None
    segs = split_scope(scope)
    lo, hi, n, k = 0, len(lines), len(lines), 0
    while k < len(segs):
        seg = segs[k]
        if IDENT.match(seg):
            name = re.sub(r"\(\)$", "", seg)
            if k + 1 < len(segs) and IDENT.match(segs[k + 1]):
                nxt = re.sub(r"\(\)$", "", segs[k + 1])
                pair = [j for j in range(lo, hi) if def_info(lines[j]) == (nxt, name)]
                if len(pair) == 1:
                    lo, hi = block_bounds(lines, pair[0], False)
                    k += 2
                    continue
            hits = [j for j in range(lo, hi) if (def_info(lines[j]) or (None,))[0] == name]
            if not hits and k > 0:
                py_re = re.compile(r"^\s*(?:async\s+)?def\s+" + re.escape(name) + r"\s*\(")
                hits = [j for j in range(lo, hi) if py_re.match(lines[j])]
            anchor = False
        else:
            key = norm_ws(seg)
            hits = [j for j in range(lo, hi) if key in norm_ws(lines[j])]
            hits = [j for j in hits if lines[j].strip().startswith(SKIPPABLE)] or hits
            anchor = True
        if not hits:
            return 0, n, "scope segment '%s' not found" % seg
        if len(hits) > 1:
            where = ", ".join(str(j + 1) for j in hits[:6])
            return 0, n, "scope segment '%s' matches %d places (lines %s); qualify it as Parent > %s" % (seg, len(hits), where, seg)
        lo, hi = block_bounds(lines, hits[0], anchor)
        k += 1
    return lo, hi, None

def tree_split(line):
    s = line.lstrip(" ")
    pad = len(line) - len(s)
    for c in (T_MID, T_END, "|-- ", "\\-- "):
        if s.startswith(c):
            return pad // 4 + 1, s[len(c):].strip()
    return pad // 4, s.strip()

def tree_nodes(lines):
    """[(line_index, depth, label)] for every node line of a tree file (Line-1 header and blanks skipped)."""
    out = []
    for i, ln in enumerate(lines):
        if not ln.strip() or (i == 0 and HDR_LIKE.match(ln)):
            continue
        d, label = tree_split(ln)
        out.append((i, d, label))
    return out

def tree_key(label):
    k = label.split(" (", 1)[0].strip()
    k = re.sub(r"^(?:->|\(\))\s*", "", k)
    return re.sub(r"\(\)$", "", k).strip()

def tree_path(nodes, k):
    out, d = [tree_key(nodes[k][2])], nodes[k][1]
    for j in range(k - 1, -1, -1):
        if nodes[j][1] < d:
            d = nodes[j][1]
            out.append(tree_key(nodes[j][2]))
    return " > ".join(reversed(out))

def tree_children_hint(nodes, lo, hi, cur):
    """For a tree node that was not found: where the search looked and the names at that level, so a selector is copied instead of guessed."""
    if lo >= hi:
        return ""
    top = min(nodes[j][1] for j in range(lo, hi))
    names = [tree_key(nodes[j][2]) for j in range(lo, hi) if nodes[j][1] == top]
    where = " under " + tree_path(nodes, cur) if cur is not None else ""
    more = " +%d more" % (len(names) - 12) if len(names) > 12 else ""
    return "%s; the nodes there are: %s%s" % (where, ", ".join(names[:12]), more)

def resolve_tree_scope(lines, scope):
    """Node path -> (start, end, note, (nodes, first, stop)). Segments may skip levels but must be unique."""
    nodes = tree_nodes(lines)
    lo, hi, cur = 0, len(nodes), None
    for seg in [s.strip() for s in scope.split(" > ") if s.strip()]:
        key = tree_key(seg)
        cands = [j for j in range(lo, hi) if seg in nodes[j][2] or key in nodes[j][2]]
        exact = [j for j in cands if tree_key(nodes[j][2]) == key or tree_key(nodes[j][2]).split(" / ")[0] == key]
        cands = exact or cands
        if not cands:
            return 0, len(lines), "node '%s' not found%s" % (seg, tree_children_hint(nodes, lo, hi, cur)), None
        if len(cands) > 1:
            paths = "; ".join(tree_path(nodes, j) for j in cands[:6])
            return 0, len(lines), "node '%s' matches %d places (%s); qualify it as Parent > %s" % (seg, len(cands), paths, seg), None
        cur = cands[0]
        end = cur + 1
        while end < len(nodes) and nodes[end][1] > nodes[cur][1]:
            end += 1
        lo, hi = cur + 1, end
    if cur is None:
        return 0, len(lines), None, (nodes, 0, len(nodes))
    stop_line = nodes[hi][0] if hi < len(nodes) else len(lines)
    return nodes[cur][0], stop_line, None, (nodes, cur, hi)

def resolve_scope(rel, lines, scope):
    scope = (scope or "").strip()
    if scope.upper() in ("", "TOP"):
        return 0, len(lines), None
    if is_tree_file(rel):
        return resolve_tree_scope(lines, scope)[:3]
    return resolve_code_scope(lines, scope)

# ---------------------------------------------------------------- Stage: Matching

def kx(s):
    return s.rstrip().replace("\u00a0", " ")

def kf(s):
    return s.strip().replace("\u00a0", " ")

def find_exact(lines, needle, lo, hi):
    keys = [kx(x) for x in needle]
    n = len(keys)
    return [(i, i + n) for i in range(lo, hi - n + 1)
            if kx(lines[i]) == keys[0] and all(kx(lines[i + k]) == keys[k] for k in range(1, n))]

def kw(s):
    return re.sub(r"\s+", " ", kf(s))

def find_loose(lines, needle, lo, hi):
    """Like find_fuzzy, but blind to whitespace inside lines (tabs pasted as spaces, realigned comments)."""
    return find_fuzzy(lines, needle, lo, hi, kw)

def find_fuzzy(lines, needle, lo, hi, key=kf):
    """Indentation-agnostic match that tolerates differing blank lines; returns every candidate span."""
    keys = [key(x) for x in needle if x.strip()]
    out = []
    if not keys:
        return out
    for i in range(lo, hi):
        if key(lines[i]) != keys[0]:
            continue
        j, k, last = i, 0, i
        while j < hi and k < len(keys):
            s = key(lines[j])
            if s:
                if s != keys[k]:
                    break
                last, k = j, k + 1
            j += 1
        if k == len(keys):
            out.append((i, last + 1))
    return out

def first_nonblank(xs):
    for x in xs:
        if x.strip():
            return x
    return ""

def reindent(disk_first, needle_first, repl_lines):
    """Shift replacement lines by the indentation delta between the on-disk block and the payload block."""
    dws = disk_first[:indent_of(disk_first)]
    nws = needle_first[:indent_of(needle_first)]
    if dws == nws:
        return list(repl_lines)
    tabs = "\t" in dws
    def width(ws):
        return len(ws.replace("    ", "\t")) if tabs else len(ws.replace("\t", "    "))
    delta, unit, out = width(dws) - width(nws), ("\t" if tabs else " "), []
    for rl in repl_lines:
        if not rl.strip():
            out.append("")
        else:
            out.append(unit * max(0, width(rl[:indent_of(rl)]) + delta) + rl.lstrip())
    return out

def apply_match(rel, content, scope, find_s, repl_s):
    """Scope-first unique matching. -> (new_content, status, detail); status is OK / ALREADY APPLIED / MISMATCH / AMBIGUOUS."""
    lines = content.split("\n")
    repl = repl_s.split("\n") if repl_s else []
    if (scope or "").strip().upper() == "EOF":
        if find_s:
            return content, "MISMATCH", "scope EOF appends to the file: OLD CODE must be empty"
        if not repl:
            return content, "MISMATCH", "scope EOF with empty NEW CODE"
        if find_exact(lines, repl, 0, len(lines)):
            return content, "ALREADY APPLIED", None
        base = content.rstrip("\n")
        return (base + "\n" if base else "") + repl_s + "\n", "OK", None
    if not find_s:
        return content, "MISMATCH", "empty OLD CODE (use scope EOF to append, or include the lines to replace)"
    needle = find_s.split("\n")
    lo, hi, note = resolve_scope(rel, lines, scope)
    spans = [(lo, hi)] if note is None and (lo, hi) != (0, len(lines)) else []
    spans.append((0, len(lines)))
    for idx, (a, b) in enumerate(spans):
        for finder, fuzzy in ((find_exact, False), (find_fuzzy, True), (find_loose, True)):
            hits = finder(lines, needle, a, b)
            if len(hits) == 1:
                s, e = hits[0]
                block = reindent(lines[s], first_nonblank(needle), repl) if fuzzy else repl
                where = "matched outside the named scope, at line %d" % (s + 1) if idx == 1 and len(spans) == 2 else note
                if finder is find_loose:
                    where = "; ".join(x for x in (where, "matched ignoring whitespace inside lines") if x)
                return "\n".join(lines[:s] + block + lines[e:]), "OK", where
            if len(hits) > 1:
                where = ", ".join(str(h[0] + 1) for h in hits[:8])
                tip = note or "add distinguishing context lines or a narrower scope"
                return content, "AMBIGUOUS", "OLD CODE matches %d places (lines %s); %s" % (len(hits), where, tip)
    if repl:
        for a, b in spans:
            rh = find_exact(lines, repl, a, b) or find_fuzzy(lines, repl, a, b)
            if len(rh) == 1:
                return content, "ALREADY APPLIED", None
    if len(needle) == 1 and needle[0].strip():
        part = [i for i, l in enumerate(lines) if needle[0].strip() in l and l.strip() != needle[0].strip()]
        if len(part) == 1:
            return content, "MISMATCH", "OLD CODE is only part of line %d; hunks match whole lines, so copy that full line into OLD CODE" % (part[0] + 1)
    return content, "MISMATCH", note

def print_diagnostics(rel, content, scope, find_s, status, detail):
    """On-disk excerpt for a failed hunk: Stage A best window, Stage B scope head, Stage C signature TOC."""
    lines = content.split("\n")
    tot = len(lines)
    print("\n--- [%s] /%s | Scope: %s%s ---" % (status, rel, scope, (" | " + detail) if detail else ""))
    if status == "AMBIGUOUS" or not find_s:
        return
    lo, hi, note = resolve_scope(rel, lines, scope)
    scoped = note is None and (lo, hi) != (0, tot)
    keys = [kf(l) for l in find_s.split("\n") if len(l.strip()) >= 4]
    toks = set(re.findall(r"[A-Za-z_]\w{2,}", find_s))
    win = max(5, len(find_s.split("\n")))
    line_toks = [set(re.findall(r"[A-Za-z_]\w{2,}", l)) for l in lines]
    best, best_i = 0, -1
    for i in range(lo, hi):
        chunk = range(i, min(hi, i + win))
        cl = set(kf(lines[j]) for j in chunk)
        lh = sum(1 for k in keys if k in cl)
        th = len(toks & set().union(*[line_toks[j] for j in chunk])) if toks else 0
        if (lh >= 1 or (toks and th * 2 >= len(toks))) and lh * 4 + th > best:
            best, best_i = lh * 4 + th, i
    if best_i >= 0:
        a, b, stage = max(lo, best_i - 8), min(hi, best_i + win + 12), "A (closest on-disk block)"
    elif scoped:
        a, b, stage = lo, min(hi, lo + 40), "B (start of resolved scope)"
    else:
        print("--- ON-DISK SIGNATURE TOC [Lines 1-%d of %d | Stage: C] ---" % (tot, tot))
        for i, l in enumerate(lines):
            if is_toc_line(l):
                print("  L%d: %s" % (i + 1, l.rstrip()[:110]))
        return
    print("--- ON-DISK CODE [Lines %d-%d of %d | Stage: %s] ---" % (a + 1, b, tot, stage))
    print("\n".join(lines[a:b]))

# ---------------------------------------------------------------- Stage: Syntax checks and rollback

def restore_pre(rel, raw, mode):
    if raw is None:
        if os.path.isfile(rel):
            os.remove(rel)
        return
    write_bytes(rel, raw)
    if mode is not None and os.name == "posix":
        os.chmod(rel, mode)

def run_tool(args, cwd=None):
    """Run an external tool; returncode None means the tool is not installed."""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout, r.stderr
    except OSError:
        return None, "", ""

def check_files(changed, pre):
    """Syntax-check changed files; restore the pre-image on Python or gofmt syntax errors. -> ({rel: status}, rolled_back)"""
    status, rolled = {}, set()
    for rel in changed:
        if not os.path.isfile(rel):
            status[rel] = "DELETED"
            continue
        if rel.endswith(".py"):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    compile(read_bytes(rel), rel, "exec", dont_inherit=True)
                status[rel] = "PASS"
            except Exception as e:
                restore_pre(rel, pre[rel]["raw"], pre[rel]["mode"])
                rolled.add(rel)
                status[rel] = "SYNTAX ERROR -> restored (%s)" % " ".join(str(e).split())[:160]
        elif rel.endswith(".go"):
            before = sha_of(rel)
            rc, out, err = run_tool(["gofmt", "-e", "-w", rel])
            if rc is None:
                status[rel] = "UNCHECKED (gofmt not found)"
            elif rc != 0:
                msg = ((err or out).strip().splitlines() or ["syntax error"])[0]
                restore_pre(rel, pre[rel]["raw"], pre[rel]["mode"])
                rolled.add(rel)
                status[rel] = "GOFMT ERROR -> restored (%s)" % msg[:160]
            elif sha_of(rel) != before:
                status[rel] = "PASS (formatted by gofmt, e.g. spaces from the chat turned back into tabs)"
            else:
                status[rel] = "PASS"
        elif rel.endswith(".json"):
            try:
                json.loads(read_text(rel))
                status[rel] = "PASS"
            except ValueError as e:
                status[rel] = "WARN_JSON (%s)" % str(e)[:120]
        else:
            status[rel] = "UNCHECKED"
    go_files = [f for f in changed if f.endswith(".go") and os.path.isfile(f) and f not in rolled]
    mod_dir = None
    for gf in go_files:
        d = os.path.dirname(os.path.abspath(gf))
        while d and d != os.path.dirname(d) and not mod_dir:
            if os.path.isfile(os.path.join(d, "go.mod")):
                mod_dir = d
            d = os.path.dirname(d)
    if mod_dir:
        rc, out, err = run_tool(["go", "build", "./..."], cwd=mod_dir)
        if rc is None:
            for gf in go_files:
                status[gf] += " | build UNCHECKED (go not found)"
        elif rc != 0:
            err_txt = (err or out).strip()
            for gf in go_files:
                status[gf] = "BUILD_PENDING (%s)" % (err_txt.splitlines() or ["error"])[0][:160]
            print("\n=== COMPILER DIAGNOSTICS ===\n" + err_txt)
    run_project_checks(changed, status, rolled)
    return status, rolled

# ---------------------------------------------------------------- Stage: Payload parser

DIRECTIVES = ("@SCRIPT @WORKSPACE @GOAL @FILE @HUNK @NEW_FILE @DELETE_FILE @RENAME @RUN @RUN_ALWAYS @RUN_BLOCK "
              "@PROBE @XREF @FIND @GREP @LIST_DIR @LIST_RECURSIVE @INIT_DEBUG @UNDO @GIT_INIT @GIT_STATUS @GIT_COMMIT @GIT_FOLD @GIT_BRANCH @GIT_WORKTREE @GIT_TAG @GIT_PUSH @GIT_PULL @GIT_MERGE @GIT_ACCOUNT @GIT_REMOTE @STEWARD @TAKEOVER @CHAT_LINK @KB @PLAYBOOK @SESSIONS @HISTORY @L1_REFRESH @L1_PROOF @SIDE "
              "@NOTE_ADD @NOTE_EDIT @NOTE_REMOVE @NOTE_PIN @NOTE_BRIEF @NOTE_LIST @HELP @SESSION @SCOPE @SCOPE_END @SESSION_END "
              "@MESSAGE @MSG_ACK @WAIT_MSG @PING @SCOPE_REQUEST @DELEGATE @SPLIT @BORROW @RECLAIM @UNCLAIM @GUIDE @ASK_USER @MILESTONE @RETURN @BRAKE @BRAKE_ACK @REPEATABLE @TEXT_REPLACE @VERDICT @VERDICTS @CAMPAIGN @CAMPAIGN_END @PART @REDO")
DEBUG_SKELETON = """# Stage: Symptom & Target Invariant
(replace: exact discrepancy between observed behavior and required state)

# Stage: Functionality & Prerequisite Checklist
(replace: one line per atomic prerequisite, each marked [PASS], [FAIL] or [UNVERIFIED - TEST NEXT])

# Stage: Eliminated Approaches & Touched Scopes
(replace: one line per attempt: [<ACT>-XX] | /path/file (Scope) | Hypothesis | Observed Result. Never retry anything listed here.)

# Stage: Isolation & Telemetry Plan
(replace: next diagnostic action: @XREF on a suspect symbol, @PROBE on an uninspected scope, a minimal reproduction, or a debug-log injection)"""

def parse_payload(txt):
    """One state machine: directives are recognized only outside hunk and file bodies."""
    P = {"id": None, "num": None, "title": "", "workspace": None, "goal": None, "ops": [], "notes": [], "probes": [], "xrefs": [], "helps": [],
         "runs": [], "finds": [], "greps": [],
         "list_dir": [], "list_rec": [], "undo": [], "git": [], "git_status": False, "git_init": False, "side": False, "session": None,
         "scope": None, "scope_end": False, "session_end": False, "session_aim": None, "msgs": [], "msg_acks": [], "wait_msgs": [], "ping": False, "brake_ack": False, "repeatable": False,
         "verdicts": [], "verdict_lists": [], "campaigns": [], "part": None, "warnings": []}
    lines = txt.split("\n")
    n, i, cur_file, stray = len(lines), 0, None, []

    def bad(kind, file, label, why, at):
        P["ops"].append({"type": kind, "file": (file or "?").lstrip("/"), "scope": "-", "label": label, "malformed": "%s (payload line %d)" % (why, at + 1)})

    while i < n:
        ln = lines[i]
        m = re.match(r"^@([A-Z0-9_]+)(?:[ \t]+(.*))?$", ln)
        if not m:
            if ln.strip() and not ln.startswith("#"):
                stray.append(i + 1)
            i += 1
            continue
        d, arg = m.group(1), (m.group(2) or "").strip()
        P.setdefault("seen", set()).add("@" + d)
        if d == "SCRIPT":
            mm = re.match(r"^\[([^\]:]+)(?::\s*([^\]]*))?\]", arg)
            if mm:
                P["id"], P["title"] = mm.group(1).strip(), (mm.group(2) or "").strip()
                num = re.search(r"\d+", P["id"])
                P["num"] = int(num.group(0)) if num else None
        elif d == "WORKSPACE":
            P["workspace"] = arg.strip().strip('"').strip("'")
        elif d == "SESSION":
            name, _, aim = arg.partition("|")
            P["session"] = re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("-") or None
            P["session_aim"] = aim.strip() or None
        elif d == "SCOPE":
            P["scope"] = arg
        elif d == "SCOPE_END":
            P["scope_end"] = arg.strip() or True
        elif d == "SESSION_END":
            P["session_end"] = arg.strip() or True
        elif d == "CHAT_LINK":
            P["chat_link"] = arg.strip()
        elif d in ("MESSAGE", "SCOPE_REQUEST", "BRAKE", "DELEGATE", "RETURN", "SPLIT"):
            P["msgs"].append(({"MESSAGE": "message", "SCOPE_REQUEST": "scope request", "BRAKE": "brake", "DELEGATE": "delegate", "RETURN": "return", "SPLIT": "split"}[d], arg))
        elif d == "VERDICT":
            P["verdicts"].append(arg)
        elif d == "VERDICTS":
            P["verdict_lists"].append(arg)
        elif d in ("CAMPAIGN", "CAMPAIGN_END"):
            P["campaigns"].append((d, arg))
        elif d == "PART":
            pm = re.match(r"^(\d+)\s*/\s*(\d+)$", arg)
            if pm and 1 <= int(pm.group(1)) <= int(pm.group(2)):
                P["part"] = (int(pm.group(1)), int(pm.group(2)))
            else:
                P["warnings"].append("expected '@PART <i>/<n>', e.g. @PART 1/2")
        elif d == "REPEATABLE":
            P["repeatable"] = True
        elif d == "ASK_USER":
            P["ask_user"] = arg.strip() or "(no message)"
        elif d == "MILESTONE":
            P["milestone"] = arg.strip()
        elif d == "BRAKE_ACK":
            P["brake_ack"] = True
        elif d == "GOAL":
            if arg:
                P["goal"] = arg
            else:
                P["warnings"].append("@GOAL needs the goal text, e.g. '@GOAL Port every Python service to Go'")
        elif d in ("RUN", "RUN_ALWAYS"):
            mt = re.match(r"^--timeout\s+(\d+)\s+(.*)$", arg)
            cmd, limit = (mt.group(2), min(3600, int(mt.group(1)))) if mt else (arg, RUN_TIMEOUT)
            nxt = lines[i + 1] if i + 1 < n else ""
            # Comment (invariant): an @RUN is one line, so a line after it that is not blank, not a # comment and not a directive means the command was probably broken across lines (a multi-line python -c, say); running the first line alone could do something else than was meant, so the command is not run
            if cmd.strip() and nxt.strip() and not nxt.startswith("#") and not re.match(r"^@([A-Z0-9_]+)(?:[ \t]+(.*))?$", nxt):
                P["warnings"].append("@RUN at payload line %d is directly followed by a line that is not a directive, so the command was probably cut off at the line break and was not run (an @RUN is one line: use @RUN_BLOCK ... @END_RUN_BLOCK for multi-line commands, or @NEW_FILE + @RUN python <file>)" % (i + 1))
            elif cmd.strip():
                P["runs"].append({"cmd": cmd.strip(), "timeout": max(1, limit), "always": d == "RUN_ALWAYS"})
            else:
                P["warnings"].append("@%s needs a command" % d)
        elif d == "RUN_BLOCK":
            at, always, limit = i, False, RUN_TIMEOUT
            for tok in arg.split():
                if tok.lower() == "always":
                    always = True
            mt = re.search(r"--timeout\s+(\d+)", arg)
            if mt:
                limit = min(3600, int(mt.group(1)))
            i += 1
            body = []
            while i < n and lines[i].strip() != "@END_RUN_BLOCK":
                body.append(lines[i])
                i += 1
            if i >= n:
                P["warnings"].append("@RUN_BLOCK at payload line %d is missing @END_RUN_BLOCK" % (at + 1))
                continue
            cmd = "\n".join(body).strip()
            if cmd:
                P["runs"].append({"cmd": cmd, "timeout": max(1, limit), "always": always})
            else:
                P["warnings"].append("@RUN_BLOCK at payload line %d is empty" % (at + 1))
        elif d == "FIND":
            P["finds"].append(arg)
        elif d == "GREP":
            P["greps"].append(arg)
        elif d == "INIT_DEBUG":
            slug = re.sub(r"[^A-Za-z0-9_-]+", "_", arg).strip("_")
            if not slug:
                P["warnings"].append("@INIT_DEBUG needs a slug, e.g. '@INIT_DEBUG login_loop'")
            else:
                path = "docs/debug/bug_%s.txt" % slug
                P["ops"].append({"type": "new_file", "file": path, "scope": "TOP", "label": "Init debug ledger", "replace": DEBUG_SKELETON, "init": True})
                P["probes"].append("/%s | Lines | 1-200" % path)
        elif d == "FILE":
            cur_file = arg
        elif d == "NEW_FILE":
            j = i + 1
            while j < n and lines[j].rstrip() != "@END_NEW_FILE":
                j += 1
            if j >= n:
                bad("new_file", arg, "Create file", "missing @END_NEW_FILE", i)
            else:
                P["ops"].append({"type": "new_file", "file": arg, "scope": "TOP", "label": "Create file", "replace": "\n".join(lines[i + 1:j])})
                i = j
        elif d == "HUNK":
            scope, _, label = arg.partition("|")
            scope, label = scope.strip() or "TOP", label.strip() or scope.strip()
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j >= n or lines[j].rstrip() != OLD_M:
                bad("hunk", cur_file, label, "expected '%s' right after @HUNK" % OLD_M, i)
            else:
                k = j + 1
                while k < n and lines[k].rstrip() not in (NEW_M, LINE_M):
                    k += 1
                e = k + 1
                while e < n and lines[e].rstrip() != END_M:
                    e += 1
                old, new = lines[j + 1:k], lines[k + 1:e]
                edit_err = None
                if k < n and e < n and lines[k].rstrip() == LINE_M:
                    new, edit_err = apply_line_edits("\n".join(old).strip("\n").split("\n"), new)
                if k >= n:
                    bad("hunk", cur_file, label, "missing '%s' (or '%s')" % (NEW_M, LINE_M), i)
                elif e >= n:
                    bad("hunk", cur_file, label, "missing '%s'" % END_M, i)
                elif edit_err:
                    bad("hunk", cur_file, label, edit_err, i)
                    i = e
                elif any(x.rstrip() in (OLD_M, NEW_M, LINE_M) for x in old + new) or any(x.rstrip() == END_M for x in old):
                    bad("hunk", cur_file, label, "a hunk terminator is missing before the next hunk; resend this hunk and the ones after it", i)
                    i = e
                elif not cur_file:
                    bad("hunk", None, label, "@HUNK before any @FILE", i)
                    i = e
                else:
                    find_s = "\n".join(old).strip("\n")
                    repl_s = "\n".join(new).strip("\n") if find_s else "\n".join(new).rstrip("\n")
                    P["ops"].append({"type": "hunk", "file": cur_file, "scope": scope, "label": label, "find": find_s, "replace": repl_s, "line_edits": lines[k].rstrip() == LINE_M})
                    i = e
        elif d == "TEXT_REPLACE":
            target, _, rest = arg.partition("|")
            m = re.search(r"\bexpect\s+(\d+)", rest)
            expect = int(m.group(1)) if m else 1
            md = re.search(r"\bdepth\s+(\d+)", rest)
            label = re.sub(r"\b(expect|depth)\s+\d+", "", rest).strip(" |") or "Text replace"
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j >= n or lines[j].rstrip() != TXT_OLD:
                bad("text", target.strip(), label, "expected '%s' right after @TEXT_REPLACE" % TXT_OLD, i)
            else:
                k = j + 1
                while k < n and lines[k].rstrip() != TXT_NEW:
                    k += 1
                e = k + 1
                while e < n and lines[e].rstrip() != TXT_END:
                    e += 1
                old, new = lines[j + 1:k], lines[k + 1:e]
                if k >= n or e >= n:
                    bad("text", target.strip(), label, "missing '%s' or '%s'" % (TXT_NEW, TXT_END), i)
                elif len(old) != 1 or len(new) > 1:
                    bad("text", target.strip(), label, "OLD TEXT and NEW TEXT are one line each; use @HUNK for multi-line changes", i)
                elif len(old[0]) < TEXT_MIN:
                    bad("text", target.strip(), label, "OLD TEXT needs at least %d characters so it cannot hit the wrong place; include more of the line" % TEXT_MIN, i)
                else:
                    P["ops"].append({"type": "text", "file": target.strip(), "scope": "TEXT", "label": label, "find": old[0], "replace": new[0] if new else "", "expect": expect,
                                     "depth": int(md.group(1)) if md else None})
                i = e
        elif d == "DELETE_FILE":
            P["ops"].append({"type": "delete", "file": arg, "scope": "TOP", "label": "Delete file"})
        elif d == "RENAME":
            a, sep, b = arg.partition("->")
            if not sep or not a.strip() or not b.strip():
                bad("rename", arg, "Rename file", "expected '@RENAME /old -> /new'", i)
            else:
                P["ops"].append({"type": "rename", "file": a.strip(), "to": b.strip(), "scope": "TOP", "label": "Rename to " + b.strip()})
        elif d == "NOTE_ADD":
            if not arg:
                P["warnings"].append("@NOTE_ADD needs non-empty text")
            else:
                who, text, own = note_audience(arg)
                P["notes"].append({"action": "add", "text": text, "for": who, "own": own})
        elif d == "NOTE_EDIT":
            nm = re.match(r"^(N\d+)\s+(.+)$", arg)
            if not nm:
                P["warnings"].append("expected '@NOTE_EDIT <note-id> <text>'")
            else:
                who, text, own = note_audience(nm.group(2))
                P["notes"].append({"action": "edit", "id": nm.group(1).upper(), "text": text, "for": who, "own": own})
        elif d == "NOTE_BRIEF":
            bm = re.match(r"^(N\d+)\s*\|?\s*(.+)$", arg, re.IGNORECASE)
            if not bm:
                P["warnings"].append("expected '@NOTE_BRIEF <note-id> | <short text>'")
            else:
                P["notes"].append({"action": "brief", "id": bm.group(1).upper(), "short": bm.group(2).strip()})
        elif d == "NOTE_PIN":
            pm = re.match(r"^(N\d+)\s+(.+)$", arg, re.IGNORECASE)
            if not pm:
                P["warnings"].append("expected '@NOTE_PIN <note-id> <*, names, all or own>'")
            else:
                P["notes"].append({"action": "pin", "id": pm.group(1).upper(), "aud": pm.group(2).strip()})
        elif d == "NOTE_REMOVE":
            if not re.fullmatch(r"N\d+", arg, re.IGNORECASE):
                P["warnings"].append("expected '@NOTE_REMOVE <note-id>'")
            else:
                P["notes"].append({"action": "remove", "id": arg.upper()})
        elif d == "NOTE_LIST":
            P["notes"].append({"action": "list", "query": arg})
        elif d == "PROBE":
            P["probes"].append(arg)
        elif d == "HELP":
            P["helps"].append(arg)
        elif d == "KB":
            P["helps"].append("KB " + arg)
        elif d == "PLAYBOOK":
            P["helps"].append("PLAYBOOK " + arg)
        elif d == "SESSIONS":
            P["helps"].append("SESSIONS")
        elif d == "HISTORY":
            P["helps"].append("HISTORY " + arg)
        elif d == "L1_REFRESH":
            P["l1_refresh"] = True
        elif d == "L1_PROOF":
            P["l1_proof"] = arg.strip().lower()
        elif d == "MSG_ACK":
            P["msg_acks"].append(arg)
        elif d == "WAIT_MSG":
            P["wait_msgs"].append(arg)
        elif d == "PING":
            P["ping"] = True
        elif d == "XREF":
            P["xrefs"].append(arg)
        elif d == "LIST_DIR":
            P["list_dir"].append(arg)
        elif d == "LIST_RECURSIVE":
            P["list_rec"].append(arg)
        elif d == "UNDO":
            P["undo"].append(arg)
        elif d == "GIT_STATUS":
            P["git_status"] = True
        elif d == "GIT_INIT":
            P["git_init"] = arg or True
        elif d == "SIDE":
            P["side"] = True
        elif d == "STEWARD":
            P["steward"] = arg.strip().lower() or "status"
        elif d == "TAKEOVER":
            P["takeover"] = arg.strip()
        elif d == "BORROW":
            P["borrow"] = arg.strip()
        elif d == "RECLAIM":
            P["reclaim"] = True
        elif d == "UNCLAIM":
            P["unclaim"] = arg.strip()
        elif d == "GUIDE":
            P["guide"] = arg.strip().lower() or "on"
        elif d == "GIT_FOLD":
            P["git"].append({"kind": "fold", "n": int(arg) if arg.isdigit() else 0})
        elif d == "GIT_BRANCH":
            m = re.match(r"^(\S+)(?:\s+from\s+(\S+))?\s*$", arg)
            P["git"].append({"kind": "branch", "name": m.group(1) if m else "", "base": m.group(2) if m else None})
        elif d == "GIT_WORKTREE":
            P["git"].append({"kind": "worktree", "args": arg.split()})
        elif d == "GIT_TAG":
            name, _, msg = arg.partition("|")
            P["git"].append({"kind": "tag", "name": name.strip(), "msg": msg.strip()})
        elif d == "GIT_PUSH":
            P["git"].append({"kind": "push", "what": arg.strip()})
        elif d == "GIT_PULL":
            P["git"].append({"kind": "pull"})
        elif d == "GIT_MERGE":
            P["git"].append({"kind": "merge", "arg": arg.strip()})
        elif d == "GIT_ACCOUNT":
            P["git"].append({"kind": "account", "arg": arg.strip()})
        elif d == "GIT_REMOTE":
            P["git"].append({"kind": "remote", "args": arg.split()})
        elif d == "GIT_COMMIT":
            j = i + 1
            while j < n and lines[j].rstrip() != "@END_GIT_COMMIT" and not lines[j].lstrip().startswith("@"):
                j += 1
            closed = j < n and lines[j].rstrip() == "@END_GIT_COMMIT"
            paths = [x.strip() for x in lines[i + 1:j] if x.strip() and not x.startswith("#")]
            if not closed:
                P["warnings"].append("@GIT_COMMIT at payload line %d had no @END_GIT_COMMIT; its path list was closed at the %s -> end every path list with @END_GIT_COMMIT" % (i + 1, "next directive" if j < n else "end of the script"))
            if paths:
                P["git"].append({"kind": "commit", "msg": arg, "paths": paths})
            else:
                P["warnings"].append("@GIT_COMMIT at payload line %d lists no paths; ignored" % (i + 1))
            i = j if closed else j - 1
        else:
            P["warnings"].append("unknown directive @%s at payload line %d was ignored -> valid directives: %s" % (d, i + 1, DIRECTIVES))
        i += 1
    if stray:
        P["warnings"].append("%d stray line(s) outside any block (first at payload line %d): a block marker is probably missing -> resend the affected hunks" % (len(stray), stray[0]))
    if re.search(r"\[(\w+://[^\]\s]+)\]\(\1\)", txt):
        P["warnings"].append("the payload contains a markdown-autolinked URL ([url](url)), so the chat UI altered the code -> resend with the scheme written as https" + "@@" + "://")
    return P

# ---------------------------------------------------------------- Stage: Executing file operations

NEXT_STEPS = {
    "MISMATCH": "rebuild ONLY that hunk from the on-disk excerpt printed below (never from memory) and resend it under the next script number.",
    "AMBIGUOUS": "resend ONLY that hunk with 2-3 more distinguishing context lines or a narrower scope.",
    "MALFORMED": "a marker line is missing (if the fence was cut short, write " + SENT_BT3 + " for three backticks); resend that hunk and every hunk after it, or, when nothing in this script was applied, send @REDO <this script's number> with --- [OLD TEXT] --- / +++ [NEW TEXT] +++ corrections for the broken markers instead of resending it whole.",
    "ROLLED BACK": "the file was restored to its pre-script state; resend every hunk for that file, corrected.",
    "REFUSED": "each refusal above names its reason (a path not written from the workspace root, a missing @SCOPE claim, another chat's scope, a wrong count, a brake): fix that and resend only those operations, or, when nothing in this script was applied, send @REDO <this script's number> with --- [OLD TEXT] --- / +++ [NEW TEXT] +++ corrections instead of resending it whole.",
}

def structure_sig(text):
    """Names of the classes, functions and # Stage anchors in a file: the things the architecture tree mirrors."""
    sig = set()
    for ln in text.split("\n"):
        info = def_info(ln)
        if info:
            sig.add(info[0])
        elif ANCHOR_RE.match(ln):
            sig.add(norm_ws(ln.strip()))
    return sig

def tree_sync_reminder(changed, pre):
    """Say so when a script changed code structure (or added/removed files) without touching any tree file in the same script."""
    if not os.path.isfile(TREE_MASTER) or any(is_tree_file(rel) for rel in changed):
        return
    notes = []
    tree_text = "\n".join(read_text(t) for t in sorted(glob.glob(os.path.join("docs", "trees", "*.txt"))))
    def in_trees(anchor):
        name = re.sub(r"^\W*#?\s*(?:Stage|Step)\b\s*:?\s*", "", anchor).split(" (")[0].strip()
        return bool(name) and name in tree_text
    def documented(x):
        if ANCHOR_RE.match(x):
            return in_trees(x)
        name = x.split(".")[-1].split("(")[0].strip()
        return bool(name) and re.search(r"\b%s\b" % re.escape(name), tree_text) is not None
    for rel in changed:
        if rel.startswith("docs/trees/"):
            continue
        before = structure_sig(decode_bytes(pre[rel]["raw"])[0]) if pre[rel]["raw"] is not None else None
        after = structure_sig(read_text(rel)) if os.path.isfile(rel) else None
        if before is None:
            notes.append("/%s: file added" % rel)
        elif after is None:
            notes.append("/%s: file removed" % rel)
        elif before != after:
            tracked = any(in_trees(x) for x in before | after if ANCHOR_RE.match(x))
            keep = lambda x: tracked or not ANCHOR_RE.match(x)
            added, gone = [x for x in sorted(after - before) if keep(x)], [x for x in sorted(before - after) if keep(x)]
            added, gone = [x for x in added if not documented(x)], [x for x in gone if documented(x)]
            if added or gone:
                notes.append("/%s: %s" % (rel, ", ".join(["+" + x for x in added[:5]] + ["-" + x for x in gone[:5]])))
    if notes:
        print("\n=== TREE SYNC REMINDER ===")
        for n in notes:
            print("  " + n)
        print("  -> no tree file under /docs/trees/ was updated in this script: send the matching tree hunk(s) in the next script, scoped by parent node path.")

def suggest_line_edits(ops):
    """Tips, never refusals: a hunk that resent a long, mostly unchanged block could have used +++ [LINE EDITS] +++; line edits that rewrite most of their block read better as +++ [NEW CODE] +++."""
    import difflib
    for op in ops:
        if op.get("type") != "hunk" or op.get("status") != "OK":
            continue
        old, new = (op.get("find") or "").split("\n"), (op.get("replace") or "").split("\n")
        edits = same = 0
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag == "equal":
                same += i2 - i1
            else:
                edits += max(i2 - i1, j2 - j1)
        if op.get("line_edits"):
            touched = len(old) - same
            if len(old) >= 4 and touched >= 3 and touched * 10 >= len(old) * 6:
                print("  [TIP] /%s | %s: these line edits change %d of %d lines; plain +++ [NEW CODE] +++ is clearer for rewrites" % (op["file"].lstrip("/"), op["label"], touched, len(old)))
        elif len(old) >= 10 and 0 < edits <= 3 and same >= 8:
            print("  [TIP] /%s | %s: this hunk resent %d unchanged lines to change %d; +++ [LINE EDITS] +++ would need %d line(s)" % (op["file"].lstrip("/"), op["label"], same, edits, edits))

COMMENT_LINE_RE = re.compile(r"^\s*(#|//|/\*+|<!--|--)\s*Comment\b")

def report_removed_comments(changed, pre, rolled):
    """A change that deletes a 'Comment' line (a recorded reason) is flagged, so the AI confirms the reason is really gone; nothing is refused."""
    for rel in changed:
        raw = (pre.get(rel) or {}).get("raw")
        if raw is None or rel in rolled:
            continue
        old = [l.strip() for l in decode_bytes(raw)[0].split("\n") if COMMENT_LINE_RE.match(l)]
        if not old:
            continue
        new = set(l.strip() for l in decode_bytes(read_bytes(rel))[0].split("\n")) if os.path.isfile(rel) else set()
        for c in old:
            if c not in new:
                print("  [COMMENT REMOVED] /%s: %s -> confirm its reason no longer holds; if it still does, put it back" % (rel, c[:160]))

def execute_ops(ops):
    """Apply ops on an in-memory view, flush once, syntax-check, print the scorecard. -> (hunk_log, files_log)"""
    cur, meta, pre, dirty, new_mode, fails = {}, {}, {}, [], {}, []
    moved = {}

    def load(rel):
        if rel not in cur:
            if os.path.isfile(rel):
                raw = read_bytes(rel)
                cur[rel], meta[rel] = decode_bytes(raw)
                pre[rel] = {"raw": raw, "mode": os.stat(rel).st_mode & 0o777}
            else:
                cur[rel], meta[rel], pre[rel] = None, None, {"raw": None, "mode": None}
        return cur[rel]

    def touch(rel):
        if rel not in dirty:
            dirty.append(rel)

    for op in ops:
        op["detail"] = None
        if op.get("malformed"):
            op["status"], op["detail"] = "MALFORMED", op["malformed"]
            continue
        if op.get("blocked"):
            op["status"], op["detail"] = "REFUSED", op["blocked"]
            continue
        rel = safe_rel(op["file"])
        if rel is None:
            op["status"], op["detail"] = "REFUSED", "path is outside the workspace or inside git or harness internals"
            continue
        op["file"] = rel
        text = load(rel)
        if op["type"] == "hunk":
            if text is None:
                op["status"], op["detail"] = "MISMATCH", "file does not exist (use @NEW_FILE)"
                continue
            op["find"], op["replace"] = sanitize_tree(rel, op["find"]), sanitize_tree(rel, op["replace"])
            new, st, detail = apply_match(rel, text, op["scope"], op["find"], op["replace"])
            op["status"], op["detail"] = st, detail
            if st == "OK":
                cur[rel] = new
                touch(rel)
            elif st in ("MISMATCH", "AMBIGUOUS"):
                fails.append((op, text))
        elif op["type"] == "text_file":
            if text is None:
                op["status"], op["detail"] = "MISMATCH", "file does not exist"
                continue
            lines = text.split("\n")
            at = [i for i in range(op["lo"], min(op["hi"], len(lines))) if op["find"] in lines[i]]
            if sum(lines[i].count(op["find"]) for i in at) != op["count"]:
                op["status"], op["detail"] = "MISMATCH", "an earlier change in this script moved or altered the matches; send the text replacement in its own script"
                continue
            for i in at:
                lines[i] = lines[i].replace(op["find"], op["replace"])
            shown = lines[at[0]].strip()
            # Comment (decision): an empty replacement that leaves a whole line empty removes that line (it used to leave a blank line behind); a later text replacement of the same script that was limited to a scope (lo, hi) was measured before the removal and may miss by a line, so it is refused with its own message and can be sent in a script of its own
            gone = [i for i in at if op["replace"] == "" and not lines[i].strip()]
            for i in reversed(gone):
                del lines[i]
            cur[rel] = "\n".join(lines)
            touch(rel)
            if gone and len(gone) == len(at):
                op["status"], op["detail"] = "OK", "%d line(s) removed, from line %d" % (len(gone), gone[0] + 1)
            else:
                op["status"], op["detail"] = "OK", "line %d now: %s" % (at[0] + 1, shown if len(shown) <= 110 else shown[:110] + "...")
        elif op["type"] == "new_file":
            if text is not None and op.get("init"):
                op["status"], op["detail"] = "ALREADY APPLIED", "ledger exists: update it with @FILE hunks scoped by its # Stage anchors"
            elif text is not None:
                op["status"], op["detail"] = "MISMATCH", "file exists: use @FILE hunks"
            else:
                cur[rel], meta[rel] = sanitize_tree(rel, op["replace"]), default_meta(rel)
                op["status"] = "OK"
                touch(rel)
        elif op["type"] == "delete":
            if text is None:
                op["status"] = "ALREADY APPLIED"
            else:
                cur[rel] = None
                num = re.search(r"(\d+)$", CURRENT_SCRIPT or "")
                op["status"], op["detail"] = "OK", "recoverable: @UNDO %s | /%s" % (num.group(1), rel) if num else None
                touch(rel)
        elif op["type"] == "rename":
            dst = safe_rel(op["to"])
            if dst is None:
                op["status"], op["detail"] = "REFUSED", "target path is outside the repository"
                continue
            op["to"] = dst
            dtext = load(dst)
            if text is None and dtext is not None:
                op["status"] = "ALREADY APPLIED"
            elif text is None or dtext is not None:
                op["status"], op["detail"] = "MISMATCH", "source missing" if text is None else "target already exists"
            else:
                # Comment (order): the header is normally fixed when files are written; doing it here lets later hunks in the same script match the file as it will end up
                cur[dst], meta[dst], cur[rel] = ensure_line1_header(dst, text)[0], meta[rel], None
                # Comment (invariant): a rename moves a file's exact bytes (binary files, line endings, missing final newline); only a header rewrite or a later edit in the same script re-encodes it, as any edit does
                moved[dst] = (text, pre[rel]["raw"])
                new_mode[dst] = pre[rel]["mode"]
                op["status"] = "OK"
                touch(rel)
                touch(dst)

    changed = []
    for rel in dirty:
        if cur[rel] is None:
            if os.path.isfile(rel):
                os.remove(rel)
                changed.append(rel)
            continue
        text, _ = ensure_line1_header(rel, sanitize_tree(rel, cur[rel]))
        data = moved[rel][1] if rel in moved and text == moved[rel][0] else encode_text(text, meta[rel] or default_meta(rel))
        if data != pre[rel]["raw"]:
            write_bytes(rel, data)
            changed.append(rel)
            if pre[rel]["raw"] is None and os.name == "posix":
                mode = new_mode.get(rel) or (0o755 if text.startswith("#!") else None)
                if mode:
                    os.chmod(rel, mode)

    for d in sorted({op["folder"] for op in ops if op.get("type") in ("delete", "rename") and op.get("folder") and op.get("status") == "OK"}, key=len, reverse=True):
        for root, _, _ in sorted(os.walk(d, topdown=False), key=lambda t: -len(t[0])):
            try:
                if not os.listdir(root):
                    os.rmdir(root)
            except OSError:
                pass
    pruned = prune_emptied_parents([op["file"] for op in ops if op.get("type") in ("delete", "rename") and op.get("status") == "OK"])
    checks, rolled = check_files(changed, pre) if changed else ({}, set())
    print("\n=== EXECUTION SCORECARD ===")
    for op in ops:
        files = [op["file"]] + ([op["to"]] if op.get("to") and op["status"] == "OK" else [])
        if op["status"] == "OK" and any(f in rolled for f in files):
            op["status"] = "ROLLED BACK"
        diag = any(f[0] is op for f in fails)
        st = op["status"] + ((" (%s)" % op["detail"]) if op["detail"] and not diag else "")
        chk = (checks.get(files[-1]) or "UNCHANGED") if op["status"] in ("OK", "ROLLED BACK") else "-"
        print("  [%s] /%s | Scope: %s | %s | Check: %s" % (st, op["file"].lstrip("/"), op["scope"], op["label"], chk))
    report_removed_comments(changed, pre, rolled)
    report_pruned(pruned)
    suggest_line_edits(ops)
    seen = set(op["status"] for op in ops)
    if seen & {"MISMATCH", "AMBIGUOUS", "MALFORMED", "ROLLED BACK", "REFUSED"}:
        globals()["RUN_FAILED"] = True
    for st in ("MISMATCH", "AMBIGUOUS", "MALFORMED", "ROLLED BACK", "REFUSED"):
        if st in seen:
            if st == "MALFORMED" and not any(op["status"] == "MALFORMED" and ("missing" in (op.get("detail") or "") or "expected '" in (op.get("detail") or "")) for op in ops):
                print("  -> [MALFORMED]: fix what the parentheses above say, then resend that directive.")
                continue
            print("  -> [%s]: %s" % (st, NEXT_STEPS[st]))
    if any("BUILD_PENDING" in v for v in checks.values()):
        print("  -> [BUILD_PENDING]: fix the errors listed under COMPILER DIAGNOSTICS in the next script.")
    if seen == {"ALREADY APPLIED"}:
        print("  -> Every hunk was already applied: this is a repeated paste. Do not regenerate; tell the user in one sentence which script to paste next.")
    for op, text in fails:
        print_diagnostics(op["file"], text, op["scope"], op["find"], op["status"], op["detail"])
    live = [rel for rel in changed if rel not in rolled]
    tree_sync_reminder(live, pre)
    if any(os.path.abspath(rel) == SELF_PATH for rel in live) and pre.get(os.path.relpath(SELF_PATH, ".").replace("\\", "/"), {}).get("raw"):
        write_bytes(os.path.join(SELF_DIR, "harness.prev.py"), pre[os.path.relpath(SELF_PATH, ".").replace("\\", "/")]["raw"])
        print("\n  NOTE: harness.py patched itself; the previous version is saved as harness.prev.py. If the harness misbehaves, copy that file over harness.py.")

    files_log = {}
    for rel in changed:
        post = sha_of(rel)
        if post != sha_bytes(pre[rel]["raw"]):
            files_log[rel] = {"pre": pack(pre[rel]["raw"]), "mode": pre[rel]["mode"], "post_sha": post, "undone": False}
    hunk_log = [{k: op.get(k) for k in ("type", "file", "to", "scope", "label", "status", "find", "replace")} for op in ops]
    return hunk_log, files_log

# ---------------------------------------------------------------- Stage: Journal and undo

def history_path(num):
    found = glob.glob(os.path.join(HISTORY_DIR, "%04d_*.json" % num))
    return found[0] if found else None

def save_history(P, raw_txt, hunk_log, files_log):
    """Journal the payload, per-hunk outcomes and pre-image snapshots so undo can restore exactly."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    old_path = history_path(P["num"])
    old = load_json(old_path, None) if old_path else None
    if old and old.get("id") == P["id"] and not all(f.get("undone") for f in old.get("files", {}).values()):
        for rel, fl in old["files"].items():
            if rel in files_log:
                files_log[rel]["pre"], files_log[rel]["mode"] = fl["pre"], fl["mode"]
            else:
                files_log[rel] = fl
        hunk_log = old.get("hunks", []) + hunk_log
    if old_path:
        os.remove(old_path)
    name = "%04d_%s.json" % (P["num"], re.sub(r"[^A-Za-z0-9_-]", "_", P["id"]))
    save_json(os.path.join(HISTORY_DIR, name), {"id": P["id"], "num": P["num"], "title": P["title"], "session": P.get("session"),
                                                 "payload": raw_txt, "hunks": hunk_log, "files": files_log})
    entries = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")))
    for stale in entries[:max(0, len(entries) - MAX_HISTORY)]:
        try:
            os.remove(stale)
        except OSError:
            pass

def drain_console(fi):
    """Throw away input already waiting at the terminal (a second paste, keys typed ahead), so only what the user types after the question counts."""
    try:
        if os.name == "nt":
            import msvcrt
            while msvcrt.kbhit():
                msvcrt.getwch()
        else:
            poll_tty_focus()
            import termios
            termios.tcflush(fi.fileno(), termios.TCIFLUSH)
    except Exception:
        pass

def ask_console(prompt):
    """Ask the person at the terminal while the script itself arrives on stdin; None when no one is there (output captured, no console, or prompts turned off)."""
    if os.environ.get("LLM_HARNESS_NO_PROMPT") or agent_mode() or not os.isatty(1):
        return None
    was_tracking = bool(TTY_FOCUS.get("active"))
    if was_tracking:
        stop_tty_focus(keep_state=True)
    try:
        tin, tout = ("CONIN$", "CONOUT$") if os.name == "nt" else ("/dev/tty", "/dev/tty")
        with open(tin, "r") as fi, open(tout, "w") as fo:
            sys.stdout.flush()
            drain_console(fi)
            fo.write(prompt)
            fo.flush()
            return fi.readline().strip()
    except (OSError, ValueError):
        return None
    finally:
        if was_tracking:
            start_tty_focus(resume=True)

def journal_entries(start, session):
    """Journaled scripts of one chat (or of no chat) from number start on, newest first."""
    out = []
    for path in glob.glob(os.path.join(HISTORY_DIR, "*.json")):
        e = load_json(path, None)
        if e and e.get("num", -1) >= start and (e.get("session") or None) == (session or None):
            out.append(e)
    return sorted(out, key=lambda e: e["num"], reverse=True)

def repaste_choice(rid, session):
    """R(eplay), U(ndo) or E(xecute again) for a pasted script that already ran, asked at the terminal; R when no one can answer."""
    ans = ask_console("\nThis script already ran: [%s]%s.\n  [R] replay its saved output   (Enter = R)\n  [U] undo it, and everything this chat did after it\n  [E] execute it again\n> " % (rid, " (chat %s)" % session if session else ""))
    ans = (ans or "R")[:1].upper()
    return ans if ans in ("R", "U", "E") else "R"

def undo_from(start, session, state):
    """Undo every journaled script of this chat from number start on, newest first, after a preview and the user's yes; committed scripts are kept."""
    live = [e for e in journal_entries(start, session) if not all(f.get("undone") for f in e.get("files", {}).values())]
    kept = [e for e in live if e["num"] <= state.get("committed_through", 0)]
    todo = [e for e in live if e not in kept]
    print("\n=== UNDO FROM SCRIPT %d (chat %s) ===" % (start, session or "none"))
    for e in todo:
        print("  [%s] %s: %s" % (e["id"], e.get("title", ""), ", ".join("/" + r for r in e.get("files", {})) or "no files"))
    for e in kept:
        print("  [KEPT] [%s] %s is already committed; undo leaves committed work alone" % (e["id"], e.get("title", "")))
    if not todo:
        print("  nothing to undo: no uncommitted file changes from this chat since that script")
        return
    if (ask_console("Undo these %d script(s)? (y/n) " % len(todo)) or "").lower()[:1] != "y":
        print("  [UNDO CANCELLED] nothing was changed")
        return
    for e in todo:
        run_undo(str(e["num"]), state)
    print("  -> the files are back to how they were before script %d; in the chat, continue from the message before it." % start)

def recover_to(rel, fl, entry, dest, matches):
    """@UNDO <n> | /old -> /new: copy a file as it was before that script to another path; the original path is left as it is. A destination ending in / (or several matches) takes each file's own name."""
    target = dest.rstrip("/") + "/" + os.path.basename(rel) if dest.endswith("/") or matches > 1 else dest
    holder = scope_owner(target, CURRENT_SESSION)[0] if CURRENT_SESSION else None
    if safe_rel(target) is None:
        print("  [RECOVER SKIPPED] /%s is outside the workspace or inside git or harness internals" % target)
    elif fl["pre"] is None:
        print("  [RECOVER SKIPPED] /%s did not exist before [%s], so there is nothing to copy" % (rel, entry["id"]))
    elif os.path.exists(target):
        print("  [RECOVER SKIPPED] /%s already exists; pick a free path" % target)
    elif holder:
        print("  [RECOVER SKIPPED] /%s is inside session %s's scope%s; ask them, or the user" % (target, holder, chat_link(holder)))
    else:
        raw = unpack(fl["pre"])
        text, meta = decode_bytes(raw)
        fixed = ensure_line1_header(target, text)[0]
        restore_pre(target, encode_text(fixed, meta) if fixed != text else raw, fl["mode"])
        print("  [RECOVERED] /%s -> /%s (as it was before [%s])" % (rel, target, entry["id"]))

def loan_undo_allowed(e):
    """For an undo of a script another session ran: None when that session never borrowed this session's work (or the script touched none of it), so the usual skip applies; otherwise the user is asked at the terminal, naming the script, the borrower and the returned files, and the answer gives the files to undo (Enter) or False (n, or no terminal)."""
    if not CURRENT_SESSION:
        return None
    rec = load_json(sessions_path(), {}).get(CURRENT_SESSION) or {}
    holder = e.get("session")
    loans = [ln for ln in rec.get("returned_loans", []) if ln.get("holder") == holder]
    files = [r for r in e.get("files", {}) if any(path_in(r, p) for ln in loans for p in ln.get("paths", []))]
    if not files:
        return None
    ans = ask_console("\nSession %s asks to undo [%s] (%s), which %s ran while it borrowed this session's work; it changed %s.\nPress Enter to undo those files, or type n to leave them: " % (CURRENT_SESSION, e.get("id"), e.get("title", ""), holder, ", ".join("/" + r for r in files)))
    if ans is None:
        print("\n  [UNDO SKIPPED] [%s] was run by %s while it borrowed this work; undoing it needs the user's answer at a terminal" % (e.get("id"), holder))
        return False
    if ans.strip().lower() not in ("", "y", "yes"):
        print("\n  [UNDO SKIPPED] [%s]: the user answered no" % e.get("id"))
        return False
    return files

def run_undo(spec, state):
    """Reverse journaled scripts newest-first: exact snapshot restore when the file is unchanged since, else reverse-diff."""
    spec, _, only = spec.partition("|")
    items = []
    for part in only.split(","):
        src, arrow, dst = part.partition("->")
        src, dst = src.strip().replace("\\", "/").lstrip("/"), dst.strip().replace("\\", "/").lstrip("/")
        if src:
            items.append((src, dst if arrow else None))
    only = items
    nums = [int(x) for x in re.findall(r"\d+", spec)]
    if not nums:
        print("  [UNDO ERROR] expected '@UNDO <hi>..<lo>' or '@UNDO <num>', optionally followed by '| /path', got: " + spec)
        return
    hi, lo, seen = max(nums), min(nums), 0
    for path in sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")), reverse=True):
        e = load_json(path, None)
        if not e or not (lo <= e.get("num", -1) <= hi):
            continue
        limit = None
        if CURRENT_SESSION and e.get("session") and e.get("session") != CURRENT_SESSION:
            # Comment (decision): another chat's script stays out of reach, except a borrower's script on work it gave back: its owner may undo that, only on the user's own answer at the terminal, and only the returned files
            allowed = loan_undo_allowed(e)
            if not allowed:
                if allowed is None:
                    print("\n  [UNDO SKIPPED] [%s] belongs to session %s; undo it from that session." % (e["id"], e["session"]))
                continue
            limit = allowed
        if only and not any(path_in(r, s) for s, _ in only for r in e.get("files", {})):
            continue
        seen += 1
        print("\n=== REVERSING [%s: %s] ===" % (e["id"], e["title"]))
        if e["num"] <= state.get("committed_through", 0):
            print("  NOTE: this script was already committed; undo only edits the working tree.")
        for rel, fl in e["files"].items():
            if only and not any(path_in(rel, s) for s, _ in only):
                continue
            if limit is not None and rel not in limit:
                print("  [UNDO SKIPPED] /%s is %s's own file, not part of the returned work" % (rel, e.get("session")))
                continue
            holder = scope_owner(rel, CURRENT_SESSION)[0] if CURRENT_SESSION else None
            if holder:
                print("  [UNDO SKIPPED] /%s is inside session %s's scope%s; ask them, or the user, before undoing it" % (rel, holder, chat_link(holder)))
                continue
            dest = next((d for s, d in only if d is not None and path_in(rel, s)), None) if only else None
            if dest is not None:
                recover_to(rel, fl, e, dest, sum(1 for r in e["files"] if any(path_in(r, s) for s, _ in only)))
                continue
            if fl.get("undone"):
                print("  [ALREADY UNDONE] /" + rel)
            elif sha_of(rel) == fl["post_sha"]:
                restore_pre(rel, unpack(fl["pre"]), fl["mode"])
                fl["undone"] = True
                print("  [RESTORED] /%s (exact pre-script snapshot%s)" % (rel, "; file removed" if fl["pre"] is None else ""))
            else:
                hs = [h for h in reversed(e["hunks"]) if h["file"] == rel and h["type"] == "hunk" and h["status"] == "OK"]
                if not hs or not os.path.isfile(rel):
                    print("  [SKIPPED] /%s changed after this script; undo the later scripts first or restore it by hand" % rel)
                    continue
                text, meta = decode_bytes(read_bytes(rel))
                done = True
                for h in hs:
                    if not h["replace"]:
                        done = False
                        print("  [MANUAL] /%s | %s | deleted block cannot be re-placed automatically:\n%s" % (rel, h["label"], h["find"]))
                        continue
                    scope = "TOP" if h["scope"].strip().upper() == "EOF" else h["scope"]
                    text, st, detail = apply_match(rel, text, scope, h["replace"], h["find"])
                    done = done and st == "OK"
                    print("  [%s] /%s | %s%s" % ("REVERSED" if st == "OK" else "SKIPPED: " + st, rel, h["label"], (" | " + detail) if detail and st != "OK" else ""))
                write_bytes(rel, encode_text(text, meta))
                fl["undone"] = done
        save_json(path, e)
    if not seen:
        print("  [UNDO] no journaled scripts in range %d..%d%s" % (hi, lo, " that changed " + ", ".join("/" + s for s, _ in only) if only else ""))

# ---------------------------------------------------------------- Stage: Git

def run_git(args):
    rc, out, err = run_tool(["git"] + list(args))
    return (127 if rc is None else rc), out.strip("\n"), (err.strip() if rc is not None else "git not found")

def git_blockers():
    names = ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "index.lock")
    return [x for x in names if os.path.exists(os.path.join(GIT_DIR, x))]

GITATTRIBUTES_DEFAULT = """# The harness merges its own committed memory (notes by id, verdicts by key, tokens additively) so two devices adding notes do not leave conflict markers.
.llm_harness/notes.md merge=llm-harness-notes
.llm_harness/verdicts.json merge=llm-harness-verdicts
.llm_harness/tokens.json merge=llm-harness-tokens
"""

GITIGNORE_DEFAULT = """# Machine-local harness state (numbering, undo journal, saved runs, graph stamp).
# goal.md and notes.md are project memory and stay tracked.
.llm_harness/*
!.llm_harness/goal.md
!.llm_harness/notes.md
!.llm_harness/verdicts.json
!.llm_harness/tokens.json
!.llm_harness/git.json
__pycache__/
"""

def carry_state(src, with_state):
    """Copy machine-local history (journal, saved runs, and optionally the numbering) from src into the current state folder."""
    for sub in ("history", "runs"):
        if os.path.isdir(os.path.join(src, sub)):
            shutil.copytree(os.path.join(src, sub), os.path.join(HARNESS_DIR, sub), dirs_exist_ok=True)
    if with_state and os.path.isfile(os.path.join(src, "state.json")):
        os.makedirs(HARNESS_DIR, exist_ok=True)
        shutil.copyfile(os.path.join(src, "state.json"), STATE_PATH)

def git_init(ident):
    """@GIT_INIT [Name <email>]: create the repository on main, add the default .gitignore, set this repository's identity when given, switch this run to git mode carrying numbering and undo history, and show the commit identity."""
    print("\n=== GIT INIT ===")
    if MODE == "git":
        print("  already a git repository; nothing to do.")
        return
    rc, out, err = run_git(["init", "-b", "main"])
    if rc != 0:
        rc, out, err = run_git(["init"])
        if rc == 0:
            run_git(["symbolic-ref", "HEAD", "refs/heads/main"])
    if rc != 0:
        print("  [FAILED] git init: %s" % (err or out))
        return
    print("  " + out.strip())
    if not os.path.exists(".gitignore"):
        with open(".gitignore", "w", encoding="utf-8", newline="\n") as f:
            f.write(GITIGNORE_DEFAULT)
        print("  wrote .gitignore (machine state ignored; goal.md and notes.md tracked)")
    if not os.path.exists(".gitattributes"):
        with open(".gitattributes", "w", encoding="utf-8", newline="\n") as f:
            f.write(GITATTRIBUTES_DEFAULT)
        print("  wrote .gitattributes (the harness's merge rules for notes and verdicts); commit it with .gitignore in the first commit")
    old = HARNESS_DIR
    set_mode("git")
    carry_state(old, False)
    print("  this run is now in git mode; numbering and undo history carried over")
    m = re.match(r"^(.+?)\s*<([^<>@\s]+@[^<>\s]+)>$", ident) if isinstance(ident, str) else None
    if m:
        run_git(["config", "user.name", m.group(1).strip()])
        run_git(["config", "user.email", m.group(2)])
    elif isinstance(ident, str):
        print("  [WARNING] identity not understood: expected '@GIT_INIT Name <email>'; nothing was set")
    name, email = run_git(["config", "user.name"])[1].strip(), run_git(["config", "user.email"])[1].strip()
    print("  commits will be authored as: %s <%s>" % (name or "(no name set)", email or "(no email set)"))
    if not name or not email:
        print("  -> commits will fail until a name and email are set: the user runs git config user.name / user.email in this folder.")
    elif (name, email) == (run_git(["config", "--global", "user.name"])[1].strip(), run_git(["config", "--global", "user.email"])[1].strip()):
        print("  -> that is the global identity; if this repository needs another, use '@GIT_INIT Name <email>' or set it here with git config user.name / user.email (no --global) before committing.")

def git_status_report():
    print("\n=== GIT STATUS ===")
    if MODE != "git":
        print("  no-git workspace: there is no repository to report on.")
        return
    _, branch, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if run_git(["rev-parse", "-q", "--verify", "HEAD"])[0] != 0:
        branch = (run_git(["symbolic-ref", "--short", "HEAD"])[1] or "main") + " (no commits yet)"
    rc, up, _ = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    line = "  Branch: %s | Upstream: %s" % (branch or "(no commits yet)", up if rc == 0 else "none")
    if rc == 0:
        rc2, cnt, _ = run_git(["rev-list", "--left-right", "--count", "@{u}...HEAD"])
        if rc2 == 0 and len(cnt.split()) == 2:
            line += " | ahead %s, behind %s" % (cnt.split()[1], cnt.split()[0])
    print(line)
    print("  In-progress operations: " + (", ".join(git_blockers()) or "none"))
    _, log, _ = run_git(["log", "--oneline", "-n", "20", "HEAD", "--not", "--remotes"])
    print("  Unpushed commits (foldable, newest first):" + ("" if log else " none"))
    for l in log.splitlines():
        print("    " + l)
    _, st, _ = run_git(["status", "--short"])
    rows = st.splitlines()
    print("  Working tree:" + ("" if rows else " clean"))
    for l in rows[:60]:
        print("    " + l)
    if len(rows) > 60:
        print("    ... +%d more" % (len(rows) - 60))

MEMORY_FILES = {p: p for p in (WORKSPACE_NOTES_DIR + "/goal.md", WORKSPACE_NOTES_DIR + "/notes.md", WORKSPACE_NOTES_DIR + "/verdicts.json", ".gitignore")}

COMMIT_TYPES = ("build", "chore", "ci", "docs", "feat", "fix", "perf", "refactor", "revert", "style", "test")
REPO_KINDS = ("branch", "worktree", "tag", "push", "pull", "merge", "account")
ACTIVE_S = 15 * 60

def park_tokens(incoming):
    """Set aside this checkout's own tokens.json when it is modified (or untracked) and the incoming commits change it too, because git would refuse the fast-forward: returns (local text, committed text) or None. The harness never commits the file alone, so it is dirty on every machine that has copied output."""
    rel = WORKSPACE_NOTES_DIR + "/tokens.json"
    if rel not in incoming:
        return None
    status = run_git(["status", "--porcelain", "--", rel])[1]
    if not status.strip():
        return None
    try:
        with open(rel, "r", encoding="utf-8") as f:
            local = f.read()
    except OSError:
        return None
    rc, base, _ = run_git(["show", "HEAD:" + rel])
    if status.lstrip().startswith("??"):
        os.remove(rel)
    else:
        run_git(["checkout", "--", rel])
    return local, (base if rc == 0 else "")

def unpark_tokens(parked, moved):
    """Put the set-aside counts back after the move: merged with the incoming file by the tokens merge rule (the committed text is the base), or unchanged when the move failed or the files cannot be merged. Returns what happened, for the report."""
    rel = WORKSPACE_NOTES_DIR + "/tokens.json"
    local, base = parked
    text, note = local, "kept as they were"
    if moved:
        try:
            with open(rel, "r", encoding="utf-8") as f:
                theirs = f.read()
            text, note = merge_tokens_text(base, local, theirs), "merged with the incoming counts"
        except (OSError, ValueError, KeyError, TypeError):
            note = "could not be merged with the incoming file, so they were kept as they were"
    os.makedirs(os.path.dirname(rel), exist_ok=True)
    with open(rel, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return note

def repo_guard(what, clean=True, alone=True):
    """The shared safety checks for operations that affect a whole checkout: no unfinished git operation, no local changes, no other active chat in this folder. '' when it is safe."""
    blockers = git_blockers()
    if blockers:
        return "an unfinished git operation (%s) must be finished or aborted first" % ", ".join(blockers)
    if clean:
        _, st, _ = run_git(["status", "--porcelain"])
        # Comment (decision): the harness's own project memory (.llm_harness/: notes, verdicts, git.json) changes outside commits; git itself refuses a switch that would overwrite it
        dirty = [l[3:].strip('"') for l in st.splitlines() if l.strip() and not l[3:].strip('"').startswith(WORKSPACE_NOTES_DIR + "/")]
        if dirty:
            return "this checkout has uncommitted or untracked changes (%s%s); commit them (or ask the user) first" % (", ".join(dirty[:4]), " +%d more" % (len(dirty) - 4) if len(dirty) > 4 else "")
    if alone:
        now = time.time()
        # Comment (decision): a session lent to the current chat is paused while borrowed, so it must not block the borrower's repo ops (pull/merge/branch)
        busy = [nm for nm, rec in load_json(sessions_path(), {}).items() if nm != CURRENT_SESSION and (rec.get("lent") or {}).get("to") != CURRENT_SESSION and (rec.get("scope") or now - rec.get("last_active", 0) < ACTIVE_S)]
        if busy:
            return "other chats are active in this checkout (%s), and %s would change the files under them; give each branch its own folder with @GIT_WORKTREE add instead" % (", ".join(sorted(busy)), what)
    return ""

def remember_base(branch, base):
    """Git does not record where a branch was cut from, so the harness keeps it (shared by all worktrees)."""
    path = os.path.join(SHARED_DIR, "branches.json")
    data = load_json(path, {})
    data[branch] = base
    save_json(path, data)

def new_branch_problem(name, policy):
    if not re.match(r"^[\w.\-/]+$", name or "") or name.startswith("-"):
        return "'%s' is not a usable branch name" % name
    pattern = policy.get("branches")
    if pattern and name not in (policy.get("protected") or []) and not re.match(pattern, name):
        return "%s does not match this project's branch pattern %s" % (name, pattern)
    return ""

def parse_cmdkey_accounts(text, host):
    """Account names from 'cmdkey /list' output: Git Credential Manager keeps one entry per account as git:https://<account>@<host>. Reading the name from the target keeps this independent of the Windows display language."""
    return list(dict.fromkeys(m.group(1) for m in re.finditer(r"git:https?://([^@/\s]+)@%s\b" % re.escape(host), text or "", re.I)))

def remote_login_info():
    """The remote this branch pushes to (its upstream's, else origin) as {url, scheme, host}; scheme is None for SSH and other non-http remotes; None when there is no remote."""
    rc, up, _ = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    rc2, url, _ = run_git(["remote", "get-url", up.split("/", 1)[0] if rc == 0 else "origin"])
    if rc2 != 0 or not url.strip():
        return None
    m = re.match(r"^(https?)://(?:[^@/]+@)?([^/:]+)", url.strip())
    return {"url": url.strip(), "scheme": m.group(1) if m else None, "host": m.group(2) if m else ""}

GH_SOURCE = "GitHub CLI (gh)"

def parse_gh_accounts(text, host):
    """(logins, active) from 'gh auth status --json hosts': only accounts whose state is success count, because that command exits 0 even when a login is broken; garbage gives ([], None)."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return [], None
    hosts = data.get("hosts") if isinstance(data, dict) else None
    rows = hosts.get(host) if isinstance(hosts, dict) else None
    ok = [r for r in (rows or []) if isinstance(r, dict) and r.get("state") == "success" and r.get("login")]
    return list(dict.fromkeys(r["login"] for r in ok)), next((r["login"] for r in ok if r.get("active")), None)

def run_gh(args):
    """Run the gh CLI: (exit code, stdout, stderr); 127 when it is not installed or hangs."""
    try:
        p = subprocess.run(["gh"] + args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return 127, "", "gh is not available"
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")

def gh_after_pin(host, login, source):
    """After pinning an account that came from gh: switch gh's active account to it and say whether git uses gh as its credential helper. The harness never runs 'gh auth setup-git' itself, since that edits the user's git config."""
    if source != GH_SOURCE:
        return
    rc, out, err = run_gh(["auth", "switch", "--hostname", host, "--user", login])
    last = ((err or out).strip().splitlines() or ["exit code %d" % rc])[-1]
    print("  [GH] %s" % ("gh's active account for %s is now %s" % (host, login) if rc == 0 else "gh auth switch failed: " + last))
    helpers = run_git(["config", "--get-all", "credential.helper"])[1] + "\n" + run_git(["config", "--get-all", "credential.https://%s.helper" % host])[1]
    if not re.search(r"gh(\.exe)?\"?\s+auth\s+git-credential", helpers):
        print("  -> git does not use gh as its credential helper here, so https pushes will not use this account yet; set it up once with: gh auth setup-git --hostname %s" % host)

def known_accounts(host):
    """(accounts, source): the signed-in accounts for a host. GitHub is asked through Git Credential Manager ('github list'); failing that, on Windows, the git entries of the credential list."""
    found = []
    if host == "github.com":
        rc, out, _ = run_git(["credential-manager", "github", "list"])
        if rc == 0:
            found = [l.strip() for l in out.splitlines() if l.strip()]
            if found:
                return list(dict.fromkeys(found)), "Git Credential Manager"
    if os.name == "nt":
        rc, out, _ = run_tool(["cmdkey", "/list"])
        if rc == 0:
            found = parse_cmdkey_accounts(out, host)
            if found:
                return found, "the Windows credential list"
    # Comment (decision): the GitHub CLI is the last source, for machines (a headless Linux server, say) that have gh but no Git Credential Manager; it lists only accounts that are signed in and healthy
    if host == "github.com":
        rc, out, _ = run_gh(["auth", "status", "--hostname", host, "--json", "hosts", "--no-refresh"])
        if rc == 0:
            found, _active = parse_gh_accounts(out, host)
            if found:
                return found, GH_SOURCE
    return [], ""

def offer_account_pin():
    """Before a push or pull the user asked for: when several accounts are signed in for the remote's host and this project has none pinned, ask once (at a terminal, one key) which one it uses and pin it in this clone's git config, so Git Credential Manager never has to show its chooser for this project on this machine. Silent when the remote is not https, the URL names the user, an account is pinned (in any git config), fewer than two accounts exist, or nobody is at a terminal."""
    info = remote_login_info()
    if not info or not info["scheme"] or re.match(r"^https?://[^@/]+@", info["url"]):
        return
    key = "credential.%s://%s.username" % (info["scheme"], info["host"])
    if run_git(["config", "--get", key])[1].strip():
        return
    accounts, _ = known_accounts(info["host"])
    if len(accounts) < 2:
        return
    while True:
        shown = accounts[:9]
        listing = "\n".join("    %d. %s" % (i + 1, a) for i, a in enumerate(shown))
        pressed = ask_key("\nSeveral accounts are signed in for %s. Which one does this project use?\n%s\nPress 1-%d (asked once for this project on this machine), A to add another account, X to decide later: " % (info["host"], listing, len(shown)), "".join(str(i + 1) for i in range(len(shown))) + "ax")
        if pressed == "a":
            accounts, _ = add_account(info["host"])
            continue
        if pressed and pressed != "x":
            run_git(["config", "--local", key, shown[int(pressed) - 1]])
            print("  [PINNED] %s -> %s (this project on this machine)" % (info["host"], shown[int(pressed) - 1]))
        return

def add_account(host):
    """The picker's A key: run Git Credential Manager's own sign-in to add another account (GitHub only), then return the refreshed (accounts, source). The browser page does not say which account it is for, so the user is told to check first."""
    if host != "github.com":
        print("  adding an account from here works for github.com only; sign in with your git host's own tool")
        return known_accounts(host)
    print("  Git Credential Manager will open its sign-in. Before you authorize, make sure the browser is signed in to the account you want to add.")
    try:
        rc = subprocess.run(["git", "credential-manager", "github", "login"], stdin=subprocess.DEVNULL, timeout=600).returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("  the sign-in could not run: %s" % exc)
        return known_accounts(host)
    print("  sign-in %s" % ("finished" if rc == 0 else "ended with code %d" % rc))
    return known_accounts(host)

def announce_account():
    """Before a push or pull the user asked for: say which account is pinned (and warn if it is no longer signed in), so a sign-in window that opens can be answered with the right one."""
    info = remote_login_info()
    if not info or not info["scheme"]:
        return
    pinned = run_git(["config", "--get", "credential.%s://%s.username" % (info["scheme"], info["host"])])[1].strip()
    if pinned:
        accounts, source = known_accounts(info["host"])
        if accounts and not any(a.lower() == pinned.lower() for a in accounts):
            print("  [ACCOUNT WARNING] pinned account %s for %s is no longer signed in (%s has: %s); run @GIT_ACCOUNT to switch or sign %s back in" % (pinned, info["host"], source, ", ".join(accounts), pinned))
        else:
            print("  [ACCOUNT] signing in to %s as %s (pinned for this project); if a sign-in window opens, authorize %s in the browser" % (info["host"], pinned, pinned))

def account_hint():
    """One footer line when the pinned account is no longer signed in, or when the automatic fetch could not sign in without a pin."""
    if MODE != "git":
        return
    info = remote_login_info()
    if not info or not info["scheme"]:
        return
    pinned = run_git(["config", "--get", "credential.%s://%s.username" % (info["scheme"], info["host"])])[1].strip()
    if pinned:
        setting = os.environ.get("LLM_HARNESS_FETCH", "60").strip().lower()
        if setting != "off":
            every = int(setting) if setting.isdigit() else 60
            stamp = os.path.join(SHARED_DIR, "fetch.json")
            seen = load_json(stamp, {}) or {}
            ckey = "acct:" + info["host"]
            cached = seen.get(ckey) if isinstance(seen.get(ckey), dict) else {}
            if time.time() - cached.get("t", 0) >= every:
                accounts, source = known_accounts(info["host"])
                seen[ckey] = {"t": time.time(), "accounts": accounts, "source": source}
                save_json(stamp, seen)
            else:
                accounts, source = cached.get("accounts", []), cached.get("source", "")
            if accounts and not any(a.lower() == pinned.lower() for a in accounts):
                print("=== GIT ACCOUNT: pinned account %s for %s is no longer signed in (%s has: %s). Pick another with @GIT_ACCOUNT, or sign %s back in ===" % (pinned, info["host"], source, ", ".join(accounts), pinned))
        return
    if not (load_json(os.path.join(SHARED_DIR, "fetch.json"), {}) or {}).get("_signin"):
        return
    print("=== GIT ACCOUNT: the automatic fetch could not sign in to %s and this project has no account pinned; with several accounts signed in that is the usual reason. Pin one once with @GIT_ACCOUNT (kept for this project on this machine only) ===" % info["host"])

def count_pair(spec):
    """(commits only on the left, commits only on the right) for a 'A...B' range; (0, 0) when git cannot say."""
    out = run_git(["rev-list", "--left-right", "--count", spec])[1]
    try:
        left, right = out.split()
        return int(left), int(right)
    except ValueError:
        return 0, 0

def upstream_status():
    """Fetch the upstream at most every LLM_HARNESS_FETCH seconds (default 60; 'off' never; a failure or being offline is silent) and say what it has that this checkout lacks: {"up", "ahead", "behind", "files"}, or None when there is no upstream or nothing is missing. Fetching only moves the remote-tracking refs; no file in the checkout changes."""
    if MODE != "git":
        return None
    rc_up, up, _ = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if rc_up != 0:
        return None
    setting = os.environ.get("LLM_HARNESS_FETCH", "60").strip().lower()
    if setting != "off":
        every = int(setting) if setting.isdigit() else 60
        stamp = os.path.join(SHARED_DIR, "fetch.json")
        seen = load_json(stamp, {}) or {}
        if time.time() - seen.get(up, 0) >= every:
            # Comment (decision): the time is stored even when the fetch fails, so being offline costs one short wait per interval, not one per script
            # Comment (constraint): with several accounts signed in, Git Credential Manager opens an account chooser on every fetch; a fetch nobody asked for must never do that, so it runs quiet and is simply skipped when it cannot authenticate by itself
            rc_f, out_f, err_f = run_git_network(["fetch", "--quiet", up.split("/", 1)[0]], timeout=8, quiet=True)
            seen["_signin"] = bool(rc_f and re.search(r"terminal prompts disabled|could not read username|authentication failed|invalid username or password", out_f + " " + err_f, re.I))
            seen[up] = time.time()
            save_json(stamp, seen)
    ahead, behind = count_pair("HEAD...@{u}")
    if not behind:
        return None
    return {"up": up, "ahead": ahead, "behind": behind, "files": run_git(["diff", "--name-only", "HEAD...@{u}"])[1].splitlines()}

def upstream_line(me):
    """The footer's UPSTREAM line: the incoming files sorted into 'inside your scope', project memory and other files. Nothing is pulled."""
    st = upstream_status()
    if not st:
        return
    mine = ((((load_json(sessions_path(), {}) or {}).get(me) or {}).get("scope") or {}).get("paths", [])) if me else []
    inside = [f for f in st["files"] if any(scope_path_covers(f, e) for e in mine)]
    memory = [f for f in st["files"] if f.startswith(WORKSPACE_NOTES_DIR + "/") and f not in inside]
    other = [f for f in st["files"] if f not in inside and f not in memory]
    few = lambda items: ", ".join(items[:6]) + (" +%d more" % (len(items) - 6) if len(items) > 6 else "")
    parts = (["INSIDE YOUR SCOPE: " + few(inside)] if inside else []) + (["project memory: " + few(memory)] if memory else []) + (["other files: " + few(other)] if other else [])
    if memory and not has_merge_rules():
        parts.append("the harness's merge rules for notes and verdicts are not in .gitattributes yet (README: Several chats), so merging that memory may leave conflict markers")
    print("=== UPSTREAM: %s has %d commit(s) this checkout lacks%s | incoming changes: %s | nothing was pulled; %s ===" % (st["up"], st["behind"], " and this checkout has %d the upstream lacks (diverged)" % st["ahead"] if st["ahead"] else "", "; ".join(parts) or "none in files", "if INSIDE YOUR SCOPE is listed stop changing those files and tell the user, otherwise bring them in with @GIT_PULL once your work is committed (fast-forward only)" if not st["ahead"] else "a fast-forward is impossible: tell the user, and @GIT_PULL will name any conflict"))

def run_git_network(args, timeout=120, quiet=False):
    """git commands that reach the network: no terminal prompt (a missing credential fails at once instead of hanging the run), a time limit, and never a forced update. quiet=True is for work nobody asked for (the automatic fetch): it also asks Git Credential Manager not to open its sign-in or account window (GCM_INTERACTIVE=never), so a background fetch is skipped instead of interrupting the user. -> (returncode, stdout, stderr)"""
    try:
        r = subprocess.run(["git"] + list(args), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=dict(os.environ, GIT_TERMINAL_PROMPT="0", **({"GCM_INTERACTIVE": "never"} if quiet else {})))
        return r.returncode, r.stdout.strip("\n"), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %d s (a credential prompt, or a slow connection)" % timeout
    except OSError:
        return 127, "", "git not found"

def run_repo_ops(ops):
    """@GIT_BRANCH, @GIT_WORKTREE and @GIT_TAG, each through repo_guard; merging and pushing stay with the user."""
    print("\n=== REPOSITORY ACTIONS ===")
    policy = git_policy()
    _, here, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    for op in ops:
        if op["kind"] == "branch":
            name, base = op.get("name"), op.get("base")
            exists = bool(name) and run_git(["rev-parse", "--verify", "-q", "refs/heads/" + name])[0] == 0
            why = "" if exists else new_branch_problem(name, policy)
            why = why or repo_guard("switching branches")
            if why:
                print("  [BRANCH REFUSED] %s. Nothing changed." % why)
                return False
            # Comment (decision): the local token counts (never committed alone, changed by every paste) are set aside around a switch to an existing branch and merged back, exactly as for a pull; git refuses the switch when that branch commits a different tokens.json
            parked = park_tokens(run_git(["diff", "--name-only", "HEAD", name, "--"])[1].splitlines()) if exists else None
            with state_lock():
                rc, out, err = run_git(["switch", name] if exists else ["switch", "-c", name] + ([base] if base else []))
            tokens_note = unpark_tokens(parked, rc == 0) if parked else ""
            if rc:
                print("  [BRANCH FAILED] %s. Nothing changed." % (err or out))
                return False
            if not exists:
                remember_base(name, base or here)
            print("  [BRANCH] now on %s%s" % (name, "" if exists else " (new, from %s)" % (base or here)))
            if tokens_note:
                print("  -> .llm_harness/tokens.json: the local token counts were set aside for the switch and %s (still uncommitted)" % tokens_note)
        elif op["kind"] == "worktree":
            args = op.get("args") or []
            if args[:1] == ["list"]:
                print("  " + run_git(["worktree", "list"])[1].replace("\n", "\n  "))
                continue
            if args[:1] == ["add"] and len(args) in (2, 4) and (len(args) == 2 or args[2] == "from"):
                name, base = args[1], (args[3] if len(args) == 4 else None)
                exists = run_git(["rev-parse", "--verify", "-q", "refs/heads/" + name])[0] == 0
                why = ("" if exists else new_branch_problem(name, policy)) or repo_guard("adding a worktree", clean=False, alone=False)
                if why:
                    print("  [WORKTREE REFUSED] %s. Nothing changed." % why)
                    return False
                path = os.path.abspath(os.path.join("..", "%s.%s" % (os.path.basename(os.path.abspath(".")), re.sub(r"[^\w.\-]+", "-", name))))
                rc, out, err = run_git(["worktree", "add", path, name] if exists else ["worktree", "add", "-b", name, path] + ([base] if base else []))
                if rc:
                    print("  [WORKTREE FAILED] %s. Nothing changed." % (err or out))
                    return False
                if not exists:
                    remember_base(name, base or here)
                print("  [WORKTREE] %s on branch %s%s\n  -> continue that work with '@WORKSPACE %s'; script numbers stay shared, claims and undo are that folder's own" % (path, name, "" if exists else " (new, from %s)" % (base or here), path))
                continue
            if args[:1] == ["remove"] and len(args) == 2:
                _, listing, _ = run_git(["worktree", "list", "--porcelain"])
                target = None
                for block in listing.split("\n\n"):
                    wt = dict(l.split(" ", 1) for l in block.splitlines() if " " in l)
                    if wt.get("branch") == "refs/heads/" + args[1] or os.path.normcase(os.path.abspath(wt.get("worktree", ""))) == os.path.normcase(os.path.abspath(args[1])):
                        target = wt.get("worktree")
                if not target or os.path.normcase(os.path.abspath(target)) == os.path.normcase(os.path.abspath(".")):
                    print("  [WORKTREE REFUSED] %s. Nothing changed." % ("no other worktree is on %s" % args[1] if not target else "this is the checkout the script runs in"))
                    return False
                if run_git(["-C", target, "status", "--porcelain"])[1].strip():
                    print("  [WORKTREE REFUSED] %s has uncommitted or untracked changes; commit them there first. Nothing changed." % target)
                    return False
                rc, out, err = run_git(["worktree", "remove", target])
                if rc:
                    print("  [WORKTREE FAILED] %s. Nothing changed." % (err or out))
                    return False
                print("  [WORKTREE] removed %s (its branch stays; its undo journal went with the folder)" % target)
                continue
            print("  [WORKTREE REFUSED] use '@GIT_WORKTREE add <branch> [from <base>]', '@GIT_WORKTREE list' or '@GIT_WORKTREE remove <branch or path>'. Nothing changed.")
            return False
        elif op["kind"] == "tag":
            name = op.get("name") or ""
            why = ""
            if not re.match(r"^v?\d+\.\d+\.\d+(?:[-+.][\w.\-]+)?$", name):
                why = "'%s' is not a version tag like v1.4.0" % name
            elif run_git(["rev-parse", "--verify", "-q", "refs/tags/" + name])[0] == 0:
                why = "tag %s already exists" % name
            src = policy.get("tags_from")
            why = why or repo_guard("tagging", alone=False)
            if not why and src and run_git(["merge-base", "--is-ancestor", "HEAD", src])[0] != 0:
                why = "this commit is not part of %s's history; this project tags only commits on %s" % (src, src)
            if not why and policy.get("tag_changelog"):
                try:
                    log = read_text("CHANGELOG.md")
                except OSError:
                    log = ""
                if not re.search(r"(?m)^##\s+v?%s\b" % re.escape(name.lstrip("v")), log):
                    why = "CHANGELOG.md has no '## %s' section, which this project requires before tagging" % name.lstrip("v")
            if why:
                print("  [TAG REFUSED] %s. Nothing changed." % why)
                return False
            rc, out, err = run_git(["tag", "-a", name, "-m", op.get("msg") or "release " + name])
            if rc:
                print("  [TAG FAILED] %s. Nothing changed." % (err or out))
                return False
            print("  [TAGGED] %s at %s\n  -> publish it with @GIT_PUSH tag %s once the user says so (a pushed release tag can start a deployment)" % (name, run_git(["rev-parse", "--short", "HEAD"])[1], name))
        elif op["kind"] == "push":
            what = (op.get("what") or "").strip()
            _, branch, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
            rc_up, up, _ = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
            remotes = run_git(["remote"])[1].split()
            remote = up.split("/", 1)[0] if rc_up == 0 else ("origin" if "origin" in remotes else (remotes[0] if len(remotes) == 1 else ""))
            tag = what[4:].strip() if what.lower().startswith("tag ") else ""
            why = ""
            if what and not tag:
                why = "use '@GIT_PUSH' for the current branch, or '@GIT_PUSH tag <name>' for one tag"
            elif not remote:
                why = "there is no remote to push to (git remote add origin <url>)"
            elif tag:
                if run_git(["rev-parse", "--verify", "-q", "refs/tags/" + tag])[0] != 0:
                    why = "there is no tag %s here; create it with @GIT_TAG first" % tag
            elif branch == "HEAD":
                why = "HEAD is detached; switch to a branch first"
            elif branch in (policy.get("protected") or []):
                why = "%s is a protected branch (git.json): push a feature branch and merge it by pull request" % branch
            why = why or repo_guard("pushing", clean=False, alone=False)
            if why:
                print("  [PUSH REFUSED] %s. Nothing was pushed." % why)
                return False
            ahead = []
            if tag:
                args, shown = ["push", remote, "refs/tags/" + tag], "tag %s -> %s" % (tag, remote)
            else:
                ahead = run_git(["log", "--oneline", "@{u}..HEAD"])[1].splitlines() if rc_up == 0 else []
                if rc_up == 0 and not ahead:
                    print("  [PUSH] nothing to push: %s is level with %s" % (branch, up))
                    continue
                args, shown = ["push"] + ([] if rc_up == 0 else ["-u"]) + [remote, branch], "%s -> %s/%s" % (branch, remote, branch)
            offer_account_pin()
            announce_account()
            # Comment (invariant): a push is never forced and never takes a refspec from the script; a rejected push is reported, not overridden
            rc, out, err = run_git_network(args)
            text = "\n".join(x for x in (out, err) if x)
            if rc == 0:
                print("  [PUSHED] %s%s" % (shown, " (%d commit(s): %s)" % (len(ahead), ", ".join(c.split()[0] for c in ahead[:6])) if ahead else ""))
                print("  -> published; take it back with a revert commit, never a forced push")
            elif re.search(r"rejected|non-fast-forward|fetch first", text):
                print("  [PUSH REJECTED] the remote has commits this branch lacks (someone pushed first). Nothing was forced: bring them in first, then push again.")
                return False
            else:
                print("  [PUSH FAILED] %s" % (text.splitlines()[-1] if text else "exit code %d" % rc))
                return False
        elif op["kind"] == "pull":
            rc_up, up, _ = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
            why = "this branch has no upstream to pull from (the first @GIT_PUSH sets one)" if rc_up != 0 else repo_guard("pulling")
            if why:
                print("  [PULL REFUSED] %s. Nothing changed." % why)
                return False
            offer_account_pin()
            announce_account()
            rc, out, err = run_git_network(["fetch", "--quiet", up.split("/", 1)[0]], timeout=60)
            if rc:
                print("  [PULL FAILED] could not fetch %s: %s. Nothing changed." % (up, (err or out).splitlines()[-1] if (err or out) else "exit code %d" % rc))
                return False
            ahead, behind = count_pair("HEAD...@{u}")
            if not behind:
                print("  [PULL] already up to date with %s" % up)
                continue
            files = run_git(["diff", "--name-only", "HEAD...@{u}"])[1].splitlines()
            if ahead:
                rc, out, _ = run_git(["merge-tree", "--write-tree", "--name-only", "HEAD", up])
                if rc == 1:
                    names = []
                    for line in out.splitlines()[1:]:
                        if not line.strip():
                            break
                        names.append(line.strip())
                    verdict = "merging them would conflict in: %s" % ", ".join(names[:8])
                elif rc == 0:
                    verdict = "merging them would be clean"
                else:
                    verdict = "this git cannot preview the merge"
                print("  [PULL REFUSED] this branch is %d ahead and %d behind %s, so a fast-forward is impossible (%s). Nothing changed: tell the user, who decides between a merge and a rebase." % (ahead, behind, up, verdict))
                return False
            # Comment (invariant): a pull is a fast-forward of a clean checkout or nothing, so it never merges and never touches local work; the old position is bookmarked first
            bookmark = "refs/llm_harness/backup/" + time.strftime("%Y%m%d-%H%M%S")
            run_git(["update-ref", bookmark, "HEAD"])
            # Comment (decision): tokens.json changes with every paste on every machine and is never committed alone, so a pull whose incoming commits change it too would be refused by git; the local counts are set aside and merged back with the tokens merge rule
            parked = park_tokens(files)
            rc, out, err = run_git(["merge", "--ff-only", up])
            tokens_note = unpark_tokens(parked, rc == 0) if parked else ""
            if rc:
                print("  [PULL FAILED] %s. Nothing changed." % ((err or out).splitlines()[-1] if (err or out) else "exit code %d" % rc))
                return False
            mine = ((((load_json(sessions_path(), {}) or {}).get(CURRENT_SESSION) or {}).get("scope") or {}).get("paths", [])) if CURRENT_SESSION else []
            hit = [f for f in files if any(scope_path_covers(f, e) for e in mine)]
            print("  [PULLED] fast-forwarded %d commit(s) from %s; %d file(s) changed: %s%s" % (behind, up, len(files), ", ".join(files[:8]) + (" +%d more" % (len(files) - 8) if len(files) > 8 else ""), "; INSIDE YOUR SCOPE: " + ", ".join(hit[:6]) if hit else ""))
            print("  -> where this branch was is bookmarked as %s; going back is the user's command (a hard reset), and @UNDO does not cover a pull" % bookmark)
            if tokens_note:
                print("  -> .llm_harness/tokens.json: the local token counts were set aside for the pull and %s (still uncommitted)" % tokens_note)
        elif op["kind"] == "merge":
            arg = (op.get("arg") or "").strip()
            in_merge = run_git(["rev-parse", "-q", "--verify", "MERGE_HEAD"])[0] == 0
            if arg == "--abort":
                if not in_merge:
                    print("  [MERGE REFUSED] no merge is in progress. Nothing changed.")
                    return False
                rc, out, err = run_git(["merge", "--abort"])
                if rc:
                    print("  [MERGE FAILED] %s" % ((err or out).splitlines()[-1] if (err or out) else "exit code %d" % rc))
                    return False
                print("  [MERGE ABORTED] restored pre-merge state")
                continue
            if arg == "--continue":
                if not in_merge:
                    print("  [MERGE REFUSED] no merge is in progress. Nothing changed.")
                    return False
                unmerged = [p for p in run_git(["diff", "--name-only", "--diff-filter=U"])[1].splitlines() if p.strip()]
                still = []
                for p in unmerged:
                    try:
                        txt = open(p, "r", encoding="utf-8", errors="replace").read()
                        if "<<<<<<<" in txt or ">>>>>>>" in txt:
                            still.append(p)
                    except OSError:
                        still.append(p)
                if still:
                    print("  [MERGE REFUSED] conflict markers remain in: %s. Resolve them before '@GIT_MERGE --continue'." % ", ".join(still))
                    return False
                if unmerged:
                    run_git(["add", "--"] + unmerged)
                rc, out, err = run_git(["commit", "--no-edit"])
                if rc:
                    print("  [MERGE FAILED] %s" % ((err or out).splitlines()[-1] if (err or out) else "exit code %d" % rc))
                    return False
                print("  [MERGED] merge commit completed on %s" % here)
                continue
            ref = arg
            if not ref:
                rc_up, up, _ = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
                if rc_up != 0:
                    print("  [MERGE REFUSED] no ref given and this branch has no upstream. Nothing changed.")
                    return False
                ref = up
            why = repo_guard("merging")
            if why:
                print("  [MERGE REFUSED] %s. Nothing changed." % why)
                return False
            bookmark = "refs/llm_harness/backup/" + time.strftime("%Y%m%d-%H%M%S")
            run_git(["update-ref", bookmark, "HEAD"])
            files = run_git(["diff", "--name-only", "HEAD..." + ref])[1].splitlines()
            parked = park_tokens(files)
            rc, out, err = run_git(["merge", "--no-edit", ref])
            tokens_note = unpark_tokens(parked, rc == 0) if parked else ""
            if rc == 0:
                print("  [MERGED] merged %s into %s" % (ref, here))
                print("  -> pre-merge HEAD is bookmarked as %s" % bookmark)
                if tokens_note:
                    print("  -> .llm_harness/tokens.json: the local token counts were set aside for the merge and %s (still uncommitted)" % tokens_note)
                continue
            conflicts = [p for p in run_git(["diff", "--name-only", "--diff-filter=U"])[1].splitlines() if p.strip()]
            if conflicts:
                print("  [MERGE CONFLICTS] merging %s stopped with conflicts in %d file(s): %s" % (ref, len(conflicts), ", ".join(conflicts)))
                print("  -> resolve the conflict markers with @HUNK, then finish with '@GIT_MERGE --continue' (or undo with '@GIT_MERGE --abort'; pre-merge HEAD is bookmarked as %s)" % bookmark)
                return False
            print("  [MERGE FAILED] %s. Nothing changed." % ((err or out).splitlines()[-1] if (err or out) else "exit code %d" % rc))
            return False
        elif op["kind"] == "remote":
            words = list(op.get("args") or [])
            if words and words[0].lower() in ("add", "set-url"):
                words = words[1:]
            if not words:
                have = run_git(["remote", "-v"])[1].strip()
                print("  [GIT REMOTE] %s" % (have.replace("\n", "\n    ") if have else "this repository has no remote yet; add one with @GIT_REMOTE <name> <url>"))
                continue
            name, url = words[0], (words[1] if len(words) > 1 else "")
            if len(words) > 2 or not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", name):
                print("  [GIT REMOTE REFUSED] expected @GIT_REMOTE [<name> [<url>]]; a name holds letters, digits, dots, dashes and underscores. Nothing changed.")
                return False
            rc_old, old, _ = run_git(["remote", "get-url", name])
            old = old.strip() if rc_old == 0 else ""
            if not url:
                print("  [GIT REMOTE] %s -> %s" % (name, old or "no such remote"))
                continue
            # Comment (invariant): only a network address the owner typed is accepted, with no password or token inside it (it would be kept in plain text in .git/config and echoed here); a remote is added or its address changed, never removed or renamed
            if url.startswith("-") or not re.match(r"^(https://[^\s/@]+/\S+|ssh://[A-Za-z0-9_.-]+@[^\s/@:]+(:\d+)?/\S+|[A-Za-z0-9_.-]+@[^\s:/]+:\S+)$", url):
                print("  [GIT REMOTE REFUSED] '%s' is not an https:// or ssh address without a password or token in it (sign in with @GIT_ACCOUNT instead). Nothing changed." % url)
                return False
            if old == url:
                print("  [GIT REMOTE] %s already points at %s; nothing to change" % (name, url))
                continue
            rc, out, err = run_git(["remote", "set-url", name, url] if old else ["remote", "add", name, url])
            if rc:
                print("  [GIT REMOTE FAILED] %s" % ((err or out).splitlines()[-1] if (err or out) else "exit code %d" % rc))
                return False
            print("  [GIT REMOTE] %s" % ("changed %s from %s to %s" % (name, old, url) if old else "added %s -> %s" % (name, url)))
            print("  -> @GIT_PUSH publishes the current branch there (it sets the upstream the first time); @GIT_ACCOUNT pins the account git signs in with")
        elif op["kind"] == "account":
            info = remote_login_info()
            if not info:
                print("  [GIT ACCOUNT] this repository has no remote to sign in to")
                continue
            if not info["scheme"]:
                print("  [GIT ACCOUNT] %s is not an https remote (an SSH key picks the account there), so there is nothing to pin" % info["url"])
                continue
            key = "credential.%s://%s.username" % (info["scheme"], info["host"])
            pinned = run_git(["config", "--local", "--get", key])[1].strip()
            accounts, source = known_accounts(info["host"])
            want = (op.get("arg") or "").strip()
            if want.lower() == "clear":
                if pinned:
                    run_git(["config", "--local", "--unset", key])
                print("  [GIT ACCOUNT] %s" % ("cleared: this project no longer pins an account for %s" % info["host"] if pinned else "nothing was pinned for %s" % info["host"]))
                continue
            if want:
                match = next((a for a in accounts if a.lower() == want.lower()), None)
                if accounts and not match:
                    print("  [GIT ACCOUNT REFUSED] %s is not among the accounts signed in for %s (%s); add it first with: git credential-manager github login. Nothing changed." % (want, info["host"], ", ".join(accounts)))
                    return False
                pick = match or want
                run_git(["config", "--local", key, pick])
                print("  [PINNED] %s -> %s (this project on this machine)" % (info["host"], pick))
                gh_after_pin(info["host"], pick, source)
                continue
            while True:
                print("  [GIT ACCOUNT] %s%s" % (info["host"], "  (accounts from %s)" % source if source else ""))
                for i, a in enumerate(accounts):
                    print("    %d. %s%s" % (i + 1, a, "   <- pinned for this project" if pinned and a.lower() == pinned.lower() else ""))
                if not accounts:
                    print("    none found")
                if not pinned:
                    print("  none pinned yet: git may ask which account to use each time")
                shown = accounts[:9]
                lead = "Press 1-%d to pin one for this project, " % len(shown) if len(shown) > 1 else "Press 1 to pin it for this project, " if shown else "Press "
                pressed = ask_key("\n%sA to add %s account, X to skip: " % (lead, "another" if shown else "an"), "".join(str(i + 1) for i in range(len(shown))) + "ax")
                if pressed == "a":
                    accounts, source = add_account(info["host"])
                    continue
                if pressed and pressed != "x":
                    pick = shown[int(pressed) - 1]
                    run_git(["config", "--local", key, pick])
                    print("  [PINNED] %s -> %s (this project on this machine)" % (info["host"], pick))
                    gh_after_pin(info["host"], pick, source)
                elif pressed is None:
                    print("  -> pin one with @GIT_ACCOUNT <account>, add one with 'git credential-manager github login', or remove the pin with @GIT_ACCOUNT clear")
                break
    return True

def git_policy():
    """The project's optional branch and commit policy, .llm_harness/git.json ({} when absent). A harness safety rule, not a security boundary: GitHub branch protection is the real enforcement."""
    path = os.path.join(WORKSPACE_NOTES_DIR, "git.json")
    if not os.path.isfile(path):
        return {}
    pol = load_json(path, None)
    if not isinstance(pol, dict) or pol.get("version") != 1:
        print("  [GIT POLICY] .llm_harness/git.json is not valid JSON with \"version\": 1, so it is ignored.")
        return {}
    return pol

def commit_message_problem(msg, policy):
    """Why a commit message breaks the conventional-commit form type(scope): subject, or '' when it is fine; commitlint, where a project installs it, stays authoritative."""
    types = policy.get("commit_types") or COMMIT_TYPES
    head = msg.strip()
    m = re.match(r"^(\w+)(\([^()]+\))?(!)?: (\S.*)$", head)
    if not m:
        return "it needs the form type(scope): subject, e.g. fix(api): handle empty payloads"
    if m.group(1) not in types:
        return "type '%s' is not one of: %s" % (m.group(1), ", ".join(types))
    limit = policy.get("header_max")
    if isinstance(limit, int) and len(head) > limit:
        return "it is %d characters long; this project allows at most %d" % (len(head), limit)
    return ""

def run_git_ops(ops):
    """Pre-flight guard, optional fold of unpushed commits, path-scoped commits; any failure restores the original HEAD."""
    print("\n=== GIT ACTIONS ===")
    blockers = git_blockers()
    if blockers:
        print("  [ABORTED] in-progress git operation (%s). Nothing was committed. -> the user must finish or abort it first." % ", ".join(blockers))
        return False
    _, branch, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    rc, orig, _ = run_git(["rev-parse", "--verify", "-q", "HEAD"])
    orig = orig if rc == 0 else None
    if orig and branch == "HEAD":
        print("  [ABORTED] detached HEAD. Check out a branch first. Nothing was committed.")
        return False
    policy = git_policy()
    commits = [op for op in ops if op["kind"] == "commit"]
    for op in commits:
        why = commit_message_problem(op["msg"], policy)
        if why:
            print("  [COMMIT REFUSED] '%s': %s. Nothing was committed. -> resend the commit with a fixed message" % (op["msg"][:80], why))
            return False
    if commits and branch in (policy.get("protected") or []):
        print("  [COMMIT REFUSED] %s is a protected branch in .llm_harness/git.json: commit on a feature branch; it reaches %s through a pull request. Nothing was committed." % (branch, branch))
        return False
    if commits and policy.get("branches") and not re.match(policy["branches"], branch or ""):
        print("  [BRANCH NAME] %s does not match this project's branch pattern %s; the commit goes ahead, but rename the branch before pushing" % (branch, policy["branches"]))

    def fail(msg):
        print("  [FAILED] " + msg)
        if orig:
            run_git(["reset", "--soft", orig])
            run_git(["reset", "-q"])
            print("  [RESTORED] HEAD is back at %s; working tree untouched; nothing is staged. -> fix the cause above and resend under the next script number." % orig[:10])
        return False

    folded = committed = False
    fold_paths = []
    for op in ops:
        if op["kind"] == "fold":
            n = op["n"]
            busy = [nm for nm, rec in load_json(sessions_path(), {}).items() if nm != CURRENT_SESSION and rec.get("scope")]
            if busy:
                return fail("@GIT_FOLD is blocked while other sessions hold scopes (%s): folding would rewrite their commits too" % ", ".join(busy))
            if folded or committed:
                return fail("@GIT_FOLD must be the first and only fold in the script")
            if not orig or n < 1:
                return fail("@GIT_FOLD needs a positive commit count and existing history")
            if run_git(["diff", "--cached", "--quiet"])[0] != 0:
                return fail("the index has staged changes; unstage them before folding")
            for k in range(n):
                rc, out, _ = run_git(["rev-list", "--parents", "-n", "1", "HEAD~%d" % k])
                if rc != 0 or len(out.split()) != 2:
                    return fail("HEAD~%d is a root or merge commit: cannot fold %d commit(s)" % (k, n))
            rc, refs, _ = run_git(["for-each-ref", "--contains", "HEAD~%d" % (n - 1), "refs/remotes"])
            if rc != 0 or refs.strip():
                return fail("the last %d commit(s) reach pushed history, which is immutable" % n)
            _, names, _ = run_git(["diff", "--name-only", "--no-renames", "-z", "HEAD~%d" % n, "HEAD"])
            fold_paths = [p for p in names.split("\0") if p]
            rc, _, err = run_git(["reset", "-q", "HEAD~%d" % n])
            if rc != 0:
                return fail("git reset: " + err)
            folded = True
            print("  [FOLDED] last %d unpushed commit(s) reset; their changes are back in the working tree for re-slicing" % n)
        else:
            paths = [MEMORY_FILES.get(p.strip().replace("\\", "/").lstrip("/")) or safe_rel(p) for p in op["paths"]]
            if not op["msg"] or not paths or None in paths:
                return fail("@GIT_COMMIT needs a subject and repo-relative paths: '%s'" % op["msg"])
            if CURRENT_SESSION:
                foreign = [(p, foreign_uncommitted(p)) for p in paths]
                foreign = [(p, s) for p, s in foreign if s]
                if foreign:
                    return fail("these paths hold uncommitted changes from other active sessions, and committing them would take that work along: %s (they commit theirs, hand it over, or the user runs --release)" % "; ".join("%s: %s" % (p, ", ".join(n + chat_link(n) for n in s)) for p, s in foreign))
            rc, _, err = run_git(["add", "-A", "--"] + paths)
            if rc != 0:
                return fail("git add: " + err)
            rc, out, err = run_git(["commit", "-m", op["msg"], "--"] + paths)
            if rc != 0:
                return fail("git commit '%s': %s" % (op["msg"], ((err or out).strip().splitlines() or ["error"])[-1]))
            committed = True
            print("  [COMMITTED] %s %s (%d path(s))" % (run_git(["rev-parse", "--short", "HEAD"])[1], op["msg"], len(paths)))
            kind = re.match(r"^(feat|fix|perf)\b", op["msg"])
            if kind and os.path.isfile("CHANGELOG.md") and "CHANGELOG.md" not in paths:
                print("  -> CHANGELOG.md was not in this %s commit: add a line under '## Unreleased' and commit it with the next change" % kind.group(1))
    if folded and fold_paths:
        _, left, _ = run_git(["status", "--porcelain", "--"] + fold_paths)
        if left.strip():
            return fail("the fold left these paths out of the re-sliced commits: " + ", ".join(x[3:] for x in left.splitlines()))
    return committed

# ---------------------------------------------------------------- Stage: Read-only directives

# Comment (decision): types that are never code a chat needs to see in a listing; .json and .sql are left out on purpose, since configs and migrations are code
JUNK_EXTS = frozenset(".png .jpg .jpeg .gif .bmp .ico .webp .tif .tiff .psd .svgz .mp4 .mov .avi .mkv .webm .mp3 .wav .ogg .flac .m4a .zip .7z .rar .tar .gz .tgz .bz2 .xz .parquet .feather .arrow .avro .orc .db .sqlite .sqlite3 .pkl .pickle .npy .npz .h5 .exe .dll .so .dylib .pyc .pyo .class .jar .o .obj .lib .a .pdb .woff .woff2 .ttf .otf .eot .pdf .log".split())

def repo_files(base):
    """Files under base: tracked plus untracked-but-not-ignored in git mode, else a walk that skips tool and build folders."""
    rc, out, _ = run_git(["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", base]) if MODE == "git" else (1, "", "")
    if rc == 0:
        files = [p for p in out.split("\0") if p and os.path.isfile(p)]
    else:
        files = []
        for r, dirs, fs in os.walk(base):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
            files += [os.path.relpath(os.path.join(r, f), ".").replace("\\", "/") for f in fs]
    return sorted(set(f for f in files if not SKIP_DIRS.intersection(f.split("/")[:-1])))

def run_list(arg, recursive):
    show_all = bool(re.search(r"\|\s*all\s*(?=\||$)", arg, re.IGNORECASE))
    arg = re.sub(r"\|\s*all\s*(?=\||$)", "", arg, flags=re.IGNORECASE)
    arg, depth = split_depth(arg)
    dp = safe_rel(arg, allow_root=True)
    label = "RECURSIVE" if recursive else "NON-RECURSIVE"
    if dp is None or not os.path.isdir(dp):
        print("\n=== DIR LISTING (%s): /%s (NOT FOUND) ===" % (label, arg.strip().lstrip("/")))
        return
    print("\n=== DIR LISTING (%s): /%s%s ===" % (label, "" if dp == "." else dp, " | depth %d" % depth if depth else ""))
    if recursive:
        rows = [r for r in repo_files(dp) if within_depth(r, "" if dp == "." else dp, depth)]
    else:
        rows = [x + ("/" if os.path.isdir(os.path.join(dp, x)) else "") for x in sorted(os.listdir(dp)) if x != ".git"]
    # Comment (decision): a listing is for finding code, so what .gitignore excludes and binary or media files are counted instead of listed, and '| all' lists them (the owner's request)
    hidden = []
    if not show_all:
        base = "" if dp == "." else dp.replace("\\", "/").rstrip("/") + "/"
        ignored = set()
        if not recursive and MODE == "git" and rows:
            ignored = set(run_git(["check-ignore", "--"] + [base + x for x in rows])[1].splitlines())
        keep = []
        for x in rows:
            junk = not x.endswith("/") and os.path.splitext(x)[1].lower() in JUNK_EXTS
            (hidden if junk or (base + x) in ignored else keep).append(x)
        rows = keep
    for x in rows[:LIST_CAP]:
        print("  " + x)
    if len(rows) > LIST_CAP:
        print("  ... +%d more (list a subfolder)" % (len(rows) - LIST_CAP))
    if hidden:
        kinds = {}
        for h in hidden:
            k = os.path.splitext(h.rstrip("/"))[1].lower() or "ignored"
            kinds[k] = kinds.get(k, 0) + 1
        most = sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
        print("  (%d hidden, ignored by .gitignore or binary/media: %s; add '| all' to list them)" % (len(hidden), ", ".join("%s %d" % kv for kv in most)))

def run_xref(arg):
    """@XREF <symbol> is a text search; '| callers', '| callees' or '| impact' asks the code graph."""
    sym, _, mode = arg.partition("|")
    sym, mode = sym.strip(), mode.strip().lower()
    if not mode:
        return xref_text(sym)
    if mode not in GRAPH_MODES:
        print("\n=== XREF: %s | %s ===" % (sym, mode))
        print("  [WARNING] unknown @XREF mode '%s' -> use callers, callees or impact" % mode)
        return
    graph_xref(sym, mode)

def xref_text(sym, header=True):
    """Whole-word references to a symbol across the repo, definitions first."""
    if header:
        print("\n=== XREF: %s ===" % sym)
    if not sym:
        return
    pat = re.compile(r"(?<![\w$])" + re.escape(re.sub(r"\(\)$", "", sym)) + r"(?![\w$])")
    defs, refs = [], []
    for rel in repo_files("."):
        try:
            if os.path.getsize(rel) > 1000000:
                continue
            raw = read_bytes(rel)
        except OSError:
            continue
        if b"\0" in raw[:4096]:
            continue
        for i, l in enumerate(norm_nl(raw.decode("utf-8", "replace")).split("\n")):
            if pat.search(l):
                info = def_info(l)
                row = "/%s:%d: %s" % (rel, i + 1, l.strip()[:140])
                (defs if info and pat.fullmatch(info[0]) else refs).append(row)
    for row in defs:
        print("  DEF  " + row)
    for row in refs[:XREF_CAP]:
        print("  ref  " + row)
    if len(refs) > XREF_CAP:
        print("  ... +%d more references (narrow the symbol)" % (len(refs) - XREF_CAP))
    if not defs and not refs:
        print("  (no matches)")

# ---------------------------------------------------------------- Stage: Code graph (optional codebase-memory-mcp backend)

GRAPH_MODES = {"callers": ("inbound", 1), "callees": ("outbound", 1), "impact": ("inbound", 5)}
CBM_NOISE = re.compile(r"^(level=|hint:|Preparing one-shot|Running \w+ locally|Completed \w+ \()")

def find_cbm():
    """The codebase-memory-mcp executable on PATH or in its default install folders, or None."""
    exe = shutil.which("codebase-memory-mcp")
    if exe:
        return exe
    local = os.environ.get("LOCALAPPDATA")
    cands = [os.path.expanduser("~/.local/bin/codebase-memory-mcp")]
    if local:
        cands.insert(0, os.path.join(local, "Programs", "codebase-memory-mcp", "codebase-memory-mcp.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None

def run_cbm(exe, args, timeout):
    """One-shot 'codebase-memory-mcp cli ...' call; CBM keeps every project's index in its own per-user cache -> (returncode or None, stdout, stderr-or-reason)."""
    try:
        r = subprocess.run([exe, "cli"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return None, "", "timed out after %ds" % timeout
    except OSError as e:
        return None, "", str(e)

def cbm_clean(text):
    """CBM output without its progress, hint and log lines."""
    return "\n".join(l for l in norm_nl(text).split("\n") if not CBM_NOISE.match(l.strip())).strip("\n")

def cbm_json(text):
    """The first JSON object in CBM output, or None."""
    lines = norm_nl(text).split("\n")
    for i, l in enumerate(lines):
        if l.lstrip().startswith("{"):
            for chunk in ("\n".join(lines[i:]), l):
                try:
                    obj = json.loads(chunk)
                    return obj if isinstance(obj, dict) else None
                except ValueError:
                    pass
    return None

def workspace_stamp():
    """Fingerprint of the source files (path, size, mtime) that moves whenever source moves: git HEAD plus changed files, or every file without git."""
    if MODE != "git":
        h = hashlib.sha1()
        for rel in repo_files("."):
            try:
                st = os.stat(rel)
                h.update(("%s:%d:%d|" % (rel, st.st_size, st.st_mtime_ns)).encode("utf-8", "surrogateescape"))
            except OSError:
                pass
        return h.hexdigest()
    h = hashlib.sha1(run_git(["rev-parse", "-q", "--verify", "HEAD"])[1].encode())
    _, out, _ = run_git(["status", "--porcelain", "-z", "--untracked-files=all"])
    for entry in out.split("\0"):
        path = entry[3:] if len(entry) > 3 and entry[2] == " " else entry
        h.update(entry.encode("utf-8", "surrogateescape"))
        try:
            st = os.stat(path)
            h.update(("%d:%d" % (st.st_size, st.st_mtime_ns)).encode())
        except OSError:
            pass
    return h.hexdigest()

GAP_SECTIONS = {"parse_partial": "partly parsed (lines %s)", "parse_unusable": "unusable", "skipped": "skipped"}

def index_gaps(exe, project):
    """{path: problem} for files CBM indexed only partly, could not use, or skipped, from index_status."""
    rc, out, _ = run_cbm(exe, ["index_status", "--project", project, "--diagnostics", "full"], 60)
    gaps, section = {}, None
    if rc != 0:
        return gaps
    for ln in cbm_clean(out).split("\n"):
        s = ln.strip()
        if s and not ln.startswith(" ") and s.endswith(":"):
            section = s[:-1]
            continue
        if section in GAP_SECTIONS and indent_of(ln) >= 4 and s and not re.match(r"^\w+:", s):
            parts = s.split()
            text = GAP_SECTIONS[section]
            gaps[parts[0].replace("\\", "/")] = text % (parts[1] if len(parts) > 1 else "?") if "%s" in text else text
    return gaps

_COVERAGE_SHOWN = []

def print_coverage_note(focus=None):
    """Warn when a graph answer may be incomplete because CBM parsed some source files only partly."""
    gaps = load_json(GRAPH_PATH, {}).get("gaps") or {}
    if focus and focus in gaps:
        print("  -> coverage: /%s itself was %s, so the graph may miss definitions or calls in it" % (focus, gaps[focus]))
    code = [p for p in gaps if p != focus and p.endswith(CODE_EXTS)]
    if code and not _COVERAGE_SHOWN:
        _COVERAGE_SHOWN.append(True)
        print("  -> coverage: %d source file(s) were only partly indexed (%s); graph links inside them may be missing" % (len(code), ", ".join("/%s %s" % (p, gaps[p]) for p in code[:3])))

def ensure_graph_index(exe, force=False):
    """CBM project name for this workspace, re-indexing first whenever the workspace changed (or when forced). -> (project, error)"""
    g = load_json(GRAPH_PATH, {})
    stamp = workspace_stamp()
    if not force and g.get("project") and g.get("stamp") == stamp:
        return g["project"], None
    rc, out, err = run_cbm(exe, ["index_repository", "--repo-path", os.path.abspath(".")], 600)
    if rc is None:
        return None, "index_repository " + err
    data = cbm_json(out) or cbm_json(err)
    if not data or not data.get("project"):
        tail = " | ".join((cbm_clean(err) or cbm_clean(out)).splitlines()[-3:])
        hint = " (if another app is running CBM with a different cache folder, close it and retry)" if "cache" in tail.lower() else ""
        return None, "index_repository failed: " + tail + hint
    save_json(GRAPH_PATH, {"project": data["project"], "stamp": stamp, "gaps": index_gaps(exe, data["project"])})
    print("  (graph index %s for project %s)" % ("refreshed" if g.get("project") else "built", data["project"]))
    return data["project"], None

def norm_key(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

def graph_xref(sym, mode):
    """Callers, callees or impact from codebase-memory-mcp; falls back to text search, labelled as such, when the graph cannot answer."""
    sym = re.sub(r"\(\)$", "", sym)
    parts = [p for p in re.split(r"\.|::", sym) if p]
    leaf = parts[-1] if parts else sym
    print("\n=== XREF: %s | %s (code graph) ===" % (sym, mode))

    def fallback(reason):
        print("  -> graph unavailable (%s); whole-word text matches below are NOT proven %s." % (reason, mode))
        xref_text(leaf, header=False)

    exe = find_cbm()
    if not exe:
        return fallback("codebase-memory-mcp is not installed")
    project, err = ensure_graph_index(exe)
    if not project:
        return fallback(err)
    direction, depth = GRAPH_MODES[mode]
    name = leaf
    for attempt in range(2):
        rc, out, err = run_cbm(exe, ["trace_path", "--project", project, "--function-name", name,
                                     "--direction", direction, "--depth", str(depth)], 120)
        if rc is None:
            return fallback("trace_path " + err)
        body = cbm_clean(out)
        data = cbm_json(body) if body.lstrip().startswith("{") else None
        if data and data.get("status") == "ambiguous":
            sugg = data.get("suggestions") or []
            keys = [norm_key(p) for p in parts[:-1]]
            picks = [x for x in sugg if keys and all(k in norm_key("%s %s" % (x.get("qualified_name", ""), x.get("file_path", ""))) for k in keys)]
            if attempt == 0 and len(picks) == 1 and picks[0].get("qualified_name"):
                name = picks[0]["qualified_name"]
                continue
            print("  [AMBIGUOUS] %d symbols are named %s:" % (len(sugg), leaf))
            for x in sugg:
                print("    %s  (/%s)" % (x.get("qualified_name", "").replace(project + ".", ""), x.get("file_path", "")))
            print("  -> qualify it with its package, type or file, e.g. @XREF <package>.%s | %s" % (leaf, mode))
            return
        lost = data and "not indexed" in str(data.get("error", "")) + str(data.get("message", ""))
        if lost and attempt == 0:
            project, err = ensure_graph_index(exe, force=True)
            if not project:
                return fallback(err)
            continue
        if data and (data.get("error") or data.get("status") not in (None, "ok")):
            print("  [GRAPH ERROR] " + str(data.get("error") or data.get("message") or data))
            return fallback("the graph could not resolve this symbol")
        if rc != 0 or not body:
            return fallback("trace_path exited %s: %s" % (rc, (cbm_clean(err).splitlines() or ["no output"])[-1]))
        print("\n".join("  " + l for l in body.replace(project + ".", "").split("\n")))
        if mode == "callers":
            print_call_sites(leaf)
        print_coverage_note()
        print("  -> static call graph: confirm a relation in source before relying on it.")
        return

# ---------------------------------------------------------------- Stage: File and text search

def split_depth(arg):
    """'<anything> | depth N' -> (<anything>, N); (arg, None) without it."""
    m = re.search(r"\s*\|\s*depth\s+(\d+)\s*$", arg)
    return (arg[:m.start()], int(m.group(1))) if m else (arg, None)

def within_depth(rel, base, depth):
    """True when rel sits at most depth folder levels below base ('' = the workspace root; 1 = directly inside)."""
    if depth is None:
        return True
    if base and not rel.startswith(base + "/"):
        return False
    rest = rel[len(base) + 1:] if base else rel
    return rest.count("/") + 1 <= depth

def glob_files(pattern):
    """Workspace files a glob names: with a '/' it starts at the root and * stays in one folder (** crosses folders); without one it matches file names at any depth."""
    p = pattern.strip().replace("\\", "/").lstrip("/")
    if "/" in p:
        return [f for f in repo_files(".") if path_in(f, p)]
    return [f for f in repo_files(".") if fnmatch.fnmatch(f.rsplit("/", 1)[-1], p)]

def path_filter(pattern):
    """Predicate for a path pattern: a glob (with a '/' it starts at the root and * stays in one folder; without one it matches file names at any depth), else a case-insensitive substring."""
    if pattern.strip().lower().startswith("re:"):
        try:
            rx = re.compile(pattern.strip()[3:])
        except re.error as e:
            print("  [WARNING] invalid path regex: %s" % e)
            return lambda rel: False
        return lambda rel: rx.search(rel) is not None
    p = pattern.strip().replace("\\", "/").lstrip("/").lower()
    if any(c in p for c in "*?["):
        if "/" in p:
            return lambda rel: path_in(rel.lower(), p)
        return lambda rel: fnmatch.fnmatch(rel.rsplit("/", 1)[-1].lower(), p)
    return lambda rel: p in rel.lower()

def run_find(pattern):
    """Files whose path or name matches a glob or substring."""
    pattern, depth = split_depth(pattern)
    print("\n=== FIND: %s%s ===" % (pattern.strip(), " | depth %d" % depth if depth else ""))
    if not pattern.strip():
        print("  [WARNING] @FIND needs a name, path fragment or glob, e.g. '@FIND lease' or '@FIND *.vue'")
        return
    keep = path_filter(pattern)
    base = "" if pattern.strip().lower().startswith("re:") else (literal_base(pattern) if any(c in pattern for c in "*?[") else "")
    rows = [rel for rel in repo_files(".") if keep(rel) and within_depth(rel, base, depth)]
    for rel in rows[:LIST_CAP]:
        print("  /" + rel)
    if len(rows) > LIST_CAP:
        print("  ... +%d more (narrow the pattern)" % (len(rows) - LIST_CAP))
    print("  (%d file(s))" % len(rows))

def run_grep(arg):
    """Lines containing a text (case-insensitive) or matching a /regex/, optionally limited to paths after '| in'."""
    arg, depth = split_depth(arg)
    text, sep, flt = arg.rpartition(" | in ")
    if not sep:
        text, flt = arg, ""
    text = text.strip()
    print("\n=== GREP: %s%s%s ===" % (text, (" | in " + flt.strip()) if flt.strip() else "", " | depth %d" % depth if depth else ""))
    if not text:
        print("  [WARNING] @GREP needs a text or /regex/")
        return
    mr = re.match(r"^/(.+)/(i?)$", text)
    try:
        rx = re.compile(mr.group(1), re.I if mr.group(2) else 0) if mr else re.compile(re.escape(text), re.I)
    except re.error as e:
        print("  [WARNING] invalid regex: %s" % e)
        return
    in_flt = path_filter(flt) if flt.strip() else (lambda rel: True)
    base = "" if flt.strip().lower().startswith("re:") else (literal_base(flt) if any(c in flt for c in "*?[") else "")
    keep = lambda rel: in_flt(rel) and within_depth(rel, base, depth)
    hits, files = [], set()
    for rel in repo_files("."):
        if not keep(rel):
            continue
        try:
            if os.path.getsize(rel) > 1000000:
                continue
            raw = read_bytes(rel)
        except OSError:
            continue
        if b"\0" in raw[:4096]:
            continue
        for i, l in enumerate(norm_nl(raw.decode("utf-8", "replace")).split("\n")):
            if rx.search(l):
                files.add(rel)
                hits.append("  /%s:%d: %s" % (rel, i + 1, l.strip()[:160]))
    for row in hits[:GREP_CAP]:
        print(row)
    if len(hits) > GREP_CAP:
        print("  ... +%d more (narrow the text or add '| in <path>')" % (len(hits) - GREP_CAP))
    print("  (%d match(es) in %d file(s))" % (len(hits), len(files)))

# ---------------------------------------------------------------- Stage: Running commands

# Comment (decision): 'git tag' alone, 'git tag --list' and the other listing forms, and 'git stash list' or 'show' only read; the same words with a name, -d, -a or -f still write, so they stay refused
GIT_WRITE_RE = re.compile(r"(^|[;&|(]\s*)git(\.exe)?\s+(commit|push|pull|reset|rebase|merge|cherry-pick|revert|checkout|switch|stash(?!\s+(?:list|show)\b)|clean|restore|am|apply|tag(?!\s*(?:$|[;&|)]|-l\b|--list\b|-n\d*\b|--contains\b|--points-at\b|--merged\b|--no-merged\b|--sort\b))|branch\s+-[dDmM]|worktree(?!\s+list\b)|update-ref|symbolic-ref(?=\s+\S+\s+\S)|filter-branch)\b", re.I)

def kill_tree(proc):
    """Stop a command and every process it started."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ValueError):
        pass
    try:
        proc.kill()
    except OSError:
        pass

def run_command(cmd, timeout, shell):
    """Run one shell command in the workspace with no stdin; print head and tail of its combined output, exit code and time."""
    print("\n=== RUN: %s ===" % cmd)
    if GIT_WRITE_RE.search(cmd):
        print("  [REFUSED] git commands that change history or the working tree go through @GIT_COMMIT / @GIT_FOLD; publishing goes through @GIT_PUSH.")
        return
    if re.search(r"harness\.py\b.*--(grant|revoke|release|unbrake|merge|check|link|steward|auto|agent-allow)\b", cmd, re.I):
        print("  [REFUSED] --grant, --revoke, --release, --unbrake, --merge, --check, --link and --steward are the user's own commands, typed in their terminal; a script never runs them.")
        return
    if agent_mode():
        # Comment (decision): host permissions are not a sandbox, so in agent mode the harness itself is the gate: only an allowlisted program, named without a path, with arguments matching its pattern in full, run directly with no shell (so no operators, no cd, no second command)
        args, why = agent_run_args(cmd)
        if args is None:
            print("  [REFUSED] auto-shell runs only commands on this project's allowlist, as a program and its arguments with no shell: %s. Nothing was run." % why)
            print("  -> tell the user what you need to run; only they can allow it, at their terminal: harness.py --workspace <folder> --agent-allow <program> [<argument pattern>]")
            return
    elif shell == "powershell":
        prefix = "$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
        args = [shutil.which("powershell") or shutil.which("pwsh") or "powershell", "-NoProfile", "-NonInteractive", "-Command", prefix + cmd]
    else:
        args = [shutil.which("bash") or "/bin/sh", "-c", cmd]
    start = time.time()
    try:
        # Comment (constraint): a Python child writing to a pipe uses the Windows code page (cp1252), which cannot print Vietnamese or other non-Latin text, while this output is read as UTF-8; say so to Python children (only the standard streams; open() defaults are left alone)
        proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                start_new_session=(os.name != "nt"))
    except OSError as e:
        print("  [FAILED] could not start the shell: %s" % e)
        return
    try:
        raw, _ = proc.communicate(timeout=timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        try:
            raw, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            raw = b""
        code = "TIMEOUT"
    out = (raw or b"").decode("utf-8", "replace")
    lines = norm_nl(out).rstrip("\n").split("\n") if out.strip() else []
    if len(lines) > RUN_HEAD + RUN_TAIL:
        shown = lines[:RUN_HEAD] + ["  ... %d lines omitted ..." % (len(lines) - RUN_HEAD - RUN_TAIL)] + lines[-RUN_TAIL:]
    else:
        shown = lines
    for l in shown:
        print("  " + l[:400])
    print("  [exit %s | %.1fs]" % (code, time.time() - start))
    if code != 0:
        globals()["RUN_FAILED"] = True
    if code == "TIMEOUT":
        print("  -> the command hit the %ds limit and was stopped; use '@RUN --timeout <seconds> <command>' for longer jobs." % timeout)
    elif code != 0:
        print("  -> exited with code %s: judge it from the output above (some tools use non-zero codes for 'nothing found')." % code)

def print_toc(lines):
    for i, l in enumerate(lines):
        if is_toc_line(l):
            print("  L%d: %s" % (i + 1, l.rstrip()[:110]))

def tree_node_paths(lines):
    """{line index: workspace path} for the folder and file nodes of a tree file, resolved the way the drift check does."""
    proj = "/" + project_name()
    out, folders = {}, []
    for i, d, label in tree_nodes(lines):
        while folders and folders[-1][0] >= d:
            folders.pop()
        key = tree_key(label)
        if key.startswith("/"):
            path = key[len(proj):] if key == proj or key.startswith(proj + "/") else key
            segs = [s for s in path.split("/") if s]
            base = ("/".join(segs) if len(segs) != 1 or not folders else folders[-1][1] + "/" + segs[0]).strip("/")
            folders.append((d, base))
            out[i] = base
            continue
        parts = [p.strip() for p in key.split(" / ")]
        if parts and all(tree_file_name(p, folders[-1][1] if folders else "") for p in parts):
            out[i] = ((folders[-1][1] if folders else "") + "/" + parts[0]).strip("/")
    return out

def tree_verdict_mark(verdicts, path):
    """The <<verdict: ...>> mark for a tree node: every chat's verdict on that path, with stale flags."""
    recs = [v for _, p, v in verdict_items(verdicts) if p == path] if path else []
    marks = []
    for v in recs:
        new, changed, gone = verdict_changes(v, path)
        marks.append("%s%s%s%s" % (v["verdict"], " by %s" % (v.get("session") or "none") if len(recs) > 1 else "", " (campaign %s)" % v["campaign"] if v.get("campaign") else "", ", STALE" if new or changed or gone else ""))
    return "  <<verdict: %s>>" % "; ".join(marks) if marks else ""

def verdict_items(verdicts):
    """(key, path, record) for every verdict; each chat keeps its own verdict on a path (older files keyed by path alone still read)."""
    return [(k, v.get("path") or k.split("\t")[0], v) for k, v in verdicts.items()]

def active_campaigns():
    try:
        return load_json(verdicts_path(), {}).get("campaigns", {}) or {}
    except Exception:
        return {}

def apply_campaigns(P):
    """@CAMPAIGN <name> | <word> = <meaning>; ...  starts a sweep with its verdict legend; @CAMPAIGN_END <name> ends it and removes its verdicts."""
    if not P["campaigns"]:
        return
    with state_lock():
        data = load_json(verdicts_path(), {"verdicts": {}})
        camps = data.setdefault("campaigns", {})
        for kind, arg in P["campaigns"]:
            name, _, legend = arg.partition("|")
            name = re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("-")
            if not name:
                print("  [CAMPAIGN REFUSED] a campaign needs a name: %s" % arg)
                continue
            if kind == "CAMPAIGN_END":
                if name not in camps:
                    print("  [CAMPAIGN] no active campaign named %s" % name)
                    continue
                gone = [p for p, v in data["verdicts"].items() if v.get("campaign") == name]
                for p in gone:
                    del data["verdicts"][p]
                del camps[name]
                print("  [CAMPAIGN ENDED] %s: %d verdict(s) removed" % (name, len(gone)))
                continue
            words = {}
            for item in legend.split(";"):
                w, _, meaning = item.partition("=")
                if w.strip():
                    words[w.strip()] = meaning.strip()
            if not words:
                print("  [CAMPAIGN REFUSED] expected '@CAMPAIGN <name> | <word> = <meaning>; <word> = <meaning>'")
                continue
            camps[name] = {"legend": words, "started": time.time(), "by": CURRENT_SESSION}
            print("  [CAMPAIGN] %s: %s" % (name, "; ".join("%s = %s" % kv for kv in words.items())))
        os.makedirs(WORKSPACE_NOTES_DIR, exist_ok=True)
        save_json(verdicts_path(), data)

def print_footer_campaigns():
    """While a campaign runs, every footer names it with its legend and how many areas carry its verdicts."""
    camps = active_campaigns()
    if not camps:
        return
    verdicts = load_json(verdicts_path(), {"verdicts": {}}).get("verdicts", {})
    for name, cv in sorted(camps.items()):
        n = sum(1 for v in verdicts.values() if v.get("campaign") == name)
        print("=== CAMPAIGN %s (%d area(s) with a verdict): %s ===" % (name, n, "; ".join("%s = %s" % kv for kv in cv.get("legend", {}).items())))

def probe_tree(lines, target, depth):
    """Print a tree node and its descendants down to a relative depth; deeper levels collapse to a count."""
    if target.strip().upper() in ("", "TOP"):
        nodes = tree_nodes(lines)
        first, stop, limit, path = 0, len(nodes), depth, "TOP"
    else:
        _, _, note, pos = resolve_tree_scope(lines, target)
        if note:
            print("--- [NODE NOT RESOLVED: %s] ---" % note)
            return
        nodes, first, stop = pos
        limit, path = nodes[first][1] + depth, tree_path(nodes, first)
    rows, paths, verdicts = [], tree_node_paths(lines), load_json(verdicts_path(), {"verdicts": {}})["verdicts"]
    for j in range(first, stop):
        i, d, _ = nodes[j]
        if d > limit:
            continue
        e = j + 1
        while e < stop and nodes[e][1] > d:
            e += 1
        hidden = e - j - 1 if d == limit else 0
        rows.append(lines[i] + ("  <<+%d hidden>>" % hidden if hidden else "") + tree_verdict_mark(verdicts, paths.get(i)))
    print("--- [Tree: %s | depth %d | %d of %d nodes shown | <<+N hidden>> and <<verdict: ...>> are added by the harness and are not on disk] ---" % (path, depth, len(rows), stop - first))
    print("\n".join(rows))
    if len(rows) < stop - first:
        print("  -> expand one node with: @PROBE /<this file> | Tree | <node path> | <depth>")

TREE_FILE_RE = re.compile(r"^[\w.\-]+\.[A-Za-z0-9]+$")
TREE_BARE_FILE_RE = re.compile(r"^(?:[A-Z][A-Za-z]*file|LICENSE|README|CODEOWNERS|\.[\w.\-]+)$")

def tree_file_name(p, here):
    """True when a tree node names a file: a name with an extension, a well-known extensionless file (Dockerfile, Makefile, .gitignore...), or any existing file."""
    return bool(TREE_FILE_RE.match(p) or TREE_BARE_FILE_RE.match(p) or os.path.isfile((here + "/" + p).lstrip("/")))
TREE_NAME_RE = re.compile(r"([A-Za-z_$][\w$]*)\(\)")

def check_tree(rel, lines):
    """Drift check: tree nodes whose file, function/class name or # Stage anchor no longer exists in the code."""
    nodes = tree_nodes(lines)
    proj = "/" + project_name()
    texts, stale, counts, anchor_lines = {}, [], {"file": 0, "name": 0, "anchor": 0}, {}
    folders, files = [], []
    for i, d, label in nodes:
        while folders and folders[-1][0] >= d:
            folders.pop()
        while files and files[-1][0] >= d:
            files.pop()
        head = label.split(" (", 1)[0].strip()
        key = tree_key(label)
        if key.startswith("/"):
            path = key[len(proj):] if key == proj or key.startswith(proj + "/") else key
            segs = [s for s in path.split("/") if s]
            base = "/".join(segs) if len(segs) != 1 or not folders else folders[-1][1] + "/" + segs[0]
            folders.append((d, base.strip("/")))
            continue
        parts = [p.strip() for p in key.split(" / ")]
        here = folders[-1][1] if folders else ""
        if parts and all(tree_file_name(p, here) for p in parts):
            paths = [(here + "/" + p).lstrip("/") for p in parts]
            files.append((d, paths[0]))
            for p in paths:
                counts["file"] += 1
                if not os.path.isfile(p):
                    stale.append((i, label, "file not found: /" + p))
            continue
        if not files or not os.path.isfile(files[-1][1]):
            continue
        fpath = files[-1][1]
        if fpath not in texts:
            texts[fpath] = read_text(fpath)
        body = texts[fpath]
        if head.startswith("#"):
            anchor = norm_ws(head.lstrip("#").lstrip("*-= ").strip())
            counts["anchor"] += 1
            if fpath not in anchor_lines:
                anchor_lines[fpath] = [norm_ws(re.sub(r"^\s*(?:#|//|<!--|--|;|::)\s*#?\s*[-=*]*\s*", "", l)) for l in body.split("\n") if ANCHOR_RE.match(l)]
            if anchor and not any(a == anchor or (a.startswith(anchor) and a[len(anchor)] in " (:") for a in anchor_lines[fpath]):
                stale.append((i, label, "anchor not found in /%s: %s" % (fpath, anchor)))
            continue
        names = TREE_NAME_RE.findall(head)
        m = re.match(r"^(?:->|\(\))\s*([A-Za-z_$][\w$]*)", head)
        if m:
            names.append(m.group(1))
        for name in dict.fromkeys(names):
            counts["name"] += 1
            if not re.search(r"(?<![\w$])" + re.escape(name) + r"(?![\w$])", body):
                stale.append((i, label, "name not found in /%s: %s" % (fpath, name)))
    print("--- [Tree check: %d file(s), %d name(s), %d anchor(s) checked | %d stale] ---" % (counts["file"], counts["name"], counts["anchor"], len(stale)))
    for i, label, why in stale:
        print("  L%d: %s\n      -> %s" % (i + 1, label[:110], why))
    if stale:
        print("  -> fix a stale node in the script that next touches its file; a tree-only cleanup needs the user's request.")

UNUSED_ROW_RE = re.compile(r"^\s+(\S+)\s+(Function|Method|Class)\s+(\d+)-(\d+)\s+(\d+)\s+(\d+)\s*$")
UNUSED_HEAD_RE = re.compile(r"^\S.*\(([^()]+)\):\s*$")
UNUSED_FLAT_RE = re.compile(r"^\s+(\S+)\s+(Function|Method|Class)\s+(\S+)\s+(\d+)-(\d+)\s+(\d+)\s+(\d+)\s*$")

def graph_definitions(rel):
    """[(name, kind, start, end, callers)] for one file from CBM's search_graph, or (None, reason) when the graph cannot answer."""
    exe = find_cbm()
    if not exe:
        return None, "codebase-memory-mcp is not installed"
    project, err = ensure_graph_index(exe)
    if not project:
        return None, err
    rc, out, err = run_cbm(exe, ["search_graph", "--project", project, "--file-pattern", "*" + rel, "--limit", "2000"], 120)
    if rc is None or rc != 0:
        return None, "search_graph failed: " + ((cbm_clean(err) or cbm_clean(out)).splitlines() or ["no output"])[-1]
    rows, here, refs, in_refs = [], None, {}, False
    expand = lambda tok: (lambda m: refs.get(m.group(1), "") + m.group(2) if m else tok)(re.match(r"^@(\d+)\+(.*)$", tok))
    for ln in cbm_clean(out).split("\n"):
        if ln.startswith("results_refs:"):
            in_refs = True
            continue
        if in_refs:
            r = re.match(r"^\s+(\d+)\s+(\S+)\s*$", ln)
            if r:
                refs[r.group(1)] = r.group(2)
                continue
            in_refs = False
        f = UNUSED_FLAT_RE.match(ln)
        if f:
            if expand(f.group(3)).replace("\\", "/") == rel:
                rows.append((expand(f.group(1)).rsplit(".", 1)[-1], f.group(2), int(f.group(4)), int(f.group(5)), int(f.group(6))))
            continue
        h = UNUSED_HEAD_RE.match(ln)
        if h:
            here = h.group(1).replace("\\", "/")
            continue
        m = UNUSED_ROW_RE.match(ln)
        if m and here == rel:
            rows.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5))))
    if "has_more: true" in out:
        return None, "search_graph returned a partial list"
    return rows, None

def text_definitions(lines):
    """[(name, kind, start, end, None)] from the harness's own definition finder; callers unknown."""
    rows = []
    for i, ln in enumerate(lines):
        info = def_info(ln)
        if info and not SFC_BLOCK.match(ln):
            a, b = block_bounds(lines, i, False)
            rows.append((info[0], "Definition", i + 1, b, None))
    return rows

def check_unused(rel, lines):
    """Candidates for deletion: definitions in one file that nothing calls (call graph) and that no other line mentions (text)."""
    rows, why = graph_definitions(rel)
    source = "call graph + text"
    if rows == [] and text_definitions(lines):
        rows, why = None, "the graph listed no definitions for this file, though it has some"
    if rows is None:
        rows, source = text_definitions(lines), "text only (graph unavailable: %s)" % why
    skip = re.compile(r"^(__\w+__|main|init)$")
    cands = [r for r in rows if not skip.match(r[0]) and (r[4] == 0 if r[4] is not None else True)]
    names = set(r[0] for r in cands)
    hits = {n: [] for n in names}
    if names:
        pat = re.compile(r"(?<![\w$])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![\w$])")
        for f in repo_files("."):
            try:
                if os.path.getsize(f) > 1000000:
                    continue
                raw = read_bytes(f)
            except OSError:
                continue
            if b"\0" in raw[:4096]:
                continue
            for i, ln in enumerate(norm_nl(raw.decode("utf-8", "replace")).split("\n")):
                info = def_info(ln)
                for m in pat.finditer(ln):
                    if info and info[0] == m.group(1):
                        continue
                    call = f.endswith(CODE_EXTS) and re.match(r"\s*\(", ln[m.end():]) is not None
                    hits[m.group(1)].append((f, i + 1, call))
    found = []
    for name, kind, a, b, _ in cands:
        outside = [h for h in hits.get(name, []) if not (h[0] == rel and a <= h[1] <= b)]
        calls = [h for h in outside if h[2]]
        if source.startswith("text") and outside:
            continue
        decorated = a >= 2 and lines[a - 2].strip().startswith("@")
        rank = 2 if calls else (1 if outside else 0)
        found.append((rank, a, name, kind, outside, calls, decorated))
    print("--- [Unused check: /%s | source: %s | %d definition(s), %d candidate(s), strongest first] ---" % (rel, source, len(rows), len(found)))
    if source.startswith("call"):
        print_coverage_note(rel)
    for rank, a, name, kind, outside, calls, decorated in sorted(found):
        where = lambda xs: ", ".join("/%s:%d" % (x[0], x[1]) for x in xs[:3])
        if source.startswith("text"):
            notes = ["no other mentions"]
        elif calls:
            notes = ["no callers in the graph, but called by name %dx (e.g. %s): the graph likely missed it, treat as live" % (len(calls), where(calls))]
        elif outside:
            notes = ["no callers; mentioned %dx but never as a call (%s): check for string or dynamic use" % (len(outside), where(outside))]
        else:
            notes = ["no callers; no other mentions"]
        if decorated:
            notes.append("decorated, so a framework may call it")
        print("  L%d %s() %s -> %s" % (a, name, kind, "; ".join(notes)))
    if found:
        print("  -> candidates only: confirm each in source (routes, decorators, getattr or string names, other languages over HTTP) before deleting.")

CODE_EXTS = (".py", ".go", ".js", ".mjs", ".ts", ".jsx", ".tsx", ".vue", ".cs", ".java", ".kt", ".kts", ".rs", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".swift", ".dart", ".scala", ".php")
IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
CONST_RE = re.compile(r"^(?:(?:export\s+)?(?:const|let|var)\s+)?([A-Z][A-Z0-9_]{2,})\s*(?::[^=]+)?=(?!=)")
_REPO_LINES = []
NOT_CALLS = set("and or not if elif else for while return in is lambda with as assert await yield def class func function switch case catch typeof new delete void go defer select except raise from import print".split()) - {"print"}

def repo_code_lines():
    """[(rel, lines)] for every source file in the workspace, read once per run."""
    if not _REPO_LINES:
        for f in repo_files("."):
            if not f.endswith(CODE_EXTS):
                continue
            try:
                if os.path.getsize(f) > 1000000:
                    continue
                raw = read_bytes(f)
            except OSError:
                continue
            if b"\0" not in raw[:4096]:
                _REPO_LINES.append((f, norm_nl(raw.decode("utf-8", "replace")).split("\n")))
    return _REPO_LINES

def definition_index():
    """name -> [(file, line, kind)] for every definition and top-level constant in the workspace's source files."""
    index = {}
    for f, lines in repo_code_lines():
        for i, ln in enumerate(lines):
            info = def_info(ln)
            if info and not SFC_BLOCK.match(ln):
                m = DEF_KW.match(ln)
                index.setdefault(info[0], []).append((f, i + 1, m.group(1) if m else "def"))
                continue
            c = CONST_RE.match(ln)
            if c:
                index.setdefault(c.group(1), []).append((f, i + 1, "const"))
    return index

def enclosing_definition(lines, i):
    """Name of the innermost definition whose body contains line index i, or None at top level."""
    ind = indent_of(lines[i])
    for j in range(i, -1, -1):
        info = def_info(lines[j])
        if info and (j == i or indent_of(lines[j]) < ind or not lines[i].strip()):
            return info[0]
        if lines[j].strip() and not lines[j].strip().startswith(SKIPPABLE):
            ind = min(ind, indent_of(lines[j]) if j != i else ind)
    return None

def call_sites(name, limit=20):
    """Call-shaped uses of name across the source files, each with the function it sits in."""
    pat = re.compile(r"(?<![\w$])" + re.escape(name) + r"\s*\(")
    out = []
    for f, lines in repo_code_lines():
        for i, ln in enumerate(lines):
            if pat.search(ln):
                info = def_info(ln)
                if info and info[0] == name:
                    continue
                anon = "(anonymous function)" if f.endswith((".go", ".js", ".mjs", ".ts", ".jsx", ".tsx", ".vue")) and indent_of(ln) > 0 else None
                out.append((f, i + 1, enclosing_definition(lines, i) or anon))
    return out

def print_call_sites(name):
    sites = call_sites(name)
    shared = len(definition_index().get(name, []))
    if shared > 1:
        print("  call sites (text, by name): %d; %d definitions are named %s, so some of these call another one" % (len(sites), shared, name))
    else:
        print("  call sites (text): %d" % len(sites))
    for f, n, fn in sites[:20]:
        print("    /%s:%d in %s" % (f, n, fn or "(top level)"))
    if len(sites) > 20:
        print("    ... +%d more" % (len(sites) - 20))

def refs_in_scope(rel, lines, target):
    """What a scope uses: each project name with its use lines and definition sites, plus the calls that resolve outside the project."""
    lo, hi, note = resolve_scope(rel, lines, target)
    if note:
        print("--- [SCOPE NOT RESOLVED: %s] ---" % note)
        return
    index = definition_index()
    own = def_info(lines[lo])
    uses, external = {}, {}
    for i in range(lo, min(hi, len(lines))):
        ln = lines[i]
        code = code_only(ln)
        for m in IDENT_RE.finditer(code):
            name = m.group(0)
            if own and name == own[0] and i == lo:
                continue
            outside = [d for d in index.get(name, []) if not (d[0] == rel and lo < d[1] <= hi)]
            if outside:
                uses.setdefault(name, []).append(i + 1)
            elif name not in index and name not in NOT_CALLS and re.match(r"\s*\(", code[m.end():]):
                start = m.start()
                while start > 0 and (code[start - 1] == "." or IDENT_RE.match(code[start - 1])):
                    start -= 1
                external.setdefault(code[start:m.end()].lstrip("."), i + 1)
    print("--- [Refs: /%s | %s (L%d-%d) | %d project name(s), %d external call(s)] ---" % (rel, target or "TOP", lo + 1, min(hi, len(lines)), len(uses), len(external)))
    for name in sorted(uses, key=lambda n: uses[n][0]):
        defs = [d for d in index[name] if not (d[0] == rel and lo < d[1] <= hi)]
        at = ", ".join("L%d" % n for n in uses[name][:6]) + (" +%d" % (len(uses[name]) - 6) if len(uses[name]) > 6 else "")
        where = "/%s:%d (%s)" % defs[0] if len(defs) == 1 else "%d definitions: %s" % (len(defs), ", ".join("/%s:%d" % d[:2] for d in defs[:3]))
        print("  %-28s used %-18s -> %s" % (name, at, where))
    if external:
        print("  external calls: " + ", ".join(sorted(external)[:40]))

CURRENT_SCRIPT, CURRENT_RUN, CURRENT_PART = None, None, None
RUN_FAILED = False

def inspections_path():
    return os.path.join(HARNESS_DIR, "inspections.json")

def read_units(lines, a, b):
    """The definitions a line range covers (innermost, qualified by their parent), plus whether it touched code outside any definition."""
    defs = []
    for j, ln in enumerate(lines):
        info = def_info(ln)
        if info and not SFC_BLOCK.match(ln):
            s, e = block_bounds(lines, j, False)
            defs.append((info[0], s, e))
    units, outside = {}, False
    for i in range(a, b):
        cont = [d for d in defs if d[1] <= i < d[2]]
        if not cont:
            outside = outside or bool(lines[i].strip())
            continue
        d = min(cont, key=lambda x: x[2] - x[1])
        parents = [p for p in defs if p is not d and p[1] <= d[1] and d[2] <= p[2]]
        name = (min(parents, key=lambda x: x[2] - x[1])[0] + "." if parents else "") + d[0]
        units[name] = (d[1], d[2])
    return units, outside

def note_inspection(rel, lines, a, b):
    """Record what a read covered; say when the same definition was read before and has not changed since (context was lost, or it is still in context)."""
    units, outside = read_units(lines, a, b)
    seen = [(name + "()", hashlib.sha1("\n".join(lines[s:e]).encode("utf-8", "surrogateescape")).hexdigest()) for name, (s, e) in units.items()]
    if outside:
        seen.append(("(code outside definitions)", hashlib.sha1("\n".join(lines).encode("utf-8", "surrogateescape")).hexdigest()))
    again, now = [], time.time()
    with state_lock():
        log = load_json(inspections_path(), {})
        for name, fp in seen:
            key = rel + "#" + name
            prev = log.get(key)
            if prev and prev.get("fp") == fp and prev.get("run") != CURRENT_RUN:
                again.append((name, prev))
            log[key] = {"fp": fp, "session": CURRENT_SESSION, "script": CURRENT_SCRIPT, "run": CURRENT_RUN, "time": now}
        if len(log) > 5000:
            log = dict(sorted(log.items(), key=lambda kv: kv[1].get("time", 0))[-4000:])
        save_json(inspections_path(), log)
    for name, prev in again[:6]:
        age = now - prev.get("time", now)
        when = "%dm" % (age // 60) if age < 7200 else ("%dh" % (age // 3600) if age < 172800 else "%dd" % (age // 86400))
        print("  [REVISIT] /%s %s was read %s ago by %s (%s) and has not changed since" % (rel, name, when, "session " + prev["session"] if prev.get("session") else "a script without a session", prev.get("script") or "?"))
    if len(again) > 6:
        print("  [REVISIT] ... and %d more unchanged definitions read before" % (len(again) - 6))
    show_verdicts_for(rel, ["%s#%s" % (rel, name) for name in units])

_VERDICT_SHOWN = set()

def verdicts_path():
    return os.path.join(WORKSPACE_NOTES_DIR, "verdicts.json")

def verdict_inventory(target):
    """Fingerprints of what a verdict covers: a folder's files, a file, or one file#Class.method; None when the target does not exist."""
    path, _, scope = target.partition("#")
    if scope:
        if not os.path.isfile(path):
            return None
        lines = read_text(path).split("\n")
        lo, hi, note = resolve_scope(path, lines, scope)
        return None if note else {target: hashlib.sha1("\n".join(lines[lo:hi]).encode("utf-8", "surrogateescape")).hexdigest()}
    if os.path.isfile(path):
        return {path: sha_of(path)}
    if not os.path.isdir(path or "."):
        return None
    return {f: sha_of(f) for f in repo_files(".") if path_in(f, path or "**")}

def verdict_changes(v, target):
    """(new, changed, deleted) files under a verdict since it was recorded."""
    inv, old = verdict_inventory(target) or {}, v.get("inventory", {})
    return [f for f in inv if f not in old], [f for f in inv if f in old and inv[f] != old[f]], [f for f in old if f not in inv]

def tree_description(target):
    """The description of the tree node that names this path, from any tree file, or ''."""
    base = target.split("#")[0].strip("/")
    name = base.split("/")[-1]
    for t in sorted(glob.glob(os.path.join("docs", "trees", "*.txt"))):
        for _, _, label in tree_nodes(read_text(t).split("\n")):
            key = tree_key(label).strip("/")
            if key and (key == base or key == name or base.endswith("/" + key)):
                m = re.search(r"\((.*)\)\s*$", label)
                if m:
                    return m.group(1)[:140]
    return ""

def record_verdicts(P):
    """@VERDICT <folder, file or file#Class.method> | <verdict> | <note>: a conclusion about that area, fingerprinted so later changes mark it stale."""
    if not P["verdicts"]:
        return
    with state_lock():
        data = load_json(verdicts_path(), {"verdicts": {}})
        for arg in P["verdicts"]:
            parts = [x.strip() for x in arg.split("|")]
            target = parts[0].replace("\\", "/").strip("/")
            word = parts[1] if len(parts) > 1 else ""
            if not target or not word:
                print("  [VERDICT REFUSED] expected '@VERDICT <path> | <verdict> | <note>' (or '| clear'): %s" % arg)
                continue
            key = target + "\t" + (CURRENT_SESSION or "")
            legacy = data["verdicts"].get(target)
            if legacy is not None and legacy.get("session") == CURRENT_SESSION:
                data["verdicts"].pop(target)
                data["verdicts"].setdefault(key, dict(legacy, path=target))
            if word.lower() == "clear":
                print("  [VERDICT CLEARED] /%s" % target if data["verdicts"].pop(key, None) else "  [VERDICT] this chat has no verdict to clear at /%s" % target)
                continue
            inv = verdict_inventory(target)
            if inv is None:
                print("  [VERDICT REFUSED] /%s is not an existing folder, file or resolvable file#Class.method" % target)
                continue
            camps = [c for c, cv in data.get("campaigns", {}).items() if word in cv.get("legend", {})]
            if data.get("campaigns") and not camps:
                print("  -> '%s' is not a word of any active campaign's legend (%s); recorded as an ordinary verdict" % (word, "; ".join("%s: %s" % (c, ", ".join(cv.get("legend", {}))) for c, cv in data["campaigns"].items())))
            data["verdicts"][key] = {"path": target, "verdict": word, "note": " | ".join(parts[2:]), "session": CURRENT_SESSION, "script": CURRENT_SCRIPT, "time": time.time(), "inventory": inv, "campaign": camps[0] if camps else None}
            others = sorted("%s (%s)" % (v["verdict"], v.get("session") or "none") for k, p, v in verdict_items(data["verdicts"]) if p == target and k != key)
            print("  [VERDICT] /%s: %s%s (%d fingerprint(s) kept)%s" % (target, word, (" - " + " | ".join(parts[2:])) if parts[2:] else "", len(inv), ("; other chats' verdicts here: " + ", ".join(others)) if others else ""))
        os.makedirs(WORKSPACE_NOTES_DIR, exist_ok=True)
        save_json(verdicts_path(), data)
    if MODE == "git" and run_git(["check-ignore", "-q", verdicts_path().replace("\\", "/")])[0] == 0:
        print("  -> .llm_harness/verdicts.json is ignored by .gitignore, so verdicts will not travel with the project: add the line !.llm_harness/verdicts.json")

def show_verdicts_for(rel, scoped):
    """While reading code, show each verdict that covers it (once per run), with a stale warning when its area changed since."""
    data = load_json(verdicts_path(), {"verdicts": {}})["verdicts"]
    for key, target, v in sorted(verdict_items(data), key=lambda t: (t[1], t[2].get("session") or "")):
        base = target.split("#")[0]
        covers = target in scoped if "#" in target else (rel == base or rel.startswith(base + "/") or not base)
        if not covers or key in _VERDICT_SHOWN:
            continue
        _VERDICT_SHOWN.add(key)
        new, changed, gone = verdict_changes(v, target)
        stale = " [STALE VERDICT: %d new, %d changed, %d deleted since]" % (len(new), len(changed), len(gone)) if new or changed or gone else ""
        print("  [VERDICT] /%s: %s%s (session %s)%s" % (target, v["verdict"], (" - " + v["note"]) if v.get("note") else "", v.get("session") or "none", stale))

def list_verdicts(arg):
    """@VERDICTS [all | stale | session <name>]: verdicts as path, tree description and conclusion; a parent verdict hides children that say the same."""
    data = load_json(verdicts_path(), {"verdicts": {}})["verdicts"]
    a = arg.strip()
    rows = verdict_items(data)
    if a.lower().startswith("session "):
        who = a.split(None, 1)[1].strip()
        rows, label = [r for r in rows if r[2].get("session") == who], "session " + who
    elif a.lower() in ("all", "stale"):
        label = a.lower()
    elif CURRENT_SESSION:
        rows, label = [r for r in rows if r[2].get("session") == CURRENT_SESSION], "session " + CURRENT_SESSION
    else:
        label = "all"
    print("\n=== VERDICTS (%s) ===" % label)
    shown = 0
    for key, p, v in sorted(rows, key=lambda t: (t[1], t[2].get("session") or "")):
        base = p.split("#")[0]
        above = [(q, w) for k2, q, w in rows if k2 != key and "#" not in q and w.get("session") == v.get("session") and (base == q or base.startswith(q + "/") or not q)]
        if above and max(above, key=lambda t: len(t[0]))[1]["verdict"] == v["verdict"]:
            continue
        new, changed, gone = verdict_changes(v, p)
        if a.lower() == "stale" and not (new or changed or gone):
            continue
        age = time.time() - v.get("time", time.time())
        when = "%dm" % (age // 60) if age < 7200 else ("%dh" % (age // 3600) if age < 172800 else "%dd" % (age // 86400))
        desc = tree_description(p)
        print("  /%s%s [%s]%s" % (p, "/" if "#" not in p and os.path.isdir(base or ".") else "", v["verdict"], (" " + v["note"]) if v.get("note") else ""))
        print("      session %s, %s ago (%s)%s" % (v.get("session") or "none", when, v.get("script") or "?", (" | tree: " + desc) if desc else ""))
        if new or changed or gone:
            print("      [STALE VERDICT] %d new, %d changed, %d deleted since: %s" % (len(new), len(changed), len(gone), ", ".join("/" + f for f in (new + changed + gone)[:6])))
        shown += 1
    if not shown:
        print("  (none)")

def run_probe(spec):
    parts = [p.strip() for p in spec.split("|")]
    rel = safe_rel(parts[0])
    mode = (parts[1] if len(parts) > 1 else "").lower()
    target = parts[2] if len(parts) > 2 else ""
    if rel is None or not os.path.isfile(rel):
        print("\n=== FILE: /%s (NOT FOUND) ===" % parts[0].lstrip("/"))
        return
    text = read_text(rel)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    tot = len(lines)
    print("\n=== FILE: /%s (Total: %dL | Line-1 Header: %s) ===" % (rel, tot, ensure_line1_header(rel, text)[1]))
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", target or (parts[1] if len(parts) > 1 else ""))
    if mode == "toc":
        print("--- [On-Disk Lines 1-%d of %d | Signature TOC] ---" % (tot, tot))
        print_toc(lines)
    elif mode == "tree":
        depth = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 2
        probe_tree(lines, target, depth)
    elif mode == "check":
        check_tree(rel, lines)
    elif mode == "unused":
        check_unused(rel, lines)
    elif mode == "refs":
        refs_in_scope(rel, lines, target)
    elif m:
        a, b = max(1, int(m.group(1))), min(tot, int(m.group(2)))
        print("--- [On-Disk Lines %d-%d of %d] ---" % (a, b, tot))
        print("\n".join(lines[a - 1:b]))
        note_inspection(rel, lines, a - 1, b)
    else:
        lo, hi, note = resolve_scope(rel, lines, target)
        if note:
            print("--- [SCOPE NOT RESOLVED: %s | Signature TOC shown instead] ---" % note)
            print_toc(lines)
            return
        hi = min(hi, tot)
        cut = min(hi, lo + PROBE_CAP)
        more = " | TRUNCATED at %dL: continue with Lines %d-%d" % (PROBE_CAP, cut + 1, hi) if cut < hi else ""
        print("--- [On-Disk Lines %d-%d of %d | Scope: %s%s] ---" % (lo + 1, cut, tot, target or "TOP", more))
        print("\n".join(lines[lo:cut]))
        note_inspection(rel, lines, lo, cut)

# ---------------------------------------------------------------- Stage: Entry point

class OutputTee:
    """Copies everything printed during a run, so the output can be replayed when the same script is pasted again."""
    def __init__(self, stream):
        self.stream, self.parts = stream, []

    def write(self, s):
        self.parts.append(s)
        return self.stream.write(s)

    def flush(self):
        self.stream.flush()

    def text(self):
        return "".join(self.parts)

    def __getattr__(self, name):
        return getattr(self.stream, name)

RUNS_KEEP = 50

def payload_key(txt):
    """Fingerprint of a payload that ignores trailing spaces and blank edges, so a re-pasted script matches its first run."""
    return hashlib.sha1("\n".join(l.rstrip() for l in txt.strip().split("\n")).encode("utf-8", "surrogateescape")).hexdigest()

def runs_dir():
    return os.path.join(HARNESS_DIR, "runs")

LOCK_STALE_S, LOCK_WAIT_S = 120, 30

@contextlib.contextmanager
def state_lock():
    """Cross-process lock around shared state updates; held only for those updates, never while commands run."""
    os.makedirs(HARNESS_DIR, exist_ok=True)
    os.makedirs(SHARED_DIR, exist_ok=True)
    path = os.path.join(SHARED_DIR, "state.lock")
    deadline = time.time() + LOCK_WAIT_S
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except (FileExistsError, PermissionError):
            # Windows refuses to create a file another process is deleting ("delete pending"): the lock is still busy
            try:
                if time.time() - os.path.getmtime(path) > LOCK_STALE_S:
                    os.remove(path)
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise RuntimeError("could not get the harness state lock at %s within %ds" % (path, LOCK_WAIT_S))
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

def assign_number(P, state):
    """Give an unnumbered script the next free number, atomically across concurrent harness processes."""
    with state_lock():
        cur = load_json(STATE_PATH, {})
        num = max(int(cur.get("last_num", 0)), state["last_num"]) + 1
        P["num"], P["id"] = num, "%s-%d" % (P["id"] or "S", num)
        cur["last_num"], cur["last_id"] = num, P["id"]
        save_json(STATE_PATH, cur)
    state["last_num"], state["last_id"] = P["num"], P["id"]

def claim_number(P, state):
    """Record a script's own number unless another process took it since this run started. -> claimed"""
    with state_lock():
        cur = load_json(STATE_PATH, {})
        if P["num"] <= int(cur.get("last_num", 0)):
            return False
        cur["last_num"], cur["last_id"] = P["num"], P["id"]
        save_json(STATE_PATH, cur)
    state["last_num"], state["last_id"] = P["num"], P["id"]
    return True

def save_state(state):
    """Write this run's state fields without rolling back numbers that other sessions took meanwhile."""
    with state_lock():
        cur = load_json(STATE_PATH, {})
        for k in ("goal", "committed_through", "shell"):
            if k in state:
                cur[k] = state[k]
        if state.get("last_num", 0) >= int(cur.get("last_num", 0)):
            cur["last_num"], cur["last_id"] = state["last_num"], state["last_id"]
        save_json(STATE_PATH, cur)

def find_run_by_key(key):
    """Saved run whose payload fingerprint matches, so an identical re-paste of an unnumbered script replays."""
    for path in glob.glob(os.path.join(runs_dir(), "*.json")):
        if not os.path.basename(path).startswith("side_"):
            e = load_json(path, None)
            if e and e.get("key") == key:
                return e
    return None

def sessions_path():
    return os.path.join(HARNESS_DIR, "sessions.json")

def touch_session(P):
    """Record a session's latest script and activity time in the project's session registry; the first script that names an UNCLAIMED session (set up by @SPLIT or @UNCLAIM) claims it, and its brief prints once."""
    with state_lock():
        reg = load_json(sessions_path(), {})
        if P["session"] not in reg:
            for owner, orec in reg.items():
                if P["session"] in orec.get("merged_from", []):
                    orec["merged_from"] = [m for m in orec["merged_from"] if m != P["session"]]
                    print("=== MERGED: session %s was taken over by %s%s (its scope, notes and queues moved there); this chat starts again with nothing claimed: check @SESSIONS and ask the user before changing anything ===" % (P["session"], owner, chat_link(owner)))
        rec = reg.get(P["session"], {})
        claimed = False if P.get("unclaimed_now") else rec.pop("unclaimed", False)
        if claimed:
            rec["link_asked"] = False
            print("=== CLAIMED: this chat now holds session %s, set up by %s for: %s | brief: %s ===" % (P["session"], rec.get("created_by", "?"), rec.get("aim", ""), rec.get("brief", "")))
        rec["last_active"], rec["last_script"] = time.time(), P["id"]
        rec["idle_runs"] = rec.get("idle_runs", 0) + 1 if idle_script(P) else 0
        if P.get("session_aim"):
            rec["aim"] = P["session_aim"]
        rec["used"] = sorted(set(rec.get("used", [])) | set(P.get("used", [])))
        reg[P["session"]] = rec
        save_json(sessions_path(), reg)

def chat_link(name):
    """' (chat: <address>)' for a session whose chat address is known, else ''."""
    rec = load_json(sessions_path(), {}).get(name) or {}
    return " (chat: %s)" % rec["link"] if valid_link(rec.get("link")) else (" (host: %s session %s)" % (rec.get("host") or "agent", rec["host_session_id"]) if rec.get("host_session_id") else "")

def valid_link(link):
    return bool(link) and re.match(r"^https?://\S+$", link.strip()) is not None

def store_chat_link(name, address):
    """Keep a chat's address in its session record."""
    with state_lock():
        reg = load_json(sessions_path(), {})
        if name in reg:
            reg[name]["link"], reg[name]["link_asked"] = address.strip(), True
            save_json(sessions_path(), reg)

def ask_chat_link(name):
    """At a terminal, until it is known: ask for this chat's address, so other chats can point the user back to it. It cannot be skipped: an empty or wrong answer asks again (five tries end this run's question, and it returns on the next script); a wrong address already on file is replaced with @CHAT_LINK."""
    if not name:
        return
    rec = load_json(sessions_path(), {}).get(name) or {}
    if valid_link(rec.get("link")):
        return
    ans = ask_console("\nThis chat (session %s) needs its address, so other chats can point you back to it.\nPaste it from the browser's address bar: " % name)
    tries = 1
    while ans is not None and not valid_link(ans) and tries < 5:
        ans = ask_console("  That is not a web address (it starts with http). Paste it again: ")
        tries += 1
    if ans is None:
        return
    if not valid_link(ans):
        print("  [NOT SAVED] no web address was given; you will be asked again on the next script, or use @CHAT_LINK <address>")
        return
    store_chat_link(name, ans)

def set_chat_link(name, address):
    """@CHAT_LINK [<address>]: ask the user at the terminal for this chat's address (or set it when given), replacing any old address on file."""
    rec = load_json(sessions_path(), {}).get(name) or {}
    old = rec.get("link") if valid_link(rec.get("link")) else ""
    print("\n=== CHAT LINK ===")
    if not address:
        print("  current: %s" % (old or "none"))
        address = ask_console("\nPaste the new address%s: " % (" (Enter keeps the current one)" if old else ""))
        if address is None:
            print("  -> at a terminal, bare @CHAT_LINK asks the user directly; without one, send @CHAT_LINK <address>")
            return
        if old and not address.strip():
            print("  kept as it was")
            return
        tries = 1
        while address is not None and not valid_link(address) and tries < 5:
            address = ask_console("  That is not a web address (it starts with http). Paste it again: ")
            if old and address is not None and not address.strip():
                print("  kept as it was")
                return
            tries += 1
        if not address or not valid_link(address):
            print("  [NOT SAVED] no web address was given. Nothing changed.")
            return
    if not valid_link(address):
        print("  [CHAT LINK REFUSED] that is not a web address (it starts with http). Nothing changed.")
        return
    store_chat_link(name, address)
    print("  [CHAT LINK] %s -> %s%s" % (name, address.strip(), "  (was %s)" % old if old and old != address.strip() else ""))

def checks_path():
    """Where the user's check commands live: a file in the harness's own folder, never in the project, so a project that came from somewhere else cannot make the harness run its commands (LLM_HARNESS_CHECKS overrides it for tests)."""
    return os.environ.get("LLM_HARNESS_CHECKS") or os.path.join(os.path.dirname(os.path.abspath(SELF_PATH)), "checks.json")

def project_checks():
    """{'.ext': 'command'} the user set for the current project on this machine with --check."""
    data = (load_json(checks_path(), {}) or {}).get(os.path.normcase(os.path.abspath(".")))
    return {k: v for k, v in (data or {}).items() if isinstance(k, str) and k.startswith(".") and isinstance(v, str) and v.strip()}

def run_check_command(cmd):
    """(exit code, output) of one check command run from the workspace folder in the harness's shell; the code is 'timeout' after five minutes and None when the command could not start."""
    if os.name == "nt":
        args = [shutil.which("powershell") or shutil.which("pwsh") or "powershell", "-NoProfile", "-NonInteractive", "-Command", cmd]
    else:
        args = [shutil.which("bash") or "/bin/sh", "-c", cmd]
    try:
        r = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return "timeout", ""
    except OSError as exc:
        return None, str(exc)

def run_project_checks(changed, status, rolled):
    """After a change, run the user's own check command once per command for the file types that changed. It only reports (PASS, CHECK FAILED with the command's output, CHECK UNCHECKED when it cannot start) and never rolls anything back: a build of C#, Java or Rust needs the whole project, so a failure may belong to another file."""
    checks = project_checks()
    done = {}
    for rel in changed:
        cmd = checks.get(os.path.splitext(rel)[1].lower())
        if not cmd or rel in rolled or not os.path.isfile(rel):
            continue
        if cmd not in done:
            done[cmd] = run_check_command(cmd)
            rc, out = done[cmd]
            if rc not in (0, None, "timeout"):
                print("\n=== PROJECT CHECK: %s (exit %s) ===\n%s" % (cmd, rc, "\n".join(out.splitlines()[-40:])))
        rc, out = done[cmd]
        if rc == 0:
            status[rel] = "PASS (project check: %s)" % cmd
        elif rc == "timeout":
            status[rel] = "CHECK TIMED OUT (%s, 300 s)" % cmd
        elif rc is None:
            status[rel] = "CHECK UNCHECKED (%s could not start: %s)" % (cmd, out[:100])
        else:
            status[rel] = "CHECK FAILED (%s exit %s: %s)" % (cmd, rc, ((out.splitlines() or ["see the output above"])[-1])[:120])

def check_cli():
    """User-only command: harness.py --workspace <folder> --check [<.ext> <command...> | <.ext> --clear]. Without arguments it lists this project's check commands. They are kept on this machine for this project only."""
    after = sys.argv[1:][sys.argv[1:].index("--check") + 1:]
    rest, k = [], 0
    while k < len(after):
        if after[k] == "--workspace":
            k += 2
            continue
        rest.append(after[k])
        k += 1
    err = enter_workspace(arg_value("--workspace"))
    if err:
        print("usage: harness.py --workspace <project folder> --check [<.ext> <command> | <.ext> --clear] | " + err)
        return
    key, path = os.path.normcase(os.path.abspath(".")), checks_path()
    with state_lock():
        data = load_json(path, {}) or {}
        mine = dict(data.get(key) or {})
        if not rest:
            print("check commands for %s on this machine: %s" % (os.path.abspath("."), "; ".join("%s -> %s" % kv for kv in sorted(mine.items())) or "none"))
            return
        ext = rest[0].lower()
        if not re.fullmatch(r"\.[a-z0-9]+", ext) or len(rest) < 2:
            print("usage: harness.py --workspace <project folder> --check <.ext> <command> | <.ext> --clear")
            return
        if rest[1:] == ["--clear"]:
            mine.pop(ext, None)
            print("CHECK CLEARED: %s files have no check command in this project" % ext)
        else:
            mine[ext] = " ".join(rest[1:])
            print("CHECK SET: after a change to a %s file the harness runs: %s" % (ext, mine[ext]))
        data[key] = mine
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        save_json(path, data)

def link_cli():
    """User-only command: harness.py --workspace <folder> --link <session> <chat address>."""
    args = sys.argv[1:]
    i = args.index("--link")
    sess = args[i + 1] if len(args) > i + 1 else ""
    link = args[i + 2] if len(args) > i + 2 else ""
    err = enter_workspace(arg_value("--workspace"))
    if err or not sess or not valid_link(link):
        print("usage: harness.py --workspace <project folder> --link <session> <chat address starting with http>" + ((" | " + err) if err else ""))
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        if sess not in reg:
            print("no session named %s in this project; sessions: %s" % (sess, ", ".join(sorted(reg)) or "none"))
            return
        reg[sess]["link"], reg[sess]["link_asked"] = link, True
        save_json(sessions_path(), reg)
    print("LINKED: session %s -> %s" % (sess, link))

def find_deadlocks(reg):
    """Circles in who-waits-on-whom, as [(names, details)]: each chat waits on a file the next one still holds, so none of them can finish. Waits whose holder let go do not count. Each circle is listed once, from its alphabetically first chat; details is [(waiter, holder, [paths])] around it."""
    edges = {}
    for me, rec in reg.items():
        for w in rec.get("waiting", []):
            owner = w.get("owner")
            held = ((reg.get(owner) or {}).get("scope") or {}).get("paths", [])
            if owner and owner != me and owner in reg and held and scope_overlap([w["path"]], held):
                edges.setdefault(me, {}).setdefault(owner, []).append(w["path"])
    found = []

    def walk(start, node, trail):
        for nxt in sorted(edges.get(node, {})):
            if nxt == start and len(trail) >= 2:
                found.append(list(trail))
            elif nxt not in trail and nxt > start:
                walk(start, nxt, trail + [nxt])

    for start in sorted(edges):
        walk(start, start, [start])
    return [(names, [(a, names[(i + 1) % len(names)], edges[a][names[(i + 1) % len(names)]]) for i, a in enumerate(names)]) for names in found]

def print_sessions(current, full=False):
    SESSIONS_SHOWN[0] = True
    reg = load_json(sessions_path(), {})
    if not reg:
        return

    def describe(rec):
        age = time.time() - rec.get("last_active", 0)
        when = "%dm ago" % (age // 60) if age < 7200 else "%dh ago" % (age // 3600)
        sc = rec.get("scope")
        scope = "%s (%s)" % (sc.get("aim") or "no aim", ", ".join(sc.get("paths", []))) if sc else "none"
        brake = " | BRAKED by %s" % rec["brake"]["from"] if rec.get("brake") else ""
        link = " | chat: %s" % rec["link"] if valid_link(rec.get("link")) else (" | host: %s session %s" % (rec.get("host") or "agent", rec["host_session_id"]) if rec.get("host_session_id") else "")
        return ("UNCLAIMED, set up by %s, brief: %s | " % (rec.get("created_by", "?"), (rec.get("brief") or "")[:200]) if rec.get("unclaimed") else "") + "aim: %s | write scope: %s | last %s, %s%s%s" % (rec.get("aim") or "not set", scope, rec.get("last_script", "?"), when, brake, link)
    if current in reg:
        print("=== THIS SESSION: %s | %s ===" % (current, describe(reg[current])))
        if reg[current].get("waiting"):
            print("=== WAITING ON (blocked work to resume, never to drop silently): %s ===" % "; ".join("/%s held by %s%s since %s" % (w["path"], w["owner"], chat_link(w["owner"]), w.get("script") or "?") for w in reg[current]["waiting"]))
        for names, details in find_deadlocks(reg):
            if current in names:
                print("=== DEADLOCK (chats waiting on each other's files, so none can finish): %s | chats: %s | tell the user; the chat that can finish its part first commits and releases (@SCOPE_END), or one hands the files the other waits for to it with @DELEGATE <chat> | <paths> | <task>; the others resume on [UNBLOCKED] ===" % ("; ".join("%s waits on %s for %s" % (a, b, ", ".join("/" + p for p in paths[:3])) for a, b, paths in details), ", ".join(n + chat_link(n) for n in names if n != current)))
    mine = reg.get(current) or {}
    if mine.get("inherited"):
        print("=== INHERITED (the user set delegation to run automatically: these files and tasks were handed to this chat and are in its scope now; do each task, then @RETURN <chat> | <result>): %s ===" % "; ".join("from %s%s: %s (%s)" % (i["from"], chat_link(i["from"]), i["task"], ", ".join("/" + p for p in i["paths"][:4])) for i in mine["inherited"]))
    if mine.get("delegated"):
        print("=== DELEGATED (handed to other chats; each hands the files back with @RETURN, then claim them again to continue): %s ===" % "; ".join("%s%s has %s (%s)" % (d["to"], chat_link(d["to"]), ", ".join("/" + p for p in d["paths"][:4]), d["task"]) for d in mine["delegated"]))
    guide = next((n for n, r in reg.items() if r.get("role") == "guide"), None)
    if guide and guide == current:
        print("=== YOU ARE THE PROJECT'S GUIDE: you change no code (your scope stays in docs/: plans, the tree, the backlog); frame requests, review proposals, plan, answer workers and hand out work with @SPLIT; @GUIDE off ends the role ===")
    elif guide:
        print("=== GUIDE: %s%s keeps the project's direction: @MESSAGE it about cross-worker interfaces, architecture, data ownership or a change of direction; never wait on it for local work ===" % (guide, chat_link(guide)))
    if mine.get("lent"):
        lt = mine["lent"]
        print("=== LENT (this session's work is held by %s%s since %s: %s; it stays yours, so do not change those files; @RECLAIM takes it back after the user's answer at the terminal) ===" % (lt["to"], chat_link(lt["to"]), lt.get("since") or "?", ", ".join("/" + p for p in lt.get("paths", [])[:6])))
    for b in mine.get("borrowed", []):
        print("=== BORROWING (this chat holds %s's work: %s; it stays %s's: after each finished step record it with @MILESTONE <what is done>, so a lost chat leaves a trail; when done, @RETURN %s | <what was done>) ===" % (b["from"], ", ".join("/" + p for p in b.get("paths", [])[:6]), b["from"], b["from"]))
    recent = [m for m in mine.get("milestones", []) if time.time() - m.get("time", 0) < 7 * 86400][-3:]
    if recent:
        print("=== MILESTONES (what chats that held this session's work recorded as done, a week at most): %s ===" % "; ".join("%s at %s: %s" % (m.get("by"), m.get("script") or "?", m.get("text", "")) for m in recent))
    others = sorted(((n, r) for n, r in reg.items() if n != current), key=lambda kv: -kv[1].get("last_active", 0))
    if others:
        # Comment (decision): every footer used to list every registered session with its scope and address, a cost that grows with the number of chats and never shrinks (idle ones stayed); now a count and the names, and the full list only on request (@SESSIONS) or when this chat waits, holds delegated or inherited work, or is braked
        if full or mine.get("waiting") or mine.get("inherited") or mine.get("delegated") or mine.get("brake"):
            print("=== OTHER SESSIONS (newest first) ===")
            for n, r in others:
                print("  %s: %s" % (n, describe(r)))
        else:
            now = time.time()
            active = sum(1 for _, r in others if now - r.get("last_active", 0) < ACTIVE_S)
            names = ", ".join(n for n, _ in others[:8]) + (", ..." if len(others) > 8 else "")
            print("=== OTHER SESSIONS: %d (%d active): %s%s | @SESSIONS lists each one's aim, write scope and chat address ===" % (len(others), active, names, ("; UNCLAIMED, waiting for a new chat: " + ", ".join(n for n, r in others if r.get("unclaimed"))) if any(r.get("unclaimed") for _, r in others) else ""))

CURRENT_SESSION = None
SESSIONS_SHOWN = [False]

def show_state_if_missing():
    """A run that ends early (a replay, an undo from a re-paste, a refused script) still shows its chat what a normal run ends with: work that became free, messages and scope changes since, then the session lines."""
    if SESSIONS_SHOWN[0] or not CURRENT_SESSION:
        return
    check_waiting(CURRENT_SESSION)
    announce_scope_changes(CURRENT_SESSION)
    print_sessions(CURRENT_SESSION)

def name_session(P):
    """Name the script's session (and part) for the footer before anything can end the run: a replay, an undo from a re-paste and every early refusal (a @REDO that cannot run, a @REPEATABLE script that carries a number, a stale number) then describe this chat as it is now; the registration (touch_session) and the one-time deliveries stay later and happen only for a run that executes."""
    globals()["CURRENT_SESSION"], globals()["CURRENT_PART"] = P["session"], P.get("part")

def print_footer(state):
    # Comment (decision): every early exit ends with print_footer, while a normal run prints the session state before it; the flag set by print_sessions keeps a normal run from printing it twice
    show_state_if_missing()
    result = print_footer_body(state); print_auto_line(state); return result

def events_path():
    return os.path.join(HARNESS_DIR, "scope_events.json")

def grants_path():
    return os.path.join(HARNESS_DIR, "grants.json")

def path_in(path, pattern):
    """True when a workspace path falls under a scope pattern: a plain folder or file, or a glob with * ? and **."""
    p = pattern.strip().replace("\\", "/").lstrip("/")
    if not p:
        return False
    if not any(c in p for c in "*?["):
        p = p.rstrip("/")
        return path == p or path.startswith(p + "/")
    rx = re.escape(p).replace(r"\*\*", ".*").replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
    return re.fullmatch(rx, path) is not None

def literal_base(pattern):
    """The fixed folder or file part of a scope pattern, before any wildcard ('' means the whole workspace)."""
    p = pattern.strip().replace("\\", "/").lstrip("/")
    cut = min([i for i in (p.find("*"), p.find("?"), p.find("[")) if i >= 0] or [len(p)])
    if cut == len(p):
        return p.rstrip("/")
    return p[:cut].rsplit("/", 1)[0] if "/" in p[:cut] else ""

def scope_item(item):
    """A scope entry -> (path pattern, definition or '', depth or None): 'src/**', 'src depth 2' or 'src/a.py#Class.method'."""
    s = item.strip()
    m = re.search(r"\s+depth\s+(\d+)$", s)
    if m:
        s = s[:m.start()]
    pat, _, sym = s.partition("#")
    return pat.strip().replace("\\", "/").lstrip("/"), sym.strip(), int(m.group(1)) if m else None

def scope_path_covers(path, item):
    """True when a scope entry covers this file (a definition entry covers the file that holds it)."""
    pat, _, depth = scope_item(item)
    return path_in(path, pat) and within_depth(path, literal_base(pat), depth)

def touches_symbol(path, sym, op):
    """Whether a file change lands inside one definition of that file; unplaceable changes count as touching it."""
    if not op or op.get("type") not in ("hunk", "text_file") or not os.path.isfile(path):
        return True
    lines = decode_bytes(read_bytes(path))[0].split("\n")
    lo, hi, note = resolve_scope(path, lines, sym)
    if note:
        return False
    if op["type"] == "text_file":
        return any(lo <= i < hi for i in range(op["lo"], min(op["hi"], len(lines))) if op["find"] in lines[i])
    old = [x.rstrip() for x in op.get("find", "").split("\n")]
    if not any(old):
        return hi >= len(lines) - 1
    starts = [i for i in range(len(lines) - len(old) + 1) if [x.rstrip() for x in lines[i:i + len(old)]] == old]
    if len(starts) != 1:
        return True
    return starts[0] < hi and starts[0] + len(old) > lo

def sym_range(path, sym):
    """(start, end) lines of a definition or # Stage anchor in a file, or None when it cannot be found."""
    if not os.path.isfile(path):
        return None
    lines = decode_bytes(read_bytes(path))[0].split("\n")
    lo, hi, note = resolve_scope(path, lines, sym)
    return None if note else (lo, hi)

def auto_commit_memory(P):
    """In a git project, commit the harness's project memory (goal, notes, verdicts, git policy) after a script changed it: no chat lists these files in its own commits, so they would never travel with the project. Left alone, with a note, on a protected branch, during an unfinished git operation, on a detached HEAD, and when .gitignore hides them."""
    if MODE != "git":
        return
    present = [n for n in (os.path.join(WORKSPACE_NOTES_DIR, f).replace("\\", "/") for f in ("goal.md", "notes.md", "verdicts.json", "tokens.json", "git.json")) if os.path.isfile(n)]
    if not present:
        return
    _, out, _ = run_git(["status", "--porcelain", "--"] + present)
    changed = [l[3:].strip().strip('"') for l in out.splitlines() if l.strip()]
    touched = bool(P["notes"] or P["goal"] or P["verdicts"] or P["campaigns"])
    # Comment (decision): the token counts change on every paste, so they are committed only along with other memory changes or when a session ends; a commit after every script buried the history in chore commits
    if changed and all(os.path.basename(c) == "tokens.json" for c in changed) and not P.get("session_end"):
        return
    if not changed:
        hidden = [n for n in present if touched and run_git(["check-ignore", "-q", "--", n])[0] == 0]
        if hidden:
            print("\n  [MEMORY] %s is ignored by .gitignore, so it cannot travel with the project; add a '!%s' line after '.llm_harness/*'" % (", ".join("/" + n for n in hidden), hidden[0]))
        return
    blockers = git_blockers()
    _, branch, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if blockers:
        why = "an unfinished git operation (%s)" % ", ".join(blockers)
    elif branch == "HEAD":
        why = "HEAD is detached"
    elif branch in (git_policy().get("protected") or []):
        why = "%s is a protected branch; they go with your next commit on a feature branch" % branch
    else:
        why = ""
    if why:
        print("\n  [MEMORY] %s changed but was not committed: %s" % (", ".join("/" + c for c in changed), why))
        return
    msg = "chore(harness): update project memory (%s)" % ", ".join(os.path.basename(c) for c in changed)
    run_git(["add", "--"] + changed)
    rc, out, err = run_git(["commit", "-m", msg, "--"] + changed)
    if rc:
        print("\n  [MEMORY] commit failed: %s. The files stay uncommitted." % (err or out))
    else:
        print("\n  [MEMORY COMMITTED] %s %s" % (run_git(["rev-parse", "--short", "HEAD"])[1], msg))

def spaced_entry_problem(entry):
    """True for a scope entry that holds a space, names nothing known, and reads as several paths run together (a.py b.py); a deleted or tracked file whose name has a space is fine."""
    if not re.search(r"\s", entry) or glob.glob(entry):
        return False
    if not all("/" in t or re.search(r"\.\w+$", t) for t in entry.split()):
        return False
    return not (MODE == "git" and run_git(["ls-files", "--cached", "--", entry])[1].strip())

def scope_overlap(paths_a, paths_b):
    """Entry pairs that can claim the same code: nesting fixed parts, except two definitions of one file, which overlap only when one contains the other."""
    out, files = [], None
    for x in paths_a:
        for y in paths_b:
            (px, sx, _), (py, sy, _) = scope_item(x), scope_item(y)
            if sx and sy and px == py:
                rx, ry = sym_range(px, sx), sym_range(py, sy)
                if rx and ry:
                    if rx[0] < ry[1] and ry[0] < rx[1]:
                        out.append((x, y))
                elif sx == sy or sx.startswith(sy + ".") or sy.startswith(sx + "."):
                    out.append((x, y))
                continue
            wx, wy = any(c in px for c in "*?["), any(c in py for c in "*?[")
            if wx or wy:
                # Comment (decision): a glob can only collide with files it really matches; comparing fixed prefixes alone made '/why*.txt' "overlap" every file in the workspace, and 'docs/*.md' a .txt below docs/
                if files is None:
                    files = repo_files(".")
                g, c = (px, py) if wx else (py, px)
                if (wx and wy and any(path_in(f, px) and path_in(f, py) for f in files)) or (not (wx and wy) and (path_in(c, g) or any(path_in(f, g) and path_in(f, c) for f in files))):
                    out.append((x, y))
                continue
            a, b = literal_base(px), literal_base(py)
            if a == "" or b == "" or a == b or a.startswith(b + "/") or b.startswith(a + "/"):
                dx, dy = scope_item(x)[2], scope_item(y)[2]
                if (dy is not None and a.startswith(b + "/") and not within_depth(a, b, dy)) or (dx is not None and b.startswith(a + "/") and not within_depth(b, a, dx)):
                    continue
                out.append((x, y))
    return out

def granted(session, path):
    return any(path_in(path, g) for g in load_json(grants_path(), {}).get(session or "", []))

def scope_owner(path, me, op=None):
    """(name, scope) of another session whose scope covers this change, unless the user granted this session that path; a definition entry only claims changes inside that definition."""
    for name, rec in load_json(sessions_path(), {}).items():
        sc = rec.get("scope")
        if name == me or not sc or granted(me, path):
            continue
        for item in sc.get("paths", []):
            if scope_path_covers(path, item):
                sym = scope_item(item)[1]
                if not sym or touches_symbol(path, sym, op):
                    return name, dict(sc, owned=item)
    return None, None

def wake_waiters(reg, holder, freed):
    """When a scope is released, name the chats that were waiting on it so the user can open them; their next run says [UNBLOCKED]."""
    for name, r in sorted(reg.items()):
        hits = [w["path"] for w in r.get("waiting", []) if w.get("owner") == holder and freed and scope_overlap([w["path"]], freed)]
        if name != holder and hits:
            print("  [WAKE] session %s was waiting on %s%s: open that chat so it resumes (its next run says [UNBLOCKED])" % (name, ", ".join("/" + h for h in hits[:4]), chat_link(name)))

def apply_scope_change(P):
    """@SCOPE / @SCOPE_END / @SESSION_END: update this session's write scope, refusing overlaps, and log the change for the other sessions."""
    me = P["session"]
    if not me:
        print("  [REFUSED] @SCOPE, @SCOPE_END and @SESSION_END need an @SESSION line. Scopes are unchanged.")
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        rec = reg.setdefault(me, {})
        if (P["session_end"] or P["scope_end"]) and rec.get("inherited") and not re.search(r"\b(drop|handover)\b", str(P["session_end"] or P["scope_end"]).lower()):
            print("  [RELEASE REFUSED] this session still holds work other chats delegated to it: %s" % "; ".join("%s (from %s)" % (i["task"], i["from"]) for i in rec["inherited"][:4]))
            print("  -> finish it and @RETURN it, or end with 'drop' (@SESSION_END drop) to give it back unfinished and tell the user.")
            return
        if P["session_end"] and rec.get("waiting") and not re.search(r"\b(drop|handover)\b", str(P["session_end"]).lower()):
            print("  [SESSION END REFUSED] this session still waits on blocked work: %s" % "; ".join("/%s (held by %s)" % (w["path"], w["owner"]) for w in rec["waiting"][:6]))
            print("  -> finish it once it is free, or end with '@SESSION_END drop' to give it up and tell the user what is left undone.")
            return
        if P["session_end"] or P["scope_end"]:
            pending = own_uncommitted(me)
            if pending and "handover" not in str(P["session_end"] or P["scope_end"]).lower():
                print("  [RELEASE REFUSED] this session's changes are not committed yet: %s" % ", ".join("/" + p for p in pending[:8]))
                print("  -> commit them first, or write '@SCOPE_END handover' (or '@SESSION_END handover') to leave them to another session; the hand-over is announced.")
                return
            freed = (rec.get("scope") or {}).get("paths", [])
            rec["scope"] = None
            wake_waiters(reg, me, freed)
            rec["handed_over"] = sorted(set(rec.get("handed_over", [])) | set(pending))
            kind = "session ended" if P["session_end"] else "scope released"
            if pending:
                kind += "; uncommitted work handed over: " + ", ".join(pending[:8])
            event = {"session": me, "kind": kind, "aim": "", "paths": []}
            release_unfinished(reg, me)
            if P["session_end"]:
                reg.pop(me, None)
        else:
            aim, _, raw = P["scope"].partition("|")
            paths = [x.strip().replace("\\", "/").lstrip("/") for x in raw.split(",") if x.strip()]
            if not paths:
                print("  [REFUSED] @SCOPE needs '<aim> | <path or glob>, ...'. Scopes are unchanged.")
                return
            # Comment (decision): the project's guide keeps the direction and never changes code, so its claims stay inside docs/ (plans, the tree, the backlog); edits outside a session's scope are refused already
            if rec.get("role") == "guide":
                code = [x for x in paths if not scope_item(x)[0].replace("\\", "/").lstrip("/").startswith("docs/")]
                if code:
                    print("  [REFUSED] this session is the project's guide: it may claim only docs/ (plans, the tree, the backlog), not %s. Scopes are unchanged." % ", ".join(code[:4]))
                    return
            spaced = [x for x in paths if spaced_entry_problem(scope_item(x)[0])]
            if spaced:
                print("  [REFUSED] scope entry '%s' holds a space and names no existing path: separate scope paths with commas (a.py, b.py). Scopes are unchanged." % spaced[0])
                return
            for x in paths:
                pat, sym, _ = scope_item(x)
                if sym and os.path.isfile(pat):
                    _, _, note = resolve_scope(pat, decode_bytes(read_bytes(pat))[0].split("\n"), sym)
                    if note:
                        print("  [REFUSED] scope entry '%s': %s. Scopes are unchanged." % (x, note))
                        return
            clashes = [(name, x, y) for name, other in reg.items() if name != me and other.get("scope")
                       for x, y in scope_overlap(paths, other["scope"].get("paths", [])) if not granted(me, literal_base(scope_item(x)[0]))]
            if clashes:
                print("  [SCOPE REFUSED] this scope overlaps another session's; scopes are unchanged:")
                for name, x, y in clashes[:6]:
                    print("    %s  overlaps  %s's  %s%s" % (x, name, y, chat_link(name)))
                print("  -> narrow the scope, or tell the user: they can have that session release its scope, or grant this session the overlap with their own --grant command.")
                # Comment (decision): the claim stays all-or-nothing, so half of a cross-file change cannot land while its other half waits; the count and the free list only make the next step obvious
                busy = {x for name, x, y in clashes}
                free = [x for x in paths if x not in busy]
                print("  %d of %d requested path(s) are free and %d are held by another chat; nothing was claimed, and the held ones are on WAITING ON." % (len(free), len(paths), len(busy)))
                if free:
                    print("  -> if the work on the free paths stands alone, claim them in their own @SCOPE (%s) and leave the rest waiting; when nothing in this script was applied, send @REDO <this script's number> with the @SCOPE line corrected." % ", ".join(free[:8]))
                note_waiting(reg, me, [(x, name) for name, x, y in clashes])
                save_json(sessions_path(), reg)
                return
            rec["scope"] = {"aim": aim.strip(), "paths": paths}
            event = {"session": me, "kind": "scope set", "aim": aim.strip(), "paths": paths}
        save_json(sessions_path(), reg)
        log = load_json(events_path(), {"seq": 0, "events": []})
        log["seq"] += 1
        event["seq"], event["time"] = log["seq"], time.time()
        log["events"] = (log["events"] + [event])[-200:]
        save_json(events_path(), log)
    print("  [SCOPE] %s %s%s" % (me, event["kind"], (": " + event["aim"] + " | " + ", ".join(event["paths"])) if event["paths"] else ""))
    if event["kind"] == "scope set":
        files = repo_files(".")
        covered = [f for f in files if any(scope_path_covers(f, g) for g in event["paths"] if not scope_item(g)[1])]
        if files and (len(covered) > 200 or len(covered) * 3 > len(files)):
            print("  [SCOPE WIDE] this scope covers %d of %d files, and every other session is refused all of them: narrow it to the files this task changes and widen it later if needed." % (len(covered), len(files)))
        if any(literal_base(g) in ("", "docs", "docs/trees") for g in event["paths"]):
            print("  -> tree files are shared by every session: claim the tree_*.txt files this task edits, not the whole trees folder.")

def note_waiting(reg, me, items, notify=True):
    """Remember work session me could not do because another session holds it, and (once per item) tell the holder; call inside state_lock."""
    rec = reg.setdefault(me, {})
    have = {(w["path"], w["owner"]) for w in rec.get("waiting", [])}
    for path, owner in items:
        if owner == me or (path, owner) in have:
            continue
        have.add((path, owner))
        rec.setdefault("waiting", []).append({"path": path, "owner": owner, "script": CURRENT_SCRIPT, "time": time.time()})
        if notify and owner in reg:
            log_event({"session": me, "kind": "message", "to": owner, "text": "session %s is blocked by your scope on %s%s: finish and release it, or hand it over (sent by the harness)" % (me, path, chat_link(me))})

def check_waiting(me, ack=False):
    """Tell a session when work it was blocked on is free again; the rest stays on its WAITING ON line. The notice stays in this chat's footers until its next numbered script (ack=True), like a message; only a numbered script's output counts as shown."""
    if not me:
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        rec = reg.get(me) or {}
        still, newly = [], []
        for w in rec.get("waiting", []):
            sc = (reg.get(w["owner"]) or {}).get("scope") or {}
            held = bool(sc) and not granted(me, literal_base(scope_item(w["path"])[0])) and bool(scope_overlap([w["path"]], sc.get("paths", [])))
            (still if held else newly).append(w)
        before = json.dumps(rec.get("freed", []), sort_keys=True)
        freed = [dict(f) for f in rec.get("freed", []) if not (ack and f.get("shown"))] + [dict(w) for w in newly]
        if ack:
            for f in freed:
                f["shown"] = True
        if me in reg and (newly or before != json.dumps(freed, sort_keys=True)):
            rec["waiting"], rec["freed"] = still, freed
            save_json(sessions_path(), reg)
    for w in freed:
        print("  [UNBLOCKED] /%s is free now (session %s no longer holds it); you were blocked on it in %s: resume that work" % (w["path"], w["owner"], w.get("script") or "?"))

def own_scope_covers(me, rel):
    """True when this session's own scope, or a user grant, covers the file (a definition entry counts for its whole file here)."""
    sc = (load_json(sessions_path(), {}).get(me) or {}).get("scope") or {}
    return granted(me, rel) or any(scope_path_covers(rel, e) for e in sc.get("paths", []))

def guard_ops(P):
    """Refuse file changes that fall inside another session's declared scope, unless the user granted them."""
    if not P["ops"]:
        return
    warned, blocked = set(), []
    for op in P["ops"]:
        for path in (op.get("file"), op.get("to")):
            rel = path.strip().replace("\\", "/").lstrip("/") if path else ""
            owner, sc = scope_owner(rel, P["session"], op) if rel else (None, None)
            if owner:
                op["blocked"] = "inside session %s's scope (%s): %s%s; tell the user, who can coordinate or --grant it" % (owner, sc.get("owned"), sc.get("aim") or "no aim", chat_link(owner))
                blocked.append((rel, owner))
                break
            if rel and P["session"] and not own_scope_covers(P["session"], rel):
                op["blocked"] = "outside this session's write scope: claim it with @SCOPE <aim> | <paths> (a claim in the same script runs before the changes) and resend; when nothing in this script was applied, send @REDO <this script's number> with the @SCOPE line corrected instead of resending it whole"
                break
            others = foreign_uncommitted(rel) if rel and P["session"] else []
            if others and rel not in warned:
                warned.add(rel)
                print("  [SHARED FILE] /%s holds uncommitted changes from session %s: your edit lands in the same file, and you cannot commit it until they commit or hand theirs over." % (rel, ", ".join(others)))
    if blocked and P["session"]:
        with state_lock():
            reg = load_json(sessions_path(), {})
            note_waiting(reg, P["session"], blocked)
            save_json(sessions_path(), reg)

def watch_other_scopes(me):
    """Fingerprints of the files inside other sessions' scopes, taken before @RUN so changes made by commands can be reported."""
    pats = [(n, g) for n, rec in load_json(sessions_path(), {}).items() if n != me and rec.get("scope") for g in rec["scope"].get("paths", [])]
    if not pats:
        return None
    marks = {}
    for f in repo_files("."):
        owners = [n for n, g in pats if scope_path_covers(f, g)]
        if owners:
            try:
                st = os.stat(f)
                marks[f] = (owners[0], st.st_size, st.st_mtime_ns)
            except OSError:
                pass
    return {"marks": marks, "pats": pats}

def report_scope_changes(watched):
    """Detected, not prevented: report files in other sessions' scopes that @RUN commands created, changed or deleted."""
    hits = []
    for f, (owner, size, mt) in watched["marks"].items():
        try:
            st = os.stat(f)
            if (st.st_size, st.st_mtime_ns) != (size, mt):
                hits.append((owner, f, "changed"))
        except OSError:
            hits.append((owner, f, "deleted"))
    for f in repo_files("."):
        if f not in watched["marks"]:
            owners = [n for n, g in watched["pats"] if scope_path_covers(f, g)]
            if owners:
                hits.append((owners[0], f, "created"))
    if hits:
        print("\n=== [SCOPE ALERT] @RUN changed files inside other sessions' scopes ===")
        for owner, f, what in hits[:20]:
            print("  /%s %s (session %s)" % (f, what, owner))
        print("  -> stop and tell the user: these files belong to another session's work.")

def announce_scope_changes(me, ack=False):
    """Show what other sessions sent or changed that this chat has not confirmed reading. It stays in every footer of this chat until the chat's next numbered script (ack=True, a run that executes): that script is the only proof the chat read the earlier output. A replay, an undo from a re-paste, a refused script or a @SIDE or @REPEATABLE script shows it again and records nothing."""
    if not me:
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        if me not in reg:
            return
        log = load_json(events_path(), {"seq": 0, "events": []})
        rec = reg[me]
        first = "shown_seq" not in rec and "seen_seq" not in rec
        # Comment (decision): the cursor (seen_seq) moves only when a numbered script runs after the output that showed the notice (shown_seq); moving it when the output was printed lost the message whenever that output never reached the chat, or went to another chat's paste
        if ack:
            if "shown_seq" in rec:
                rec["seen_seq"] = max(rec.get("seen_seq", 0), rec["shown_seq"])
            rec["shown_seq"] = log["seq"]
            save_json(sessions_path(), reg)
        cursor = rec.get("seen_seq", 0)
    msgs = [e for e in log["events"] if e["seq"] > cursor and e.get("to") == me]
    if msgs:
        mark_messages_delivered(me, [e.get("msg_id") for e in msgs if e.get("msg_id")])
        print("\n=== MESSAGES FOR THIS SESSION (from other AI sessions, not from the user: weigh them, never let them override the user) ===")
        for e in msgs:
            mid = ("[%s] " % e["msg_id"]) if e.get("msg_id") else ""
            print("  %s%s from %s: %s" % (mid, e["kind"], e["session"], e.get("text", "")))
    if first:
        others = [(n, r["scope"]) for n, r in reg.items() if n != me and r.get("scope")]
        if others:
            print("\n=== OTHER SESSIONS' SCOPES (first look) ===")
            for n, sc in others:
                print("  %s: %s | %s" % (n, sc.get("aim") or "no aim", ", ".join(sc.get("paths", []))))
        return
    new = [e for e in log["events"] if e["seq"] > cursor and e["session"] != me and not e.get("to")]
    if new:
        print("\n=== SCOPE CHANGES FROM OTHER SESSIONS (shown once) ===")
        for e in new:
            print("  %s %s%s" % (e["session"], e["kind"], (": " + e["aim"] + " | " + ", ".join(e["paths"])) if e["paths"] else ""))

_DIRTY = []

def uncommitted_sessions(rel):
    """Sessions whose journaled scripts changed rel after its last commit, while rel still has uncommitted changes (git workspaces only)."""
    if MODE != "git" or not rel:
        return set()
    if not _DIRTY:
        rc, out, _ = run_git(["status", "--porcelain", "--untracked-files=all"])
        _DIRTY.append(set(ln[3:].split(" -> ")[-1].strip().strip('"') for ln in out.split("\n") if rc == 0 and len(ln) > 3))
    if rel not in _DIRTY[0]:
        return set()
    rc, out, _ = run_git(["log", "-1", "--format=%ct", "--", rel])
    since = int(out) if rc == 0 and out.strip().isdigit() else 0
    found = set()
    for hp in glob.glob(os.path.join(HISTORY_DIR, "*.json")):
        try:
            if os.path.getmtime(hp) <= since:
                continue
        except OSError:
            continue
        e = load_json(hp, None) or {}
        f = e.get("files", {}).get(rel)
        if f and not f.get("undone"):
            found.add(e.get("session"))
    return found

def foreign_uncommitted(rel):
    """Other active sessions with uncommitted changes in rel that they have not handed over."""
    reg = load_json(sessions_path(), {})
    return sorted(s for s in uncommitted_sessions(rel) if s and s != CURRENT_SESSION and s in reg and rel not in reg[s].get("handed_over", []))

def own_uncommitted(me):
    """Files this session changed through the harness that still hold its uncommitted changes."""
    rels = set()
    for hp in glob.glob(os.path.join(HISTORY_DIR, "*.json")):
        e = load_json(hp, None) or {}
        if e.get("session") == me:
            rels.update(r for r, f in e.get("files", {}).items() if not f.get("undone"))
    return sorted(r for r in rels if me in uncommitted_sessions(r))

def log_event(event):
    """Append one event to the shared log; call inside state_lock."""
    log = load_json(events_path(), {"seq": 0, "events": []})
    log["seq"] += 1
    event.setdefault("aim", "")
    event.setdefault("paths", [])
    event["seq"], event["time"] = log["seq"], time.time()
    # Comment (invariant): the newest 200 events are kept, and so is any event addressed to a session that has not read it yet (its seen_seq is behind), up to 1000 in all; trimming by count alone would delete a message for a chat that stays idle while others work
    reg = load_json(sessions_path(), {})
    allev = log["events"] + [event]
    unread = [e for e in allev[:-200] if isinstance(reg.get(e.get("to")), dict) and e.get("seq", 0) > (reg[e["to"]].get("seen_seq") or 0)]
    log["events"] = (unread + allev[-200:])[-1000:]
    save_json(events_path(), log)

def hand_over_work(reg, me, arg):
    """@DELEGATE <session> | <paths> | <task>: give another chat write access to some of this chat's files together with a task. The files move at once (the other chat finds them in its scope and its footer says INHERITED), with this chat's uncommitted work in them; the other chat hands them back with @RETURN. Call inside state_lock."""
    parts = [x.strip() for x in arg.split("|")]
    to = re.sub(r"[^A-Za-z0-9_.-]+", "-", parts[0]).strip("-")
    paths = [x.strip().replace("\\", "/").lstrip("/") for x in (parts[1] if len(parts) > 1 else "").split(",") if x.strip()]
    task = " | ".join(parts[2:]).strip()
    mine = (reg.get(me) or {}).get("scope") or {}
    held = mine.get("paths", [])
    problem = ""
    if to not in reg or to == me:
        problem = "no other session by that name (see the sessions list)"
    elif not paths or not task:
        problem = "the form is @DELEGATE <session> | <paths> | <task>"
    elif reg[to].get("brake"):
        problem = "session %s is braked and cannot take work on" % to
    else:
        for p in paths:
            if p not in held:
                wider = [e for e in held if scope_path_covers(p, e)]
                problem = ("/%s is only part of your scope entry '%s': narrow your scope with @SCOPE so it lists /%s on its own, then delegate it" % (p, wider[0], p)) if wider else "you do not hold /%s (your scope: %s)" % (p, ", ".join(held) or "none")
                break
    if problem:
        print("  [DELEGATE REFUSED] %s" % problem)
        return
    pending = [r for r in own_uncommitted(me) if any(path_in(r, p) for p in paths)]
    left = [e for e in held if e not in paths]
    reg[me]["scope"] = dict(mine, paths=left) if left else None
    reg[me]["handed_over"] = sorted(set(reg[me].get("handed_over", [])) | set(pending))
    theirs = reg[to].get("scope") or {"aim": "delegated by %s: %s" % (me, task[:60]), "paths": []}
    theirs["paths"] = theirs.get("paths", []) + [p for p in paths if p not in theirs.get("paths", [])]
    reg[to]["scope"] = theirs
    reg[to]["waiting"] = [w for w in reg[to].get("waiting", []) if not (w.get("owner") == me and any(path_in(w["path"], p) or path_in(p, w["path"]) for p in paths))]
    now = {"paths": paths, "task": task, "script": CURRENT_SCRIPT, "time": time.time()}
    reg[to].setdefault("inherited", []).append(dict(now, **{"from": me}))
    reg[me].setdefault("delegated", []).append(dict(now, to=to))
    log_event({"session": me, "kind": "delegation", "to": to, "paths": paths, "text": "handed you %s to do: %s. They are in your scope now%s; when done, @RETURN %s | <what was done>" % (", ".join("/" + p for p in paths), task, " (with the uncommitted work in them)" if pending else "", me)})
    print("  [DELEGATED] %s -> %s: %s%s" % (", ".join("/" + p for p in paths), to, task, chat_link(to)))

def take_back_work(reg, me, arg):
    """@RETURN <session> | <result>: hand back everything that chat delegated to this one. The files are released (the delegating chat claims them again to continue) and the result goes to it as a note. Refused while this chat has uncommitted work in them, unless the result says 'handover'. Call inside state_lock."""
    parts = [x.strip() for x in arg.split("|")]
    to = re.sub(r"[^A-Za-z0-9_.-]+", "-", parts[0]).strip("-")
    result = " | ".join(parts[1:]).strip()
    rec = reg.get(me) or {}
    if any(b.get("from") == to for b in rec.get("borrowed", [])):
        return_loan(reg, me, to, result)
        return
    items = [i for i in rec.get("inherited", []) if i.get("from") == to]
    if not items:
        print("  [RETURN REFUSED] nothing was delegated to this session by '%s'" % parts[0])
        return
    if not result:
        print("  [RETURN REFUSED] say what was done: @RETURN %s | <result>" % to)
        return
    paths = sorted({p for i in items for p in i["paths"]})
    pending = [r for r in own_uncommitted(me) if any(path_in(r, p) for p in paths)]
    if pending and "handover" not in result.lower():
        print("  [RETURN REFUSED] this session's changes in them are not committed yet: %s" % ", ".join("/" + p for p in pending[:8]))
        print("  -> commit them first, or put the word 'handover' in the result to leave them to the other session.")
        return
    sc = rec.get("scope") or {}
    left = [e for e in sc.get("paths", []) if e not in paths]
    rec["scope"] = dict(sc, paths=left) if left else None
    rec["inherited"] = [i for i in rec.get("inherited", []) if i.get("from") != to]
    rec["handed_over"] = sorted(set(rec.get("handed_over", [])) | set(pending))
    wake_waiters(reg, me, paths)
    if to in reg:
        reg[to]["delegated"] = [d for d in reg[to].get("delegated", []) if d.get("to") != me]
        log_event({"session": me, "kind": "delegation returned", "to": to, "paths": paths, "text": "finished %s: %s. The files are free now; claim them again with @SCOPE to continue" % (", ".join("/" + p for p in paths), result)})
    print("  [RETURNED] %s -> %s: %s%s" % (", ".join("/" + p for p in paths), to, result, "" if to in reg else " (that session has ended; the files are simply free)"))

def create_session(reg, me, kind, arg):
    """@SPLIT <name> | <aim> | <paths, or nothing> | <brief>: set up a session no chat holds yet (UNCLAIMED) with an aim and a brief for the chat that will take it; a split also hands it some of this chat's files, with their uncommitted work and the waits on them, the way @DELEGATE does. Call inside state_lock."""
    parts = [x.strip() for x in arg.split("|")]
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", parts[0]).strip("-")
    need = 4
    form = "@SPLIT <name> | <aim> | <paths, or nothing for a session with no files> | <brief>"
    if len(parts) < need or not (name and parts[1] and " | ".join(parts[3:]).strip()):
        print("  [SESSION REFUSED] the form is %s" % form)
        return
    if name in reg or name == me:
        print("  [SESSION REFUSED] a session named %s already exists; pick another name" % name)
        return
    aim, brief = parts[1], " | ".join(parts[need - 1:])
    paths = [x.strip().replace("\\", "/").lstrip("/") for x in parts[2].split(",") if x.strip()]
    reg[name] = {"aim": aim, "unclaimed": True, "brief": brief, "created_by": me, "last_active": time.time(), "last_script": CURRENT_SCRIPT}
    if paths:
        hand_over_work(reg, me, "%s | %s | %s" % (name, ", ".join(paths), aim))
        if not reg[name].get("inherited"):
            reg.pop(name, None)
            print("  [SPLIT REFUSED] %s was not created, since the files could not move (see the line above)" % name)
            return
        # Comment (decision): only the waits on the moved files follow the split; waits that belong to the tasks this chat keeps stay here
        mine = reg.get(me) or {}
        moving = [w for w in mine.get("waiting", []) if any(path_in(w["path"], p) or path_in(p, w["path"]) for p in paths)]
        if moving:
            mine["waiting"] = [w for w in mine["waiting"] if w not in moving]
            reg[name]["waiting"] = moving
    print("  [SESSION CREATED] %s (UNCLAIMED): %s%s -> to take it, open a new chat whose first script says @SESSION %s | <aim>; its footer then prints the brief once" % (name, aim, (" with " + ", ".join("/" + p for p in paths)) if paths else "", name))

def release_unfinished(reg, me):
    """A session that ends with delegated work still in hand gives it back unfinished: the delegating chats are told, and the files are free. Call inside state_lock."""
    for i in (reg.get(me) or {}).get("inherited", []):
        src = i.get("from")
        if src in reg:
            reg[src]["delegated"] = [d for d in reg[src].get("delegated", []) if d.get("to") != me]
            log_event({"session": me, "kind": "delegation dropped", "to": src, "paths": i["paths"], "text": "ended without finishing %s (%s); the files are free, claim them again with @SCOPE to continue" % (", ".join("/" + p for p in i["paths"]), i["task"])})

MSG_RANK = {"queued": 0, "delivered": 1, "ack": 2, "accepted": 3, "rejected": 3, "completed": 4}
MSG_STATE_MAP = {"ack": "ack", "acknowledged": "ack", "accept": "accepted", "accepted": "accepted", "reject": "rejected", "rejected": "rejected", "done": "completed", "complete": "completed", "completed": "completed"}

def messages_path():
    return os.path.join(HARNESS_DIR, "messages.json")

def mark_messages_delivered(me, ids):
    if not me or not ids:
        return
    with state_lock():
        store = load_json(messages_path(), {"seq": 0, "msgs": []})
        changed = False
        now = time.time()
        for m in store.get("msgs", []):
            if m.get("id") in ids:
                r = (m.get("receipts") or {}).get(me)
                if r and r.get("state") == "queued":
                    r["state"], r["time"] = "delivered", now
                    changed = True
        if changed:
            save_json(messages_path(), store)

def record_message(me, targets, text, script_id, broadcast=False):
    store = load_json(messages_path(), {"seq": 0, "msgs": []})
    key = "%s|%s|%s|%s" % (script_id or "", me, "*" if broadcast else ",".join(targets), text)
    if script_id:
        for m in store.get("msgs", []):
            if m.get("key") == key:
                return m["id"], True
    store["seq"] = int(store.get("seq", 0)) + 1
    mid = "M-%03d" % store["seq"]
    now = time.time()
    rec = {"id": mid, "from": me, "text": text, "key": key, "time": now, "broadcast": broadcast,
           "receipts": {t: {"state": "queued", "note": "", "time": now} for t in targets}}
    store["msgs"] = (store.get("msgs", []) + [rec])[-500:]
    save_json(messages_path(), store)
    return mid, False

def apply_msg_acks(P):
    if not P.get("msg_acks"):
        return
    me = P.get("session")
    if not me:
        print("  [MSG_ACK REFUSED] @MSG_ACK needs an @SESSION line.")
        return
    with state_lock():
        store = load_json(messages_path(), {"seq": 0, "msgs": []})
        by_id = {m["id"].upper(): m for m in store.get("msgs", []) if m.get("id")}
        changed = False
        for arg in P["msg_acks"]:
            parts = [x.strip() for x in arg.split("|")]
            mid = parts[0].upper() if parts else ""
            if mid not in by_id:
                print("  [MSG_ACK] unknown message '%s'" % mid)
                continue
            m = by_id[mid]
            r = (m.get("receipts") or {}).get(me)
            if not r:
                print("  [MSG_ACK] %s is not addressed to session '%s'" % (mid, me))
                continue
            state_tok = parts[1].lower() if len(parts) > 1 and parts[1] else "ack"
            if state_tok in MSG_STATE_MAP:
                st = MSG_STATE_MAP[state_tok]
                note = " | ".join(parts[2:]).strip()
            else:
                st = "ack"
                note = " | ".join(parts[1:]).strip()
            r["state"], r["time"] = st, time.time()
            if note:
                r["note"] = note
            changed = True
            print("  [MSG_ACK] %s -> %s (by %s)%s" % (mid, st, me, (": " + note) if note else ""))
        if changed:
            save_json(messages_path(), store)

def wait_for_messages(P):
    if not P.get("wait_msgs"):
        return
    if not agent_mode():
        print("  [REFUSED] @WAIT_MSG is for auto-shell mode only; in chat mode use @REPEATABLE + @PING to check receipts.")
        return
    for arg in P["wait_msgs"]:
        parts = [x.strip() for x in arg.split("|") if x.strip()]
        mid = parts[0].upper() if parts else ""
        target_st, timeout_s = "ack", 90.0
        for p in parts[1:]:
            pl = p.lower()
            if pl in ("delivered", "ack", "accepted", "rejected", "done", "complete", "completed"):
                target_st = "delivered" if pl == "delivered" else MSG_STATE_MAP.get(pl, pl)
            elif re.fullmatch(r"\d+(?:\.\d+)?s?", pl):
                timeout_s = max(0.1, float(pl.rstrip("s")))
        want_rank = MSG_RANK.get(target_st, 2)
        deadline = time.time() + timeout_s
        reached, rec = False, None
        while True:
            store = load_json(messages_path(), {"seq": 0, "msgs": []})
            rec = next((m for m in store.get("msgs", []) if (m.get("id") or "").upper() == mid), None)
            if not rec:
                print("  [WAIT_MSG] unknown message '%s'" % mid)
                break
            rcpts = rec.get("receipts") or {}
            if rcpts and all(MSG_RANK.get(r.get("state", "queued"), 0) >= want_rank for r in rcpts.values()):
                reached = True
                break
            if time.time() >= deadline:
                break
            time.sleep(min(0.25, max(0.05, deadline - time.time())))
        if rec:
            print("\n=== WAIT_MSG: %s (target: %s) ===" % (mid, target_st))
            for to, r in sorted((rec.get("receipts") or {}).items()):
                print("  %s: %s%s" % (to, r.get("state", "queued"), (" (" + r["note"] + ")") if r.get("note") else ""))
            print("  [WAIT_MSG] %s" % ("reached" if reached else ("timed out after %gs" % timeout_s)))

def print_ping(P):
    if not P.get("ping"):
        return
    me = P.get("session")
    print("\n=== PING: %s ===" % (me or "no session"))
    if not me:
        print("  @PING needs an @SESSION line.")
        return
    store = load_json(messages_path(), {"seq": 0, "msgs": []})
    incoming = [m for m in store.get("msgs", []) if me in (m.get("receipts") or {}) and m["receipts"][me].get("state") in ("queued", "delivered")]
    if incoming:
        mark_messages_delivered(me, [m["id"] for m in incoming])
        print("  Incoming:")
        for m in incoming:
            print("    [%s] from %s: %s" % (m["id"], m["from"], m["text"]))
    sent = [m for m in store.get("msgs", []) if m.get("from") == me][-10:]
    if sent:
        print("  Sent receipts:")
        for m in sent:
            summary = ", ".join("%s=%s%s" % (t, r.get("state", "queued"), ("(" + r["note"] + ")" if r.get("note") else "")) for t, r in sorted((m.get("receipts") or {}).items()))
            print("    [%s] %s -> %s" % (m["id"], m["text"][:60], summary))
    if not incoming and not sent:
        print("  no messages or receipts")

def send_messages(P):
    """@MESSAGE, @SCOPE_REQUEST and @BRAKE: notes this session writes for another one, delivered once on that session's next run."""
    if not P["msgs"]:
        return
    me = P["session"]
    if not me:
        print("  [NOT SENT] @MESSAGE, @SCOPE_REQUEST and @BRAKE need an @SESSION line.")
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        for kind, arg in P["msgs"]:
            if kind in ("delegate", "return"):
                (hand_over_work if kind == "delegate" else take_back_work)(reg, me, arg)
                continue
            if kind in ("new session", "split"):
                create_session(reg, me, kind, arg)
                continue
            parts = [x.strip() for x in arg.split("|")]
            raw_to = parts[0].strip() if parts else ""
            text = " | ".join(parts[1:]).strip()
            if kind == "message" and raw_to == "*":
                targets = sorted(n for n, r in reg.items() if n != me and not r.get("unclaimed"))
                if not targets or not text:
                    print("  [NOT SENT] broadcast to '*': %s" % ("no text" if targets else "no other active sessions"))
                    continue
                mid, dup = record_message(me, targets, text, P.get("id"), broadcast=True)
                if dup:
                    print("  [SENT (duplicate)] broadcast [%s] to %s: %s" % (mid, ", ".join(targets), text))
                    continue
                for to in targets:
                    log_event({"session": me, "kind": kind, "to": to, "text": text, "msg_id": mid})
                print("  [SENT] broadcast [%s] to %s: %s" % (mid, ", ".join(targets), text))
                continue
            to = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw_to).strip("-")
            if to not in reg or to == me or not text:
                print("  [NOT SENT] %s to '%s': %s" % (kind, parts[0], "no text" if to in reg and to != me else "no other session by that name (see the sessions list)"))
                continue
            if kind == "scope request":
                note_waiting(reg, me, [(p.strip().replace("\\", "/").lstrip("/"), to) for p in (parts[1] if len(parts) > 1 else "").split(",") if p.strip()], notify=False)
                text = "asks for write access to " + text
            if kind == "brake":
                reg[to]["brake"] = {"from": me, "text": text}
            if kind == "message":
                mid, dup = record_message(me, [to], text, P.get("id"), broadcast=False)
                if dup:
                    print("  [SENT (duplicate)] message [%s] to %s: %s" % (mid, to, text))
                    continue
                log_event({"session": me, "kind": kind, "to": to, "text": text, "msg_id": mid})
                print("  [SENT] %s [%s] to %s: %s" % (kind, mid, to, text))
            else:
                log_event({"session": me, "kind": kind, "to": to, "text": text})
                print("  [SENT] %s to %s: %s" % (kind, to, text))
        save_json(sessions_path(), reg)

def enforce_brake(P):
    """A braked session acknowledges with @BRAKE_ACK before it changes anything; reads and searches still run."""
    me = P["session"]
    if not me:
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        brake = (reg.get(me) or {}).get("brake")
        if brake and P["brake_ack"]:
            reg[me]["brake"] = None
            save_json(sessions_path(), reg)
            log_event({"session": me, "kind": "brake acknowledged", "to": brake["from"], "text": "%s read your brake and continues" % me})
    if not brake:
        return
    if P["brake_ack"]:
        print("  [BRAKE ACKNOWLEDGED] the brake from session %s is lifted" % brake["from"])
        return
    print("  [BRAKED] session %s (an AI, not the user) paused this session's changes: %s" % (brake["from"], brake["text"]))
    print("  -> take it into account, tell the user, and add @BRAKE_ACK to the next script; until then file changes, git and @RUN are refused here (reads still run).")
    for op in P["ops"]:
        op["blocked"] = "this session is braked by session %s; add @BRAKE_ACK first" % brake["from"]
    P["git"], P["runs"], P["undo"] = [], [], []

def session_cli(flag):
    """User-only commands: --release <session> ends a session and frees its scope; --unbrake <session> lifts a brake on it."""
    args = sys.argv[1:]
    i = args.index(flag)
    sess = args[i + 1] if len(args) > i + 1 else ""
    err = enter_workspace(arg_value("--workspace"))
    if err or not sess:
        print("usage: harness.py --workspace <project folder> %s <session>" % flag + ((" | " + err) if err else ""))
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        if sess not in reg:
            print("no session named %s; sessions: %s" % (sess, ", ".join(sorted(reg)) or "none"))
            return
        if flag == "--release":
            freed = (reg[sess].get("scope") or {}).get("paths", [])
            reg.pop(sess)
            wake_waiters(reg, sess, freed)
            kind = "session released by the user"
        else:
            reg[sess]["brake"] = None
            kind = "brake lifted by the user"
        save_json(sessions_path(), reg)
        log_event({"session": sess, "kind": kind})
    print("%s: %s" % (kind.upper(), sess))

AUTO_LINE = [""]
AUTO_MAX = 10
_AUTO_BAD = re.compile(r"(?m)^\s*(?:-> )?\[(?:REFUSED|SCOPE REFUSED|SCOPE ALERT|SHARED FILE|BRAKED|NOT SENT|RELEASE REFUSED|MALFORMED|ROLLED BACK)\b")

def is_borrower():
    """True when the running session currently holds another session's lent work (the only chats that are shown @MILESTONE)."""
    try:
        return bool(CURRENT_SESSION and (load_json(sessions_path(), {}).get(CURRENT_SESSION) or {}).get("borrowed"))
    except Exception:
        return False

def milestone_directive(P):
    """@MILESTONE <what is done>: a borrower records a finished step on the session whose work it holds (<owner> | <text> when it borrows from several); the last 20 are kept on the owner's record, so they survive a return, a second borrow and a takeover, and the owner's footer shows the latest."""
    me, text = P.get("session"), (P.get("milestone") or "").strip()
    if P.get("side") or P.get("repeatable") or not me:
        print("  [MILESTONE REFUSED] it needs a numbered script with an @SESSION line (not @SIDE or @REPEATABLE). Nothing recorded.")
        return
    if not text:
        print("  [MILESTONE REFUSED] say what is done: @MILESTONE <what is done>. Nothing recorded.")
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        owners = [b["from"] for b in (reg.get(me) or {}).get("borrowed", []) if b.get("from") in reg]
        target = owners[0] if len(owners) == 1 else None
        if len(owners) > 1:
            head, _, rest = text.partition("|")
            if head.strip() in owners and rest.strip():
                target, text = head.strip(), rest.strip()
        if not target:
            print("  [MILESTONE REFUSED] %s. Nothing recorded." % ("this session borrows no work" if not owners else "it borrows from several sessions (%s): write @MILESTONE <owner> | <what is done>" % ", ".join(owners)))
            return
        log = reg[target].setdefault("milestones", [])
        log.append({"by": me, "script": CURRENT_SCRIPT, "text": text[:300], "time": time.time()})
        reg[target]["milestones"] = log[-20:]
        save_json(sessions_path(), reg)
    print("  [MILESTONE] recorded on %s's session: %s" % (target, text[:120]))

def harness_states_line():
    """One handshake line with the switches that change how the harness behaves on this machine for this project; the hidden AUTO line is named only while it is on."""
    env = os.environ
    if env.get("LLM_HARNESS_NO_COPY") or env.get("LLM_HARNESS_NO_PROMPT"):
        copy = "off"
    elif env.get("LLM_HARNESS_COPY", "").lower() == "auto":
        copy = "always at once"
    elif env.get("LLM_HARNESS_COPY", "").lower() == "ask":
        copy = "always asks"
    else:
        copy = "at once while the terminal is in front, otherwise asks"
    fetch = env.get("LLM_HARNESS_FETCH", "60").strip().lower()
    return "=== HARNESS STATES (this machine, this project): stewardship %s | auto-copy of the output: %s | upstream fetch: %s%s ===" % ("on" if steward_on() else "off", copy, "off" if fetch == "off" else "at most every %s s" % fetch, " | AUTO status line ON" if auto_on() else "")

def auto_path():
    return os.path.join(HARNESS_DIR, "auto.json")

def auto_on():
    """True when the user switched the AUTO status line on for this project on this machine (--auto on); off by default, and anything unreadable counts as off."""
    if not HARNESS_DIR:
        return False
    try:
        return bool((load_json(auto_path(), {}) or {}).get("on"))
    except (TypeError, AttributeError, OSError):
        return False

L1_REFRESH = False
L1_PROOF = ""
PING_ONLY = False

def session_l1_token(rotate=False):
    """Read or rotate the 6-hex compaction proof token stored on CURRENT_SESSION."""
    if not CURRENT_SESSION or not HARNESS_DIR:
        return ""
    with state_lock():
        reg = load_json(sessions_path(), {})
        rec = reg.get(CURRENT_SESSION)
        if not isinstance(rec, dict):
            return ""
        if rotate or not rec.get("l1_token"):
            raw = "%s|%.6f|%d|%s" % (CURRENT_SESSION, time.time(), os.getpid(), rec.get("l1_token", ""))
            rec["l1_token"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:6]
            save_json(sessions_path(), reg)
        return rec.get("l1_token", "")

def compacted_cli():
    """Host-hook / user command: harness.py --workspace <folder> --compacted [<session>]. Clears l1_token and turn_seen so the next run prints full L1."""
    args = sys.argv[1:]
    i = args.index("--compacted")
    target = args[i + 1].strip() if len(args) > i + 1 and not args[i + 1].startswith("--") else ""
    err = enter_workspace(arg_value("--workspace"))
    if err:
        print("usage: harness.py --workspace <project folder> --compacted [<session>] | " + err)
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        names = [target] if target and target in reg else (list(reg.keys()) if not target else [])
        for n in names:
            if isinstance(reg.get(n), dict):
                reg[n].pop("l1_token", None)
                reg[n].pop("turn_seen", None)
        if names:
            save_json(sessions_path(), reg)
    print("COMPACTED: cleared L1 proof/turn cache for %s; next run will print full L1." % (", ".join(names) if names else "no matching session"))

def compact_path():
    return os.path.join(HARNESS_DIR, "compact.json")

def compact_on():
    """Compaction-aware L1 is ON by default; --compact off opts out for this project on this machine."""
    if not HARNESS_DIR:
        return True
    try:
        data = load_json(compact_path(), None)
        return True if not isinstance(data, dict) or "on" not in data else bool(data.get("on"))
    except (TypeError, AttributeError, OSError):
        return True

def compact_cli():
    """User-only command: harness.py --workspace <folder> --compact [on | off]. Switches compaction-aware L1 on (default) or off for this project on this machine."""
    args = sys.argv[1:]
    i = args.index("--compact")
    word = args[i + 1].lower() if len(args) > i + 1 and not args[i + 1].startswith("--") else ""
    err = enter_workspace(arg_value("--workspace"))
    if err or word not in ("", "on", "off"):
        print("usage: harness.py --workspace <project folder> --compact [on | off]" + ((" | " + err) if err else ""))
        return
    if word:
        os.makedirs(HARNESS_DIR, exist_ok=True)
        save_json(compact_path(), {"on": word == "on"})
    print("COMPACTION-AWARE L1 IS %s for %s on this machine: normal chat turns omit unchanged standing rules and keep [L1-Compact] + [L1-Syntax] visible; @L1_REFRESH restores full L1." % ("ON" if compact_on() else "OFF", os.path.abspath(".")))

def auto_cli():
    """User-only command: harness.py --workspace <folder> --auto [on | off]. Switches the last footer line (AUTO: CONTINUE or PAUSE) on or off for this project on this machine only; a script can never run it."""
    args = sys.argv[1:]
    i = args.index("--auto")
    word = args[i + 1].lower() if len(args) > i + 1 and not args[i + 1].startswith("--") else ""
    err = enter_workspace(arg_value("--workspace"))
    if err or word not in ("", "on", "off"):
        print("usage: harness.py --workspace <project folder> --auto [on | off]" + ((" | " + err) if err else ""))
        return
    if word:
        os.makedirs(HARNESS_DIR, exist_ok=True)
        save_json(auto_path(), {"on": word == "on"})
    print("THE AUTO STATUS LINE IS %s for %s on this machine: the last footer line says AUTO: CONTINUE (a pure read) or AUTO: PAUSE (<reason>), decided by code. Nothing is sent anywhere, the switch is kept outside the project, and a script cannot change it." % ("ON" if auto_on() else "OFF", os.path.abspath(".")))

def auto_verdict(P, out):
    """Decides this run's AUTO line from the parsed script and what the run printed, never from the AI's prose: CONTINUE only for a numbered script that purely read; PAUSE for anything else, for @ASK_USER, and on the AUTO_MAX-th read in a row."""
    if not auto_on():
        return
    me, why = P.get("session"), ""
    if P.get("ask_user"):
        why = "the AI asks for you: %s" % P["ask_user"][:200]
    elif not me:
        why = "no @SESSION line"
    elif P.get("repeatable"):
        why = "a @REPEATABLE script"
    elif idle_script(P):
        why = "the script did nothing"
    elif not read_only(P) or RUN_FAILED:
        why = "the script changed something, ran a command or touched git or sessions"
    elif _AUTO_BAD.search(out or ""):
        why = "the run refused or flagged something"
    if me:
        with state_lock():
            reg = load_json(sessions_path(), {})
            rec = reg.setdefault(me, {})
            if not why and rec.get("brake"):
                why = "this session is braked"
            n = 0 if why else rec.get("auto_reads", 0) + 1
            if n >= AUTO_MAX:
                why, n = "%d read-only scripts in a row" % AUTO_MAX, 0
            rec["auto_reads"] = n
            save_json(sessions_path(), reg)
    AUTO_LINE[0] = ("=== AUTO: PAUSE (%s) ===" % why) if why else "=== AUTO: CONTINUE ==="

def print_auto_line(state):
    """The last footer line while the switch is on; a run that never reached the verdict (a replay, a refusal, an undo) pauses."""
    if state is None or not auto_on() or (CURRENT_PART and CURRENT_PART[0] < CURRENT_PART[1]):
        return
    print(AUTO_LINE[0] or "=== AUTO: PAUSE (this run ended early: a replay, a refusal or an undo) ===")
    AUTO_LINE[0] = ""

def steward_path():
    return os.path.join(HARNESS_DIR, "steward.json")

def steward_on():
    """True when the user switched project stewardship on for this project on this machine (--steward on); anything unreadable, or no workspace yet, counts as off."""
    if not HARNESS_DIR:
        return False
    try:
        return bool((load_json(steward_path(), {}) or {}).get("on"))
    except (TypeError, AttributeError, OSError):
        return False

def steward_cli():
    """User-only command: harness.py --workspace <folder> --steward [on | off]. Switches the backlog-and-review rule ([L1-Steward]) on or off for this project on this machine only; without on or off it only says which. A script can never run it."""
    args = sys.argv[1:]
    i = args.index("--steward")
    word = args[i + 1].lower() if len(args) > i + 1 and not args[i + 1].startswith("--") else ""
    err = enter_workspace(arg_value("--workspace"))
    if err or word not in ("", "on", "off"):
        print("usage: harness.py --workspace <project folder> --steward [on | off]" + ((" | " + err) if err else ""))
        return
    if word:
        os.makedirs(HARNESS_DIR, exist_ok=True)
        save_json(steward_path(), {"on": word == "on"})
    on = steward_on()
    print("PROJECT STEWARDSHIP IS %s for %s on this machine: the backlog and review rule [L1-Steward] %s. The switch is kept outside the project, so other machines and other projects are not affected, and a script cannot change it." % ("ON" if on else "OFF", os.path.abspath("."), "is printed in every footer" if on else "is not printed"))

def shift_paths(reg, frm, to, paths, aim=None):
    """Move scope entries from one session to another (a loan going out, moving on or coming back); the giver's uncommitted work in them is recorded as handed over, as a delegation does. Call inside state_lock."""
    pending = [r for r in own_uncommitted(frm) if any(path_in(r, p) for p in paths)] if frm in reg else []
    if frm in reg:
        fsc = reg[frm].get("scope") or {}
        left = [e for e in fsc.get("paths", []) if e not in paths]
        reg[frm]["scope"] = dict(fsc, paths=left) if left else None
        if pending:
            reg[frm]["handed_over"] = sorted(set(reg[frm].get("handed_over", [])) | set(pending))
    if to in reg:
        tsc = reg[to].get("scope") or {"aim": aim or reg[to].get("aim") or "", "paths": []}
        tsc["paths"] = tsc.get("paths", []) + [p for p in paths if p not in tsc.get("paths", [])]
        reg[to]["scope"] = tsc
    return pending

def loan_scripts(holder, paths):
    """The scripts a session ran that changed any of these files (from the history journal, which keeps each script's own session as its author)."""
    out = []
    for hp in sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json"))):
        e = load_json(hp, None)
        if isinstance(e, dict) and e.get("session") == holder and any(any(path_in(r, p) for p in paths) for r in e.get("files", {})):
            out.append(os.path.splitext(os.path.basename(hp))[0])
    return out

def return_loan(reg, holder, owner, result, force=False):
    """A borrowed session's work goes back to its owner: the files return to the owner's scope (a delegation only frees them), the holder keeps its own files, and the owner is told the result and the holder's scripts on them. force is the owner's @RECLAIM after the user's answer: the holder's uncommitted changes go along. Call inside state_lock."""
    hrec = reg.get(holder) or {}
    loan = next((b for b in hrec.get("borrowed", []) if b.get("from") == owner), None)
    if not loan:
        return False
    if not result:
        print("  [RETURN REFUSED] say what was done: @RETURN %s | <result>" % owner)
        return False
    paths = loan.get("paths", [])
    pending = [r for r in own_uncommitted(holder) if any(path_in(r, p) for p in paths)]
    if pending and not force and "handover" not in result.lower():
        print("  [RETURN REFUSED] this session's changes in them are not committed yet: %s" % ", ".join("/" + p for p in pending[:8]))
        print("  -> commit them first, or put the word 'handover' in the result to leave them to %s." % owner)
        return False
    lent = (reg.get(owner) or {}).get("lent") or {}
    shift_paths(reg, holder, owner, paths, aim=lent.get("aim"))
    hrec["borrowed"] = [b for b in hrec.get("borrowed", []) if b.get("from") != owner]
    if owner in reg:
        reg[owner].pop("lent", None)
        reg[owner].setdefault("returned_loans", []).append({"holder": holder, "paths": paths, "time": time.time()})
    scripts = loan_scripts(holder, paths)
    files = ", ".join("/" + p for p in paths)
    log_event({"session": holder, "kind": "loan returned", "to": owner, "paths": paths, "text": "%s your work (%s), back in your scope: %s%s" % ("had to give back" if force else "gave back", files, result, " | its scripts on them: " + ", ".join(scripts[-10:]) if scripts else "")})
    if force:
        log_event({"session": owner, "kind": "loan reclaimed", "to": holder, "paths": paths, "text": "took its work back (%s) by the user's answer at the terminal; you no longer hold those files" % files})
    print("  [RETURNED] %s -> %s (back in its scope): %s" % (files, owner, result))
    return True

def borrow_directive(P):
    """@BORROW <session>: this chat (keeping its own name, address and files) asks to hold another session's work for a while, or to move an existing loan of it to itself; @RECLAIM: the owner asks for its lent work back. Only the user's answer at the terminal moves files (no terminal, no change); a loan has one owner and at most one holder, so loans never chain."""
    me = P.get("session")
    word = "RECLAIM" if P.get("reclaim") else "BORROW"
    if P.get("side") or P.get("repeatable") or not me:
        print("  [%s REFUSED] it needs a numbered script with an @SESSION line (not @SIDE or @REPEATABLE). Nothing changed." % word)
        return
    reg = load_json(sessions_path(), {})

    def ago(name):
        age = time.time() - (reg.get(name) or {}).get("last_active", 0)
        return "%dm ago" % (age // 60) if age < 7200 else "%dh ago" % (age // 3600)

    def agreed(ans):
        return ans.strip().lower() in ("", "y", "yes")
    if P.get("reclaim"):
        lent = (reg.get(me) or {}).get("lent")
        if not lent:
            print("  [RECLAIM REFUSED] nothing of session %s is lent out. Nothing changed." % me)
            return
        holder, files = lent["to"], ", ".join("/" + p for p in lent.get("paths", [])[:6])
        ans = ask_console("\nSession %s asks for its work back from %s (%s; %s was last active %s).\nPress Enter to take it back now, with %s's uncommitted changes in those files, or type n to only ask %s to return it: " % (me, holder, files, holder, ago(holder), holder, holder))
        if ans is None:
            print("  [RECLAIM NOT DONE] it needs you at a terminal to answer. Nothing changed; ask the user in Talk instead.")
            return
        with state_lock():
            reg = load_json(sessions_path(), {})
            if agreed(ans):
                if not return_loan(reg, holder, me, "taken back by the owner (@RECLAIM)", force=True):
                    lent = reg[me].pop("lent", None) or {}
                    shift_paths(reg, holder, me, lent.get("paths", []), aim=lent.get("aim"))
                    print("  [RECLAIMED] %s holds its work again (%s no longer had it on record)" % (me, holder))
            else:
                log_event({"session": me, "kind": "message", "to": holder, "text": "asks for its work back: finish what you are on, then @RETURN %s | <what was done>" % me})
                print("  [SENT] %s is asked to return %s's work" % (holder, me))
            save_json(sessions_path(), reg)
        return
    src = re.sub(r"[^A-Za-z0-9_.-]+", "-", P.get("borrow") or "").strip("-")
    if not src or src == me or src not in reg:
        print("  [BORROW REFUSED] expected @BORROW <another session>; sessions: %s. Nothing changed." % (", ".join(sorted(n for n in reg if n != me)) or "none"))
        return
    srec = reg[src]
    if srec.get("unclaimed"):
        print("  [BORROW REFUSED] %s is unclaimed: name it in a new chat's @SESSION line to take it whole. Nothing changed." % src)
        return
    lent = srec.get("lent") or {}
    holder = lent.get("to")
    if holder == me:
        print("  [BORROW REFUSED] this session already holds %s's work. Nothing changed." % src)
        return
    paths = lent.get("paths", []) if holder else ((srec.get("scope") or {}).get("paths") or [])
    if not paths:
        print("  [BORROW REFUSED] %s holds no files to lend. Nothing changed." % src)
        return
    files = ", ".join("/" + p for p in paths[:6])
    # Comment (decision): a loan has one owner and at most one holder; borrowing work that is already lent moves the loan from its holder to this chat, so the work always returns to its owner and loans never chain
    if holder:
        q = "\nSession %s asks to take over the loan of %s's work from %s (%s; %s was last active %s; the work stays %s's).\nPress Enter to move the loan to %s, or type n to only ask %s to return it to %s: " % (me, src, holder, files, holder, ago(holder), src, me, holder, src)
    else:
        q = "\nSession %s asks to borrow %s's work (%s; %s was last active %s; it stays %s's and comes back with @RETURN or @RECLAIM).\nPress Enter to lend it, or type n to leave it: " % (me, src, files, src, ago(src), src)
    ans = ask_console(q)
    if ans is None:
        print("  [BORROW NOT DONE] it needs you at a terminal to answer. Nothing changed; ask the user in Talk instead.")
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        if not agreed(ans):
            if holder:
                log_event({"session": me, "kind": "message", "to": holder, "text": "asks you to give %s's work back: finish what you are on, then @RETURN %s | <what was done>" % (src, src)})
                print("  [SENT] %s is asked to return %s's work" % (holder, src))
            else:
                print("  [BORROW NOT DONE] you answered no; %s keeps its work" % src)
            return
        reg.setdefault(me, {})
        if holder:
            shift_paths(reg, holder, me, paths)
            if holder in reg:
                reg[holder]["borrowed"] = [b for b in reg[holder].get("borrowed", []) if b.get("from") != src]
            ln = reg[src]["lent"]
            ln["holders"], ln["to"] = ln.get("holders", []) + [holder], me
            log_event({"session": me, "kind": "loan moved", "to": holder, "paths": paths, "text": "the user moved the loan of %s's work (%s) to %s; you no longer hold those files" % (src, files, me)})
        else:
            aim = (reg[src].get("scope") or {}).get("aim")
            shift_paths(reg, src, me, paths)
            reg[src]["lent"] = {"to": me, "paths": paths, "since": CURRENT_SCRIPT, "time": time.time(), "aim": aim, "holders": []}
        reg[me].setdefault("borrowed", []).append({"from": src, "paths": paths, "since": CURRENT_SCRIPT})
        log_event({"session": me, "kind": "loan", "to": src, "paths": paths, "text": "holds your work now (%s) by the user's answer at the terminal; it stays yours: when you are back, do not change those files, and @RECLAIM asks for them" % files})
        save_json(sessions_path(), reg)
    print("  [BORROWED] %s now holds %s's work (%s); it stays %s's: @RETURN %s | <what was done> gives it back" % (me, src, files, src, src))

def unclaim_directive(P):
    """@UNCLAIM <brief>: this chat hands its own session to whichever chat comes next. The session becomes UNCLAIMED with the brief and keeps its files, uncommitted work, notes, messages and queues; this chat's address is cleared (the claiming chat is asked for its own), and this chat sends nothing more under that name."""
    me, brief = P.get("session"), (P.get("unclaim") or "").strip()
    if P.get("side") or P.get("repeatable") or not me:
        print("  [UNCLAIM REFUSED] it needs a numbered script with an @SESSION line (not @SIDE or @REPEATABLE). Nothing changed.")
        return
    if not brief:
        print("  [UNCLAIM REFUSED] say what the next chat needs: @UNCLAIM <brief> (the goal, the decisions, what is done, the code locations and what is left). Nothing changed.")
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        rec = reg.setdefault(me, {})
        if rec.get("lent"):
            print("  [UNCLAIM REFUSED] this session's work is lent to %s; take it back with @RECLAIM first. Nothing changed." % rec["lent"].get("to"))
            return
        # Comment (decision): the address is cleared but marked as asked, so the chat that unclaims is not asked again in this run; the claim step clears the mark, so the next chat records its own address
        rec["unclaimed"], rec["brief"], rec["created_by"] = True, brief, me
        rec["link"], rec["link_asked"] = None, True
        save_json(sessions_path(), reg)
    P["unclaimed_now"] = True
    print("  [UNCLAIMED] session %s waits for the next chat, with its files, uncommitted work, notes and messages; this chat must send nothing more under that name. A new chat takes it by starting with @SESSION %s | <aim>, and gets the brief once." % (me, me))

def guide_directive(P):
    """@GUIDE: this session becomes the project's guide (one at a time): it claims only docs/ (plans, the tree, the backlog), never code, and every other chat's footer names it for cross-worker, architecture, data-ownership and direction questions; @GUIDE off ends the role."""
    me, arg = P.get("session"), P.get("guide")
    if P.get("side") or P.get("repeatable") or not me:
        print("  [GUIDE REFUSED] it needs a numbered script with an @SESSION line (not @SIDE or @REPEATABLE). Nothing changed.")
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        rec = reg.setdefault(me, {})
        if arg in ("off", "end", "stop"):
            was = rec.pop("role", None)
            save_json(sessions_path(), reg)
            print("  [GUIDE] %s" % ("%s is no longer the project's guide" % me if was else "%s was not the guide; nothing changed" % me))
            return
        other = next((n for n, r in reg.items() if n != me and r.get("role") == "guide"), None)
        if other:
            print("  [GUIDE REFUSED] %s is already the project's guide; it ends that with @GUIDE off. Nothing changed." % other)
            return
        code = [p for p in ((rec.get("scope") or {}).get("paths") or []) if not scope_item(p)[0].replace("\\", "/").lstrip("/").startswith("docs/")]
        if code:
            print("  [GUIDE REFUSED] this session holds code files (%s): commit and release them, or hand them over, first. Nothing changed." % ", ".join("/" + p for p in code[:4]))
            return
        rec["role"] = "guide"
        save_json(sessions_path(), reg)
    print("  [GUIDE] %s is now the project's guide: it changes no code, and every other chat's footer names it for cross-worker, architecture, data-ownership and direction questions" % me)

def takeover_directive(P):
    """@TAKEOVER <session>: this chat asks to absorb another chat's work (write scope, grants, notes, verdicts, queues and unread messages), the same as the user's --merge; only the user's answer at the terminal does it (no terminal, no change), and only a numbered script of a named chat can ask."""
    src = re.sub(r"[^A-Za-z0-9_.-]+", "-", (P.get("takeover") or "")).strip("-")
    me = P.get("session")
    if P.get("side") or P.get("repeatable") or not me:
        print("  [TAKEOVER REFUSED] it needs a numbered script with an @SESSION line (not @SIDE or @REPEATABLE). Nothing changed.")
        return
    reg = load_json(sessions_path(), {})
    if not src or src == me or src not in reg:
        print("  [TAKEOVER REFUSED] expected @TAKEOVER <another session>; sessions: %s. Nothing changed." % (", ".join(sorted(n for n in reg if n != me)) or "none"))
        return
    age = time.time() - reg[src].get("last_active", 0)
    when = "%dm ago" % (age // 60) if age < 7200 else "%dh ago" % (age // 3600)
    # Comment (decision): a script can ask but never decide: another chat's work moves only on the user's own answer at the terminal, so no terminal means no change
    ans = ask_console("\nSession %s asks to take over what session %s holds (its write scope, grants, notes, verdicts and unread messages; %s was last active %s).\nPress Enter to agree, or type n to leave it as it is: " % (me, src, src, when))
    if ans is None:
        print("  [TAKEOVER NOT DONE] it needs you at a terminal to answer. Nothing changed; ask the user in Talk instead.")
        return
    if ans.strip().lower() in ("", "y", "yes"):
        merge_sessions(src, me)
        print("  [TAKEOVER] session %s now holds what %s held (your answer at the terminal)" % (me, src))
    else:
        print("  [TAKEOVER NOT DONE] you answered no; %s keeps its work" % src)

def steward_directive(P):
    """@STEWARD [on | off]: the AI asks to switch the opt-in backlog-and-review rule; only the user's answer at the terminal changes it (no terminal, no change), and a side or repeatable script cannot ask at all."""
    word = (P.get("steward") or "").lower()
    if word not in ("on", "off", "status"):
        print("  [STEWARD REFUSED] expected @STEWARD on, @STEWARD off or @STEWARD alone. Nothing changed.")
        return
    if P.get("side") or P.get("repeatable"):
        print("  [STEWARD REFUSED] a @SIDE or @REPEATABLE script cannot change it. Nothing changed.")
        return
    now = steward_on()
    if word == "status":
        print("  [STEWARD] project stewardship is %s for this project on this machine" % ("ON" if now else "OFF"))
        return
    if (word == "on") == now:
        print("  [STEWARD] it is already %s here; nothing to ask" % word.upper())
        return
    # Comment (decision): a script can ask but never decide: the switch changes only on the user's own answer at the terminal, so no terminal means no change
    ans = ask_console("\nThe AI asks to switch project stewardship %s for this project on this machine (%s).\nPress Enter to agree, or type n to leave it as it is: " % (word.upper(), "it keeps docs/backlog.md and reviews before calling work done" if word == "on" else "the backlog and review rule leaves the footer"))
    if ans is None:
        print("  [STEWARD NOT CHANGED] it needs you at a terminal to answer. Nothing changed; ask the user in Talk instead.")
        return
    if ans.strip().lower() in ("", "y", "yes"):
        os.makedirs(HARNESS_DIR, exist_ok=True)
        save_json(steward_path(), {"on": word == "on"})
        print("  [STEWARD %s] project stewardship is now %s for this project on this machine (your answer at the terminal)" % (word.upper(), word.upper()))
    else:
        print("  [STEWARD NOT CHANGED] you answered no; it stays %s" % ("ON" if now else "OFF"))

def merge_session_cli():
    """User-only command: --merge <from_session> <into_session> folds a dead or ended session's write scope, grants, uncommitted history ownership, pinned notes, verdicts, and delegation/waiting queues into an ongoing session."""
    args = sys.argv[1:]
    i = args.index("--merge")
    src = re.sub(r"[^A-Za-z0-9_.-]+", "-", args[i + 1]).strip("-") if len(args) > i + 1 else ""
    dst = re.sub(r"[^A-Za-z0-9_.-]+", "-", args[i + 2]).strip("-") if len(args) > i + 2 else ""
    err = enter_workspace(arg_value("--workspace"))
    if err or not src or not dst or src == dst:
        print("usage: harness.py --workspace <project folder> --merge <from_session> <into_session>" + ((" | " + err) if err else ""))
        return
    merge_sessions(src, dst)

def merge_sessions(src, dst):
    """Fold session src's write scope, grants, uncommitted-history ownership, pinned notes, verdicts, delegation and waiting queues and unread messages into session dst: the work of the user's --merge, and of the @TAKEOVER directive after the user's answer at the terminal."""
    moved = []
    moved_notes, moved_verdicts = 0, 0
    with state_lock():
        reg = load_json(sessions_path(), {})
        if dst not in reg:
            print("no target session named %s; sessions: %s" % (dst, ", ".join(sorted(reg)) or "none"))
            return
        src_rec = reg.pop(src, None)
        grants = load_json(grants_path(), {})
        src_grants = grants.pop(src, [])
        hist_paths = []
        for hp in sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json"))):
            e = load_json(hp, None)
            if isinstance(e, dict) and e.get("session") == src:
                e["session"] = dst
                save_json(hp, e)
                hist_paths.extend(r for r, f in e.get("files", {}).items() if not f.get("undone"))
        notes, next_id = load_workspace_notes()
        for n in notes:
            who = n.get("for") or []
            if any(w.lower() == src.lower() for w in who):
                merged_for = []
                for w in who:
                    rep = dst if w.lower() == src.lower() else w
                    if not any(x.lower() == rep.lower() for x in merged_for):
                        merged_for.append(rep)
                n["for"] = merged_for
                moved_notes += 1
        if moved_notes:
            write_workspace_notes(notes, next_id)
        vdata = load_json(verdicts_path(), {})
        verdicts = vdata.get("verdicts") if isinstance(vdata, dict) else None
        if isinstance(verdicts, dict):
            new_verdicts = {}
            for k, v in verdicts.items():
                if not isinstance(v, dict):
                    new_verdicts[k] = v
                    continue
                target, owner = k.split("\t", 1) if "\t" in k else (v.get("target") or k, v.get("session") or "")
                if owner == src:
                    moved_verdicts += 1
                    dk = "%s\t%s" % (target, dst)
                    cur = new_verdicts.get(dk) or verdicts.get(dk)
                    if not isinstance(cur, dict) or float(v.get("time") or 0) >= float(cur.get("time") or 0):
                        new_verdicts[dk] = dict(v, session=dst, path=target)
                elif k not in new_verdicts:
                    new_verdicts[k] = v
            if moved_verdicts:
                save_json(verdicts_path(), dict(vdata, verdicts=new_verdicts))
        src_seen = (src_rec or {}).get("seen_seq", 0)
        # Comment (decision): messages sent to the merged-away session that it never read are sent again to the session it is merged into (a released session has no read position, so nothing is guessed for it)
        pending = [e for e in load_json(events_path(), {"events": []}).get("events", []) if src_rec and e.get("to") == src and e.get("seq", 0) > src_seen and e.get("kind") not in ("brake", "session merged by the user")]
        if src_rec is None and not src_grants and not hist_paths and not moved_notes and not moved_verdicts and not pending:
            print("nothing found for session %s; sessions: %s" % (src, ", ".join(sorted(reg)) or "none"))
            return
        drec = reg[dst]
        drec["merged_from"] = sorted(set(drec.get("merged_from", [])) | {src})
        if (src_rec or {}).get("milestones"):
            drec["milestones"] = (drec.get("milestones", []) + src_rec["milestones"])[-20:]
        if src_grants:
            d_grants = grants.get(dst, [])
            grants[dst] = d_grants + [p for p in src_grants if p not in d_grants]
            moved.append("grants (%d)" % len(src_grants))
        save_json(grants_path(), grants)
        if src_rec:
            src_sc = src_rec.get("scope") or {}
            src_paths = src_sc.get("paths") or []
            if src_paths:
                dst_sc = drec.get("scope") or {"aim": src_sc.get("aim") or drec.get("aim") or ("merged from " + src), "paths": []}
                dst_sc["paths"] = dst_sc.get("paths", []) + [p for p in src_paths if p not in dst_sc.get("paths", [])]
                drec["scope"] = dst_sc
                moved.append("scope (%s)" % ", ".join("/" + p for p in src_paths))
            if src_rec.get("handed_over"):
                drec["handed_over"] = sorted(set(drec.get("handed_over", [])) | set(src_rec["handed_over"]))
            if src_rec.get("used"):
                drec["used"] = sorted(set(drec.get("used", [])) | set(src_rec["used"]))
            for other, orec in reg.items():
                for item in orec.get("inherited", []):
                    if item.get("from") == src:
                        item["from"] = dst
                for item in orec.get("delegated", []):
                    if item.get("to") == src:
                        item["to"] = dst
                for w in orec.get("waiting", []):
                    if w.get("owner") == src:
                        w["owner"] = dst
                if (orec.get("brake") or {}).get("from") == src:
                    orec["brake"]["from"] = dst
            # Comment (decision): loans know their two sessions by name, so a merge settles them: a loan between the two merged sessions ends (the work is simply the merged chat's), a loan the merged session held from a third moves here and that owner's LENT record follows, and work the merged session had lent out keeps pointing at its owner
            drec["borrowed"] = [b for b in drec.get("borrowed", []) if b.get("from") != src]
            if (drec.get("lent") or {}).get("to") == src:
                drec.pop("lent", None)
            for b in src_rec.get("borrowed", []):
                if b.get("from") == dst:
                    continue
                drec.setdefault("borrowed", []).append(dict(b))
                lender = reg.get(b.get("from")) or {}
                if (lender.get("lent") or {}).get("to") == src:
                    lender["lent"]["to"] = dst
            sl = src_rec.get("lent") or {}
            if sl.get("to") and sl["to"] != dst and sl["to"] in reg and not drec.get("lent"):
                drec["lent"] = dict(sl)
                for b in reg[sl["to"]].get("borrowed", []):
                    if b.get("from") == src:
                        b["from"] = dst
            inh = [dict(i) for i in src_rec.get("inherited", []) if i.get("from") != dst]
            if inh:
                drec.setdefault("inherited", []).extend(inh)
                moved.append("inherited (%d)" % len(inh))
            dlg = [dict(d) for d in src_rec.get("delegated", []) if d.get("to") != dst]
            if dlg:
                drec.setdefault("delegated", []).extend(dlg)
                moved.append("delegated (%d)" % len(dlg))
            held_now = (drec.get("scope") or {}).get("paths", [])
            wait = [dict(w) for w in src_rec.get("waiting", []) if w.get("owner") != dst and not (held_now and scope_overlap([w["path"]], held_now))]
            if wait:
                seen_w = {(w.get("path"), w.get("owner")) for w in drec.get("waiting", [])}
                added_w = [w for w in wait if (w.get("path"), w.get("owner")) not in seen_w]
                if added_w:
                    drec.setdefault("waiting", []).extend(added_w)
                    moved.append("waiting (%d)" % len(added_w))
        if hist_paths:
            moved.append("history (%s)" % ", ".join("/" + p for p in sorted(set(hist_paths))))
        if moved_notes:
            moved.append("notes (%d)" % moved_notes)
        if moved_verdicts:
            moved.append("verdicts (%d)" % moved_verdicts)
        if pending:
            for e in pending:
                log_event({"session": e.get("session", src), "kind": e.get("kind", "message"), "to": dst, "text": "(sent to %s before it was merged into you) %s" % (src, e.get("text", ""))})
            moved.append("messages (%d)" % len(pending))
        summary = ", ".join(moved) or "empty session record"
        save_json(sessions_path(), reg)
        log_event({"session": dst, "kind": "session merged by the user", "to": dst, "text": "merged session %s into your session (%s)" % (src, summary)})
    if moved_notes or moved_verdicts:
        auto_commit_memory({"notes": moved_notes, "goal": None, "verdicts": moved_verdicts, "campaigns": []})
    print("SESSION MERGED BY THE USER: %s -> %s (%s)" % (src, dst, summary))

def grant_cli():
    """User-only command: harness.py --workspace <folder> --grant|--revoke <session> <path or glob>."""
    flag = "--revoke" if "--revoke" in sys.argv[1:] else "--grant"
    args = sys.argv[1:]
    i = args.index(flag)
    sess = args[i + 1] if len(args) > i + 1 else ""
    pattern = args[i + 2].replace("\\", "/").lstrip("/") if len(args) > i + 2 else ""
    err = enter_workspace(arg_value("--workspace"))
    if err or not sess or not pattern:
        print("usage: harness.py --workspace <project folder> --grant <session> <path or glob>   (or --revoke)" + ((" | " + err) if err else ""))
        return
    with state_lock():
        g = load_json(grants_path(), {})
        cur = [p for p in g.get(sess, []) if p != pattern]
        if flag == "--grant":
            cur.append(pattern)
        g[sess] = cur
        save_json(grants_path(), g)
    print("%s: session %s %s write access to %s despite other sessions' scopes" % (flag[2:].upper() + "ED" if flag == "--grant" else "REVOKED", sess, "gets" if flag == "--grant" else "loses", pattern))

def windows_clipboard_set(text):
    """Put text on the Windows clipboard as Unicode through the Win32 API (ctypes, no external tool). False when the clipboard stays held by another program."""
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.OpenClipboard.argtypes, user32.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes, user32.SetClipboardData.restype = [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes, kernel32.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes, kernel32.GlobalLock.restype = [wintypes.HGLOBAL], wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes, kernel32.GlobalUnlock.restype = [wintypes.HGLOBAL], wintypes.BOOL
    kernel32.GlobalFree.argtypes, kernel32.GlobalFree.restype = [wintypes.HGLOBAL], wintypes.HGLOBAL
    raw = (text.replace("\r\n", "\n").replace("\n", "\r\n") + "\0").encode("utf-16-le")
    for _ in range(40):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x0002, len(raw))
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(ptr, raw, len(raw))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(13, handle):
            kernel32.GlobalFree(handle)
            return False
        return True
    finally:
        user32.CloseClipboard()

def osc52_copy(data, tty_path="/dev/tty"):
    """Write an OSC 52 clipboard sequence directly to the controlling terminal so SSH / headless sessions copy to the user's local terminal clipboard."""
    b64 = base64.b64encode(data).decode("ascii")
    seq = "\033]52;c;%s\a" % b64
    if os.environ.get("TMUX"):
        seq = "\033Ptmux;" + seq.replace("\033", "\033\033") + "\033\\"
    fd = os.open(tty_path, os.O_WRONLY)
    try:
        view = seq.encode("ascii")
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)
    return True, "OSC 52 terminal escape (SSH/TTY clipboard)"

def copy_to_clipboard(text, tty_path="/dev/tty"):
    """(ok, how): put text on the system clipboard through a tool the system already has (PowerShell on Windows, OSC 52 over SSH, or pbcopy/wl-copy/xclip/xsel locally); a temp file keeps the encoding exact on Windows."""
    data = text.encode("utf-8")
    try:
        if os.name == "nt":
            tries = []
            try:
                if windows_clipboard_set(text):
                    return True, "the Windows clipboard"
                tries.append("the Windows clipboard could not be opened (another program may be holding it)")
            except Exception as e:
                tries.append("Windows clipboard API: %s" % e)
            import tempfile
            fd, tmp = tempfile.mkstemp(suffix=".txt")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                cmd = "Get-Content -Raw -Encoding UTF8 -LiteralPath '%s' | Set-Clipboard" % tmp.replace("'", "''")
                r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, timeout=30)
            finally:
                os.remove(tmp)
            if r.returncode == 0:
                return True, "PowerShell Set-Clipboard"
            tries.append("PowerShell Set-Clipboard: " + ((r.stderr or r.stdout or b"").decode("utf-8", "replace").strip().splitlines() or ["exit %d" % r.returncode])[0][:200])
            return False, "; ".join(tries)
        # Comment (constraint): over SSH, X11/Wayland tools fail with no remote DISPLAY or copy to the remote host's RAM instead of the user's local client clipboard; send OSC 52 to /dev/tty first
        if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
            try:
                return osc52_copy(data, tty_path)
            except OSError:
                pass
        errs = []
        for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
            if shutil.which(cmd[0]):
                r = subprocess.run(cmd, input=data, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
                if r.returncode == 0:
                    return True, cmd[0]
                why = ((r.stderr or b"").decode("utf-8", "replace").strip().splitlines() or ["exit %d" % r.returncode])[0][:160]
                errs.append("%s (%s)" % (cmd[0], why))
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            try:
                return osc52_copy(data, tty_path)
            except OSError:
                pass
        return False, "; ".join(errs) if errs else "no clipboard tool found (install xclip, xsel or wl-copy)"
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)

def ancestors(pid, parents):
    """Every ancestor of a process, from a {pid: parent pid} table; a loop in the table (a recycled pid) ends the walk instead of repeating."""
    seen, p = set(), parents.get(pid)
    while p and p not in seen:
        seen.add(p)
        p = parents.get(p)
    return seen

def process_parents():
    """{pid: parent pid} for every running process (Windows, through a toolhelp snapshot)."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.argtypes, k32.CreateToolhelp32Snapshot.restype = [wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    k32.Process32FirstW.restype = k32.Process32NextW.restype = wintypes.BOOL
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    table = {}
    if snap in (None, 0, -1, 0xFFFFFFFFFFFFFFFF):
        return table
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            table[entry.th32ProcessID] = entry.th32ParentProcessID
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return table

TTY_FOCUS = {"active": False, "fd": None, "old": None, "buf": b"", "focused": None, "reason": ""}

def parse_focus_events(buf, focused=None, reason=""):
    """Scan raw TTY bytes for xterm DECSET 1004 focus events (\\033[I = focus in, \\033[O = focus out) in arrival order; keep any trailing incomplete '\\033' or '\\033[' prefix for the next read."""
    for m in re.finditer(rb"\033\[([IO])", buf):
        if m.group(1) == b"I":
            focused, reason = True, "terminal focus event"
        else:
            focused, reason = False, ""
    tail = b"\033[" if buf.endswith(b"\033[") else (b"\033" if buf.endswith(b"\033") else b"")
    return focused, reason, tail

def start_tty_focus(resume=False):
    """Enable xterm DECSET 1004 focus reporting (\\033[?1004h) on /dev/tty with ECHO/ICANON off (keeping ISIG for Ctrl-C) so focus-out (\\033[O) during a run is caught silently without printing ^[[O."""
    if os.name == "nt" or TTY_FOCUS["active"] or os.environ.get("LLM_HARNESS_NO_COPY") or os.environ.get("LLM_HARNESS_NO_PROMPT") or not os.isatty(1):
        return
    try:
        import termios
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NONBLOCK)
        old = termios.tcgetattr(fd)
        cur = termios.tcgetattr(fd)
        # Comment (constraint): suppress ICANON and ECHO while focus reporting is on so \033[O / \033[I never echo as ^[[O^[[I on screen, while keeping ISIG so Ctrl-C still raises SIGINT
        cur[3] &= ~(termios.ICANON | termios.ECHO)
        termios.tcsetattr(fd, termios.TCSANOW, cur)
        os.write(fd, b"\033[?1004h")
        if not resume:
            is_ssh = bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY")) and not os.environ.get("TMUX")
            TTY_FOCUS["focused"] = True if is_ssh else None
            TTY_FOCUS["reason"] = "SSH terminal stayed focused" if is_ssh else ""
            TTY_FOCUS["buf"] = b""
        TTY_FOCUS.update({"active": True, "fd": fd, "old": old})
    except Exception:
        pass

def poll_tty_focus():
    """Read any non-blocking bytes from /dev/tty while DECSET 1004 is active and update focus state."""
    fd = TTY_FOCUS.get("fd")
    if not TTY_FOCUS.get("active") or fd is None:
        return
    chunks = []
    while True:
        try:
            b = os.read(fd, 1024)
            if not b:
                break
            chunks.append(b)
        except BlockingIOError:
            break
        except OSError:
            break
    if chunks:
        focused, reason, tail = parse_focus_events(TTY_FOCUS["buf"] + b"".join(chunks), TTY_FOCUS["focused"], TTY_FOCUS["reason"])
        TTY_FOCUS["focused"], TTY_FOCUS["reason"], TTY_FOCUS["buf"] = focused, reason, tail

def stop_tty_focus(keep_state=False):
    """Disable DECSET 1004 (\\033[?1004l), harvest final focus events, and restore original /dev/tty termios."""
    if not TTY_FOCUS.get("active"):
        return
    poll_tty_focus()
    fd, old = TTY_FOCUS.get("fd"), TTY_FOCUS.get("old")
    try:
        if fd is not None:
            try:
                os.write(fd, b"\033[?1004l")
            except OSError:
                pass
            poll_tty_focus()
            if old is not None:
                import termios
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        TTY_FOCUS.update({"active": False, "fd": None, "old": None, "buf": b""})
        if not keep_state:
            TTY_FOCUS.update({"focused": None, "reason": ""})

def terminal_has_focus():
    """(focused, why): True when the window in front is this run's own terminal. On Windows, checks GetForegroundWindow against console/ancestor PIDs; on POSIX/SSH, checks DECSET 1004 focus events (\\033[I / \\033[O) captured during the run."""
    if os.name != "nt":
        poll_tty_focus()
        if TTY_FOCUS.get("focused") is True:
            return True, TTY_FOCUS.get("reason") or "terminal focus event"
        return False, ""
    try:
        import ctypes
        from ctypes import wintypes
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        u32.GetForegroundWindow.restype = wintypes.HWND
        k32.GetConsoleWindow.restype = wintypes.HWND
        front = u32.GetForegroundWindow()
        if not front:
            return False, ""
        if front == k32.GetConsoleWindow():
            return True, "console window"
        owner = wintypes.DWORD(0)
        u32.GetWindowThreadProcessId(wintypes.HWND(front), ctypes.byref(owner))
        if owner.value and owner.value in ancestors(os.getpid(), process_parents()):
            return True, "terminal program %d" % owner.value
    except Exception:
        pass
    return False, ""

AUTO_COPY = []

def ask_key(prompt, keys, aliases=None):
    """Wait at the terminal for one of the keys in `keys` (lowercase letters), without needing Enter, and return it; `aliases` maps other characters to a key (Enter to "c", say); Esc and Ctrl-C return the last key of `keys` (the way out) and every other key is ignored. None when no one is there (output captured, no console, or prompts turned off)."""
    if os.environ.get("LLM_HARNESS_NO_PROMPT") or agent_mode() or not os.isatty(1):
        return None
    way_out, key, aliases = keys[-1], None, aliases or {}
    try:
        sys.stdout.flush()
        if os.name == "nt":
            import msvcrt
            with open("CONOUT$", "w") as fo:
                drain_console(None)
                fo.write(prompt)
                fo.flush()
                try:
                    while key is None:
                        ch = msvcrt.getwch()
                        if ch in ("\x00", "\xe0"):
                            msvcrt.getwch()
                        elif ch in ("\x03", "\x1b"):
                            key = way_out
                        elif ch in aliases:
                            key = aliases[ch]
                        elif ch.lower() in keys:
                            key = ch.lower()
                except KeyboardInterrupt:
                    key = way_out
                fo.write(key.upper() + "\n")
            return key
        import termios, tty
        fd = os.open("/dev/tty", os.O_RDWR)
        try:
            old = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                termios.tcflush(fd, termios.TCIFLUSH)
                os.write(fd, prompt.encode("utf-8"))
                while key is None:
                    raw = os.read(fd, 1)
                    ch = raw.decode("utf-8", "ignore")
                    if not raw or ch == "\x1b":
                        key = way_out
                    elif ch in aliases:
                        key = aliases[ch]
                    elif ch.lower() in keys:
                        key = ch.lower()
            except KeyboardInterrupt:
                key = way_out
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            os.write(fd, (key.upper() + "\n").encode("utf-8"))
            return key
        finally:
            os.close(fd)
    except Exception:
        return None

def offer_copy():
    """At a real terminal, copy the whole output of this run to the clipboard so it can be pasted straight into the chat. After a replay, with LLM_HARNESS_COPY=auto, and on Windows while this terminal is still the window in front, it copies at once; otherwise it waits for one key: C (or Enter) copies, X (or Esc) skips, other keys are ignored. LLM_HARNESS_COPY=ask always asks. Nothing happens when the output is captured, no console is attached, or LLM_HARNESS_NO_COPY is set."""
    if os.environ.get("LLM_HARNESS_NO_COPY") or os.environ.get("LLM_HARNESS_NO_PROMPT") or not os.isatty(1):
        return
    text = getattr(sys.stdout, "text", None)
    text = text() if callable(text) else ""
    if not text.strip():
        return
    # Comment (decision): a replay is instant and a terminal still in front means the user is looking at it, so there is nothing to wait for; a terminal left in the background waits, so the clipboard is never replaced behind the user's back
    mode, why = os.environ.get("LLM_HARNESS_COPY", "").lower(), ""
    if AUTO_COPY:
        why = "after a replay"
    elif mode == "auto":
        why = "LLM_HARNESS_COPY=auto"
    elif mode != "ask":
        focused, reason = terminal_has_focus()
        why = "the terminal is in front: " + reason if focused else ""
    stop_tty_focus()
    if not why and ask_key("\nPress C or Enter to copy this output to the clipboard, X to skip: ", "cx", {"\r": "c", "\n": "c"}) != "c":
        return
    ok, how = copy_to_clipboard(text)
    if ok:
        tok, sess_tok, bucket_tok, proj_tok, pastes, bkey, sess = record_copied_tokens(text, replay=bool(AUTO_COPY))
        scope_part = "~%s tok %s, ~%s tok project total" % (format(bucket_tok, ","), bkey, format(proj_tok, ",")) if bucket_tok != proj_tok else "~%s tok project total [%s]" % (format(proj_tok, ","), bkey)
        print("  [COPIED] %d characters (~%s tok this paste, ~%s tok session %s, %s across %d paste%s) via %s%s. Paste them into the chat." % (
            len(text), format(tok, ","), format(sess_tok, ","), sess, scope_part, pastes, "" if pastes == 1 else "s", how, " (without asking: %s)" % why if why else ""))
    else:
        print("  [NOT COPIED] %s. Select the output by hand." % how)

def tokens_path():
    return os.path.join(WORKSPACE_NOTES_DIR, "tokens.json")

def estimate_tokens(text):
    """Heuristic token count (~4 chars/token) for harness output sent to the AI."""
    return max(1, (len(text) + 3) // 4) if text else 0

# Comment (workaround): Git Credential Manager lists a token (PAT) sign-in under the placeholder name 'Personal Access Token', which is not a GitHub login, so it is never used as the account in a token bucket's label
TOKEN_PLACEHOLDER_ACCOUNTS = ("personal access token",)

def usable_accounts(accounts):
    """The signed-in account names without Credential Manager's placeholder for token sign-ins."""
    return [a for a in accounts if a.strip().lower() not in TOKEN_PLACEHOLDER_ACCOUNTS]

def token_bucket_key():
    """Return '<github_account>@<machine>' so uploaded token totals stay separated per preferred GitHub account + machine pair."""
    acct = ""
    if MODE == "git":
        info = remote_login_info()
        if info and info.get("scheme") and info.get("host"):
            acct = run_git(["config", "--get", "credential.%s://%s.username" % (info["scheme"], info["host"])])[1].strip()
            if not acct:
                accts = usable_accounts(known_accounts(info["host"])[0])
                if len(accts) == 1:
                    acct = accts[0]
        if not acct:
            acct = run_git(["config", "--get", "user.name"])[1].strip()
    if not acct:
        acct = os.environ.get("USERNAME") or os.environ.get("USER") or "local"
    host = (os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or __import__("socket").gethostname() or "local").strip()
    return "%s@%s" % (acct, host)

def _normalize_tokens_doc(data):
    if not isinstance(data, dict):
        return {"buckets": {}}
    buckets = {}
    raw_buckets = data.get("buckets") if isinstance(data.get("buckets"), dict) else {}
    for bkey, bval in raw_buckets.items():
        if not isinstance(bval, dict):
            continue
        acct, _, mach = bkey.partition("@")
        sessions = {}
        raw_sess = bval.get("sessions") if isinstance(bval.get("sessions"), dict) else {}
        for skey, sval in raw_sess.items():
            if isinstance(sval, dict):
                sessions[skey] = {
                    "tokens": int(sval.get("tokens") or 0),
                    "pastes": int(sval.get("pastes") or 0),
                    "chars": int(sval.get("chars") or 0),
                    "last_tok": int(sval.get("last_tok") or 0),
                    "last_chars": int(sval.get("last_chars") or 0),
                }
        entry = {
            "account": str(bval.get("account") or acct or "local"),
            "machine": str(bval.get("machine") or mach or "local"),
            "tokens": int(bval.get("tokens") or 0),
            "pastes": int(bval.get("pastes") or 0),
            "chars": int(bval.get("chars") or 0),
            "last_tok": int(bval.get("last_tok") or 0),
            "last_chars": int(bval.get("last_chars") or 0),
            "sessions": sessions,
        }
        if bval.get("last_session"):
            entry["last_session"] = str(bval["last_session"])
        buckets[bkey] = entry
    if not buckets and any(int(data.get(k) or 0) > 0 for k in ("tokens", "pastes", "chars")):
        buckets["legacy@local"] = {
            "account": "legacy",
            "machine": "local",
            "tokens": int(data.get("tokens") or 0),
            "pastes": int(data.get("pastes") or 0),
            "chars": int(data.get("chars") or 0),
            "last_tok": int(data.get("last_tok") or 0),
            "last_chars": int(data.get("last_chars") or 0),
            "sessions": {},
        }
    return {"buckets": buckets}

def record_copied_tokens(text, replay=False, bucket_key=None, session=None):
    """Accumulate estimated tokens in .llm_harness/tokens.json under <github_account>@<machine> and per session; a replay replaces the previous paste's count instead of adding again. Returns (this_tok, session_tok, bucket_tok, project_tok, project_pastes, bucket_key, session)."""
    tok = estimate_tokens(text)
    bkey = bucket_key or token_bucket_key()
    sess = session or CURRENT_SESSION or "default"
    if not os.path.isdir(".git") and not os.path.isdir(WORKSPACE_NOTES_DIR):
        return tok, tok, tok, tok, 1, bkey, sess
    with state_lock():
        doc = _normalize_tokens_doc(load_json(tokens_path(), {"buckets": {}}))
        buckets = doc["buckets"]
        acct, _, mach = bkey.partition("@")
        b = buckets.setdefault(bkey, {"account": acct or "local", "machine": mach or "local", "tokens": 0, "pastes": 0, "chars": 0, "last_tok": 0, "last_chars": 0, "sessions": {}})
        s = b["sessions"].setdefault(sess, {"tokens": 0, "pastes": 0, "chars": 0, "last_tok": 0, "last_chars": 0})
        if tok:
            if replay and s["pastes"] > 0:
                prev_tok = s["last_tok"]
                prev_chars = s["last_chars"]
                s["tokens"] = max(0, s["tokens"] - prev_tok) + tok
                s["chars"] = max(0, s["chars"] - prev_chars) + len(text)
                b["tokens"] = max(0, b["tokens"] - prev_tok) + tok
                b["chars"] = max(0, b["chars"] - prev_chars) + len(text)
            else:
                s["tokens"] += tok
                s["pastes"] += 1
                s["chars"] += len(text)
                b["tokens"] += tok
                b["pastes"] += 1
                b["chars"] += len(text)
            s["last_tok"] = tok
            s["last_chars"] = len(text)
            b["last_tok"] = tok
            b["last_chars"] = len(text)
            b["last_session"] = sess
            os.makedirs(WORKSPACE_NOTES_DIR, exist_ok=True)
            save_json(tokens_path(), doc)
        sess_tok = max(s["tokens"], tok)
        bucket_tok = max(b["tokens"], tok)
        proj_tok = max(sum(v["tokens"] for v in buckets.values()), tok)
        proj_pastes = max(sum(v["pastes"] for v in buckets.values()), 1)
    return tok, sess_tok, bucket_tok, proj_tok, proj_pastes, bkey, sess

def lock_holders(folder):
    """Names of processes whose working folder is inside this folder (needs the optional psutil package); [] when psutil is missing or nothing is found. Only reported, never stopped."""
    try:
        import psutil
    except ImportError:
        return []
    root = os.path.normcase(os.path.abspath(folder))
    out = []
    for pr in psutil.process_iter(["pid", "name"]):
        try:
            cwd = os.path.normcase(pr.cwd())
        except Exception:
            continue
        if cwd == root or cwd.startswith(root + os.sep):
            out.append("%s (PID %s)" % (pr.info.get("name"), pr.info.get("pid")))
    return out[:6]

def prune_emptied_parents(paths):
    """After files left their folders (moved or deleted), remove each emptied folder above them, up to the workspace root; a folder holding only __pycache__ counts as empty, since the cache regrows. Returns (removed folders, [(folder, error)]) for folders that could not go."""
    gone, kept = [], []
    for p in paths:
        d = os.path.dirname(p)
        while d:
            if not os.path.isdir(d):
                d = os.path.dirname(d)
                continue
            names = os.listdir(d)
            if names and not all(n == "__pycache__" and os.path.isdir(os.path.join(d, n)) for n in names):
                break
            try:
                for n in names:
                    shutil.rmtree(os.path.join(d, n))
                os.rmdir(d)
                gone.append(d)
            except OSError as e:
                kept.append((d, e))
                break
            d = os.path.dirname(d)
    return gone, kept

def report_pruned(result):
    gone, kept = result
    if gone:
        print("\n  [FOLDERS REMOVED] " + ", ".join("/" + d for d in sorted(set(gone))) + " (emptied)")
    for d, e in kept:
        who = lock_holders(d)
        hint = "held open by " + ", ".join(who) if who else ("something has it open (a terminal, editor or watcher whose working folder is inside it): close it and remove the folder by hand, or install psutil to name the holder" if isinstance(e, PermissionError) else str(e))
        print("  [FOLDER KEPT] /%s could not be removed: %s" % (d, hint))

def expand_rename_ops(P):
    """@RENAME on a folder becomes one rename per file, so every file goes through the journal (@UNDO brings the folder back) and claims apply file by file. Refused whole when the destination exists, the folder holds a symbolic link, or the move would be into itself."""
    out = []
    for op in P["ops"]:
        src = (op.get("file") or "").strip().replace("\\", "/").strip("/")
        dst = (op.get("to") or "").strip().replace("\\", "/").strip("/")
        if op.get("type") != "rename" or op.get("malformed") or op.get("blocked") or not src or not os.path.isdir(src) or os.path.isfile(src):
            out.append(op)
            continue
        why = ""
        if safe_rel(src) is None or safe_rel(dst or ".") is None:
            why = "a folder inside the repository, away from git and harness internals, is needed on both sides"
        # Comment (constraint): os.path.normcase turns "/" into "\" on Windows, which made the "into itself" test miss and let a folder move into itself; compare lowercased forward-slash paths instead
        elif src == dst:
            why = "the source and the destination are the same folder"
        elif src.lower() == dst.lower():
            why = "this would only change the case, which is the same folder on Windows and macOS; rename it through an intermediate name"
        elif dst.lower().startswith(src.lower() + "/"):
            why = "a folder cannot be moved into itself"
        elif os.path.exists(dst) and (os.path.isfile(dst) or os.listdir(dst)):
            why = "/%s already exists and is not empty; move into a free path, or move its files one by one" % dst
        files = []
        for root, dirs, fs in os.walk(src):
            for name in dirs + fs:
                if os.path.islink(os.path.join(root, name)):
                    why = why or "it holds a symbolic link (%s); move those by hand" % os.path.join(root, name).replace("\\", "/")
            files += [os.path.join(root, f).replace("\\", "/") for f in fs]
        if not why and not files:
            why = "/%s holds no files" % src
        if not why and sum(os.path.getsize(f) for f in files) > 50 * 1024 * 1024:
            why = "/%s holds more than 50 MB, too much for the undo journal" % src
        if why:
            out.append(dict(op, blocked="folder rename refused: " + why + ". Nothing was moved"))
            continue
        for f in sorted(files):
            out.append({"type": "rename", "file": f, "to": dst + f[len(src):], "scope": "TOP", "label": "Rename (in /%s) to /%s" % (src, dst + f[len(src):]), "folder": src})
    P["ops"] = out

def expand_delete_ops(P):
    """@DELETE_FILE on a folder or glob becomes one delete per file, so every file goes into the journal (recoverable with @UNDO) and claims apply file by file."""
    out = []
    for op in P["ops"]:
        target = (op.get("file") or "").strip().replace("\\", "/").strip("/")
        if op.get("type") != "delete" or op.get("malformed") or op.get("blocked") or not target or os.path.isfile(target):
            out.append(op)
            continue
        if os.path.isdir(target):
            files = sorted(os.path.join(r, f).replace("\\", "/") for r, _, fs in os.walk(target) for f in fs)
        elif any(c in target for c in "*?["):
            files = glob_files(target)
        else:
            out.append(op)
            continue
        files = [f for f in files if safe_rel(f) is not None]
        if not files:
            out.append(dict(op, blocked="nothing to delete: /%s holds or matches no file" % target))
            continue
        size = sum(os.path.getsize(f) for f in files)
        if size > 50 * 1024 * 1024:
            out.append(dict(op, blocked="/%s holds %d MB, too much for the undo bin; delete it with @RUN only if losing it for good is fine" % (target, size // 1048576)))
            continue
        for f in files:
            out.append({"type": "delete", "file": f, "scope": "TOP", "label": "Delete file (in /%s)" % target, "folder": target if os.path.isdir(target) else None})
    P["ops"] = out

def expand_text_ops(P):
    """Check each @TEXT_REPLACE's total match count against its expect, then turn it into one edit per file it touches."""
    out, renames = [], {}
    for op in P["ops"]:
        if op.get("type") == "rename" and not op.get("malformed") and not op.get("blocked"):
            renames[op["to"].strip().replace("\\", "/").lstrip("/")] = op["file"].strip().replace("\\", "/").lstrip("/")
        if op.get("type") != "text" or op.get("malformed") or op.get("blocked"):
            out.append(op)
            continue
        path, _, scope = op["file"].partition("#")
        target = path.strip().replace("\\", "/").lstrip("/")
        src_of = {}
        if target and os.path.isfile(target):
            files = [target]
        elif target in renames and os.path.isfile(renames[target]):
            # Comment (order): counting happens before anything runs, while the file still sits at its old path; the edit itself runs after the rename, in script order
            files, src_of = [target], {target: renames[target]}
        else:
            named = glob_files(target) if any(c in target for c in "*?[") else [f for f in repo_files(".") if path_in(f, target or "**")]
            files = [f for f in named if within_depth(f, literal_base(target), op.get("depth"))]
        hits, per_file = [], []
        for f in files:
            src = src_of.get(f, f)
            if safe_rel(src) is None or os.path.getsize(src) > 2000000:
                continue
            raw = read_bytes(src)
            if b"\0" in raw[:4096]:
                continue
            lines = decode_bytes(raw)[0].split("\n")
            lo, hi = 0, len(lines)
            if scope.strip():
                lo, hi, note = resolve_scope(f, lines, scope.strip())
                if note:
                    continue
            found = [(i, lines[i].count(op["find"])) for i in range(lo, min(hi, len(lines))) if op["find"] in lines[i]]
            if found:
                hits += [(f, i, c) for i, c in found]
                per_file.append((f, lo, hi, sum(c for _, c in found)))
        total = sum(c for _, _, c in hits)
        if total != op["expect"]:
            where = ", ".join("/%s:%d" % (f, i + 1) for f, i, _ in hits[:12]) + (" ..." if len(hits) > 12 else "")
            op["blocked"] = "found %d occurrence(s), expected %d%s; nothing was replaced. Check with @GREP and resend with the right scope or expect" % (total, op["expect"], (": " + where) if hits else "")
            out.append(op)
            continue
        for f, lo, hi, count in per_file:
            out.append({"type": "text_file", "file": f, "scope": "TEXT" + (" " + scope.strip() if scope.strip() else ""), "label": "%s (%d here)" % (op["label"], count),
                        "find": op["find"], "replace": op["replace"], "lo": lo, "hi": hi, "count": count})
    P["ops"] = out

def side_allowed(P):
    """A @SIDE script may only read, search and @RUN: no file, note, goal, git or undo actions."""
    return not (P["ops"] or P["notes"] or P["goal"] or P["git"] or P["undo"] or P["git_init"] or P["scope"] is not None or P["scope_end"] or P["session_end"] or P["msgs"] or P["brake_ack"] or P["verdicts"] or P["campaigns"] or P.get("steward") or P.get("takeover") or P.get("borrow") or P.get("reclaim") or P.get("unclaim") or P.get("guide") or P.get("milestone"))

def side_run_path(raw_txt):
    return os.path.join(runs_dir(), "side_%s.json" % payload_key(raw_txt)[:16])

def expand_redo(raw):
    """@REDO <n>, optionally followed by corrections (--- [OLD TEXT] --- / +++ [NEW TEXT] +++ / === [END TEXT] ===, each old text found exactly once): script n's saved text, corrected, replaces the @REDO block; the rest of this script stays. Returns (text, error)."""
    lines = raw.split("\n")
    at = [i for i, l in enumerate(lines) if re.match(r"^@REDO\s+\d+\s*$", l.strip())]
    if not at:
        return raw, None
    i = at[0]
    num = int(lines[i].split()[1])
    run = find_run(num)
    if not run or not run.get("payload"):
        return raw, "@REDO %d: no saved text for script %d (only scripts run by a harness that keeps script text, and only the newest %d runs)" % (num, num, RUNS_KEEP)
    text = "\n".join(l for l in run["payload"].split("\n") if not re.match(r"^@(SCRIPT|SESSION|WORKSPACE)\b", l.strip()))
    j = i + 1
    while j < len(lines) and lines[j].strip() == "--- [OLD TEXT] ---":
        try:
            k = next(x for x in range(j + 1, len(lines)) if lines[x].strip() == "+++ [NEW TEXT] +++")
            e = next(x for x in range(k + 1, len(lines)) if lines[x].strip() == "=== [END TEXT] ===")
        except StopIteration:
            return raw, "@REDO %d: a correction needs --- [OLD TEXT] ---, +++ [NEW TEXT] +++ and === [END TEXT] ===" % num
        old, new = "\n".join(lines[j + 1:k]), "\n".join(lines[k + 1:e])
        if text.count(old) != 1:
            return raw, "@REDO %d: a correction's old text is found %d times in script %d, not once: '%s'" % (num, text.count(old), num, old[:80])
        text = text.replace(old, new)
        j = e + 1
    return "\n".join(lines[:i] + [text] + lines[j:]), None

def prune_runs(folder, pattern, by_time):
    """Keep only the newest RUNS_KEEP saved runs matching the pattern: numbered runs by name, side runs by modification time."""
    files = glob.glob(os.path.join(glob.escape(folder), pattern))
    files.sort(key=(lambda p: (os.path.getmtime(p), p)) if by_time else None)
    for stale in files[:max(0, len(files) - RUNS_KEEP)]:
        try:
            os.remove(stale)
        except OSError:
            pass

def save_run(P, raw_txt, body):
    """Keep a run's output (without its footer) for replay; only the newest RUNS_KEEP runs are kept."""
    d = runs_dir()
    os.makedirs(d, exist_ok=True)
    if P.get("side"):
        save_json(side_run_path(raw_txt), {"id": P["id"], "key": payload_key(raw_txt), "output": body})
        prune_runs(d, "side_*.json", True)
        return
    for old in glob.glob(os.path.join(d, "%06d_*.json" % P["num"])):
        os.remove(old)
    name = "%06d_%s.json" % (P["num"], re.sub(r"[^A-Za-z0-9_-]", "_", P["id"]))
    save_json(os.path.join(d, name), {"id": P["id"], "key": payload_key(raw_txt), "output": body, "payload": raw_txt})
    # Comment (constraint): numbered runs and side runs are pruned separately; sorted together, every name that starts with a digit sorts before "side_" and a flood of side runs would delete all the numbered runs first, breaking @REDO and replay
    prune_runs(d, "[0-9]*_*.json", False)

def find_run(num):
    found = glob.glob(os.path.join(runs_dir(), "%06d_*.json" % num))
    return load_json(found[0], None) if found else None

LOOP_AT = 3

def idle_script(P):
    """True for a script that did and read nothing: no changes, no searches, no probes, no help (it only reprints the footer)."""
    return read_only(P) and not (P["probes"] or P["xrefs"] or P["greps"] or P["finds"] or P["list_dir"] or P["list_rec"] or P["helps"] or P["git_status"] or P["verdict_lists"])

def read_only(P):
    """True when a script only reads: no file, note, goal, git, undo or @RUN actions."""
    return not (P["ops"] or P["notes"] or P["goal"] or P["git"] or P["undo"] or P["runs"] or P["git_init"] or P["scope"] is not None or P["scope_end"] or P["session_end"] or P["msgs"] or P["brake_ack"] or P["verdicts"] or P["campaigns"] or P.get("steward") or P.get("takeover") or P.get("borrow") or P.get("reclaim") or P.get("unclaim") or P.get("guide") or P.get("milestone"))

def load_state():
    """Numbering and shell from the machine-local state file; the goal from .llm_harness/goal.md, which travels with the project."""
    st = {"last_num": 0, "last_id": "", "committed_through": 0, "goal": "", "shell": ""}
    if MODE == "git" and not os.path.isfile(STATE_PATH) and os.path.isfile(os.path.join(WORKSPACE_NOTES_DIR, "state.json")):
        carry_state(WORKSPACE_NOTES_DIR, True)
        print("  (carried numbering and undo history from .llm_harness/ into git mode)")
    st.update(load_json(STATE_PATH, {}))
    if os.path.isfile(GOAL_PATH):
        st["goal"] = read_text(GOAL_PATH).strip()
    elif st["goal"]:
        write_goal(st["goal"])
    return st

def write_goal(text):
    """Keep the pinned goal in the project tree beside notes.md, so moves, clones and pulls carry it."""
    os.makedirs(WORKSPACE_NOTES_DIR, exist_ok=True)
    with open(GOAL_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.strip() + "\n")

def print_goal(state):
    if state.get("goal"):
        print("=== GOAL: %s ===" % state["goal"])
    else:
        print("=== GOAL: not set -> pin the user's long-term goal with @GOAL <text> in the next script ===")

def print_footer_notes():
    """The user's notes ride in every footer, so a chat keeps them in view without asking for @NOTE_LIST."""
    try:
        notes, _ = load_workspace_notes()
    except (OSError, ValueError):
        return
    for note in notes:
        if note_for(note, CURRENT_SESSION):
            # Comment (decision): the AI writes every note, so only the [own] mark it sets on its own to-do says who it belongs to; without it a chat that takes this one over would read the AI's plan as the owner's instruction
            if note.get("own"):
                print("=== NOTE %s (this chat's own to-do, written by the AI, not the user's): %s ===" % (note["id"], brief_text(note)))
            else:
                print("=== NOTE %s (the user's%s): %s ===" % (note["id"], ", pinned to this chat" if note.get("for") else "", brief_text(note)))

def rule_hash(body):
    return hashlib.sha1(body.strip().strip("`").strip().encode("utf-8")).hexdigest()[:12]

def agent_mode():
    """True when a host app (Claude Code first) runs the harness as its tool and sets LLM_HARNESS_AGENT; unset, the chat-browser flow is exactly as before."""
    return bool(os.environ.get("LLM_HARNESS_AGENT", "").strip() or os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip())

def agent_allow_path():
    return os.path.join(HARNESS_DIR, "agent_allow.json")

def agent_allow_cli():
    """User-only command: harness.py --workspace <folder> --agent-allow <program> [<argument pattern>] | list | clear. Keeps this project's agent-mode @RUN allowlist on this machine, outside the project; a script can never run it."""
    args = sys.argv[1:]
    i = args.index("--agent-allow")
    rest, j = [], i + 1
    while j < len(args):
        if args[j] == "--workspace":
            j += 2
            continue
        rest.append(args[j])
        j += 1
    err = enter_workspace(arg_value("--workspace"))
    if err or not rest:
        print("usage: harness.py --workspace <project folder> --agent-allow <program> [<argument pattern>] | list | clear" + ((" | " + err) if err else ""))
        return
    os.makedirs(HARNESS_DIR, exist_ok=True)
    data = load_json(agent_allow_path(), {"entries": []}) or {"entries": []}
    if rest[0].lower() == "clear":
        data["entries"] = []
        save_json(agent_allow_path(), data)
    elif rest[0].lower() != "list":
        exe, pattern = rest[0], " ".join(rest[1:])
        if "/" in exe or "\\" in exe:
            print("  [REFUSED] give the program by name (for example pytest), not by path. Nothing changed.")
            return
        try:
            re.compile(pattern)
        except re.error as e:
            print("  [REFUSED] the argument pattern is not a valid regular expression (%s). Nothing changed." % e)
            return
        name = exe.lower()[:-4] if exe.lower().endswith(".exe") else exe.lower()
        data["entries"] = [e for e in data.get("entries", []) if (e.get("exe"), e.get("args")) != (name, pattern)] + [{"exe": name, "args": pattern}]
        save_json(agent_allow_path(), data)
    print("AGENT-MODE @RUN ALLOWLIST for %s on this machine (the whole argument string must match the pattern; no shell, no shell operators; runs in the project folder):" % os.path.abspath("."))
    for e in data.get("entries", []) or []:
        print("  %s  %s" % (e.get("exe"), e.get("args") or "(no arguments)"))
    if not data.get("entries"):
        print("  (empty: agent mode refuses every @RUN)")

def agent_run_args(cmd):
    """Agent mode: the program and arguments to run directly (no shell) when the command has no shell operators, names its program without a path, and matches an allowlist entry in full; else None and the reason."""
    import shlex
    if re.search(r"[|&;<>`\r\n]|\$\(", cmd):
        return None, "shell operators (| & ; < > backtick, $( and newlines) are not allowed"
    try:
        toks = shlex.split(cmd, posix=(os.name != "nt"))
    except ValueError as e:
        return None, "the command could not be split into a program and arguments (%s)" % e
    if os.name == "nt":
        toks = [t[1:-1] if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'" else t for t in toks]
    if not toks:
        return None, "the command is empty"
    if "/" in toks[0] or "\\" in toks[0]:
        return None, "name the program, not a path to it"
    name = toks[0].lower()[:-4] if toks[0].lower().endswith(".exe") else toks[0].lower()
    rest = " ".join(toks[1:])
    for e in (load_json(agent_allow_path(), {}) or {}).get("entries", []) or []:
        try:
            ok = e.get("exe") == name and re.fullmatch(e.get("args") or "", rest) is not None
        except re.error:
            ok = False
        if ok:
            path = shutil.which(toks[0])
            if not path:
                return None, "%s is allowed but was not found on this machine" % toks[0]
            return [path] + toks[1:], ""
    return None, "'%s' is not on this project's allowlist" % cmd.strip()

def host_session_id():
    """The host app's own session id in agent mode: LLM_HARNESS_HOST_SESSION when a host adapter sets it, else Claude Code's CLAUDE_CODE_SESSION_ID (given to its shell tools and hooks, and new after /clear); empty outside agent mode."""
    return (os.environ.get("LLM_HARNESS_HOST_SESSION") or os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("OPENCODE_SESSION_ID") or "").strip() if agent_mode() else ""

def host_name():
    """The host app's name for the session list: the LLM_HARNESS_AGENT value, or claude-code when it is only switched on (1, true, on) inside Claude Code."""
    v = os.environ.get("LLM_HARNESS_HOST", "").strip() or os.environ.get("LLM_HARNESS_AGENT", "").strip()
    if not v or v.lower() in ("1", "true", "yes", "on"):
        return "claude-code" if os.environ.get("CLAUDE_CODE_SESSION_ID") else "opencode" if os.environ.get("OPENCODE_SESSION_ID") else "agent"
    return v

def record_host(P):
    """Agent mode: keep the host app and its session id beside the chat address (never in it), and map that host session to this harness session, so the next prompt's briefing can name it."""
    hid, me = host_session_id(), P.get("session")
    if not hid or not me or P.get("side"):
        return
    with state_lock():
        reg = load_json(sessions_path(), {})
        if me in reg:
            reg[me]["host"], reg[me]["host_session_id"] = host_name(), hid
            save_json(sessions_path(), reg)
        data = load_json(agent_turn_path(), {}) or {}
        data.setdefault("hosts", {}).setdefault(hid, {"turn": 0, "events": []})["session"] = me
        save_json(agent_turn_path(), data)

def agent_turn_path():
    return os.path.join(HARNESS_DIR, "agent_turn.json")

def new_turn_cli():
    """Host-hook command: harness.py --workspace <folder> --new-turn [<event id>]. Starts a new prompt turn, so the next harness run in agent mode briefs the full standing rules once; the same event id twice counts once, so a retried hook never starts two turns."""
    args = sys.argv[1:]
    i = args.index("--new-turn")
    event = args[i + 1] if len(args) > i + 1 and not args[i + 1].startswith("--") else ""
    err = enter_workspace(arg_value("--workspace"))
    if err:
        print("usage: harness.py --workspace <project folder> --new-turn [<event id>] | " + err)
        return
    hid = host_session_id()
    os.makedirs(HARNESS_DIR, exist_ok=True)
    with state_lock():
        data = load_json(agent_turn_path(), {}) or {}
        t = data.setdefault("hosts", {}).setdefault(hid, {"turn": 0, "events": []})
        if event and event in t.get("events", []):
            print("AGENT TURN %d continues (event %s was already counted)" % (t.get("turn", 0), event))
            return
        t["turn"] = t.get("turn", 0) + 1
        if event:
            t["events"] = (t.get("events", []) + [event])[-50:]
        save_json(agent_turn_path(), data)
    print("AGENT TURN %d starts%s: the next harness run in it briefs the full standing rules once | harness session: %s" % (
        t["turn"], " for host session " + hid if hid else "", t.get("session") or "none yet: name one with @SESSION <name> | <aim> (@SESSIONS lists them)"))

def agent_quiet(rules, briefs):
    """Agent mode only: the tags of standing rules this prompt turn already briefed and that have not changed or newly triggered since, so the footer does not repeat them. The first run of a turn for a session records the briefing (rule fingerprint and why it is expanded) and hides nothing; the chat flow always gets an empty set."""
    if not agent_mode() or not CURRENT_SESSION:
        return set()
    hid = host_session_id(); turn = "%s:%d" % (hid, (((load_json(agent_turn_path(), {}) or {}).get("hosts") or {}).get(hid) or {}).get("turn", 0))
    now = {tag: rule_hash(body) + "|" + (brief_reason(briefs[tag][0]) if tag in briefs else "") for tag, body in rules}
    with state_lock():
        reg = load_json(sessions_path(), {})
        rec = reg.get(CURRENT_SESSION)
        if rec is None:
            return set()
        if rec.get("turn_seen") != turn:
            rec["turn_seen"], rec["turn_rules"] = turn, now
            save_json(sessions_path(), reg)
            return set()
        snap = rec.get("turn_rules") or {}
    return {tag for tag, v in now.items() if snap.get(tag) == v}

def rules_seen(rules):
    """(rule fingerprints this chat saw last time, the mode it saw them in), replaced by the current ones; after a switch to git the no-git record is read once. Without a session nothing is kept."""
    if not CURRENT_SESSION:
        return {}, None
    try:
        with state_lock():
            reg = load_json(sessions_path(), {})
            rec = reg.get(CURRENT_SESSION)
            if rec is None:
                return {}, None
            old, old_mode = rec.get("rules_seen"), rec.get("rules_mode", MODE)
            if old is None and MODE == "git":
                prior = load_json(os.path.join(WORKSPACE_NOTES_DIR, "sessions.json"), {}).get(CURRENT_SESSION) or {}
                old, old_mode = prior.get("rules_seen"), "nogit"
            rec["rules_seen"], rec["rules_mode"] = {tag: rule_hash(body) for tag, body in rules}, MODE
            save_json(sessions_path(), reg)
            return (old or {}), (old_mode if old else None)
    except Exception:
        return {}, None

def open_ledgers():
    """Debug ledgers (docs/debug/bug_*.txt) not yet marked RESOLVED."""
    out = []
    for p in sorted(glob.glob(os.path.join("docs", "debug", "bug_*.txt"))):
        try:
            if "RESOLVED" not in decode_bytes(read_bytes(p))[0]:
                out.append(p.replace("\\", "/"))
        except OSError:
            pass
    return out

def brief_reason(conds):
    """Why a rule with a brief is printed in full this run ('' while the brief is enough); the harness decides, never the AI."""
    if "failed" in conds and RUN_FAILED:
        return "this run had a failure"
    if "ledger" in conds:
        n = len(open_ledgers())
        if n:
            return "%d open debug ledger%s" % (n, "" if n == 1 else "s")
    if "sessions" in conds:
        reg = load_json(sessions_path(), {})
        if len(reg) > 1 or any(r.get("waiting") or r.get("inherited") or r.get("delegated") or r.get("brake") for r in reg.values()):
            return "multiple sessions or active handoff/wait state"
    if "dirty" in conds and MODE == "git":
        if git_blockers():
            return "in-progress git operation"
        _, st_out, _ = run_git(["status", "--porcelain", "-uall"])
        # Comment (decision): the token counts change on every paste, so a modified tokens.json alone does not keep the rules expanded; -uall lists an untracked .llm_harness folder file by file, otherwise it shows as one folder line and a lone tokens.json inside it would keep the rules expanded for good
        if [l for l in st_out.splitlines() if l.strip() and not l[3:].strip().strip('"').endswith(WORKSPACE_NOTES_DIR + "/tokens.json")]:
            return "uncommitted changes in workspace"
        _, br, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        if br in (git_policy().get("protected") or []):
            return "on protected branch %s" % br
        rc_up, ahead_out, _ = run_git(["rev-list", "--count", "@{u}..HEAD"])
        if rc_up == 0 and int(ahead_out.strip() or "0") > 0:
            return "unpushed commits on branch"
    return ""

def print_footer_body(state):
    """Every run ends with the next free number, the pinned goal and the standing rules that apply to this workspace's mode."""
    if state is not None:
        print("\n=== NEXT SCRIPT NUMBER: %d ===" % (state["last_num"] + 1))
        if PING_ONLY:
            return
        if CURRENT_PART and CURRENT_PART[0] < CURRENT_PART[1]:
            print("=== PART %d of %d: the goal, notes and standing rules follow after part %d ===" % (CURRENT_PART[0], CURRENT_PART[1], CURRENT_PART[1]))
            return
        print_goal(state)
        print_footer_notes()
        print_footer_campaigns()
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            rules_text = f.read()
        found = re.findall(r"(?m)^- \*\*L1 Rule\W*(\[[^\]]+\])`?\s*(?:\(([\w-]+)\))?[`:*\s]*(.*)$", rules_text)
        briefs = {tag: ([c.strip().lower() for c in conds.split(",")], brief) for tag, conds, brief in re.findall(r"(?m)^- \*\*L1 Brief\W*(\[[^\]]+\])`?\s*\(([^)]*)\)[`:*\s]*(.*)$", rules_text)}
        modes = {"git": "git", "nogit": "nogit", "no-git": "nogit"}
        rules = [(tag, body) for tag, cond, body in found if not cond or (bool(active_campaigns()) if cond.lower() == "campaign" else steward_on() if cond.lower() == "steward" else agent_mode() if cond.lower() == "agent" else (not agent_mode()) if cond.lower() == "chat" else modes.get(cond.lower(), MODE) == MODE)]
    except OSError:
        print("=== L1 CONTRACT: workflow_commands.txt not found next to harness.py (%s); no standing rules printed ===" % SELF_DIR)
        return
    if MODE != "git":
        print("=== NO GIT HERE: @GIT_* directives are off and the git rules do not apply; use @GIT_INIT only if the user asks for git ===")
    elif os.path.isfile(os.path.join(WORKSPACE_NOTES_DIR, "git.json")):
        pol = git_policy()
        if pol:
            _, br, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
            prot = pol.get("protected") or []
            print("=== GIT POLICY: on branch %s%s | protected: %s%s ===" % (br, " (protected: no direct commits here)" if br in prot else "", ", ".join(prot) or "none", " | branch names: " + pol["branches"] if pol.get("branches") else ""))
    if rules:
        upstream_line(CURRENT_SESSION)
        account_hint()
    if CURRENT_SESSION and (load_json(sessions_path(), {}).get(CURRENT_SESSION) or {}).get("idle_runs", 0) >= LOOP_AT:
        print("=== LOOP CHECK: this chat's last %d scripts did nothing (footer only). The user may be pasting in a loop: send no manifest and no script, and reply in one or two short lines, no manifest and no formatting, so the reply can be discarded: say this looks like a repeated paste, and remind what is still pending or ask what they want next ===" % LOOP_AT)
    if rules:
        print("=== L1 CONTRACT (standing rules; apply, never echo) ===")
        before, before_mode = rules_seen(rules)
        changed = [tag for tag, body in rules if tag in before and before[tag] != rule_hash(body)]
        new = [tag for tag, body in rules if before and tag not in before]
        if before_mode == "nogit" and MODE == "git":
            print("  (this project now uses git: @GIT_* directives are on, and the rules marked [NEW] apply from here)")
        elif changed or new:
            print("  (rules marked [CHANGED] or [NEW] differ from what this chat saw last time: read them again)")
        # Comment (decision): in agent mode a host runs many harness calls per user prompt, so a rule already in this prompt's briefing is not repeated unless it changed or its trigger did; in chat mode with compaction-aware L1 (ON by default, --compact off to opt out), turns after the first omit unchanged untriggered rules unless @L1_REFRESH or a failure occurred
        quiet = agent_quiet(rules, briefs)
        compact_active = (not agent_mode()) and bool(CURRENT_SESSION) and compact_on()
        expected_tok = session_l1_token(rotate=False) if compact_active and before else ""
        proof_ok = bool(expected_tok and L1_PROOF == expected_tok)
        proof_failed = bool(compact_active and before and not L1_REFRESH and not brief_reason(["failed"]) and not proof_ok)
        compact_skip = set()
        if compact_active and before and proof_ok and not L1_REFRESH and not brief_reason(["failed"]):
            compact_skip = {tag for tag, _ in rules if tag not in changed and tag not in new and not (tag in briefs and brief_reason(briefs[tag][0]))}
        hidden, compact_hidden = 0, 0
        for tag, body in rules:
            mark = "[CHANGED] " if tag in changed else ("[NEW] " if tag in new else "")
            if tag in quiet and not mark:
                hidden += 1
                continue
            if tag in compact_skip and not mark:
                compact_hidden += 1
                continue
            if tag in briefs:
                why = brief_reason(briefs[tag][0])
                if not why:
                    print("%s%s (brief; full rule: @HELP %s) %s" % (mark, tag, tag.strip("[]"), briefs[tag][1].strip().strip("`").strip()))
                    continue
                print("%s%s (expanded: %s) %s" % (mark, tag, why, body.strip().strip("`").strip()))
                continue
            print("%s%s %s" % (mark, tag, body.strip().strip("`").strip()))
        if hidden:
            print("  (auto-shell turn: %d standing rule%s already in this prompt's briefing and unchanged, not repeated; @HELP L1-<name> prints one)" % (hidden, "" if hidden == 1 else "s"))
        if compact_active:
            if compact_hidden:
                print("[L1-Compact] %d unchanged standing rule%s omitted (proof %s verified; keep echoing @L1_PROOF %s, or send @L1_REFRESH after compaction)" % (compact_hidden, "" if compact_hidden == 1 else "s", expected_tok, expected_tok))
            else:
                new_tok = session_l1_token(rotate=True)
                if proof_failed:
                    print("[L1-Compact] proof missing or mismatched (possible compaction) -> full L1 restored (new proof: %s); echo @L1_PROOF %s on your next script" % (new_tok, new_tok))
                else:
                    print("[L1-Compact] full L1 printed (proof: %s); echo @L1_PROOF %s on your next script to keep compact mode, or send @L1_REFRESH after compaction" % (new_tok, new_tok))
            print("[L1-Syntax] @PROBE /file | Scope | symbol  |  @PROBE /tree | Tree | node | depth  |  @XREF symbol | callers")
    if state is not None:
        try:
            kb_hint()
        except Exception:
            pass
    used = set((load_json(sessions_path(), {}).get(CURRENT_SESSION) or {}).get("used", [])) if CURRENT_SESSION and state is not None else set()
    if used:
        rest = [d for d in DIRECTIVES.split() if d not in used and (d != "@ASK_USER" or auto_on()) and (d != "@MILESTONE" or is_borrower())]
        print("[L1-Commands] not used yet in this chat: %s | %d already used | full list: @HELP COMMANDS | syntax of any one: @HELP <name>" % (" ".join(rest) or "(none: every command has been used)", len(used)))
    else:
        print("[L1-Commands] " + " ".join(d for d in DIRECTIVES.split() if (d != "@ASK_USER" or auto_on()) and (d != "@MILESTONE" or is_borrower())) + " | syntax of any one: @HELP <name>")

def enter_workspace(path):
    """chdir into the project a script names. Returns an error message, or None on success."""
    if not path:
        return "missing '@WORKSPACE <project folder>' line -> add it as line 2 of the payload, exactly as shown in the SYNTAX CARD."
    full = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(full):
        return "workspace folder does not exist: %s" % full
    os.chdir(full)
    # Comment (invariant): a .git folder counts only with a HEAD inside it (or as a file, for a worktree); a folder holding only harness state is no repository, and every git command would fail in it
    set_mode("git" if os.path.isfile(os.path.join(".git", "HEAD")) or os.path.isfile(".git") else "nogit")
    return None

def set_mode(mode):
    """git mode keeps harness state in the checkout's git folder (llm_harness/), no-git mode in .llm_harness next to the notes. In a git worktree the numbering and its lock live in the repository's common git folder, shared by every worktree; sessions, scopes, the undo journal and saved runs stay with each worktree, because each has its own files."""
    global MODE, HARNESS_DIR, HISTORY_DIR, STATE_PATH, CONFIG_PATH, GRAPH_PATH, SHARED_DIR, GIT_DIR
    MODE = mode
    GIT_DIR, common = ".git", ".git"
    if mode == "git":
        try:
            out = subprocess.run(["git", "rev-parse", "--git-dir", "--git-common-dir"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20).stdout.decode("utf-8", "replace").split()
            if len(out) == 2:
                GIT_DIR, common = out
        except (OSError, subprocess.SubprocessError):
            pass
    HARNESS_DIR = os.path.join(GIT_DIR, "llm_harness") if mode == "git" else WORKSPACE_NOTES_DIR
    SHARED_DIR = os.path.join(common, "llm_harness") if mode == "git" else WORKSPACE_NOTES_DIR
    HISTORY_DIR = os.path.join(HARNESS_DIR, "history")
    STATE_PATH = os.path.join(SHARED_DIR, "state.json")
    CONFIG_PATH = os.path.join(HARNESS_DIR, "config.json")
    GRAPH_PATH = os.path.join(HARNESS_DIR, "graph.json")

def mode_label():
    if MODE != "git":
        return "no-git mode (state in .llm_harness/, git directives off)"
    if os.path.normcase(os.path.abspath(HARNESS_DIR)) != os.path.normcase(os.path.abspath(SHARED_DIR)):
        return "git mode, worktree (script numbers shared with the main checkout; sessions, scopes and undo are this folder's own)"
    return "git mode"


NOTE_HEADER_RE = re.compile(r"^<!-- llm_harness_notes_next_id: (\d+) -->$")
NOTE_ENTRY_RE = re.compile(r"^- \[(N\d+)\] (.+)$")


def note_audience(arg):
    """'pin <session>, <pattern> | <text>' -> ([sessions or patterns], text, False); 'own | <text>' -> (None, text, True), the running chat's own to-do, pinned to it when the note is written; plain text -> (None, text, False), a note for every chat."""
    own = re.match(r"^own\s*\|\s*(.+)$", arg.strip(), re.IGNORECASE)
    if own:
        return None, own.group(1).strip(), True
    m = re.match(r"^(?:pin|for)\s+([^|]+)\|\s*(.+)$", arg.strip(), re.IGNORECASE)
    if not m:
        return None, arg.strip(), False
    return [x.strip() for x in m.group(1).split(",") if x.strip()], m.group(2).strip(), False

def brief_text(note):
    """A note's footer text: the part before ' || ' with a pointer to @NOTE_LIST <id> for the rest; a note without ' || ' prints in full."""
    head, sep, _ = note["text"].partition(" || ")
    return (head.strip() + " (more: @NOTE_LIST %s)" % note["id"]) if sep else note["text"]

def note_mark(note):
    """The tag written before a note's text: [own: <session>] for a chat's own to-do, [pin: <names>] for a note pinned to chats, nothing for a note for every chat."""
    if not note.get("for"):
        return ""
    return "[%s: %s] " % ("own" if note.get("own") else "pin", ", ".join(note["for"]))

def note_for(note, session):
    """True when a note is for every chat, or names this chat (patterns like migration-* allowed)."""
    who = note.get("for")
    return not who or bool(session) and any(fnmatch.fnmatchcase(session.lower(), w.lower()) for w in who)

def load_workspace_notes():
    """Load (notes, next_id); refuse to overwrite a manually damaged notes file."""
    if not os.path.isfile(WORKSPACE_NOTES_PATH):
        return [], 1

    with open(WORKSPACE_NOTES_PATH, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    next_id, notes, seen = 1, [], set()
    for line in lines:
        header = NOTE_HEADER_RE.fullmatch(line)
        if header:
            next_id = max(next_id, int(header.group(1)))
            continue
        if not line.strip():
            continue
        entry = NOTE_ENTRY_RE.fullmatch(line)
        if not entry:
            raise ValueError("unrecognized line in notes.md; refusing to overwrite it: %s" % line[:100])
        note_id, text = entry.group(1).upper(), entry.group(2)
        if note_id in seen:
            raise ValueError("duplicate note ID in notes.md: %s" % note_id)
        seen.add(note_id)
        fm = re.match(r"^\[(pin|for|own): ([^\]]+)\] (.+)$", text)
        notes.append({"id": note_id, "text": fm.group(3) if fm else text, "for": [x.strip() for x in fm.group(2).split(",") if x.strip()] if fm else None, "own": bool(fm) and fm.group(1) == "own"})
        next_id = max(next_id, int(note_id[1:]) + 1)
    return notes, next_id


def write_workspace_notes(notes, next_id):
    """Atomically persist notes while retaining the next ID after removals."""
    os.makedirs(WORKSPACE_NOTES_DIR, exist_ok=True)
    tmp = WORKSPACE_NOTES_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write("<!-- llm_harness_notes_next_id: %d -->\n" % next_id)
            for note in notes:
                f.write("- [%s] %s%s\n" % (note["id"], note_mark(note), note["text"]))
        os.replace(tmp, WORKSPACE_NOTES_PATH)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def print_workspace_notes(query=None):
    """Print the workspace's notes; a search keeps notes whose category, pins or text contain every word of it (case-insensitive)."""
    try:
        notes, _ = load_workspace_notes()
    except (OSError, ValueError) as exc:
        print("WARNING: could not read workspace notes: %s" % exc)
        return

    words = (query or "").lower().split()
    if len(words) == 1 and re.fullmatch(r"n\d+", words[0]):
        notes = [n for n in notes if n["id"].lower() == words[0]]
    elif words:
        notes = [n for n in notes if all(w in ("%s %s" % (" ".join(n.get("for") or []), n["text"])).lower() for w in words)]
    print("=== WORKSPACE NOTES%s ===" % (" matching '%s'" % query.strip() if words else ""))
    if not notes:
        print("(none)")
        return
    for note in notes:
        print("  [%s] %s%s" % (note["id"], note_mark(note), note["text"]))


def execute_note_ops(ops):
    """Apply note commands and print confirmation plus the resulting workspace notes."""
    for op in ops:
        try:
            notes, next_id = load_workspace_notes()
            action = op["action"]

            if action == "list":
                print_workspace_notes(op.get("query"))
                continue

            if action == "add":
                who = op.get("for")
                if op.get("own"):
                    if not CURRENT_SESSION:
                        print("  [NOTE ERROR] @NOTE_ADD own needs the script's @SESSION line: the note belongs to that chat")
                        continue
                    who = [CURRENT_SESSION]
                note_id = "N%03d" % next_id
                notes.append({"id": note_id, "text": op["text"], "for": who, "own": bool(op.get("own"))})
                write_workspace_notes(notes, next_id + 1)
                print("  [NOTE ADDED] %s" % note_id)

            elif action == "edit":
                found = next((n for n in notes if n["id"] == op["id"]), None)
                if found is None:
                    print("  [NOTE ERROR] note ID not found: %s" % op["id"])
                    continue
                found["text"] = op["text"]
                if op.get("own"):
                    if not CURRENT_SESSION:
                        print("  [NOTE ERROR] @NOTE_EDIT ... own needs the script's @SESSION line: the note belongs to that chat")
                        continue
                    found["for"], found["own"] = [CURRENT_SESSION], True
                elif op.get("for") is not None:
                    found["for"], found["own"] = op["for"], False
                write_workspace_notes(notes, next_id)
                print("  [NOTE EDITED] %s" % op["id"])

            elif action == "pin":
                found = next((n for n in notes if n["id"] == op["id"]), None)
                if found is None:
                    print("  [NOTE ERROR] note ID not found: %s" % op["id"])
                    continue
                aud = re.sub(r"(?i)^(pin|for)\s+", "", op["aud"].strip())
                low = aud.lower()
                if low in ("all", "plain", "none"):
                    found["for"], found["own"] = None, False
                    shown = "every chat, and runs without a session"
                elif low == "own":
                    if not CURRENT_SESSION:
                        print("  [NOTE ERROR] @NOTE_PIN ... own needs the script's @SESSION line: the note belongs to that chat")
                        continue
                    found["for"], found["own"] = [CURRENT_SESSION], True
                    shown = "this chat's own to-do"
                elif low in ("current", "now", "existing"):
                    # Comment (decision): a snapshot of the registered session names, so chats that appear later do not get the note; the opposite is * (every chat with a session, new ones too), and @NOTE_PIN switches between the two without touching the text
                    names = sorted(load_json(sessions_path(), {}))
                    if not names:
                        print("  [NOTE ERROR] @NOTE_PIN current needs at least one registered session; none exists yet")
                        continue
                    found["for"], found["own"] = names, False
                    shown = "the %d chat(s) that exist now (%s), not chats that appear later" % (len(names), ", ".join(names))
                else:
                    names = [x.strip() for x in aud.split(",") if x.strip()]
                    if not names:
                        print("  [NOTE ERROR] @NOTE_PIN needs *, chat names, all or own")
                        continue
                    found["for"], found["own"] = names, False
                    shown = "every chat with a session, new ones too" if names == ["*"] else ", ".join(names)
                write_workspace_notes(notes, next_id)
                print("  [NOTE PINNED] %s -> %s" % (op["id"], shown))

            elif action == "brief":
                found = next((n for n in notes if n["id"] == op["id"]), None)
                if found is None:
                    print("  [NOTE ERROR] note ID not found: %s" % op["id"])
                    continue
                if " || " in op["short"] or not op["short"]:
                    print("  [NOTE ERROR] the short text must be non-empty and must not contain ' || '")
                    continue
                # Comment (decision): the existing text is kept whole behind the new short part (an old short part is replaced), so briefing a long note never means retyping it; audience, pin and own mark are untouched
                full = found["text"].split(" || ", 1)[1] if " || " in found["text"] else found["text"]
                found["text"] = op["short"] + " || " + full
                write_workspace_notes(notes, next_id)
                print("  [NOTE BRIEFED] %s" % op["id"])

            elif action == "remove":
                kept = [n for n in notes if n["id"] != op["id"]]
                if len(kept) == len(notes):
                    print("  [NOTE ERROR] note ID not found: %s" % op["id"])
                    continue
                write_workspace_notes(kept, next_id)
                print("  [NOTE REMOVED] %s" % op["id"])

        except (OSError, ValueError) as exc:
            print("  [NOTE ERROR] %s" % exc)

def harness_call(shell):
    """How a script invokes this file from any folder, in the user's shell."""
    home = os.path.expanduser("~")
    inside = SELF_PATH.startswith(home + os.sep)
    tail = SELF_PATH[len(home) + 1:]
    if shell == "powershell":
        return 'python "%s"' % (("$HOME\\" + tail.replace("/", "\\")) if inside else SELF_PATH)
    return "python3 %s" % (("~/" + tail.replace(os.sep, "/")) if inside and " " not in tail else "'%s'" % SELF_PATH)

GIT_CARD = """  @GIT_STATUS
  @GIT_COMMIT <type(scope): subject>  /<path> per line  @END_GIT_COMMIT   commits exactly those paths (list deleted and renamed-from paths too); the message must be type(scope): subject with a conventional type (feat fix docs refactor perf build test ci chore style revert); an optional .llm_harness/git.json ({"version": 1, "protected": [...], "branches": "<regex>", "header_max": 100, "commit_types": [...]}) refuses commits on protected branches
  @GIT_FOLD <n>                                   first git line only: reopens the last n unpushed commits so the @GIT_COMMIT blocks after it re-slice them
  @GIT_BRANCH <name> [from <base>]                switches to a branch, or creates it (from <base>, default the current one); refused with local changes, an unfinished git operation, or other chats active in this checkout
  @GIT_WORKTREE add <branch> [from <base>] | list | remove <branch or path>   a separate folder per branch (../<project>.<branch>) so chats on different branches never share files; continue there with @WORKSPACE <path>
  @GIT_TAG <vX.Y.Z> [| <message>]                 annotated release tag on a clean checkout; git.json may require "tags_from": "main" (commit must be in main's history) and "tag_changelog": true
  @GIT_PUSH [tag <name>]                          publishes the current branch's commits to its upstream (origin the first time), or one tag; never forced, never a protected branch (git.json); a rejected push is reported, not overridden
  @GIT_PULL                                       fast-forwards a clean checkout to its upstream (bookmarking where it was); when the branches have diverged it only reports whether a merge would conflict, and changes nothing. The footer's UPSTREAM line says what is incoming
  @GIT_MERGE [<ref> | --continue | --abort]       merges <ref> (default @{u}) into the current branch with a backup bookmark and tokens.json parking; stops cleanly on conflicts listing conflicted files so hunks can resolve them; --continue finishes the merge commit, --abort restores pre-merge state
  @GIT_ACCOUNT [<account> | clear]                lists the accounts signed in for this remote's host (GitHub through Git Credential Manager, else the gh CLI, whose active account is then switched too) and, at a terminal, lets the user press a number to pin one for this project, or A to sign in another account first; '@GIT_ACCOUNT <account>' pins by name, 'clear' removes the pin (kept in this clone's git config, so git stops asking which account)
  @GIT_REMOTE [<name> [<url>]]                    lists the remotes, shows one, or adds it / changes its address (an https:// or ssh address with no password or token in it; a remote is never removed or renamed); '@GIT_REMOTE origin <url>' prints the old and the new address, and @GIT_PUSH then publishes there
"""

def print_languages():
    """@HELP LANGUAGES: what the harness does for each kind of file, generated from the tables the code itself uses so the two cannot disagree."""
    marks = {}
    for ext in sorted(HDR_PREFIX):
        key = HDR_PREFIX[ext].strip() + ((" ... " + HDR_SUFFIX[ext].strip()) if ext in HDR_SUFFIX else "")
        marks.setdefault(key, []).append(ext)
    print("\n=== HELP: LANGUAGES ===")
    print("  every file: hunks, text replacements, line edits, scopes, undo and git work byte for byte (BOM and line endings kept)")
    print("  the marker for 'Comment' lines and the first-line header, by extension:")
    for key in sorted(marks):
        print("    %-12s %s" % (key, " ".join(marks[key])))
    print("  the header goes below a shebang, a Python coding line, an HTML doctype, an XML declaration or PHP's opening tag; other file types (json, md ...) get none")
    print("  symbols for @SCOPE file#Class.method, @XREF and @PROBE | Unused: %s" % " ".join(CODE_EXTS))
    print("  syntax check with rollback: Python (compile) and Go (gofmt); other languages are not compiled unless you set your own check command (the user's terminal command --check <.ext> <command>); otherwise build or test them with @RUN")

KB_FIELDS = ("tags", "symptom", "trap", "fix", "verified", "versions", "replaces", "obsolete")

def knowledge_dir():
    """The knowledge library: the 'knowledge' folder next to the running harness.py (LLM_HARNESS_KNOWLEDGE overrides it for tests)."""
    return os.environ.get("LLM_HARNESS_KNOWLEDGE") or os.path.join(os.path.dirname(os.path.abspath(SELF_PATH)), "knowledge")

def kb_entries(folder=None):
    """[{tech, id, file, detect, <fields>}] from the knowledge files. A file may start with '# tech: <name>' (default: the file name) and '# detect: <words>' (how to tell that a project uses the technology, see kb_active); an entry starts with '## <id>' and continues with 'key: value' lines (keys in KB_FIELDS); a line indented by two spaces continues the previous value."""
    folder, out = folder or knowledge_dir(), []
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(".txt"))
    except OSError:
        return out
    for name in names:
        try:
            with open(os.path.join(folder, name), "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        tech, detect, cur, key = os.path.splitext(name)[0], [], None, None
        for line in text.split("\n"):
            line = line.rstrip("\r")
            m = re.match(r"^#\s*tech:\s*(\S.*)$", line)
            if m:
                tech = m.group(1).strip()
                continue
            m = re.match(r"^#\s*detect:\s*(\S.*)$", line)
            if m:
                detect = [w.strip().lower() for w in m.group(1).split(",") if w.strip()]
                continue
            m = re.match(r"^##\s+(\S+)\s*$", line)
            if m:
                cur, key = {"tech": tech, "id": m.group(1), "file": name, "detect": detect}, None
                out.append(cur)
                continue
            if cur is None:
                continue
            m = re.match(r"^([a-z-]+):\s*(.*)$", line)
            if m and m.group(1) in KB_FIELDS:
                key = m.group(1)
                cur[key] = m.group(2).strip()
            elif key and line.startswith("  ") and line.strip():
                cur[key] += " " + line.strip()
    return out

def kb_lint(entries):
    """Problems in a library: an entry without symptom, trap, fix or verified, a repeated id, a replaces or obsolete note that names an id that does not exist."""
    ids, bad = {}, []
    for e in entries:
        ids[e["id"]] = ids.get(e["id"], 0) + 1
    for e in entries:
        miss = [k for k in ("tags", "symptom", "trap", "fix", "verified") if not e.get(k)]
        if miss:
            bad.append("%s: missing %s" % (e["id"], ", ".join(miss)))
        if ids[e["id"]] > 1:
            bad.append("%s: id used %d times" % (e["id"], ids[e["id"]]))
        for k in ("replaces", "obsolete"):
            for ref in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)+", e.get(k) or ""):
                if ref not in ids:
                    bad.append("%s: %s names an unknown entry %s" % (e["id"], k, ref))
    return bad

KB_SKIP_DIRS = {"node_modules", "venv", "__pycache__", "dist", "build", "target", "bin", "obj", "Library", "Temp", "Packages"}
KB_MANIFESTS = {"package.json", "go.mod", "cargo.toml", "pom.xml", "pyproject.toml", "pipfile", "setup.py", "setup.cfg", "composer.json", "gemfile", "build.gradle", "build.gradle.kts", "environment.yml"}
KB_CODE_EXTS = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".go", ".rs", ".cs", ".java", ".kt", ".php", ".c", ".h", ".cpp", ".hpp")

def kb_project_facts(root="."):
    """What the project itself says it uses: (extensions, file names, manifests, imports); manifests are (path, lower-case text) pairs and imports (path, line) pairs, so a reason can name the file. A bounded walk: dependency, build and hidden folders are skipped, at most 3000 files, 300 code files (their first 120 lines) and manifests up to 200 KB; in a .csproj or .fsproj only the PackageReference lines count."""
    exts, names, manifests, imports, seen, code = set(), set(), [], [], 0, 0
    for dirpath, dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        dirs[:] = [d for d in dirs if d not in KB_SKIP_DIRS and not d.startswith(".")] if rel.count(os.sep) < 3 else []
        for fn in files:
            seen += 1
            if seen > 3000:
                break
            low, path = fn.lower(), os.path.join(dirpath, fn)
            ext, shown = os.path.splitext(low)[1], os.path.relpath(path, root).replace(os.sep, "/")
            names.add(low)
            if ext:
                exts.add(ext)
            try:
                if low.startswith("requirements") or low in KB_MANIFESTS or ext in (".csproj", ".fsproj"):
                    if os.path.getsize(path) <= 200000:
                        with open(path, "r", encoding="utf-8", errors="replace") as f:
                            body = f.read().lower()
                        if ext in (".csproj", ".fsproj"):
                            # Comment (constraint): a generated project file (Unity's lists the engine's assemblies) can name libraries the project never uses; only its PackageReference lines declare what it depends on
                            body = "\n".join(line for line in body.split("\n") if "packagereference" in line)
                        manifests.append((shown, body))
                elif ext in KB_CODE_EXTS and code < 300:
                    code += 1
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        for _, line in zip(range(120), f):
                            s = line.strip().lower()
                            if s.startswith(("import ", "from ", "using ", "use ", "#include", "require", "const ", "package ", "@import")) or "require(" in s:
                                imports.append((shown, s))
            except OSError:
                continue
        if seen > 3000:
            break
    return exts, names, manifests, imports

def kb_active(entries, facts=None):
    """{technology: why} for the technologies this project seems to use. The words of a file's '# detect:' line mean: '*' always; '*.ext' a file with that extension; a file name, that file is present; any other word, a dependency name found in a manifest or an import line (the reason names that file)."""
    exts, names, manifests, imports = facts or kb_project_facts()
    words, active = {}, {}
    for e in entries:
        words.setdefault(e["tech"], set()).update(e.get("detect") or [])
    for tech, ws in words.items():
        for w in sorted(ws):
            why = None
            if w == "*":
                why = "every project"
            elif w.startswith("*."):
                why = ("a %s file" % w[1:]) if w[1:] in exts else None
            elif w in names:
                why = "file %s" % w
            else:
                pat = re.compile(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])")
                hit = next((p for p, body in manifests if pat.search(body)), None)
                if hit:
                    why = "'%s' in %s" % (w, hit)
                else:
                    hit = next((p for p, line in imports if pat.search(line)), None)
                    if hit:
                        why = "'%s' imported in %s" % (w, hit)
            if why:
                active[tech] = why
                break
    return active

def kb_hint():
    """One footer line naming the library's technologies this project seems to use: printed the first time in a chat and again only when that list changes (remembered per chat in a small machine-local file), so the AI knows what is on file without a search."""
    entries = kb_entries()
    active = sorted(kb_active(entries)) if entries else []
    if not active:
        return
    path = os.path.join(SHARED_DIR, "kb_hint.json")
    seen, key = load_json(path, {}) or {}, CURRENT_SESSION or "-"
    if seen.get(key) == active:
        return
    seen[key] = active
    save_json(path, seen)
    print("[KNOWLEDGE] pitfalls on file for what this project uses: %s | search: @KB <technology or symptom words>" % ", ".join(active))

def kb_stems(word):
    """The word and what it may be the plural of (freezes -> freeze, freez), so a plural finds its singular."""
    out = {word}
    if len(word) > 3 and word.endswith("s"):
        out.add(word[:-1])
    if len(word) > 4 and word.endswith("es"):
        out.add(word[:-2])
    return out

KB_STOP = {"a", "an", "the", "of", "in", "on", "at", "to", "from", "for", "with", "and", "or", "is", "are", "it", "my", "when", "how", "why", "what", "after", "before", "every", "each", "by", "as", "be", "not", "do", "does", "i", "out", "into", "this", "that"}

def kb_rank(words, entries, active):
    """([entries], hidden): the entries that match the words, best first. A word is a strong match when it names the entry's technology, is one of its tags or is part of its id, and a weak one when it appears in a tag phrase or in its symptom, trap or fix. An entry qualifies with one strong match or two matched words, and only when it covers at least 70% as much of the question as the best entry does, so one common word never pulls in unrelated entries. A technology the project does not seem to use is shown only when the words name it or include 'all'; hidden counts the matches left out for that reason. Retired entries need the word 'obsolete'."""
    toks = [w for w in re.split(r"[^\w.+#-]+", words.lower()) if w and w not in KB_STOP]
    old, every = "obsolete" in toks, "all" in toks
    toks = [t for t in toks if t not in ("obsolete", "all")]
    found = []
    for e in entries:
        if e.get("obsolete") and not old:
            continue
        tech = e["tech"].lower()
        tech_words = {tech} | {w for w in re.split(r"[-_ ]+", tech) if len(w) >= 3 and w not in ("python", "core", "api", "lang", "client", "sdk")}
        full, sub = set(), set()
        for tag in (e.get("tags") or "").lower().split(","):
            tag = tag.strip()
            if tag:
                full.update(kb_stems(tag))
                for w in re.split(r"[-_ ]+", tag):
                    if len(w) >= 3:
                        sub.update(kb_stems(w))
        text = set()
        for w in re.findall(r"[\w.+#-]+", " ".join(e.get(k) or "" for k in ("symptom", "trap", "fix")).lower()):
            text.update(kb_stems(w))
        ident, strong, weak = e["id"].lower(), set(), set()
        for t in toks:
            ts = kb_stems(t)
            if t in tech_words or ts & full or (len(t) >= 4 and t in ident):
                strong.add(t)
            elif len(t) >= 4 and (ts & sub or ts & text):
                weak.add(t)
        if strong or len(weak) >= 2:
            found.append((e, strong, weak, any(t in tech_words for t in strong)))
    if not found:
        return [], 0
    cover = lambda x: len(x[1]) + len(x[2])
    top = max(cover(x) for x in found)
    scored, hidden = [], 0
    for e, strong, weak, named in found:
        if cover((e, strong, weak)) * 10 < top * 7:
            continue
        if not every and e["tech"] not in active and not named:
            hidden += 1
            continue
        scored.append((-(3 * len(strong) + len(weak) + (1 if e["tech"] in active else 0)), e["tech"], e["id"], e))
    return [s[3] for s in sorted(scored, key=lambda s: s[:3])], hidden

def print_kb(words):
    """@HELP KB [<technology or symptom words>]: without words, the technologies in the library and which of them this project seems to use; with words, the best matching entries of those technologies (at most 6, about 5000 characters), the rest as ids."""
    entries = kb_entries()
    print("\n=== KNOWLEDGE ===")
    if not entries:
        print("  no knowledge library is installed here (the knowledge folder next to harness.py is missing or empty); run setup again from an up-to-date copy of the harness")
        return
    techs = {}
    for e in entries:
        techs.setdefault(e["tech"], []).append(e)
    active = kb_active(entries)
    if not words.strip():
        print("  pitfalls that AIs keep falling into, by technology; search with @HELP KB <technology or symptom words> (add the word all to include technologies this project does not use, obsolete for retired entries):")
        for t in sorted(techs):
            print("    %-22s %d entr%s%s" % (t, len(techs[t]), "y" if len(techs[t]) == 1 else "ies", ("   [used here: %s]" % active[t]) if t in active else ""))
        return
    hits, hidden = kb_rank(words, entries, active)
    other = ("  (%d more match%s in technologies this project does not seem to use; add the word all to include %s)" % (hidden, "" if hidden == 1 else "es", "it" if hidden == 1 else "them")) if hidden else ""
    if not hits:
        print("  nothing matches '%s'. technologies: %s" % (words.strip(), ", ".join(sorted(techs))))
        if other:
            print(other)
        return
    used, shown = 0, 0
    for e in hits:
        lines = ["  [%s] %s%s" % (e["tech"], e["id"], "   (OBSOLETE: %s)" % e["obsolete"] if e.get("obsolete") else "")]
        lines += ["    %s: %s" % (k, e[k]) for k in ("symptom", "trap", "fix", "versions", "verified") if e.get(k)]
        block = "\n".join(lines)
        if shown >= 6 or (shown and used + len(block) > 5000):
            break
        print(block)
        used, shown = used + len(block), shown + 1
    if len(hits) > shown:
        print("  (%d more match: %s; narrow the words to see them)" % (len(hits) - shown, ", ".join(e["id"] for e in hits[shown:shown + 12])))
    if other:
        print(other)

def playbooks_dir():
    """The playbooks: the 'playbooks' folder next to the running harness.py (LLM_HARNESS_PLAYBOOKS overrides it for tests)."""
    return os.environ.get("LLM_HARNESS_PLAYBOOKS") or os.path.join(os.path.dirname(os.path.abspath(SELF_PATH)), "playbooks")

def playbook_files():
    """{name: text} for every playbooks/<name>.txt, without the automatic first-line header."""
    out, folder = {}, playbooks_dir()
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(".txt"))
    except OSError:
        return out
    for n in names:
        try:
            with open(os.path.join(folder, n), "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().replace("\r", "").split("\n")
        except OSError:
            continue
        if lines and re.match(r"^#\s*/\S+", lines[0]):
            lines = lines[1:]
        out[os.path.splitext(n)[0]] = "\n".join(lines).strip("\n")
    return out

def print_playbook(name):
    """@PLAYBOOK [<name>]: without a name, the playbooks and when to use each; with a name, its steps."""
    books = playbook_files()
    print("\n=== PLAYBOOK ===")
    if not books:
        print("  no playbooks are installed here (the playbooks folder next to harness.py is missing or empty); run setup again from an up-to-date copy of the harness")
        return
    key = name.strip().lower()
    if key in books:
        print(books[key])
        return
    if key:
        print("  no playbook named '%s'." % key)
    print("  playbooks (open one with @PLAYBOOK <name>):")
    for n, text in books.items():
        m = re.search(r"(?m)^#\s*use when:\s*(.*)$", text)
        print("    %-14s %s" % (n, m.group(1).strip() if m else ""))

def sessions_listing():
    """@SESSIONS: every session of this project with its aim, write scope, last script and chat address (the footer shows only a count of the others)."""
    print("\n=== SESSIONS ===")
    if not load_json(sessions_path(), {}):
        print("  no sessions yet in this project")
        return
    print_sessions(CURRENT_SESSION, full=True)

def history_listing(arg):
    """@HISTORY <session> [| files] [| n]: read-only list of a session's recent journaled scripts."""
    parts = [p.strip() for p in arg.split("|") if p.strip()]
    session = parts[0] if parts else (CURRENT_SESSION or "")
    show_files, limit = False, 10
    for p in parts[1:]:
        if p.lower() == "files":
            show_files = True
        elif p.isdigit() and int(p) > 0:
            limit = int(p)
    if not session:
        print("\n=== HISTORY ===\n  expected '@HISTORY <session> [| files] [| n]'")
        return
    print("\n=== HISTORY: %s ===" % session)
    shown = 0
    for hp in sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")), reverse=True):
        rec = load_json(hp, None)
        if not rec or (rec.get("session") or "") != session:
            continue
        files = rec.get("files") or {}
        if files and all(f.get("undone") for f in files.values()):
            st = "undone"
        elif files and any(f.get("undone") for f in files.values()):
            st = "partially undone"
        else:
            st = "applied"
        try:
            secs = max(0, int(time.time() - os.path.getmtime(hp)))
        except OSError:
            secs = 0
        age = ("%dm ago" % (secs // 60)) if secs < 3600 else ("%dh ago" % (secs // 3600)) if secs < 86400 else ("%dd ago" % (secs // 86400))
        print("  %s | %s | %s | %s" % (rec.get("id") or "?", rec.get("title") or "", age, st))
        if show_files and files:
            print("    files: %s" % ", ".join(sorted(files.keys())))
        shown += 1
        if shown >= limit:
            break
    if not shown:
        print("  no journaled scripts for session '%s' (pure reads are not journaled)" % session)

def print_help(name, shell):
    """@HELP <directive>: the syntax-card lines for one directive, taken from the card itself so the two never disagree."""
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_card(shell, os.path.abspath("."))
    key = "@" + name.strip().lstrip("@").upper()
    kb = re.match(r"(?is)^@?kb(?:\s+(.*))?$", name.strip())
    if kb:
        print_kb(kb.group(1) or "")
        return
    pb = re.match(r"(?is)^@?playbook(?:\s+(.*))?$", name.strip())
    if pb:
        print_playbook(pb.group(1) or "")
        return
    if re.match(r"(?is)^@?sessions\s*$", name.strip()):
        sessions_listing()
        return
    hi = re.match(r"(?is)^@?history(?:\s+(.*))?$", name.strip())
    if hi:
        history_listing(hi.group(1) or "")
        return
    if key.startswith("@L1-"):
        try:
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                hits = [(t, b) for t, _, b in re.findall(r"(?m)^- \*\*L1 Rule\W*(\[[^\]]+\])`?\s*(?:\(([\w-]+)\))?[`:*\s]*(.*)$", f.read()) if t.strip("[]").upper() == key[1:]]
        except OSError:
            hits = []
        print("\n=== HELP: %s (full rule) ===" % key[1:])
        print("  " + (hits[0][1].strip().strip("`").strip() if hits else "no such rule in workflow_commands.txt"))
        return
    if key == "@LANGUAGES":
        print_languages()
        return
    if key == "@COMMANDS":
        print("\n=== HELP: all commands ===\n  " + " ".join(DIRECTIVES.split()) + "\n  syntax of any one: @HELP <name>")
        return
    out, keep = [], False
    for ln in buf.getvalue().split("\n"):
        s = ln.strip()
        if s.startswith("@"):
            keep = re.search(r"(?<![\w@])" + re.escape(key) + r"(?!\w)", ln) is not None
        elif not ln.startswith("  "):
            keep = False
        if keep:
            out.append(ln)
    print("\n=== HELP: %s ===" % key)
    print("\n".join(out) if out else "  no directive named %s in this workspace's mode -> see [L1-Commands] in the footer" % key)

def print_card(shell, workspace):
    """The whole payload grammar, printed once per session by the handshake."""
    call = harness_call(shell)
    print("=== SYNTAX CARD (shown once per session; everything else is explained by harness output when it happens) ===")
    print("Wrap every script in one code fence, exactly like this:")
    if shell == "powershell":
        print("  $OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); @'")
    else:
        print("  %s << 'HARNESS_EOF'" % call)
    print("  @SCRIPT [<ACT>: <short title>]                 no number: the harness assigns one and prints [ASSIGNED]")
    print("  @SESSION <short name> | <this chat's own aim>   the same line on every script of this chat")
    print("  @SCOPE <aim> | <path or glob>, ...              (optional) the files this session will change; an overlap with another session's scope is refused")
    print("  @WORKSPACE %s" % workspace)
    print("  <directives>")
    if shell == "powershell":
        print("  '@ | %s" % call)
        print("No payload line may begin with '@.")
    else:
        print("  # ---\n  # ---\n  # ---\n  HARNESS_EOF")
        print("At most 120 payload lines per script and nothing after HARNESS_EOF (serial/SSH paste safety); split larger changes into consecutive numbers.")
    print("""Directives:
  @GOAL <text>                                    pins the user's long-term goal in .llm_harness/goal.md (travels with the project); every run prints it in the footer
  @SIDE                                           runs the script outside the numbering (its @SCRIPT needs no number; only reads, searches and @RUN), so a second chat can work in a project another chat drives; an identical re-paste replays
  @REPEATABLE                                     the script runs on every paste, also an identical one, so the user can rerun it or edit its values by hand (no number; only reads, searches and @RUN)
  @PART <i>/<n>                                   one of n scripts sent in the same reply (e.g. a long @RUN kept apart from many probes); only part n prints the goal, notes and standing rules
  @VERDICT <folder, file or file#Class.method> | <verdict> | <note>   a conclusion about that area, kept in .llm_harness/verdicts.json (travels with git); later changes there mark it STALE; each chat keeps its own verdict on a path; '| clear' removes this chat's
  @VERDICTS [all | stale | session <name>]       lists verdicts with the tree's description; a folder verdict hides children that say the same (default: this session's)
  @CAMPAIGN <name> | <word> = <meaning>; ...      starts a sweep (only when the user asks): its verdict words, a footer line and the [L1-Campaign] rule while it runs; Tree probes show <<verdict: ...>> on marked nodes
  @CAMPAIGN_END <name>                            ends the sweep and removes every verdict it recorded
  @SCOPE <aim> | <path or glob>, ...              declares or changes this session's write scope; other sessions are told once; their scopes are refused to this session's file changes
  (a scope entry may be file#Class.method, file#Class.method > # Stage: Name, file## Stage: Name or tree_file#Node > Path, claiming only that part so others can still edit the rest of the file, or end with ' depth N')
  @SCOPE_END    @SESSION_END                      release this session's scope / end the session; refused while its changes are uncommitted, unless followed by 'handover'; @SESSION_END also waits for blocked work listed under WAITING ON, unless followed by 'drop'
  @MESSAGE <session | *> | <text>                 sends a tracked message (M-###, idempotent on replay) to one session or broadcasts to all active sessions with '*'; receipts track queued -> delivered -> ack -> accepted/rejected -> completed
  @MSG_ACK <id> [| ack|accept|reject|done] [| <note>]   records an explicit receipt for message <id> (default: ack)
  @WAIT_MSG <id> [| delivered|ack|accepted|done] [| <sec>]   auto-shell only: waits up to 90s (default) for <id> to reach the target receipt state
  @PING                                           lightweight message & receipt check (works with @REPEATABLE; suppresses L1 footer when run alone)
  @SESSIONS                                       lists every session with its aim, write scope and chat address (the footer shows only a count of the others unless this chat is waiting, delegated or braked)
  @HISTORY <session> [| files] [| n]              read-only list of a session's recent journaled scripts (id, title, age, status; '| files' adds changed paths; default 10)
  @L1_REFRESH                                     prints the full L1 standing rules on this run (use after chat compaction when compaction-aware L1 is on)
  @L1_PROOF <token>                               echoes the rotating 6-hex proof token from [L1-Compact] so the harness verifies L1 is still in context (missing/wrong proof auto-restores full L1)
  @SCOPE_REQUEST <session> | <paths> | <reason>   asks that session to give up those paths; only its owner or the user can
  @DELEGATE <session> | <paths> | <task>          hands those files (entries of your scope) and a task to that session at once, with your uncommitted work in them; its footer says INHERITED
  @SPLIT <name> | <aim> | <paths> | <brief>       sets up an UNCLAIMED session for a new chat and hands it those files the way @DELEGATE does, with the waits on them (leave <paths> empty for a session with no files); the brief (goal, decisions, what is done, code locations, what is left) prints once when a chat claims it with @SESSION <name>
  @RETURN <session> | <result>                    hands back what that session delegated to you: the files are released, the result goes to it as a note
  @BRAKE <session> | <reason>    @BRAKE_ACK       pause another session's changes until it acknowledges / acknowledge a brake on this session
  @CHAT_LINK [<address>]                          asks the user at the terminal for this chat's address (or sets it when given), replacing any old address on file; at a terminal a new session is asked once and cannot skip it
  @STEWARD [on | off]                             asks the user at the terminal to switch the opt-in backlog-and-review rule (the footer's [L1-Steward]) on or off for this project on this machine: one question, Enter agrees, and with no terminal, or in a @SIDE or @REPEATABLE script, nothing changes; alone it reports the state
  @TAKEOVER <session>                             asks the user at the terminal to let this chat take over what another chat holds (its write scope, grants, notes, verdicts, queues and unread messages), the same as the user's --merge: one question, Enter agrees, and with no terminal, or in a @SIDE or @REPEATABLE script, nothing changes; use it to continue a dead or finished chat's work
  @BORROW <session>                               asks the user at the terminal to lend that session's work to this chat, which keeps its own name and files (or to move an existing loan of it here); the work stays that session's: @RETURN <session> | <result> puts it back in its scope
  @RECLAIM                                        the owner of lent work asks for it back: Enter takes it now with the holder's uncommitted changes, n only asks the holder to return it; after a loan returns, @UNDO of a borrower's script on that work asks the user too
  @UNCLAIM <brief>                                hands this chat's own session to the next chat: it becomes UNCLAIMED with the brief and keeps its files, uncommitted work, notes and messages; the next chat claims it with @SESSION <name>; send nothing more under that name
  @GUIDE [off]                                    makes this session the project's guide (one at a time, optional): it claims only docs/, never code, and every other chat's footer names it for cross-worker, architecture, data-ownership and direction questions; @GUIDE off ends the role
  @NOTE_ADD <text>                                adds a persistent workspace note; '@NOTE_ADD pin <session>, <pattern> | <text>' pins it to those chats' footers only (patterns like migration-*; 'pin *' reaches every chat with a session, those that appear later too); '@NOTE_ADD own | <text>' is the running chat's own to-do, pinned to it and shown as its own, never as the user's; any chat can still list it; a leading 'Category: ' (Bug:, Decision:, Env:, Todo:...) makes it searchable
  @NOTE_EDIT <note-id> <text>                     edits an existing note
  @NOTE_BRIEF <note-id> | <short text>            puts a short version before a note's existing text (footers print only that, with a pointer to @NOTE_LIST <note-id>); a note's old short part is replaced, its audience stays
  @NOTE_PIN <note-id> <*|names|all|own>           changes only who sees a note, never its text: * every chat with a session (new ones too), current = only the chats that exist now (not later ones), names or patterns, all = a plain note (also for runs without a session), own = this chat's own to-do; a note's text before ' || ' is all footers print, '@NOTE_LIST <note-id>' prints it whole
  @NOTE_REMOVE <note-id>                          removes an existing note
  @NOTE_LIST [words]                              prints all workspace notes, or those whose category, pins or text contain every word
  @FILE /<path>                                   selects the file for the hunks that follow
  @HUNK <scope> | <short label>                   then exactly these marker lines:
  --- [OLD CODE] ---
  <verbatim on-disk lines>
  +++ [NEW CODE] +++
  <replacement lines; leave empty to delete the old lines>
  === [END HUNK] ===
  (or, in place of +++ [NEW CODE] +++ and its lines: +++ [LINE EDITS] +++ then one edit per line: 'N: new text' replaces line N,
   'N-' deletes it, 'N+ text' inserts after it (0 = before line 1); N counts the recited OLD CODE lines from 1, not counting blank lines before the first or after the last, so it is always verified)
  @NEW_FILE /<path>  <content>  @END_NEW_FILE     each on its own line; rejected if the file exists
  @DELETE_FILE /<path, folder or glob>             each file goes into the script's journal first: recoverable with @UNDO <n> (or @UNDO <n> | /path); emptied folders are removed
  @RENAME /<old> -> /<new>                        later hunks and @TEXT_REPLACE in the same script use the new path; a folder moves file by file through the journal (each file recoverable with @UNDO, refused whole if the destination exists); the line-1 path header is rewritten to the new path, so later OLD CODE shows the new header
  @TEXT_REPLACE <file, file#Class.method, folder or glob> | expect <N> | <label>   then these marker lines (one line of text each):
  --- [OLD TEXT] ---
  <exact text, at least 12 characters, found exactly N times in that scope (default N = 1)>
  +++ [NEW TEXT] +++
  <replacement; empty removes it>
  === [END TEXT] ===
  (for a small change inside a long line, or the same change across many files, e.g. import paths after a move; take N from a @GREP)
  @PROBE /<path> | Scope | <scope>                prints that scope (500-line cap)
  @PROBE /<path> | Lines | <start>-<end>
  @PROBE /<path> | TOC                            signatures and # Stage anchors
  @PROBE /<tree file> | Tree | <node path or TOP> | <depth>
  @PROBE /<tree file> | Check                     drift check: tree nodes whose file, name() or # Stage anchor no longer exists in the code
  @PROBE /<file> | Unused                         deletion candidates: definitions that nothing calls (call graph) and nothing else mentions (text)
  @PROBE /<file> | Refs | <scope>                 what a scope uses: each project name with its use lines and definition site, plus external calls
  @XREF <symbol>                                  whole-word references across the repo, definitions first
  @XREF <symbol> | callers|callees|impact         call graph via codebase-memory-mcp when installed (impact = callers up to 5 levels; callers also list each call line); qualify shared names as <package or Type>.<name>
  @FIND <name, path fragment or glob>             files by name or path, e.g. @FIND lease or @FIND *.vue; re:<regex> filters by a regex on the path, e.g. @FIND re:^api/.*_test[.]py$
  @GREP <text>  or  @GREP /<regex>/[i]            matching lines; add ' | in <path fragment, glob or re:<regex>>' to limit where it looks
  @LIST_DIR /<path>    @LIST_RECURSIVE /<path>
  (@FIND, @GREP, @LIST_RECURSIVE and @TEXT_REPLACE take a last '| depth N': at most N folder levels below the fixed part of the path, 1 = directly inside. @LIST_DIR and @LIST_RECURSIVE count instead of list what .gitignore excludes and binary or media files; add '| all' to list them (a recursive listing in a git project never shows ignored files: use @LIST_DIR <folder> | all).
   Globs: with a '/' they start at the workspace root and * stays in one folder, ** crosses folders; without a '/' they match file names at any depth.)
  @RUN [--timeout <s>] <command>                  any other command (tests, builds, installs, CLI tools) in the workspace; default limit 300s; skipped if an earlier @GIT_COMMIT or @FILE failed; use @RUN_ALWAYS to run anyway
  @RUN_BLOCK [always] [--timeout <s>] ... @END_RUN_BLOCK   multi-line command block without temp files
  @INIT_DEBUG <slug>                              creates docs/debug/bug_<slug>.txt with its four sections and prints it
  @UNDO <hi>..<lo>  or  @UNDO <number>            reverses journaled scripts, newest first; add '| /path, /other, /ye*' to restore only those files (e.g. @UNDO 117 | /bot.py), the rest of those scripts stays; '/old -> /new' (or '-> /folder/') copies the file as it was to another path; several @UNDO lines may share a script
  @REDO <number>                                  runs that script's saved text again under this script's number; follow it with --- [OLD TEXT] --- / +++ [NEW TEXT] +++ / === [END TEXT] === corrections (each old text found once, may span lines) and any extra directives, instead of resending the whole script
  (the user may also paste a script that already ran: at a terminal the harness asks [R]eplay / [U]ndo it and that chat's later scripts / [E]xecute again)
""" + (GIT_CARD if MODE == "git" else "  @GIT_INIT [Name <email>]                        makes this folder a git repository (main, default .gitignore, numbering and undo carried over, optional identity for this repository only); other git directives work from then on, even in the same script\n") + """Scopes: TOP | EOF (append; OLD CODE empty) | Name | Class.method | Parent > # Stage anchor | tree node path (a > b)
A hunk applies only where OLD CODE matches exactly one place, searched in the scope first, then in the whole file.
@UNDO needs its own script. Commits may open a script that then changes files: the commit runs first and the file changes are skipped if it fails.
Every script runs in this order: commit, file changes or undo, notes, @RUN, then @GIT_STATUS, listings, searches and probes (so they show the result).
A script with no directives is valid: it just prints the footer (next number, goal, standing rules).
Tree files: write |-- and \\-- connectors; they are stored as box glyphs. Every file gets a '/<project>/<path>' comment as its first line automatically.""")
    print("Notes are the user's: add, edit or remove them only when the user explicitly asks. They are stored in .llm_harness/notes.md, may ride along with any script, and are not reversed by @UNDO.")
    print("Inside a fence write %s for three consecutive backticks and https%s for a URL scheme; both are decoded before matching." % (SENT_BT3, "@@" + "://"))
    print("Lines beginning with '->' in harness output are instructions for your next turn.")

def print_rules_file():
    """The whole workflow_commands.txt, printed once by the handshake: the workflow, the reply format and every rule in full."""
    try:
        with open(RULES_PATH, "r", encoding="utf-8", errors="replace") as f:
            text = f.read().replace("\r", "").strip("\n")
    except OSError:
        return
    print("\n=== WORKFLOW AND RULES (workflow_commands.txt, printed once per chat; the footers repeat the standing rules after every run) ===")
    print(text)

def handshake(workspace, shell):
    line = "llm_harness v%s | python %s" % (VERSION, sys.version.split()[0])
    if not workspace:
        print(line + " | no workspace given")
        print('-> run: %s --workspace "<project folder>"' % harness_call(shell))
        return
    err = enter_workspace(workspace)
    if err:
        print(line + " | NOT READY: " + err)
        return
    st = load_state()
    st["shell"] = shell
    save_json(STATE_PATH, st)
    journal = len(glob.glob(os.path.join(HISTORY_DIR, "*.json")))
    print("%s | workspace: %s | %s | last script: %s | next number: %d | journal: %d" % (
        line, os.path.abspath("."), mode_label(), ("[%s]" % st["last_id"]) if st["last_id"] else "none", st["last_num"] + 1, journal))
    print_goal(st)
    if not os.path.isfile(RULES_PATH):
        print("WARNING: workflow_commands.txt is not next to harness.py (%s); standing rules cannot be printed after runs." % SELF_DIR)
    print_workspace_notes()
    # Comment (decision): a new chat reads only the handshake before its first script, so the sessions set up for it (@SPLIT, @UNCLAIM) are listed here, where its @SESSION line is chosen
    unclaimed = [(n, r) for n, r in sorted(load_json(sessions_path(), {}).items()) if r.get("unclaimed")]
    if unclaimed:
        print("=== UNCLAIMED SESSIONS (set up for a new chat: if the task matches one, name it in the first @SESSION line; when several or none fit, ask the user): %s ===" % "; ".join("%s: %s (set up by %s; brief: %s)" % (n, r.get("aim") or "no aim", r.get("created_by", "?"), (r.get("brief") or "")[:300]) for n, r in unclaimed))
    print("MODE: chat (human-pasted scripts; full standing rules arrive in every footer)")
    print(harness_states_line())
    print_card(shell, os.path.abspath("."))
    # Comment (decision): the owner pasted workflow_commands.txt beside the handshake at the start of every chat; printing it here makes one paste start a chat, and the footers keep the standing rules in view after that
    print_rules_file()

def timed(fn, *args):
    """Run one read-only directive and print how long it took, so slow steps are visible."""
    t = time.time()
    fn(*args)
    print("  (%.1fs)" % (time.time() - t))

def parse_notes_text(text):
    """(notes, next_id) from the text of notes.md, without touching the file; unknown lines (git's conflict markers, say) raise ValueError."""
    next_id, notes = 1, []
    for line in text.splitlines():
        header = NOTE_HEADER_RE.fullmatch(line)
        if header:
            next_id = max(next_id, int(header.group(1)))
        elif line.strip():
            entry = NOTE_ENTRY_RE.fullmatch(line)
            if not entry:
                raise ValueError("unrecognized line in notes.md: %s" % line[:80])
            nid, body = entry.group(1).upper(), entry.group(2)
            fm = re.match(r"^\[(pin|for|own): ([^\]]+)\] (.+)$", body)
            notes.append({"id": nid, "text": fm.group(3) if fm else body, "for": [x.strip() for x in fm.group(2).split(",") if x.strip()] if fm else None, "own": bool(fm) and fm.group(1) == "own"})
            next_id = max(next_id, int(nid[1:]) + 1)
    return notes, next_id

def merge_notes_text(base, ours, theirs):
    """Three-way merge of notes.md by note id: new notes from both sides are kept (a clash on the same new id gets the other side's note a fresh id), an edit by one side wins over no edit, a removal by one side stands unless the other side edited it, and when both edited the same note this side's text stays and the other side's becomes a new note. Returns the merged file text; raises ValueError when a side cannot be read."""
    (b, _), (o, next_o), (t, next_t) = parse_notes_text(base), parse_notes_text(ours), parse_notes_text(theirs)
    bm, om, tm = ({n["id"]: n for n in side} for side in (b, o, t))
    same = lambda x, y: x["text"] == y["text"] and (x.get("for") or []) == (y.get("for") or [])
    merged, extra = dict(om), []
    for nid, note in tm.items():
        if nid in bm:
            if nid not in om or same(note, bm[nid]):
                continue
            if same(om[nid], bm[nid]):
                merged[nid] = note
            elif not same(om[nid], note):
                extra.append(dict(note, text="(the other side's edit of %s) %s" % (nid, note["text"])))
        elif nid not in om:
            merged[nid] = note
        elif not same(om[nid], note):
            extra.append(note)
    for nid in bm:
        if nid not in tm and nid in om and same(om[nid], bm[nid]):
            merged.pop(nid, None)
    next_id = max([next_o, next_t] + [int(k[1:]) + 1 for k in merged])
    for note in extra:
        note = dict(note, id="N%03d" % next_id)
        merged[note["id"]] = note
        next_id += 1
    lines = ["<!-- llm_harness_notes_next_id: %d -->" % next_id]
    for note in sorted(merged.values(), key=lambda n: int(n["id"][1:])):
        lines.append("- [%s] %s%s" % (note["id"], note_mark(note), note["text"]))
    return "\n".join(lines) + "\n"

def merge_verdicts_text(base, ours, theirs):
    """Three-way merge of verdicts.json, entry by entry in 'verdicts' and 'campaigns': entries only one side has are kept, a change by one side wins over no change, a removal stands unless the other side changed that entry, and when both changed it the newer one (by its time field) wins. Other top-level keys stay as this side has them. Raises ValueError when a side is not a JSON object."""
    def load(text):
        data = json.loads(text) if text.strip() else {}
        if not isinstance(data, dict):
            raise ValueError("verdicts.json is not a JSON object")
        return data
    b, o, t = load(base), load(ours), load(theirs)
    out = dict(o)
    newer = lambda x, y: y if (y.get("time") or 0) > (x.get("time") or 0) else x
    for section in ("verdicts", "campaigns"):
        bs, os_, ts = (side.get(section) or {} for side in (b, o, t))
        merged = dict(os_)
        for key, tv in ts.items():
            if key in bs:
                if key not in os_ or tv == bs[key]:
                    continue
                if os_[key] == bs[key]:
                    merged[key] = tv
                elif os_[key] != tv:
                    merged[key] = newer(os_[key], tv)
            elif key not in os_:
                merged[key] = tv
            elif os_[key] != tv:
                merged[key] = newer(os_[key], tv)
        for key in bs:
            if key not in ts and key in os_ and os_[key] == bs[key]:
                merged.pop(key, None)
        if merged or section in o or section in t:
            out[section] = merged
    return json.dumps(out, ensure_ascii=True, indent=1)

def merge_tokens_text(base, ours, theirs):
    """Three-way merge of tokens.json: distinct <account>@<machine> buckets stay separate without conflict, while same-bucket/session deltas since base merge additively."""
    def load(text):
        data = json.loads(text) if text.strip() else {}
        if not isinstance(data, dict):
            raise ValueError("tokens.json is not a JSON object")
        return _normalize_tokens_doc(data)["buckets"]
    bb, ob, tb = load(base), load(ours), load(theirs)
    merged = {}
    for bkey in sorted(set(bb) | set(ob) | set(tb)):
        if bkey not in ob and bkey not in tb:
            continue
        if bkey not in ob:
            merged[bkey] = json.loads(json.dumps(tb[bkey]))
            continue
        if bkey not in tb:
            merged[bkey] = json.loads(json.dumps(ob[bkey]))
            continue
        b_ent = bb.get(bkey) or {"tokens": 0, "pastes": 0, "chars": 0, "sessions": {}}
        o_ent = ob[bkey]
        t_ent = tb[bkey]
        ent = json.loads(json.dumps(o_ent))
        for k in ("tokens", "pastes", "chars"):
            ent[k] = max(o_ent[k], o_ent[k] + max(0, t_ent[k] - b_ent.get(k, 0)))
        bs, os_, ts = b_ent.get("sessions") or {}, o_ent.get("sessions") or {}, t_ent.get("sessions") or {}
        ms = {}
        for skey in sorted(set(bs) | set(os_) | set(ts)):
            if skey not in os_ and skey not in ts:
                continue
            if skey not in os_:
                ms[skey] = json.loads(json.dumps(ts[skey]))
            elif skey not in ts:
                ms[skey] = json.loads(json.dumps(os_[skey]))
            else:
                s_entry = dict(os_[skey])
                for k in ("tokens", "pastes", "chars"):
                    s_entry[k] = max(os_[skey][k], os_[skey][k] + max(0, ts[skey][k] - (bs.get(skey) or {}).get(k, 0)))
                ms[skey] = s_entry
        ent["sessions"] = ms
        merged[bkey] = ent
    return json.dumps({"buckets": merged}, ensure_ascii=True, indent=1, sort_keys=True)

def merge_memory_cli(args):
    """git's merge driver: --merge-memory <notes|verdicts|tokens> <base> <ours> <theirs>. The merged text replaces <ours>; exit 0 when merged, 1 when a side could not be read (git then leaves the usual conflict)."""
    try:
        kind, base_p, ours_p, theirs_p = args[:4]
        texts = []
        for path in (base_p, ours_p, theirs_p):
            try:
                with open(path, "r", encoding="utf-8", newline="") as f:
                    texts.append(f.read().replace("\r\n", "\n"))
            except FileNotFoundError:
                texts.append("")
        fn = {"notes": merge_notes_text, "verdicts": merge_verdicts_text, "tokens": merge_tokens_text}[kind]
        merged = fn(*texts)
        with open(ours_p, "w", encoding="utf-8", newline="\n") as f:
            f.write(merged)
        sys.exit(0)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print("llm_harness merge driver: %s" % exc, file=sys.stderr)
        sys.exit(1)

MERGE_DRIVERS = {"llm-harness-notes": "notes", "llm-harness-verdicts": "verdicts", "llm-harness-tokens": "tokens"}

def has_merge_rules():
    """True when .gitattributes names the harness's merge drivers."""
    try:
        return "llm-harness-notes" in read_text(".gitattributes")
    except OSError:
        return False

def ensure_merge_drivers():
    """The attributes in .gitattributes travel with the project; the driver command is machine-local, so register it in this repository's own git config (and keep it pointing at this harness)."""
    if MODE != "git":
        return
    try:
        attrs = read_text(".gitattributes")
    except OSError:
        return
    here, py = SELF_PATH.replace("\\", "/"), sys.executable.replace("\\", "/")
    for name, kind in MERGE_DRIVERS.items():
        if name not in attrs:
            continue
        want = '"%s" "%s" --merge-memory %s %%O %%A %%B' % (py, here, kind)
        if run_git(["config", "--local", "--get", "merge.%s.driver" % name])[1].strip() != want:
            run_git(["config", "--local", "merge.%s.driver" % name, want])
            run_git(["config", "--local", "merge.%s.name" % name, "llm_harness %s merge" % kind])

def arg_value(name):
    args = sys.argv[1:]
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else None

def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    shell = (arg_value("--shell") or ("powershell" if os.name == "nt" else "bash")).lower()
    if "--version" in sys.argv[1:]:
        print("llm_harness v%s" % VERSION)
        return
    if "--merge-memory" in sys.argv[1:]:
        return merge_memory_cli(sys.argv[sys.argv.index("--merge-memory") + 1:])
    if "--check" in sys.argv[1:]:
        return check_cli()
    if "--steward" in sys.argv[1:]:
        return steward_cli()
    if "--auto" in sys.argv[1:]:
        return auto_cli()
    if "--compact" in sys.argv[1:]:
        return compact_cli()
    if "--compacted" in sys.argv[1:]:
        return compacted_cli()
    if "--new-turn" in sys.argv[1:]:
        return new_turn_cli()
    if "--agent-allow" in sys.argv[1:]:
        return agent_allow_cli()
    if "--link" in sys.argv[1:]:
        return link_cli()
    if "--merge" in sys.argv[1:]:
        return merge_session_cli()
    for flag in ("--release", "--unbrake"):
        if flag in sys.argv[1:]:
            return session_cli(flag)
    if "--grant" in sys.argv[1:] or "--revoke" in sys.argv[1:]:
        return grant_cli()
    if len(sys.argv) > 1 or sys.stdin.isatty():
        handshake(arg_value("--workspace"), shell)
        return
    raw_txt = decode_payload(sys.stdin.buffer.read())
    start_tty_focus()
    P = parse_payload(raw_txt)
    if agent_mode():
        _blocked_session_ops = {"@SESSIONS", "@SPLIT", "@BORROW", "@RECLAIM", "@UNCLAIM", "@TAKEOVER", "@CHAT_LINK", "@GUIDE", "@DELEGATE", "@SCOPE_REQUEST", "@MESSAGE", "@RETURN", "@BRAKE", "@BRAKE_ACK", "@SIDE"}
        _hit = (P.get("seen") or set()) & _blocked_session_ops
        if _hit:
            print("  [REFUSED] session operation %s is not allowed in auto-shell (Terminal-Only) mode. Nothing was run." % ", ".join(sorted(_hit)))
            return
    tee = sys.stdout = OutputTee(sys.stdout)
    t_start = time.time()
    print("=== llm_harness v%s | EXECUTING [%s: %s] ===" % (VERSION, P["id"] or "UNKNOWN", P["title"]))
    err = enter_workspace(P["workspace"])
    if err:
        print("  [REFUSED] %s Nothing was run." % err)
        return print_footer(None)
    print("  Workspace: %s | %s" % (os.path.abspath("."), mode_label()))
    state = load_state()
    # Comment (decision): in agent mode the AI may inspect and plan but never apply code changes; the user pastes the script in their own terminal, where it runs as the user and applies
    if agent_mode() and ({"@FILE", "@NEW_FILE", "@DELETE_FILE", "@RENAME", "@TEXT_REPLACE"} & (P.get("seen") or set())):
        print("  [REFUSED] auto-shell: code changes are applied only when you run this script yourself in your terminal; paste it there. Nothing was run.")
        return print_footer(state)
    name_session(P)
    if re.search(r"(?m)^@REDO\s+\d+\s*$", raw_txt):
        raw_txt, redo_err = expand_redo(raw_txt)
        if redo_err:
            print("  [REFUSED] %s. Nothing was run." % redo_err)
            return print_footer(state)
        P = parse_payload(raw_txt)
        name_session(P)
        print("  [REDO] runs the saved text of an earlier script, with its corrections")
    start, rerun, assigned = len(tee.text()), False, False
    if P["repeatable"] and (P["num"] is not None or not side_allowed(P)):
        print("  [REFUSED] a @REPEATABLE script has no number and may only read, search and @RUN, so running it again can never change files twice. Nothing was run.")
        return print_footer(state)
    # Comment (decision): the session is named before any replay, undo or refusal can end the run, so the footer of every such run describes this chat as it is now; the registration (touch_session) and the one-time deliveries stay below and happen only for a run that executes
    globals()["CURRENT_SESSION"], globals()["CURRENT_PART"] = P["session"], P.get("part")
    if P["repeatable"]:
        print("  [REPEATABLE] runs on every paste, also an identical one; edit its values and paste it again as often as needed")
    if P["side"]:
        if not side_allowed(P):
            print("  [REFUSED] a @SIDE script may only read, search and @RUN; file changes, notes, goal, git and undo belong to the numbered scripts of the chat that drives this project. Nothing was run.")
            return print_footer(state)
        prior = None if P["repeatable"] else load_json(side_run_path(raw_txt), None)
        if prior:
            print("  [REPLAY] this @SIDE script already ran and this paste is identical, so nothing was run again (the same paste arrived twice, usually a duplicated copy). For the AI: if you already answered this script, reply in one or two lines and remind what is pending; if this output is new to you, read it as that script's result and continue. Its saved output:")
            AUTO_COPY.append(True)
            print(prior.get("output", "").rstrip("\n"))
            return print_footer(state)
        print("  [SIDE] runs outside the numbering: no script number used, nothing journaled")
    elif P["num"] is None:
        prior = None if P["repeatable"] else find_run_by_key(payload_key(raw_txt))
        choice = repaste_choice(prior.get("id"), P["session"]) if prior else "R"
        if prior and choice == "U":
            m = re.search(r"-(\d+)$", prior.get("id") or "")
            if m:
                undo_from(int(m.group(1)), P["session"], state)
            return print_footer(state)
        if prior and choice == "E":
            print("  [EXECUTE AGAIN] [%s] runs again under a new number" % prior.get("id"))
            prior, P["again"] = None, True
        if prior:
            print("  [REPLAY] [%s] already ran and this paste is identical, so nothing was run again (the same paste arrived twice, usually a duplicated copy). For the AI: if you already answered this script, reply in one or two lines and remind what is pending; if this output is new to you, read it as that script's result and continue. Its saved output:" % prior.get("id"))
            AUTO_COPY.append(True)
            print(prior.get("output", "").rstrip("\n"))
            print("\n  -> to run it again on purpose, change its title; at a terminal the user is asked instead: replay, undo, or execute again.")
            return print_footer(state)
        assign_number(P, state)
        assigned = True
        print("  [ASSIGNED] " + P["id"])
    elif P["num"] <= state["last_num"]:
        prior = find_run(P["num"])
        same = bool(prior) and prior.get("key") == payload_key(raw_txt)
        choice = repaste_choice(P["id"], P["session"]) if same else "R"
        if same and choice == "U":
            undo_from(P["num"], P["session"], state)
            return print_footer(state)
        if same and choice == "E":
            print("  [EXECUTE AGAIN] [%s] runs again under a new number" % P["id"])
            P["id"], P["again"] = re.sub(r"-\d+$", "", P["id"]), True
            assign_number(P, state)
            assigned = True
            print("  [ASSIGNED] " + P["id"])
        elif same:
            print("  [REPLAY] [%s] already ran and this paste is identical, so nothing was run again (the same paste arrived twice, usually a duplicated copy). For the AI: if you already answered this script, reply in one or two lines and remind what is pending; if this output is new to you, read it as that script's result and continue. Its saved output:" % P["id"])
            AUTO_COPY.append(True)
            print(prior.get("output", "").rstrip("\n"))
            return print_footer(state)
        elif prior or not read_only(P):
            print("  [STALE OR DUPLICATE SCRIPT] [%s] is not newer than the last executed script [%s]. Nothing was run." % (P["id"], state["last_id"]))
            print("  -> Use the next script number printed below; do not reuse an executed number.")
            return print_footer(state)
        else:
            rerun = True
            print("  [RE-RUN] [%s] is older than [%s] but only reads and has no saved output, so it runs again; the numbering is unchanged." % (P["id"], state["last_id"]))
    for w in P["warnings"]:
        print("  [WARNING] " + w)
    if not rerun and not P["side"] and not assigned and not claim_number(P, state):
        print("  [STALE OR DUPLICATE SCRIPT] [%s] was taken by another session a moment ago. Nothing was run." % P["id"])
        print("  -> write @SCRIPT [<ACT>: <title>] without a number and the harness assigns a free one.")
        return print_footer(state)
    if P["session"]:
        known = set(DIRECTIVES.split())
        P["used"] = sorted(d for d in P.get("seen", ()) if d in known)
        touch_session(P)
        record_host(P)
        check_waiting(P["session"], not (P["side"] or P["repeatable"]))
        if P.get("chat_link") is not None:
            set_chat_link(P["session"], P["chat_link"])
        if not P.get("again"):
            ask_chat_link(P["session"])
    elif P.get("chat_link") is not None:
        print("  [CHAT LINK REFUSED] @CHAT_LINK needs an @SESSION line. Nothing changed.")
    globals()["CURRENT_SESSION"] = P["session"]
    globals()["CURRENT_SCRIPT"], globals()["CURRENT_RUN"] = P["id"], "%s@%.6f" % (P["id"], time.time())
    globals()["CURRENT_PART"] = P.get("part")
    globals()["L1_REFRESH"] = bool(P.get("l1_refresh"))
    globals()["L1_PROOF"] = P.get("l1_proof") or ""
    globals()["PING_ONLY"] = bool(P.get("ping")) and not (P["ops"] or P["runs"] or P["probes"] or P["xrefs"] or P["greps"] or P["finds"] or P["list_dir"] or P["list_rec"] or P["notes"] or P["helps"] or P["git"] or P["git_status"] or P["msgs"] or P["msg_acks"] or P["wait_msgs"])
    enforce_brake(P)
    send_messages(P)
    apply_msg_acks(P)
    wait_for_messages(P)
    print_ping(P)
    if P["scope"] is not None:
        apply_scope_change(dict(P, scope_end=False, session_end=False))
    expand_rename_ops(P)
    expand_text_ops(P)
    expand_delete_ops(P)
    guard_ops(P)
    if P["goal"]:
        state["goal"] = P["goal"]
        write_goal(P["goal"])
        print("  [GOAL SET] " + P["goal"])
    if P.get("steward"):
        steward_directive(P)
    if P.get("takeover"):
        takeover_directive(P)
    if P.get("borrow") or P.get("reclaim"):
        borrow_directive(P)
    if P.get("unclaim") is not None:
        unclaim_directive(P)
    if P.get("guide"):
        guide_directive(P)
    if P.get("milestone") is not None:
        milestone_directive(P)
    if P["git_init"] and not agent_mode():
        git_init(P["git_init"])
    if P["undo"] and (P["ops"] or P["git"]):
        print("  [REFUSED] @UNDO must be in its own script (probes, searches, notes and @RUN may ride along). No changes were made.")
        print("  -> resend the undo and the other changes as separate scripts with consecutive numbers.")
    elif (P["git"] or P["git_init"]) and agent_mode():
        print("  [REFUSED] auto-shell: git changes (commit, fold, push, pull, branch, tag, account, remote, init) need an approval the user gives in the conversation, which the harness cannot receive yet; @GIT_STATUS still works. No changes were made.")
        print("  -> finish the work, then tell the user what to commit; they send that commit from the chat-browser flow or their own terminal.")
    elif P["git"] and MODE != "git":
        print("  [REFUSED] git directives in a no-git workspace. No changes were made.")
        print("  -> drop the @GIT_* lines, or start the script with @GIT_INIT to make this folder a git repository, and resend.")
    else:
        git_ok = True
        if P["git"]:
            repo_ops = [op for op in P["git"] if op["kind"] in REPO_KINDS or op["kind"] == "remote"]
            git_rest = [op for op in P["git"] if op["kind"] not in REPO_KINDS and op["kind"] != "remote"]
            git_ok = run_git_ops(git_rest) if git_rest else True
            if git_ok and git_rest:
                state["committed_through"] = P["num"] - 1 if P["ops"] else P["num"]
            if git_ok and repo_ops:
                git_ok = run_repo_ops(repo_ops)
        if P["undo"]:
            for spec in P["undo"]:
                run_undo(spec, state)
        elif P["ops"] and not git_ok:
            print("\n  [SKIPPED] file changes in this script, because the commit before them failed. -> fix the commit, then resend.")
        elif P["ops"]:
            hunk_log, files_log = execute_ops(P["ops"])
            if files_log:
                save_history(P, raw_txt, hunk_log, files_log)
    if P["scope_end"] or P["session_end"]:
        _DIRTY.clear()
        apply_scope_change(dict(P, scope=None))
    if P["notes"]:
        execute_note_ops(P["notes"])
    run_shell = state.get("shell") or shell
    prior_failed = (bool(P["git"]) and not git_ok) or (bool(P["ops"]) and RUN_FAILED)
    watched = watch_other_scopes(P["session"]) if P["runs"] else None
    for r in P["runs"]:
        if prior_failed and not r.get("always"):
            first_line = r["cmd"].splitlines()[0][:80]
            print("\n=== RUN: %s ===\n  [SKIPPED] earlier @GIT_COMMIT or @FILE failed in this script (use @RUN_ALWAYS to run anyway)" % first_line)
            continue
        run_command(r["cmd"], r["timeout"], run_shell)
    if watched:
        report_scope_changes(watched)
    if P["git_status"]:
        git_status_report()
    for d in P["list_dir"]:
        timed(run_list, d, False)
    for d in P["list_rec"]:
        timed(run_list, d, True)
    for f in P["finds"]:
        timed(run_find, f)
    for g in P["greps"]:
        timed(run_grep, g)
    for s in P["xrefs"]:
        timed(run_xref, s)
    apply_campaigns(P)
    record_verdicts(P)
    for pr in P["probes"]:
        timed(run_probe, pr)
    for h in P["helps"]:
        print_help(h, state.get("shell") or shell)
    for arg in P["verdict_lists"]:
        list_verdicts(arg)
    ensure_merge_drivers()
    auto_commit_memory(P)
    save_state(state)
    save_run(P, raw_txt, tee.text()[start:])
    if P["git"] and not (P["ops"] or P["runs"] or P["probes"] or P["xrefs"] or P["greps"] or P["finds"] or P["list_dir"] or P["list_rec"] or P["notes"] or P["helps"]
                         or P["scope"] is not None or P["scope_end"] or P["session_end"] or P["msgs"]):
        print("\n  -> this script only did git work: put the next known change, test or probe in the same script as the commit, so no turn is spent on git alone.")
    announce_scope_changes(P["session"], not (P["side"] or P["repeatable"]))
    print_sessions(P["session"])
    auto_verdict(P, tee.text()[start:])
    print("\n=== RUN TIME: %.1fs ===" % (time.time() - t_start))
    print_footer(state)

if __name__ == "__main__":
    try:
        main()
        offer_copy()
    finally:
        stop_tty_focus()
