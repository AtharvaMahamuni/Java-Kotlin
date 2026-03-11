#!/usr/bin/env python3
"""
Build a Kindle-compatible EPUB 3 from Java/Kotlin/Android study notes.
Uses only Python stdlib — no pip required.
"""

import os, re, html, zipfile, uuid, textwrap
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────────────────

BASE   = "/home/atharva-mahamuni/Desktop/Java-Kotlin/Java-Kotlin/Code"
OUTPUT = "/home/atharva-mahamuni/Desktop/Java-Kotlin/Java-Kotlin/StudyNotes.epub"
BOOK_ID = str(uuid.uuid4())
TITLE   = "Java · Kotlin · Android · RxJava — Complete Interview Study Notes"
AUTHOR  = "Study Notes"
LANG    = "en"

# Ordered chapters: (id, file_path, display_title, subject)
CHAPTERS = [
    # Java
    ("j00", f"{BASE}/Java/Questions/J0_jvm_mental_model.md",     "J0 — JVM Mental Model",               "Java"),
    ("j01", f"{BASE}/Java/Questions/J1_type_system.md",           "J1 — Type System",                    "Java"),
    ("j02", f"{BASE}/Java/Questions/J2_oop.md",                   "J2 — OOP",                            "Java"),
    ("j03", f"{BASE}/Java/Questions/J3_generics.md",              "J3 — Generics",                       "Java"),
    ("j04", f"{BASE}/Java/Questions/J4_functional.md",            "J4 — Functional Java",                "Java"),
    ("j05", f"{BASE}/Java/Questions/J5_collections.md",           "J5 — Collections",                    "Java"),
    ("j06", f"{BASE}/Java/Questions/J6_concurrency_fundamentals.md","J6 — Concurrency Fundamentals",     "Java"),
    ("j07", f"{BASE}/Java/Questions/J7_concurrent_utilities.md",  "J7 — java.util.concurrent",           "Java"),
    ("j08", f"{BASE}/Java/Questions/J8_gc_and_jvm_tuning.md",     "J8 — GC & JVM Tuning",               "Java"),
    ("j09", f"{BASE}/Java/Questions/J9_modern_java.md",           "J9 — Modern Java",                    "Java"),
    # Kotlin
    ("k00", f"{BASE}/Kotlin/Questions/00_jvm_mental_model.md",          "K00 — JVM Mental Model",             "Kotlin"),
    ("k01", f"{BASE}/Kotlin/Questions/01_type_system_foundations.md",   "K01 — Type System Foundations",      "Kotlin"),
    ("k02", f"{BASE}/Kotlin/Questions/02_classes_and_objects.md",       "K02 — Classes & Objects",            "Kotlin"),
    ("k03", f"{BASE}/Kotlin/Questions/03_generics_and_variance.md",     "K03 — Generics & Variance",          "Kotlin"),
    ("k04", f"{BASE}/Kotlin/Questions/04_functions_lambdas_inlining.md","K04 — Functions, Lambdas & Inlining","Kotlin"),
    ("k05", f"{BASE}/Kotlin/Questions/05_properties_and_delegation.md", "K05 — Properties & Delegation",      "Kotlin"),
    ("k06", f"{BASE}/Kotlin/Questions/06_extension_functions.md",       "K06 — Extension Functions",          "Kotlin"),
    ("k07", f"{BASE}/Kotlin/Questions/07_collections_and_sequences.md", "K07 — Collections & Sequences",      "Kotlin"),
    ("k08", f"{BASE}/Kotlin/Questions/08_other_kotlin_features.md",     "K08 — Other Kotlin Features",        "Kotlin"),
    ("k09", f"{BASE}/Kotlin/Questions/09_coroutines_execution_mechanics.md","K09 — Coroutines: Execution",   "Kotlin"),
    ("k10", f"{BASE}/Kotlin/Questions/10_structured_concurrency.md",    "K10 — Structured Concurrency",       "Kotlin"),
    ("k11", f"{BASE}/Kotlin/Questions/11_flow.md",                      "K11 — Flow",                         "Kotlin"),
    ("k12", f"{BASE}/Kotlin/Questions/12_reference_operators_and_reflection.md","K12 — Reflection",          "Kotlin"),
    ("k13", f"{BASE}/Kotlin/Questions/13_android_architecture.md",      "K13 — Android Architecture",         "Kotlin"),
    ("k14", f"{BASE}/Kotlin/Questions/14_jetpack_components.md",        "K14 — Jetpack Components",           "Kotlin"),
    ("k15", f"{BASE}/Kotlin/Questions/15_networking.md",                "K15 — Networking",                   "Kotlin"),
    ("k16", f"{BASE}/Kotlin/Questions/16_android_system_internals.md",  "K16 — Android System Internals",     "Kotlin"),
    ("k17", f"{BASE}/Kotlin/Questions/17_performance_and_memory.md",    "K17 — Performance & Memory",         "Kotlin"),
    ("k18", f"{BASE}/Kotlin/Questions/18_testing.md",                   "K18 — Testing",                      "Kotlin"),
    # Android
    ("a00", f"{BASE}/Android/Questions/A0_android_platform.md",        "A0 — Android Platform",              "Android"),
    ("a01", f"{BASE}/Android/Questions/A1_activity_fragment.md",        "A1 — Activity & Fragment",           "Android"),
    ("a02", f"{BASE}/Android/Questions/A2_main_thread_and_views.md",    "A2 — Main Thread & Views",           "Android"),
    ("a03", f"{BASE}/Android/Questions/A3_architecture_patterns.md",    "A3 — Architecture Patterns",         "Android"),
    ("a04", f"{BASE}/Android/Questions/A4_offline_and_data.md",         "A4 — Offline & Data Layer",          "Android"),
    ("a05", f"{BASE}/Android/Questions/A5_jetpack_compose.md",          "A5 — Jetpack Compose",               "Android"),
    # RxJava
    ("rx_idx", f"{BASE}/RxJava/00_index.md",                           "RX — Index & Study Tracks",          "RxJava"),
    ("rx00",   f"{BASE}/RxJava/00_why_rxjava.md",                      "RX00 — Why RxJava?",                 "RxJava"),
    ("rx01",   f"{BASE}/RxJava/01_observer_pattern.md",                "RX01 — Observer Pattern",            "RxJava"),
    ("rx02",   f"{BASE}/RxJava/02_observable_types.md",                "RX02 — Observable Types",            "RxJava"),
    ("rx03",   f"{BASE}/RxJava/03_operators.md",                       "RX03 — Operators",                   "RxJava"),
    ("rx04",   f"{BASE}/RxJava/04_schedulers.md",                      "RX04 — Schedulers",                  "RxJava"),
    ("rx05",   f"{BASE}/RxJava/05_subjects.md",                        "RX05 — Subjects",                    "RxJava"),
    ("rx06",   f"{BASE}/RxJava/06_error_handling.md",                  "RX06 — Error Handling",              "RxJava"),
    ("rx07",   f"{BASE}/RxJava/07_backpressure_flowable.md",           "RX07 — Backpressure & Flowable",     "RxJava"),
    ("rx08",   f"{BASE}/RxJava/08_disposables_lifecycle.md",           "RX08 — Disposables & Lifecycle",     "RxJava"),
    ("rx09",   f"{BASE}/RxJava/09_android_patterns.md",                "RX09 — Android Patterns",            "RxJava"),
    ("rx10",   f"{BASE}/RxJava/10_decision_maps.md",                   "RX10 — Decision Maps",               "RxJava"),
    # Vocabulary
    ("v_idx",  f"{BASE}/Vocabulary/00_index.md",                       "VOC — Index (185 Questions)",        "Vocabulary"),
    ("v01",    f"{BASE}/Vocabulary/01_java_core_language.md",          "VOC01 — Java Core Language",         "Vocabulary"),
    ("v02",    f"{BASE}/Vocabulary/02_jvm_architecture_memory.md",     "VOC02 — JVM Architecture & Memory",  "Vocabulary"),
    ("v03",    f"{BASE}/Vocabulary/03_java_serialization_concurrency.md","VOC03 — Serialization & Concurrency","Vocabulary"),
    ("v04",    f"{BASE}/Vocabulary/04_kotlin_basics_classes.md",       "VOC04 — Kotlin Basics & Classes",    "Vocabulary"),
    ("v05",    f"{BASE}/Vocabulary/05_kotlin_collections_coroutines.md","VOC05 — Collections & Coroutines",  "Vocabulary"),
    ("v06",    f"{BASE}/Vocabulary/06_android_framework_components.md","VOC06 — Android Framework",          "Vocabulary"),
    ("v07",    f"{BASE}/Vocabulary/07_android_build_system.md",        "VOC07 — Android Build System",       "Vocabulary"),
    ("v08",    f"{BASE}/Vocabulary/08_android_architecture_performance.md","VOC08 — Architecture & Performance","Vocabulary"),
]

