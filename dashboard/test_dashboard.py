"""
test_dashboard.py -- browser test for dashboard/dashboard.html.

NEEDS GOOGLE CHROME (or Chromium). It starts Chrome headless and drives the page over
the DevTools protocol, using only the Python standard library. Set CHROME to the
browser executable if it is not in the default macOS location or on PATH.

    python3 dashboard/test_dashboard.py           system colour scheme
    python3 dashboard/test_dashboard.py --dark    forced dark mode

Opens every view for several runs, clicks, hovers, presses keys, checks phone width,
and reports console messages, exceptions and network requests. Exits 1 if any step
fails or the page logs an error, 2 if no browser or no page is found.
"""
import base64, json, os, shutil, socket, struct, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path


def find_chrome():
    for c in (os.environ.get("CHROME"),
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")):
        if c and Path(c).exists():
            return c
    return None


CHROME = find_chrome()
PAGE_PATH = Path(__file__).resolve().parent / "dashboard.html"
PAGE = PAGE_PATH.as_uri()
PORT = 9333
DARK = "--dark" in sys.argv


class WS:
    def __init__(self, url):
        host, rest = url[len("ws://"):].split("/", 1)
        h, p = host.split(":")
        self.s = socket.create_connection((h, int(p)))
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{rest} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                        f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.id = 0
        self.events = []

    def _recv_exact(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(1 << 20)
            if not chunk:
                raise EOFError
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        msg = b""
        while True:
            b1, b2 = self._recv_exact(2)
            n = b2 & 127
            if n == 126:
                n = struct.unpack(">H", self._recv_exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recv_exact(8))[0]
            msg += self._recv_exact(n)
            if b1 & 0x80:
                return json.loads(msg)

    def send(self, method, **params):
        self.id += 1
        data = json.dumps({"id": self.id, "method": method, "params": params}).encode()
        hdr = bytes([0x81])
        n = len(data)
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        want = self.id
        while True:
            m = self.recv()
            if m.get("id") == want:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})
            self.events.append(m)


def js(ws, expr):
    r = ws.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
    if "exceptionDetails" in r:
        raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", r["exceptionDetails"]))
    return r["result"].get("value")


def main():
    if CHROME is None:
        print("test_dashboard: no Chrome or Chromium found; set CHROME to its executable.")
        sys.exit(2)
    if not PAGE_PATH.exists():
        print("test_dashboard: dashboard/dashboard.html not found; run build_dashboard.py first.")
        sys.exit(2)
    prof = tempfile.mkdtemp()
    args = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={prof}",
            f"--remote-debugging-port={PORT}", "--window-size=1280,900", "about:blank"]
    if DARK:
        args.insert(1, "--force-dark-mode")
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                page = [t for t in tabs if t["type"] == "page"][0]
                break
            except Exception:
                time.sleep(0.1)
        ws = WS(page["webSocketDebuggerUrl"])
        ws.send("Runtime.enable"); ws.send("Log.enable"); ws.send("Page.enable")
        ws.send("Network.enable")
        ws.send("Page.navigate", url=PAGE)
        for _ in range(600):
            if js(ws, "document.readyState") == "complete" and js(ws, "typeof DATA !== 'undefined' && !!DATA"):
                break
            time.sleep(0.1)
        exec_script(ws)
    finally:
        proc.terminate()


