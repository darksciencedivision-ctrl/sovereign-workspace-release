"""
REM-02 render proofs (Gate 4b): H-13..H-17 - the rendered-page checks added permanently to
Gate 4 after DEFECT-G5-1 (docs/REMEDIATION-02.md section 3).

One test per defect D1-D4 plus the rendered-DOM proof:
  test_first_party_urls_resolve     H-13  D1 asset paths
  test_header_links_resolve         H-14  D2 doc links
  test_distillery_payload_contract  H-15  D3 Distillery payload contract
  test_light_theme_contrast         H-16  D4 light-theme badge contrast
  test_rendered_dom                 H-17  rendered DOM via headless Edge (no code change)

Artifacts written on success:
  evidence/hardening/h13-assets.txt .. h17-dom.txt
  evidence/gate5/screenshots/shell-grid-rendered.png   (H-17)

The H-17 button assertion pins the six-action row named by SWS-UI-001 v1.2 section 7.3 item 2
(Start / Stop / Restart / Open / Run startup test / View logs).
"""
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
import winreg
from html.parser import HTMLParser

from shell.tests._harness import request, start_shell, stop_shell

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HARDENING = os.path.join(WORKSPACE, "evidence", "hardening")
BLANK_RENDER_SHA256 = "f7744eb44a77e0401b85dd4dc07a9cc48860d79f2ad6ff908ba2839bd0669271"


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def header(proof):
    return "# utc: {}\n# producer: ox-alpha THEME01\n# proof: {}\n".format(utc_now(), proof)