# ─── Markdown → XHTML Converter ───────────────────────────────────────────────

def escape(text):
    """HTML-escape plain text."""
    return html.escape(text, quote=False)

def md_inline(text):
    """Convert inline markdown (bold, italic, code, links) to HTML."""
    # Escape HTML first (but not inside code spans — handle those first)
    # Split on inline code spans
    parts = re.split(r'(`+)(.*?)\1', text, flags=re.DOTALL)
    result = []
    i = 0
    while i < len(parts):
        if i + 2 < len(parts) and re.match(r'`+', parts[i] if i > 0 else ''):
            # This shouldn't happen with split — handle normally
            result.append(escape(parts[i]))
            i += 1
        else:
            chunk = parts[i]
            # Escape HTML in non-code parts
            chunk = escape(chunk)
            # Bold-italic ***text***
            chunk = re.sub(r'\*\*\*(.*?)\*\*\*', r'<strong><em>\1</em></strong>', chunk)
            # Bold **text**
            chunk = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', chunk)
            # Italic *text* (not inside words)
            chunk = re.sub(r'(?<!\w)\*([^*\n]+?)\*(?!\w)', r'<em>\1</em>', chunk)
            # Links [text](url)
            chunk = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', chunk)
            # Strikethrough ~~text~~
            chunk = re.sub(r'~~(.*?)~~', r'<del>\1</del>', chunk)
            result.append(chunk)
            i += 1
    return ''.join(result)