def exec_script(ws):
    results = []

    def step(name, expr):
        try:
            v = js(ws, expr)
            results.append((name, "ok", v))
        except Exception as e:
            results.append((name, "ERROR", str(e)[:300]))

    runs = js(ws, """(() => {
      const pick = f => RUNS.find(f);
      const a = pick(r => r.axes.universe==='nifty200' && r.axes.arm==='v3' && r.axes.survivorship==='pit' && r.axes.profile==='tradeable' && r.axes.tax==='on' && r.axes.capital==='1000000' && r.axes.impact==='0' && r.axes.pcap==='1' && r.axes.fixed==='off');
      const b = pick(r => r.axes.universe==='midcap100' && r.axes.arm==='v3' && r.axes.profile==='research' && r.axes.tax==='off' && r.axes.survivorship==='static');
      const c = pick(r => r.axes.universe==='nifty200' && r.axes.arm==='v1' && r.axes.capital==='5000000' && r.axes.impact==='0.01' && r.axes.pcap==='0.1');
      const d = pick(r => r.axes.universe==='nifty50' && r.axes.arm==='v2' && r.axes.profile==='research' && r.axes.tax==='on');
      return [a,b,c,d].map(r => r && r.id);
    })()""")
    results.append(("chosen runs", "ok", runs))
    views = ["run", "grid", "compare", "ladder", "methods", "all", "notes"]
    for rid in runs:
        step(f"open {rid}", f"openRun(BYID.get({json.dumps(rid)})); state.cmp.includes({json.dumps(rid)}) || document.getElementById('addCmp').click(); document.querySelector('.tile .v').textContent")
        for v in views:
            step(f"  view {v}", f"""(() => {{ state.view={json.dumps(v)}; render();
                const svgs = MAIN.querySelectorAll('svg.chart').length;
                const rows = MAIN.querySelectorAll('tbody tr').length;
                return `svgs ${{svgs}}, table rows ${{rows}}, hash ${{location.hash.length}} chars`; }})()""")
        # Hover each chart in the run view and read the tooltip.
        step("  hover charts (run view)", """(() => { state.view='run'; render(); const out=[];
            MAIN.querySelectorAll('svg.chart').forEach(svg => { const r=svg.getBoundingClientRect();
              svg.scrollIntoView(); const r2=svg.getBoundingClientRect();
              const tgt = svg.querySelector('.hit') || svg;
              tgt.dispatchEvent(new MouseEvent('mousemove',{clientX:r2.left+r2.width*0.6, clientY:r2.top+r2.height*0.5, bubbles:true}));
              const t=document.getElementById('tip'); const tr=t.getBoundingClientRect();
              out.push(t.style.display + ' inside=' + (tr.left>=0 && tr.right<=document.documentElement.clientWidth && tr.top>=0 && tr.bottom<=innerHeight) + ' :: ' + t.innerText.replace(/\\n/g,' | ').slice(0,160));
              svg.dispatchEvent(new MouseEvent('mouseleave')); });
            return out; })()""")
        step("  keyboard on equity chart", """(() => { const svg=MAIN.querySelector('svg.chart'); svg.focus();
            ['End','ArrowLeft','ArrowLeft'].forEach(k => svg.dispatchEvent(new KeyboardEvent('keydown',{key:k,bubbles:true})));
            return document.activeElement===svg ? document.getElementById('tip').innerText.replace(/\\n/g,' | ') : 'not focused'; })()""")
        step("  checks table and rounding notes", """(() => { state.view='run'; render(); const t=[...MAIN.querySelectorAll('section.panel')].pop();
            return 'pass ' + t.querySelectorAll('td.pass').length + ', fail ' + t.querySelectorAll('td.fail').length + ', not run ' + t.querySelectorAll('td.muted').length
              + ' | ' + [...MAIN.querySelectorAll('.tile .s')].slice(0,2).map(x=>x.textContent).join(' / '); })()""")
        step("  linear scale", "(() => { MAIN.querySelector('[data-scale=linear]').click(); return state.scale + ' ' + MAIN.querySelectorAll('svg.chart').length; })()")
        step("  one-setting table opens a run", """(() => { const tr = [...MAIN.querySelectorAll('tr[data-open]')][0]; if (!tr) return 'no rows';
            const id = tr.dataset.open; tr.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})); const ok = current() && current().id===id; history.back; return 'opened ' + id + ' ' + ok; })()""")
        step("  back to run", f"openRun(BYID.get({json.dumps(rid)})); current().id")
    # Return methods with and without a fixed-capital twin.
    step("methods: fixed-capital twin shown, no-data line gone", """(() => { const out=[];
        for (const fx of ['off','on']) {
          const r = RUNS.find(x => x.axes.universe==='nifty200' && x.axes.arm==='v3' && x.axes.survivorship==='pit' && x.axes.profile==='tradeable' && x.axes.tax==='on' && x.axes.capital==='1000000' && x.axes.impact==='0' && x.axes.pcap==='1' && x.axes.fixed===fx);
          if (!r) { out.push('fixed ' + fx + ': no run'); continue; }
          openRun(r); state.view='methods'; render();
          const h3 = [...MAIN.querySelectorAll('h3')].map(h=>h.textContent).join(' / ');
          const t = MAIN.querySelectorAll('table')[1];
          const rows = t ? [...t.querySelectorAll('tbody tr')].map(tr=>tr.innerText.replace(/\t/g,' ')) : [];
          const years = MAIN.querySelectorAll('table')[2] ? MAIN.querySelectorAll('table')[2].querySelectorAll('tbody tr').length : 0;
          out.push(`fixed ${fx}: ${h3} | ${rows.join(' ; ')} | year rows ${years} | no-data line ${MAIN.innerText.includes('is not in this data')} | sentences ${MAIN.querySelectorAll('ul')[1] ? MAIN.querySelectorAll('ul')[1].children.length : 0}`);
        }
        const nt = RUNS.find(x => !x.fixed_twin);
        openRun(nt); state.view='methods'; render();
        out.push('no twin (' + nt.id + '): no-data line ' + MAIN.innerText.includes('is not in this data') + ', fixed block ' + MAIN.querySelectorAll('h3').length);
        return out.join(' || '); })()""")
    # Grid interactions.
    step("grid: rows capital, cols impact, metric minus_basket", """(() => { state.view='grid'; state.grow='capital'; state.gcol='impact'; state.gmetric='minus_basket'; render();
        const b = MAIN.querySelectorAll('td.cell button'); const empty = MAIN.querySelectorAll('td.cell:not(:has(button))').length;
        const t = b.length ? b[0].textContent : ''; if (b.length) b[0].click(); return `cells ${b.length}, empty ${empty}, first ${t}, opened ${state.view} ${current() && current().id}`; })()""")
    for met in ["cagr", "minus_index", "max_dd", "end_equity", "tax", "costs"]:
        step(f"grid metric {met}", f"(() => {{ state.view='grid'; state.grow='universe'; state.gcol='arm'; state.gmetric='{met}'; render(); return MAIN.querySelectorAll('td.cell button').length; }})()")
    # Compare.
    step("compare rupees", "(() => { state.view='compare'; state.cmode='rupees'; render(); return state.cmp.length + ' runs, legend: ' + MAIN.querySelector('.legend').innerText.replace(/\\n/g,' | '); })()")
    step("compare hover", """(() => { const svg=MAIN.querySelector('svg.chart'); const r=svg.getBoundingClientRect();
        svg.dispatchEvent(new MouseEvent('mousemove',{clientX:r.left+r.width*0.5, clientY:r.top+r.height*0.5})); return document.getElementById('tip').innerText.replace(/\\n/g,' | '); })()""")
    # Ladder.
    for cell in js(ws, "[...new Set(DATA.ladder.map(x => `${x.universe} ${x.arm}`))]"):
        for m in ["cagr_minus_basket", "cagr", "max_dd", "impact_cost"]:
            step(f"ladder {cell} {m}", f"""(() => {{ state.view='ladder'; state.lcell={json.dumps(cell)}; state.lmetric='{m}'; render();
                const svg=MAIN.querySelector('svg.chart'); const r=svg.getBoundingClientRect();
                svg.dispatchEvent(new MouseEvent('mousemove',{{clientX:r.left+r.width*0.3, clientY:r.top+r.height*0.5}}));
                return MAIN.querySelectorAll('svg path').length + ' lines; tip: ' + document.getElementById('tip').innerText.replace(/\\n/g,' | ').slice(0,200); }})()""")
    # All runs: sort and filter.
    step("all runs: sort by CAGR desc, filter", """(() => { state.view='all'; state.filter=''; render();
        MAIN.querySelector('[data-sort=cagr]').click(); MAIN.querySelector('[data-sort=cagr]').click();
        const top = MAIN.querySelector('tbody tr').innerText.replace(/\\t/g,' ');
        state.filter='nifty200 tradeable pit'; render(); const n = MAIN.querySelectorAll('tbody tr').length;
        MAIN.querySelector('tbody tr').click(); return `top by CAGR: ${top} | filtered rows ${n} | opened ${state.view}`; })()""")
    # Not-run combination.
    step("not-run combination", """(() => { state.view='run'; state.sel = Object.assign({}, RUNS[0].axes, {cadence:'20', universe:'nifty50', capital:'50000000', profile:'research'}); render();
        return MAIN.querySelector('h2:nth-of-type(1)') ? [...MAIN.querySelectorAll('section.panel h2')].map(h=>h.textContent).join(' / ') + ' :: ' + document.getElementById('cmdText').textContent : 'none'; })()""")
    step("dimmed chips present", "MAIN.querySelectorAll('.chip.dim').length + ' dimmed of ' + MAIN.querySelectorAll('.chip').length")
    # Hash round trip.
    step("hash reopen", """(() => { const h = location.hash; state.view='notes'; state.sel = {}; location.hash = ''; location.hash = h;
        return new Promise(res => setTimeout(() => res(state.view + ' ' + (current() ? current().id : 'no run')), 300)); })()""")
    # Bad file through the same validator.
    step("validator on a bad file", "validate({schema:'x', generated_at:1, repo:{}, data_end:'2026', command_template:'run', axes:[], runs:[{}], ladder:[], known_issues:[], export_checks:[]})")
    step("validator on the embedded file", "validate(DATA).length")
    step("narrow window: page wider than viewport?", "document.documentElement.scrollWidth + ' vs ' + document.documentElement.clientWidth")

    # Phone width: every view, page must not scroll sideways.
    ws.send("Emulation.setDeviceMetricsOverride", width=375, height=812, deviceScaleFactor=2, mobile=True)
    step("phone: views without sideways page scroll", """(() => { const out=[]; openRun(RUNS[0]);
        for (const v of ['run','grid','compare','ladder','methods','all','notes']) { state.view=v; render();
          out.push(v + ' ' + document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth); }
        return out.join(', '); })()""")
    ws.send("Emulation.clearDeviceMetricsOverride")
    # Theme toggle and colours.
    step("theme cycle", """(() => { const b=document.getElementById('theme'); const out=[];
        for (let i=0;i<3;i++){ b.click(); out.push(b.textContent + ' bg=' + getComputedStyle(document.body).backgroundColor); } return out.join(' | '); })()""")
    # Fresh load from a hash.
    hash_url = js(ws, "(() => { openRun(BYID.get(" + json.dumps(runs[2]) + ")); state.view='methods'; render(); return location.href; })()")
    ws.send("Page.navigate", url="about:blank"); time.sleep(0.5)
    ws.send("Page.navigate", url=hash_url)
    for _ in range(600):
        try:
            if js(ws, "typeof DATA !== 'undefined' && !!DATA && document.readyState==='complete'"):
                break
        except Exception:
            pass
        time.sleep(0.1)
    step("fresh load from hash", "state.view + ' ' + (current() && current().id) + ' :: ' + MAIN.querySelector('tbody tr').innerText.replace(/\\t/g,' ')")

    # ---- steps for items 2 to 6 of the second fix round ----
    step("2 run view window + 4 two commands", """(() => { const r = RUNS.find(x => x.axes.universe==='microcap250' && x.axes.arm==='v1' && x.axes.survivorship==='static' && x.axes.profile==='research' && x.axes.tax==='off');
        openRun(r); const h2 = MAIN.querySelectorAll('section.panel h2')[0].textContent;
        const b = document.getElementById('cmdBatch').textContent, o = document.getElementById('cmdOne').textContent;
        return h2.slice(0,90) + ' || labels: ' + [...MAIN.querySelectorAll('.lab2')].map(x=>x.textContent).join(' / ') + ' || batch: ' + b + ' || only: ' + o + ' || copy buttons ' + MAIN.querySelectorAll('#copyBatch,#copyOne').length; })()""")
    step("4 copy button feedback", """(() => { const b=document.getElementById('copyOne'); b.click(); return new Promise(res => setTimeout(() => res(b.textContent), 50)); })()""")
    step("2 one-setting table marks different window", """(() => { const t = [...MAIN.querySelectorAll('section.panel')].find(s => s.querySelector('h2') && s.querySelector('h2').textContent.startsWith('The same run'));
        const marked = [...t.querySelectorAll('tr')].filter(tr => tr.querySelector('.diffwin')).map(tr => tr.cells[0].textContent + ' ' + tr.cells[1].textContent);
        return 'marked: ' + marked.join(', ') + ' || note: ' + t.querySelector('p.muted').textContent; })()""")
    step("2+5 grid: settings panel with spread axes, window marks", """(() => { state.view='grid'; state.grow='survivorship'; state.gcol='arm'; state.gmetric='cagr'; render();
        return 'spread notes: ' + [...MAIN.querySelectorAll('.spread')].map(x=>x.textContent).join(' / ') + ' || chips ' + MAIN.querySelectorAll('.chip').length
          + ' || marked cells ' + MAIN.querySelectorAll('td.cell .diffwin').length + ' of ' + MAIN.querySelectorAll('td.cell button').length
          + ' || note: ' + [...MAIN.querySelectorAll('p.muted')].map(p=>p.textContent).find(t=>t.includes('comparable')); })()""")
    step("5 grid chip changes the fixed settings", """(() => { const c = [...MAIN.querySelectorAll('.chip[data-axis=universe]')].find(b => b.dataset.v==='nifty200'); c.click();
        return state.view + ' universe=' + state.sel.universe + ' cells ' + MAIN.querySelectorAll('td.cell button').length; })()""")
    step("2 compare marks different window", """(() => { const a = RUNS.find(x => x.axes.universe==='microcap250' && x.axes.arm==='v1' && x.axes.survivorship==='pit' && x.axes.profile==='research' && x.axes.tax==='off');
        const b = RUNS.find(x => x.axes.universe==='microcap250' && x.axes.arm==='v1' && x.axes.survivorship==='static' && x.axes.profile==='research' && x.axes.tax==='off');
        state.cmp = [b.id, a.id]; openRun(b); state.view='compare'; render();
        return 'badges ' + MAIN.querySelectorAll('.diffwin').length + ' :: ' + [...MAIN.querySelectorAll('tbody tr')].map(tr => tr.cells[tr.cells.length-2].textContent).join(' | ') + ' || ' + [...MAIN.querySelectorAll('p.muted')][0].textContent; })()""")
    step("2 all runs start/end columns", """(() => { state.view='all'; state.filter='microcap250 pit'; render(); const hs=[...MAIN.querySelectorAll('th')].map(t=>t.textContent);
        const i = hs.findIndex(t=>t.startsWith('Start')); const starts = new Set([...MAIN.querySelectorAll('tbody tr')].map(tr=>tr.cells[i].textContent));
        state.filter=''; render(); const all = new Set([...MAIN.querySelectorAll('tbody tr')].map(tr=>tr.cells[i].textContent));
        return 'headers include Start/End: ' + hs.includes('Start') + '/' + hs.includes('End') + ' || microcap250 pit starts ' + [...starts] + ' || all starts ' + [...all]; })()""")
    step("3 ladder ramp, dashes, cap switch, edge label, note", """(() => { state.view='ladder'; state.lcell='nifty200 v3'; state.lmetric='cagr'; state.lcap='both'; render();
        const out=[]; const svg = () => MAIN.querySelector('svg.chart');
        const desc = () => { const ps=[...svg().querySelectorAll('path')]; const W=svg().viewBox.baseVal.width; const ts=[...svg().querySelectorAll('text')].filter(t=>t.getAttribute('y')>200);
          const last = ts[ts.length-1]; const bb = last.getBBox();
          return `${ps.length} lines (${ps.filter(p=>p.getAttribute('stroke-dasharray')).length} dashed), colours ${new Set(ps.map(p=>p.getAttribute('stroke'))).size}, last x label '${last.textContent}' ends at ${Math.round(bb.x+bb.width)} of ${W}`; };
        out.push('both: ' + desc());
        for (const c of ['1','0.1']) { MAIN.querySelector(`[data-lcap="${c}"]`).click(); out.push('cap ' + c + ': ' + desc()); }
        out.push('header: ' + MAIN.querySelectorAll('p.muted')[0].textContent.slice(0,60));
        out.push('note: ' + MAIN.querySelectorAll('p.muted')[1].textContent);
        return out.join(' || '); })()""")
    step("6 tooltip colours", """(() => { state.view='run'; openRun(RUNS[0]); const svg=MAIN.querySelector('svg.chart'); const r=svg.getBoundingClientRect();
        svg.dispatchEvent(new MouseEvent('mousemove',{clientX:r.left+r.width/2, clientY:r.top+r.height/2}));
        const t=getComputedStyle(document.getElementById('tip')); return 'theme ' + (isDark() ? 'dark' : 'light') + ': tip bg ' + t.backgroundColor + ', text ' + t.color + ', page bg ' + getComputedStyle(document.body).backgroundColor; })()""")
    step("6 notes: price data through, runs end", """(() => { state.view='notes'; render(); return [...MAIN.querySelectorAll('tr')].slice(1,3).map(tr=>tr.innerText.replace(/\\t/g,': ')).join(' || '); })()""")
    ws.send("Emulation.setDeviceMetricsOverride", width=375, height=812, deviceScaleFactor=2, mobile=True)
    step("6 phone: settings collapsed to a summary, opens on tap", """(() => { state.setOpen=false; state.view='run'; render(); const d=MAIN.querySelector('details.settings');
        const before = d.open + ' summary height ' + Math.round(d.querySelector('summary').getBoundingClientRect().height) + 'px: ' + d.querySelector('summary').textContent.slice(0,80);
        d.querySelector('summary').click();
        return new Promise(res => setTimeout(() => { const d2=MAIN.querySelector('details.settings'); res('closed=' + before + ' || after tap open=' + d2.open + ', chips visible ' + [...d2.querySelectorAll('.chip')].filter(c=>c.offsetParent).length + ', page ' + document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth); }, 50)); })()""")
    step("6 phone: grid view summary", """(() => { state.setOpen=false; state.view='grid'; render(); const d=MAIN.querySelector('details.settings'); return 'open=' + d.open + ' :: ' + d.querySelector('summary').textContent.slice(0,120) + ' | page ' + document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth; })()""")
    ws.send("Emulation.clearDeviceMetricsOverride")
    step("basket label on the run view", """(() => { state.view='run'; openRun(RUNS[0]); const t=[...MAIN.querySelectorAll('.tile')].find(x=>x.querySelector('.k').textContent==='Basket CAGR');
        return t.querySelector('.s').innerText.replace(/\\n/g,' | ') + ' || name in data: ' + RUNS[0].basket.name; })()""")
    # Network requests made by the page.
    reqs = [e["params"]["request"]["url"][:80] for e in ws.events if e.get("method") == "Network.requestWillBeSent"]
    cons = [(e["params"]["type"], " ".join(str(a.get("value", a.get("description", ""))) for a in e["params"]["args"])[:200])
            for e in ws.events if e.get("method") == "Runtime.consoleAPICalled"]
    excs = [e["params"]["exceptionDetails"].get("exception", {}).get("description", "")[:300]
            for e in ws.events if e.get("method") == "Runtime.exceptionThrown"]
    logs = [(e["params"]["entry"]["level"], e["params"]["entry"]["text"][:200]) for e in ws.events if e.get("method") == "Log.entryAdded"]
    for name, status, v in results:
        print(f"{status:5} {name}: {json.dumps(v)[:400] if not isinstance(v, str) else v[:400]}")
    print("network requests:", reqs)
    print("console calls:", cons)
    print("exceptions:", excs)
    print("log entries:", logs)
    failed = sum(1 for _, st, _ in results if st != "ok")
    errors = [c for c in cons if c[0] in ("error", "assert")] + excs + [l for l in logs if l[0] == "error"]
    print(f"RESULT: {len(results) - failed} of {len(results)} steps ok, "
          f"{len(errors)} console errors or exceptions")
    if failed or errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
