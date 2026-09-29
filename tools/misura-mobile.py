#!/usr/bin/env python3
"""
misura-mobile.py — Renders the deck at various widths and says what
overflows.

Why it is needed
----------------
Headless Chromium without emulation keeps the inner width at 500px
whatever you pass to `--window-size`: I tried `--headless`,
`--headless=new` and `--force-device-scale-factor`, and the result is
always 500. A 390px screenshot of a layout computed at 500px is not a
narrow render, it is a cropped render — and that has already cost me a
diagnosis.

ChromeDriver exposes device emulation, and you talk to it directly over
HTTP: no selenium, which is not installed.

Usage:
    python3 tools/misura-mobile.py [URL] [larghezze...]
"""

from __future__ import annotations

import base64
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = 9515

# The report goes in a file: --dump-dom does not work with emulation, and
# the title cannot carry the characters the messages produce.
REFERTO = pathlib.Path("/tmp/misura-mobile.json")

# Real devices, not invented widths: what fails on the phone is what is
# on the phone.
DISPOSITIVI = [
    ("Moto G54",         393, 873,  2.75),
    ("iPhone SE",        375, 667,  2),
    ("iPhone 13",        390, 844,  3),
    ("Pixel 7",          412, 915,  2.6),
    (" Galaxy S21",      360, 800,  3),
    ("iPad portrait",    820, 1180, 2),
    ("narrow desktop",   1024, 768, 1),
    ("desktop",          1600, 900, 1),
]

JS = """
const d = document.documentElement;
const finestra = d.clientWidth;
const sborsi = [];
document.querySelectorAll('*').forEach(el => {
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return;
  const st = getComputedStyle(el);
  if (st.position === 'fixed') return;
  if (r.right > finestra + 1) {
    sborsi.push({
      sel: el.tagName.toLowerCase() +
           (el.id ? '#' + el.id : '') +
           (el.className ? '.' + String(el.className).trim().split(/\\s+/).slice(0,2).join('.') : ''),
      sinistra: Math.round(r.left), destra: Math.round(r.right),
      larghezza: Math.round(r.width)
    });
  }
});
return {
  scrollWidth: d.scrollWidth,
  clientWidth: finestra,
  scrollHeight: d.scrollHeight,
  orizzontale: d.scrollWidth > finestra + 1,
  sborsi: sborsi.slice(0, 15)
};
"""


def http(method: str, path: str, body: dict | None = None) -> dict:
    url = f"http://127.0.0.1:{PORT}{path}"
    dati = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=dati, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def avvia_driver() -> subprocess.Popen:
    p = subprocess.Popen(
        ["chromedriver", f"--port={PORT}", "--silent"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            http("GET", "/status")
            return p
        except Exception:
            time.sleep(0.25)
    p.kill()
    raise SystemExit("  ✗ chromedriver does not start")


def sessione(driver_pid: subprocess.Popen) -> str:
    s = http("POST", "/session", {
        "capabilities": {"alwaysMatch": {
            "browserName": "chrome",
            "goog:chromeOptions": {"args": [
                "--headless=new", "--disable-gpu", "--no-sandbox",
                "--hide-scrollbars", "--disable-dev-shm-usage"]},
        }},
    })
    return s["value"]["sessionId"]


def esegui(sid: str, script: str) -> dict:
    r = http("POST", f"/session/{sid}/execute/sync",
             {"script": f"return (function(){{{script}}})();", "args": []})
    return r.get("value") or {}




def emula(sid: str, larghezza: int, altezza: int, dpr: float, mobile: bool) -> None:
    """The device metrics: without them the phone stays a desktop."""
    http("POST", f"/session/{sid}/goog/cdp/execute",
         {"cmd": "Emulation.setDeviceMetricsOverride", "params": {
             "width": larghezza, "height": altezza,
             "deviceScaleFactor": dpr, "mobile": mobile}})


def naviga(sid: str, url: str) -> None:
    http("POST", f"/session/{sid}/url", {"url": url})


def attendi(sid: str, ms: int) -> None:
    time.sleep(ms / 1000.0)


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8899/"
    larghezze = [int(x) for x in sys.argv[2:]] or [d[1] for d in DISPOSITIVI]
    driver = avvia_driver()
    try:
        sid = sessione(driver)
        esiti = []
        for nome, w, h, dpr in DISPOSITIVI:
            if w not in larghezze:
                continue
            emula(sid, w, h, dpr, w < 900)
            naviga(sid, url)
            attendi(sid, 1400)
            m = esegui(sid, JS)
            m["nome"] = nome
            m["impostata"] = w
            esiti.append(m)
            print(f"  {nome:16s} {w}x{h}")
            print(f"      content {m.get('scrollWidth')}px, "
                  f"viewport {m.get('clientWidth')}px, "
                  f"height {m.get('scrollHeight')}px")
            if m.get("orizzontale"):
                print(f"      ✗ OVERFLOWS horizontally")
            for s in m.get("sborsi", []):
                print(f"        outside: {s['sel']}  "
                      f"[{s['sinistra']}..{s['destra']}]")
            if not m.get("orizzontale") and not m.get("sborsi"):
                print(f"      ✓ nothing outside the viewport")
            # The screenshot: "nothing outside the viewport" does not mean
            # "it is readable". A screen can fail to overflow and still
            # be illegible.
            scatto = pathlib.Path(f"/tmp/mobile/{nome.replace(' ','-')}.png")
            scatto.parent.mkdir(parents=True, exist_ok=True)
            r = http("GET", f"/session/{sid}/screenshot")
            scatto.write_bytes(base64.b64decode(r["value"]))
            print(f"      → {scatto}")
        REFERTO.write_text(json.dumps(esiti, indent=2), encoding="utf-8")
        return 0
    finally:
        try:
            http("DELETE", f"/session/{sid}")
        except Exception:
            pass
        driver.kill()


if __name__ == "__main__":
    raise SystemExit(main())