def inline_with_code(text):
    """Handle inline code spans first, then other inline markdown."""
    # Find all `code` spans and protect them
    protected = []
    def protect_code(m):
        backticks = m.group(1)
        inner = m.group(2).strip()
        token = f"\x00CODE{len(protected)}\x00"
        protected.append(f'<code>{escape(inner)}</code>')
        return token
    text = re.sub(r'(`+)(.*?)\1', protect_code, text, flags=re.DOTALL)
    # Now do normal inline processing
    text = md_inline(text)
    # Restore code spans
    for i, code_html in enumerate(protected):
        text = text.replace(f"\x00CODE{i}\x00", code_html)
    return text

def md_to_xhtml(md_text, chapter_id, title, prev_id=None, next_id=None, toc_id="toc"):
    """Convert full markdown document to XHTML string."""
    lines = md_text.split('\n')
    body_parts = []
    i = 0
    in_code_block = False
    code_lang = ''
    code_lines = []
    in_table = False
    table_header_done = False
    in_list = None          # 'ul' or 'ol'
    in_blockquote = False
    bq_lines = []

    def flush_blockquote():
        nonlocal in_blockquote, bq_lines
        if bq_lines:
            inner = md_to_xhtml_fragment('\n'.join(bq_lines))
            body_parts.append(f'<blockquote>{inner}</blockquote>')
            bq_lines = []
        in_blockquote = False

    def flush_list():
        nonlocal in_list
        if in_list:
            body_parts.append(f'</{in_list}>')
            in_list = None

    def flush_table():
        nonlocal in_table, table_header_done
        if in_table:
            body_parts.append('</tbody></table>')
            in_table = False
            table_header_done = False

    while i < len(lines):
        line = lines[i]

        # ── Fenced code block ──
        fence_match = re.match(r'^(`{3,}|~{3,})(.*)', line)
        if fence_match and not in_code_block:
            flush_blockquote()
            flush_list()
            flush_table()
            in_code_block = True
            code_lang = fence_match.group(2).strip()
            code_lines = []
            i += 1
            continue
        if in_code_block:
            if re.match(r'^(`{3,}|~{3,})\s*$', line):
                in_code_block = False
                lang_class = f' class="language-{escape(code_lang)}"' if code_lang else ''
                code_content = escape('\n'.join(code_lines))
                body_parts.append(f'<pre><code{lang_class}>{code_content}</code></pre>')
                code_lines = []
            else:
                code_lines.append(line)
            i += 1
            continue

        # ── Blockquote ──
        bq_match = re.match(r'^>\s?(.*)', line)
        if bq_match:
            flush_list()
            flush_table()
            in_blockquote = True
            bq_lines.append(bq_match.group(1))
            i += 1
            continue
        elif in_blockquote:
            flush_blockquote()

        # ── Horizontal rule ──
        if re.match(r'^(\-{3,}|\*{3,}|_{3,})\s*$', line):
            flush_list()
            flush_table()
            body_parts.append('<hr/>')
            i += 1
            continue

        # ── ATX Headers ──
        h_match = re.match(r'^(#{1,4})\s+(.*)', line)
        if h_match:
            flush_list()
            flush_table()
            level = len(h_match.group(1))
            htag = f'h{level}'
            text = inline_with_code(h_match.group(2).strip())
            # Generate anchor id from text
            anchor = re.sub(r'[^\w\s-]', '', h_match.group(2).lower())
            anchor = re.sub(r'[\s]+', '-', anchor).strip('-')
            body_parts.append(f'<{htag} id="{anchor}">{text}</{htag}>')
            i += 1
            continue

        # ── Table ──
        if '|' in line and re.match(r'^\s*\|', line):
            flush_list()
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            # Check next line for separator
            next_line = lines[i+1] if i+1 < len(lines) else ''
            if re.match(r'^\s*\|?[\s\-:|]+\|', next_line):
                # Header row
                if not in_table:
                    body_parts.append('<table><thead><tr>')
                    body_parts.append(''.join(f'<th>{inline_with_code(c)}</th>' for c in cells))
                    body_parts.append('</tr></thead><tbody>')
                    in_table = True
                    table_header_done = False
                i += 2  # skip separator
                table_header_done = True
                continue
            elif in_table and re.match(r'^\s*\|?[\s\-:|]+\|', line):
                # separator row itself — skip
                i += 1
                continue
            elif in_table:
                body_parts.append('<tr>')
                body_parts.append(''.join(f'<td>{inline_with_code(c)}</td>' for c in cells))
                body_parts.append('</tr>')
                i += 1
                continue
            else:
                # Not a proper table, fall through
                pass

        # If we were in a table but this line is not a table row
        if in_table and not ('|' in line and re.match(r'^\s*\|', line)):
            flush_table()

        # ── Unordered list ──
        ul_match = re.match(r'^(\s*)([-*+])\s+(.*)', line)
        if ul_match:
            flush_table()
            if in_list != 'ul':
                flush_list()
                body_parts.append('<ul>')
                in_list = 'ul'
            body_parts.append(f'<li>{inline_with_code(ul_match.group(3))}</li>')
            i += 1
            continue

        # ── Ordered list ──
        ol_match = re.match(r'^(\s*)\d+\.\s+(.*)', line)
        if ol_match:
            flush_table()
            if in_list != 'ol':
                flush_list()
                body_parts.append('<ol>')
                in_list = 'ol'
            body_parts.append(f'<li>{inline_with_code(ol_match.group(2))}</li>')
            i += 1
            continue

        # ── Empty line ──
        if line.strip() == '':
            flush_list()
            flush_table()
            body_parts.append('')
            i += 1
            continue

        # ── Plain paragraph ──
        flush_list()
        flush_table()
        body_parts.append(f'<p>{inline_with_code(line)}</p>')
        i += 1

    # Flush any remaining open blocks
    flush_blockquote()
    flush_list()
    flush_table()
    if in_code_block and code_lines:
        body_parts.append(f'<pre><code>{escape(chr(10).join(code_lines))}</code></pre>')

    # Build navigation bar
    nav_parts = ['<nav class="chap-nav">']
    if prev_id:
        nav_parts.append(f'<a href="{prev_id}.xhtml">&#8592; Prev</a> ')
    nav_parts.append(f'<a href="{toc_id}.xhtml">&#8963; Index</a>')
    if next_id:
        nav_parts.append(f' <a href="{next_id}.xhtml">Next &#8594;</a>')
    nav_parts.append('</nav>')
    nav_html = '\n'.join(nav_parts)

    body_html = '\n'.join(body_parts)

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>{escape(title)}</title>
  <link rel="stylesheet" type="text/css" href="../styles/style.css"/>