def write_artifact(name, text):
    os.makedirs(HARDENING, exist_ok=True)
    path = os.path.join(HARDENING, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    return path


def _raw_get(port, path, timeout=10.0):
    """GET an exact request path (no client-side dot-segment normalization)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path, headers={"Host": "127.0.0.1:{}".format(port)})
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read().decode("utf-8", "replace")
    finally:
        conn.close()


class _RefAttrs(HTMLParser):
    """Collect every href/src attribute value.

    Classification happens in the test: values starting "/" are first-party paths to GET;
    http(s) values are external and skipped; ANYTHING ELSE (e.g. a bare relative
    "app.css") is itself a violation - that is exactly the D1 defect class, where a
    relative reference resolves against / and 404s.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ("href", "src") and isinstance(value, str) and value:
                self.values.append((key, value))


def _css_urls(css_text):
    out = []
    for m in re.finditer(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", css_text):
        u = m.group(1).strip()
        if u.startswith("/"):
            out.append(u)
    return out


def _js_urls(js_text):
    out = []
    for m in re.finditer(r"['\"](/(?:api|static)/[^'\"\s]*)['\"]", js_text):
        u = m.group(1)
        if "<id>" in u or "${" in u or "{" in u or "}" in u:
            continue  # template placeholder, not a concrete first-party URL
        out.append(u)
    return out


def _read(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def _first_nonempty(text):
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _tokens(block):
    return {k.lower(): v.lower() for k, v in
            re.findall(r"(--[a-z-]+)\s*:\s*(#[0-9a-fA-F]{6})", block)}


def _ratio(fg, bg):
    def lum(hx):
        hx = hx.lstrip("#")
        r, g, b = (int(hx[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class TestRenderProofs(unittest.TestCase):

    # ---------------------------------------------------------------- H-13
    def test_first_party_urls_resolve(self):
        lines = [header("H-13 - every first-party URL referenced by served HTML/CSS/JS "
                        "resolves with zero 4xx/5xx")]
        proc, port, nonce = start_shell()
        try:
            st, hdrs, html = request(port, "/")
            self.assertEqual(st, 200)
            refparser = _RefAttrs()
            refparser.feed(html)
            urls = []
            relative_refs = []
            for _attr, val in refparser.values:
                if val.startswith("http://") or val.startswith("https://"):
                    continue  # external references are out of scope by HC-5 design
                if val.startswith("/"):
                    urls.append(val)
                else:
                    relative_refs.append(val)

            st_css, h_css, css = request(port, "/static/app.css")
            self.assertEqual(st_css, 200)
            self.assertEqual(h_css.get("Content-Type"), "text/css")
            urls += _css_urls(css)

            st_js, h_js, js = request(port, "/static/app.js")
            self.assertEqual(st_js, 200)
            self.assertIn(h_js.get("Content-Type"),
                          ("text/javascript", "application/javascript"))
            urls += _js_urls(js)

            ordered = []
            for u in urls:
                if u not in ordered:
                    ordered.append(u)

            # H-2 (v1.2 section 7.6) makes the four action endpoints POST-only; their 404
            # answer to GET is the designed behaviour and is pinned here rather than
            # treated as a broken reference.
            action_post_routes = {"/api/start", "/api/stop", "/api/restart",
                                  "/api/startup-test"}
            bad = []
            for u in ordered:
                s, hh, _body = request(port, u)
                ctype = hh.get("Content-Type", "")
                lines.append("{:<26} -> HTTP {:<3} {}".format(u, s, ctype))
                if u in action_post_routes:
                    if s != 404:
                        bad.append((u, s))
                elif s >= 400:
                    bad.append((u, s))
            for r in sorted(set(relative_refs)):
                lines.append("{:<26} -> RELATIVE ASSET REFERENCE (D1 defect class)".format(r))
                bad.append((r, "relative"))
            lines.append("")
            lines.append("checked: {} first-party URLs; errors: {}; relative asset "
                         "references: {}; POST-only action routes pinned at HTTP 404 on "
                         "GET per H-2: {}".format(
                             len(ordered),
                             [b for b in bad if b[0] not in action_post_routes
                              and b[1] != "relative"] or "none",
                             sorted(set(relative_refs)) or "none",
                             sorted(action_post_routes)))
            lines.append("asset content-types: app.css={}, app.js={}".format(
                h_css.get("Content-Type"), h_js.get("Content-Type")))
            self.assertEqual(bad, [],
                             "first-party URLs returned errors: {}".format(bad))
            write_artifact("h13-assets.txt", "\n".join(lines) + "\n")
        finally:
            stop_shell(proc)

    # ---------------------------------------------------------------- H-14
    def test_header_links_resolve(self):
        docs = [
            ("discovery", os.path.join(WORKSPACE, "docs", "DISCOVERY.md")),
            ("theme-baseline", os.path.join(WORKSPACE, "docs", "THEME-BASELINE-v3.md")),
            ("directive", os.path.join(WORKSPACE, "BUILD-DIRECTIVE-SWS-UI-001.md")),
        ]
        lines = [header("H-14 - /doc/<name> serves exactly the three named documents")]
        proc, port, nonce = start_shell()
        try:
            for name, path in docs:
                st, hh, body = _raw_get(port, "/doc/" + name)
                self.assertEqual(st, 200, name)
                ctype = hh.get("Content-Type", "")
                self.assertTrue(ctype.startswith("text/markdown"), (name, ctype))
                self.assertEqual(hh.get("X-Content-Type-Options"), "nosniff", name)
                first_body = _first_nonempty(body)
                first_disk = _first_nonempty(_read(path))
                self.assertEqual(first_body, first_disk, name)
                lines.append("/doc/{:<14} -> 200 {} nosniff; serves {}; "
                             "first line matches disk: {!r}"
                             .format(name, ctype, os.path.basename(path),
                                     first_body[:60]))

            for probe_path, label in (("/doc/../AGENTS.md", "traversal"),
                                      ("/doc/other", "unknown name")):
                st, _, _ = _raw_get(port, probe_path)
                self.assertEqual(st, 404, (label, st))
                lines.append("{:<20} -> 404 ({})".format(probe_path, label))

            listing_st, _, _ = _raw_get(port, "/doc/")
            self.assertEqual(listing_st, 404, "directory listing must not be served")
            lines.append("/doc/                -> 404 (no directory listing)")
            write_artifact("h14-doclinks.txt", "\n".join(lines) + "\n")
        finally:
            stop_shell(proc)

    # ---------------------------------------------------------------- H-15
    def test_distillery_payload_contract(self):
        js = _read(os.path.join(WORKSPACE, "shell", "static", "app.js"))
        start = js.index("async function loadDistillery")
        end = js.index("function extractLogText", start)
        body = js[start:end]

        paths = []
        for m in re.finditer(
                r"\bdata\.([A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*)", body):
            p = m.group(1)
            if p not in paths:
                paths.append(p)
        for m in re.finditer(r"data\[[\"']([^\"']+)[\"']\]", body):
            if m.group(1) not in paths:
                paths.append(m.group(1))

        self.assertTrue(paths, "no data.* accesses found in loadDistillery()")

        lines = [header("H-15 - every key loadDistillery() reads exists in /api/distillery")]
        proc, port, nonce = start_shell()
        try:
            st, _, payload_text = request(port, "/api/distillery")
            self.assertEqual(st, 200)
            payload = json.loads(payload_text)

            def resolve(obj, dotted):
                cur = obj
                for seg in dotted.split("."):
                    if not isinstance(cur, dict) or seg not in cur:
                        return False, None
                    cur = cur[seg]
                return True, cur

            missing = []
            for p in paths:
                ok, val = resolve(payload, p)
                tname = type(val).__name__ if ok else "-"
                lines.append("{:<28} -> {} ({})".format("data." + p,
                                                        "PRESENT" if ok else "MISSING",
                                                        tname))
                if not ok:
                    missing.append(p)
            lines.append("")
            lines.append("note: dynamic accesses (data[variable]) cannot be resolved "
                         "statically and are excluded by design.")
            lines.append("checked: {} static paths; missing: {}".format(
                len(paths), missing or "none"))
            self.assertEqual(missing, [],
                             "loadDistillery() reads keys /api/distillery never returns: {}"
                             .format(missing))
            write_artifact("h15-distillery-contract.txt", "\n".join(lines) + "\n")
        finally:
            stop_shell(proc)

    # ---------------------------------------------------------------- H-16
    def test_light_theme_contrast(self):
        css_path = os.path.join(WORKSPACE, "shell", "static", "app.css")
        css = _read(css_path)

        root_m = re.search(r":root\s*\{(.*?)\}", css, re.S)
        light_m = re.search(r"@media\s*\(prefers-color-scheme:\s*light\)\s*\{(.*?)\n\}",
                            css, re.S)
        self.assertIsNotNone(root_m)
        self.assertIsNotNone(light_m)
        dark_tokens = _tokens(root_m.group(1))
        light_tokens = _tokens(light_m.group(1))

        # THEME-01 G5: every one of the six C-2 pairs is a TEXT pairing in BOTH
        # themes. The former glyph-demotion branch (which excused light
        # --ok/--warning/--danger at 1.83/2.00/2.65:1 on white) is retired with
        # THEME-BASELINE-v3 section 3.3; the light block now carries its own
        # >= 4.5:1 status tokens.
        status_pairs = [("text", "bg"), ("text", "panel"), ("text-muted", "panel"),
                        ("ok", "panel"), ("warning", "panel"), ("danger", "panel")]
        recorded_pairs = [("text-faint", "panel"), ("text", "accent-dim")]

        lines = [header("H-16 - WCAG contrast of the six C-2 token pairs, per theme; "
                        "all six asserted >= 4.5:1 as TEXT in both themes; faint and "
                        "accent-dim recorded, not asserted")]
        failures = []
        recorded_lines = []
        for theme, overrides in (("dark", None), ("light", light_tokens)):
            eff = dict(dark_tokens)
            if overrides:
                eff.update(overrides)
            for a, b in status_pairs:
                va = eff.get("--" + a)
                vb = eff.get("--" + b)
                r = _ratio(va, vb)
                ok_flag = r >= 4.5
                lines.append("{:<5} --{:<11} on --{:<5} = {:>6.2f}:1  TEXT  {}".format(
                    theme, a, b, r, "OK" if ok_flag else "FAIL (<4.5)"))
                if not ok_flag:
                    failures.append((theme, a, b, r))
            for a, b in recorded_pairs:
                va = eff.get("--" + a)
                vb = eff.get("--" + b)
                r = _ratio(va, vb)
                recorded_lines.append(
                    "{:<5} --{:<11} on --{:<5} = {:>6.2f}:1  RECORDED (below-bar carry, "
                    "out of scope per THEME-BASELINE-v3 section 3.4)".format(theme, a, b, r))

        lines.extend(recorded_lines)
        lines.append("")
        lines.append("asserted_all_text_pairs >= 4.5:1 in both themes -> {}".format(
            "PASS" if not failures else "FAIL {}".format(failures)))
        self.assertEqual(failures, [], "text pairings below 4.5:1: {}".format(failures))
        write_artifact("h16-contrast.txt", "\n".join(lines) + "\n")

    # ---------------------------------------------------------------- H-17
    def _edge_path(self):
        with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe") as k:
            val, _ = winreg.QueryValueEx(k, "")
        self.assertTrue(val, "msedge.exe not resolvable from App Paths registry")
        self.assertTrue(os.path.isfile(val), "Edge not found at {}".format(val))
        return val

    def test_rendered_dom(self):
        edge = self._edge_path()
        prof = tempfile.mkdtemp(prefix="sws-h17-")
        lines = [header("H-17 - rendered DOM of / (headless Edge) shows the five cards, "
                        "their action rows, and the runnable Distillery controls")]
        proc, port, nonce = start_shell()
        url = "http://127.0.0.1:{}/".format(port)
        try:
            cmd = [edge, "--headless=new", "--disable-gpu", "--no-first-run",
                   "--user-data-dir=" + prof, "--virtual-time-budget=8000",
                   "--dump-dom", url]
            lines.append("command: {}".format(subprocess.list2cmdline(cmd)))
            cp = subprocess.run(cmd, capture_output=True, timeout=120)
            dom = cp.stdout.decode("utf-8", "replace")
            i = dom.find("<!doctype")
            if i < 0:
                i = dom.find("<html")
            self.assertGreaterEqual(i, 0, "dump-dom produced no HTML document")
            dom = dom[i:]

            cards = _CardDOM()
            cards.feed(dom)
            lines.append("card order      : {}".format(cards.order))
            self.assertEqual(cards.order, ["sovereign", "sow", "tokencenter", "debate", "distillery"])

            expected_actions = {"start", "stop", "restart", "open", "test", "logs"}
            for mid in cards.order:
                actions = sorted(a for a, _ in cards.buttons.get(mid, []))
                lines.append("{:<10} buttons: {} ({})".format(mid, len(actions),
                                                              ", ".join(actions)))
                expected = expected_actions - ({"open"} if mid == "tokencenter" else set())
                self.assertEqual(set(actions), expected,
                                 "{} action row != contract section 7.3(2) set".format(mid))

            dist = {a: d for a, d in cards.buttons.get("distillery", [])}
            self.assertFalse(dist.get("start", True), "distillery start unexpectedly disabled")
            self.assertFalse(dist.get("test", True), "distillery startup test unexpectedly disabled")
            for act in ("stop", "restart", "open"):
                self.assertTrue(dist.get(act, False),
                                "distillery {} unexpectedly enabled while STOPPED".format(act))
            lines.append("distillery STOPPED action state start/stop/restart/open/test: "
                         "{} {} {} {} {}".format(
                             dist.get("start"), dist.get("stop"), dist.get("restart"),
                             dist.get("open"), dist.get("test")))
            lines.append("distillery Logs enabled: {}".format(not dist.get("logs", False)))

            shot_dir = os.path.join(WORKSPACE, "evidence", "gate5", "screenshots")
            os.makedirs(shot_dir, exist_ok=True)
            shot = os.path.join(shot_dir, "shell-grid-rendered.png")
            cmd2 = [edge, "--headless=new", "--disable-gpu", "--no-first-run",
                    "--user-data-dir=" + prof, "--virtual-time-budget=8000",
                    "--screenshot=" + shot, url]
            lines.append("")
            lines.append("command: {}".format(subprocess.list2cmdline(cmd2)))
            cp2 = subprocess.run(cmd2, capture_output=True, timeout=120)
            self.assertTrue(os.path.isfile(shot), "screenshot was not written")
            shot_sha = sha256_file(shot)
            lines.append("rendered png sha256: {}".format(shot_sha))
            lines.append("blank render sha256: {}".format(BLANK_RENDER_SHA256))
            self.assertNotEqual(shot_sha, BLANK_RENDER_SHA256,
                                "grid screenshot is still the blank render")

            lines.append("")
            lines.append("edge binary: {}".format(edge))
            lines.append("RESULT: five cards in order, six-action rows per contract "
                         "section 7.3(2), Distillery STOPPED controls are state-correct, PNG differs from "
                         "the blank render.")
            write_artifact("h17-dom.txt", "\n".join(lines) + "\n")
        finally:
            stop_shell(proc)
            shutil.rmtree(prof, ignore_errors=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class _CardDOM(HTMLParser):
    """Collect article.module-card order and their buttons (data-action, disabled)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.order = []
        self.current = None
        self.buttons = {}

    def handle_starttag(self, tag, attrs):
        a = {}
        for k, v in attrs:
            a[k] = "" if v is None else v
        classes = a.get("class", "").split()
        if tag == "article" and "module-card" in classes:
            mid = a.get("data-module", "")
            self.order.append(mid)
            self.current = mid
            self.buttons.setdefault(mid, [])
        elif tag == "button" and self.current:
            self.buttons[self.current].append((a.get("data-action", ""), "disabled" in a))

    def handle_endtag(self, tag):
        if tag == "article":
            self.current = None


if __name__ == "__main__":
    unittest.main()

