# /llm_harness/tests/language_header_test.py
"""Language-header test for llm_harness: the first-line '/<project>/<path>' comment uses each language's own comment marker and sits below the line a format must open with (HTML doctype, XML declaration, PHP opening tag); the 'Comment' convention is recognised in every marker the table knows; Python placement and files without comments are unchanged."""
import importlib.util, os, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-600:].replace("\n", "\n    "))


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    os.chdir(tempfile.mkdtemp(prefix="harness-lang-"))
    p = hh.project_name()

    def first(rel, text):
        out, status = hh.ensure_line1_header(rel, text)
        return out.split("\n"), status

    for rel, body, marker in (("Game/Player.cs", "using System;\n", "// "), ("src/Main.java", "package app;\n", "// "), ("src/Main.kt", "fun main() {}\n", "// "), ("src/lib.rs", "fn main() {}\n", "// "), ("src/a.cpp", "#include <a>\n", "// "), ("db/q.sql", "select 1;\n", "-- ")):
        lines, _ = first(rel, body)
        check("%s gets the header with its own marker" % rel, lines[0] == "%s/%s/%s" % (marker, p, rel) and lines[1] == body.rstrip("\n"), lines[:2])
    lines, _ = first("site.css", "body {}\n")
    check("CSS gets a block-comment header", lines[0] == "/* /%s/site.css */" % p, lines[:2])
    lines, _ = first("web/index.html", "<!DOCTYPE html>\n<html></html>\n")
    check("HTML keeps its doctype first and the header second", lines[0].lower().startswith("<!doctype") and lines[1] == "<!-- /%s/web/index.html -->" % p, lines[:3])
    lines, _ = first("conf/app.xml", '<?xml version="1.0"?>\n<a/>\n')
    check("XML keeps its declaration first", lines[0].startswith("<?xml") and lines[1] == "<!-- /%s/conf/app.xml -->" % p, lines[:3])
    lines, _ = first("web/page.php", "<?php\necho 1;\n")
    check("PHP gets the header below its opening tag", lines[0] == "<?php" and lines[1] == "// /%s/web/page.php" % p, lines[:3])
    out, status = hh.ensure_line1_header("web/plain.php", "<html>text</html>\n")
    check("a PHP file that starts with plain text is left alone", out == "<html>text</html>\n" and status == "N/A", (out, status))
    once, _ = hh.ensure_line1_header("Game/Player.cs", "using System;\n")
    twice, status = hh.ensure_line1_header("Game/Player.cs", once)
    check("running again keeps exactly one header", twice == once and twice.count("/%s/Game/Player.cs" % p) == 1 and status == "Valid", twice)
    lines, _ = first("tool.py", "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nprint(1)\n")
    check("Python still puts the header below the shebang and coding line", lines[0].startswith("#!") and "coding" in lines[1] and lines[2] == "# /%s/tool.py" % p, lines[:4])
    out, status = hh.ensure_line1_header("data.json", '{"a": 1}\n')
    check("JSON takes no comment", out == '{"a": 1}\n' and status == "N/A", (out, status))
    ok = all(hh.COMMENT_LINE_RE.match(s) for s in ("// Comment (decision): x", "    # Comment: y", "/* Comment: z */", "<!-- Comment (order): w -->", "-- Comment: q"))
    check("the Comment convention is recognised in every marker", ok)
    check("ordinary comments and code are not mistaken for it", not any(hh.COMMENT_LINE_RE.match(s) for s in ("// a plain comment", "# comment-like text", "int comments = 1;", "--i;")))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