</head>
<body>
  {nav_html}
  <h1 class="chap-title">{escape(title)}</h1>
  {body_html}
  {nav_html}
</body>
</html>'''

def md_to_xhtml_fragment(md_text):
    """Convert markdown to HTML fragment (no full document wrapper)."""
    lines = md_text.split('\n')
    parts = []
    for line in lines:
        if line.strip():
            parts.append(f'<p>{inline_with_code(line)}</p>')
    return '\n'.join(parts)

# ─── EPUB Component Builders ──────────────────────────────────────────────────

CSS = '''
body {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1em;
  line-height: 1.7;
  margin: 1em 1.5em;
  color: #1a1a1a;
}
h1 { font-size: 1.6em; margin-top: 1.5em; border-bottom: 2px solid #333; padding-bottom: 0.3em; }
h2 { font-size: 1.3em; margin-top: 1.4em; border-bottom: 1px solid #888; padding-bottom: 0.2em; }
h3 { font-size: 1.1em; margin-top: 1.2em; }
h4 { font-size: 1em; margin-top: 1em; font-style: italic; }
pre {
  background: #f4f4f4;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 0.8em 1em;
  overflow-x: auto;
  font-size: 0.82em;
  font-family: "Courier New", Courier, monospace;
  white-space: pre;
  word-wrap: normal;
}
code {
  font-family: "Courier New", Courier, monospace;
  font-size: 0.88em;
  background: #f0f0f0;
  padding: 0.1em 0.3em;
  border-radius: 3px;
}
pre code {
  background: none;
  padding: 0;
  font-size: inherit;
}
blockquote {
  border-left: 4px solid #4a90d9;
  margin: 1em 0;
  padding: 0.5em 1em;
  background: #f0f6ff;
  font-style: italic;
}
blockquote strong { font-style: normal; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 1em 0;
  font-size: 0.88em;
}
th, td {
  border: 1px solid #ccc;
  padding: 0.4em 0.7em;
  text-align: left;
}
th { background: #e8e8e8; font-weight: bold; }
tr:nth-child(even) { background: #f9f9f9; }
ul, ol { padding-left: 1.5em; }
li { margin: 0.3em 0; }
hr { border: none; border-top: 1px solid #ccc; margin: 1.5em 0; }
a { color: #2255aa; text-decoration: none; }
a:hover { text-decoration: underline; }
.chap-nav {
  font-size: 0.9em;
  text-align: center;
  padding: 0.5em;
  background: #f8f8f8;
  border: 1px solid #ddd;
  border-radius: 4px;
  margin: 1em 0;
}
.chap-nav a {
  margin: 0 0.8em;
  font-weight: bold;
}
.chap-title {
  border-bottom: 3px solid #2255aa;
  color: #2255aa;
}
.subject-header {
  background: #2255aa;
  color: white;
  padding: 0.3em 0.8em;
  border-radius: 4px;
  font-size: 0.85em;
  display: inline-block;
  margin-bottom: 0.5em;
}
.toc-subject { font-size: 1.3em; font-weight: bold; margin-top: 1.5em; color: #2255aa; border-bottom: 1px solid #2255aa; }
.toc-subject-rxjava { font-size: 1.3em; font-weight: bold; margin-top: 1.5em; color: #7e5109; border-bottom: 1px solid #f5cba7; }
.toc-subject-vocab  { font-size: 1.3em; font-weight: bold; margin-top: 1.5em; color: #6c3483; border-bottom: 1px solid #d7bde2; }
.toc-item { margin: 0.3em 0 0.3em 1.5em; }
'''

def make_cover():
    return '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Cover</title>
  <link rel="stylesheet" type="text/css" href="../styles/style.css"/>
  <style>
    .cover-wrap { text-align: center; margin-top: 3em; }
    .cover-title { font-size: 2em; color: #2255aa; margin-bottom: 0.3em; }
    .cover-sub   { font-size: 1.2em; color: #555; }
    .cover-badge { display: inline-block; margin: 0.4em; padding: 0.3em 0.9em;
                   border-radius: 20px; font-weight: bold; font-size: 1em; }
    .java   { background: #e8f4fd; color: #1a5276; border: 1px solid #aed6f1; }
    .kotlin { background: #fef9e7; color: #7d6608; border: 1px solid #f9e79f; }
    .android{ background: #e9f7ef; color: #1e8449; border: 1px solid #a9dfbf; }
    .rxjava { background: #fdebd0; color: #7e5109; border: 1px solid #f5cba7; }
    .vocab  { background: #f4ecf7; color: #6c3483; border: 1px solid #d7bde2; }
  </style>
</head>
<body>
  <div class="cover-wrap">
    <p class="cover-title">Java &#183; Kotlin &#183; Android</p>
    <p class="cover-sub">Complete Interview Study Notes</p>
    <br/>
    <span class="cover-badge java">10 Java Chapters</span>
    <span class="cover-badge kotlin">19 Kotlin Chapters</span>
    <span class="cover-badge android">6 Android Chapters</span>
    <br/>
    <span class="cover-badge rxjava">12 RxJava Chapters</span>
    <span class="cover-badge vocab">9 Vocabulary Chapters</span>
    <br/><br/>
    <p style="color:#888; font-size:0.9em;">JVM internals &#183; Concurrency &#183; Coroutines &#183; Flow<br/>
    Architecture &#183; Compose &#183; Performance &#183; Testing<br/>
    RxJava streams &#183; Operators &#183; Schedulers &#183; 185 Q&amp;A</p>
  </div>
</body>
</html>'''

def make_toc(chapters):
    items = []
    current_subject = None
    for cid, _, title, subject in chapters:
        if subject != current_subject:
            current_subject = subject
            items.append(f'<p class="toc-subject">{escape(subject)}</p>')
        items.append(f'<p class="toc-item"><a href="{cid}.xhtml">{escape(title)}</a></p>')
    body = '\n'.join(items)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Master Index</title>
  <link rel="stylesheet" type="text/css" href="../styles/style.css"/>
</head>
<body>
  <h1>Master Index</h1>
  <p style="color:#555; font-size:0.9em;">57 chapters covering Java (J0–J9), Kotlin (K00–K18), Android (A0–A5), RxJava (RX00–RX10), and Vocabulary (185 Q&amp;A)</p>
  {body}
</body>
</html>'''

def make_nav(chapters):
    items = []
    current_subject = None
    for cid, _, title, subject in chapters:
        if subject != current_subject:
            if current_subject is not None:
                items.append('      </ol></li>')  # Close previous subject
            current_subject = subject
            items.append(f'      <li><span>{escape(subject)}</span><ol>')
        items.append(f'        <li><a href="chapters/{cid}.xhtml">{escape(title)}</a></li>')
    # Close last subject
    if current_subject is not None:
        items.append('      </ol></li>')

    nav_items = '\n'.join(items)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
<head><meta charset="UTF-8"/><title>Navigation</title></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>Table of Contents</h1>
    <ol>
      <li><a href="chapters/cover.xhtml">Cover</a></li>
      <li><a href="chapters/toc.xhtml">Master Index</a></li>
{nav_items}
    </ol>
  </nav>
</body>
</html>'''

def make_ncx(chapters, book_id):
    nav_points = []
    nav_points.append(f'''    <navPoint id="cover" playOrder="1">
      <navLabel><text>Cover</text></navLabel>
      <content src="chapters/cover.xhtml"/>
    </navPoint>''')
    nav_points.append(f'''    <navPoint id="toc" playOrder="2">
      <navLabel><text>Master Index</text></navLabel>
      <content src="chapters/toc.xhtml"/>
    </navPoint>''')
    for order, (cid, _, title, _) in enumerate(chapters, start=3):
        nav_points.append(f'''    <navPoint id="{cid}" playOrder="{order}">
      <navLabel><text>{escape(title)}</text></navLabel>
      <content src="chapters/{cid}.xhtml"/>
    </navPoint>''')
    navmap = '\n'.join(nav_points)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{book_id}"/>
    <meta name="dtb:depth" content="2"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{escape(TITLE)}</text></docTitle>
  <navMap>
{navmap}
  </navMap>
</ncx>'''

def make_opf(chapters, book_id):
    # Manifest items
    manifest = []
    manifest.append('    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    manifest.append('    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    manifest.append('    <item id="css" href="styles/style.css" media-type="text/css"/>')
    manifest.append('    <item id="cover" href="chapters/cover.xhtml" media-type="application/xhtml+xml"/>')
    manifest.append('    <item id="toc-page" href="chapters/toc.xhtml" media-type="application/xhtml+xml"/>')
    for cid, _, _, _ in chapters:
        manifest.append(f'    <item id="{cid}" href="chapters/{cid}.xhtml" media-type="application/xhtml+xml"/>')

    # Spine
    spine = ['    <itemref idref="cover"/>']
    spine.append('    <itemref idref="toc-page"/>')
    for cid, _, _, _ in chapters:
        spine.append(f'    <itemref idref="{cid}"/>')

    manifest_xml = '\n'.join(manifest)
    spine_xml    = '\n'.join(spine)
    now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="bookid">urn:uuid:{book_id}</dc:identifier>
    <dc:title>{escape(TITLE)}</dc:title>
    <dc:language>{LANG}</dc:language>
    <dc:creator>{escape(AUTHOR)}</dc:creator>
    <dc:date>{now}</dc:date>
    <meta property="dcterms:modified">{now}</meta>
  </metadata>
  <manifest>
{manifest_xml}
  </manifest>
  <spine toc="ncx">
{spine_xml}
  </spine>
</package>'''

# ─── Main Builder ─────────────────────────────────────────────────────────────

def build():
    print(f"Building: {OUTPUT}")
    ids = [c[0] for c in CHAPTERS]

    with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as zf:
        # mimetype — must be first and uncompressed
        zf.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip',
                    compress_type=zipfile.ZIP_STORED)

        # META-INF/container.xml
        container = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''
        zf.writestr('META-INF/container.xml', container)

        # CSS
        zf.writestr('OEBPS/styles/style.css', CSS)

        # content.opf
        zf.writestr('OEBPS/content.opf', make_opf(CHAPTERS, BOOK_ID))

        # toc.ncx
        zf.writestr('OEBPS/toc.ncx', make_ncx(CHAPTERS, BOOK_ID))

        # nav.xhtml
        zf.writestr('OEBPS/nav.xhtml', make_nav(CHAPTERS))

        # Cover
        zf.writestr('OEBPS/chapters/cover.xhtml', make_cover())

        # Master TOC page
        zf.writestr('OEBPS/chapters/toc.xhtml', make_toc(CHAPTERS))

        # Chapter pages
        for idx, (cid, fpath, title, subject) in enumerate(CHAPTERS):
            prev_id = ids[idx - 1] if idx > 0 else None
            next_id = ids[idx + 1] if idx < len(ids) - 1 else None

            print(f"  [{idx+1:02d}/{len(CHAPTERS)}] {title}")
            with open(fpath, 'r', encoding='utf-8') as f:
                md = f.read()

            xhtml = md_to_xhtml(md, cid, title,
                                 prev_id=prev_id, next_id=next_id,
                                 toc_id='toc')
            zf.writestr(f'OEBPS/chapters/{cid}.xhtml', xhtml)

    size_kb = os.path.getsize(OUTPUT) // 1024
    print(f"\nDone! {OUTPUT}")
    print(f"Size: {size_kb} KB  |  Chapters: {len(CHAPTERS)}")

if __name__ == '__main__':
    build()
