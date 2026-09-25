"""Human pages: a landing page on `/` with live gateway status, and the
project docs rendered as HTML (`/watchtower`, `/pages/craft`, `/pages/gotchas`,
`/pages/roadmap`, `/pages/readme`) so nobody has to read Markdown in a terminal.

The Markdown files live in the repo (a checkout or an editable install); an
installed wheel without them gets a friendly 404 pointing at GitHub."""

from __future__ import annotations

import html
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from .. import __version__

router = APIRouter(tags=["pages"], include_in_schema=False)

REPO = Path(__file__).resolve().parents[3]
PAGES = {
    "watchtower": ("docs/WATCHTOWER.md", "Watchtower"),
    "craft": ("docs/VIDEO_CRAFT.md", "Video craft guide"),
    "gotchas": ("docs/GOTCHAS.md", "Gotchas"),
    "roadmap": ("docs/ROADMAP.md", "Roadmap"),
    "readme": ("README.md", "README"),
}
GITHUB = "https://github.com/thedumbstuff/dollygrip/blob/main/"

_CSS = """
:root{--bg:#f7f5f0;--ink:#1c1b1f;--muted:#6b6a70;--card:#ffffff;--line:#e4e1d8;--accent:#e0a100;--accent-ink:#5a4200;--ok:#1f8a4c;--bad:#c0392b;--code:#f0ede4}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15151a;--ink:#ecebe6;--muted:#9c9ba3;--card:#1e1e25;--line:#2c2c36;--accent:#f2b400;--accent-ink:#ffe08a;--code:#24242d}}
:root[data-theme=dark]{--bg:#15151a;--ink:#ecebe6;--muted:#9c9ba3;--card:#1e1e25;--line:#2c2c36;--accent:#f2b400;--accent-ink:#ffe08a;--code:#24242d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--card);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
header .brand{font-weight:800;letter-spacing:.2px}header .brand span{color:var(--accent)}
header nav a{color:var(--ink);text-decoration:none;margin-right:12px;opacity:.85}header nav a:hover,header nav a.active{color:var(--accent-ink);opacity:1;text-decoration:underline}
.pill{margin-left:auto;font-size:13px;padding:4px 10px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.pill.ok{color:var(--ok);border-color:var(--ok)}.pill.bad{color:var(--bad);border-color:var(--bad)}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:2rem;margin:.2em 0 .4em}h2{margin-top:2em;padding-top:.6em;border-top:1px solid var(--line)}h3{margin-top:1.4em}
a{color:var(--accent-ink)}p em{color:var(--muted)}
table{border-collapse:collapse;width:100%;margin:1em 0;font-size:15px;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:8px 10px;vertical-align:top;text-align:left}th{background:var(--code)}
tr:nth-child(even) td{background:color-mix(in srgb,var(--card) 70%,var(--bg))}
code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:.92em}pre{background:var(--code);padding:12px;border-radius:8px;overflow-x:auto}pre code{background:none;padding:0}
blockquote{border-left:4px solid var(--accent);margin:1em 0;padding:.2em 1em;color:var(--muted)}
hr{border:0;border-top:1px solid var(--line);margin:2em 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:18px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}.card h3{margin:0 0 .3em;font-size:1.05rem}.card p{margin:0;color:var(--muted);font-size:14px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;font-size:15px}.kv b{color:var(--muted);font-weight:600}
.rq-head{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}.rq-head h2{flex:1}
.rq-note{font-size:14px;color:var(--muted);margin:.4em 0}.rq-note.bad{color:var(--bad)}
.rq-bar{height:8px;border-radius:99px;background:var(--code);overflow:hidden;min-width:120px}.rq-bar i{display:block;height:100%;background:var(--accent);transition:width .4s}
.rq-bar.done i{background:var(--ok)}.rq-bar.fail i{background:var(--bad)}
.rq-sub{font-size:13px;color:var(--muted)}
"""

_HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head><body>
<header><div class="brand">Dolly<span>Grip</span> <small style="color:var(--muted);font-weight:400">v{version}</small></div>
<nav><a href="/" {a_home}>Home</a><a href="/watchtower" {a_watch}>Watchtower</a><a href="/pages/craft" {a_craft}>Craft guide</a><a href="/pages/gotchas" {a_got}>Gotchas</a><a href="/pages/roadmap" {a_road}>Roadmap</a><a href="/docs">API docs</a></nav>
<span id="health" class="pill">checking Resolve...</span></header><main>"""

_TAIL = """</main><script>
fetch('/api/v1/health').then(r=>r.json()).then(h=>{const el=document.getElementById('health');const ok=h.resolve==='connected';el.textContent=ok?`Resolve connected · ${h.product||''} ${h.version||''}`:'Resolve disconnected';el.className='pill '+(ok?'ok':'bad');}).catch(()=>{const el=document.getElementById('health');el.textContent='gateway unreachable';el.className='pill bad';});
</script></body></html>"""


def _shell(title: str, body: str, active: str = "") -> str:
    flags = {k: ('class="active"' if active == k else "") for k in ("home", "watch", "craft", "got", "road")}
    return (
        _HEAD.format(title=html.escape(title), css=_CSS, version=__version__, a_home=flags["home"], a_watch=flags["watch"], a_craft=flags["craft"], a_got=flags["got"], a_road=flags["road"])
        + body
        + _TAIL
    )


def render_markdown(text: str) -> str:
    import markdown

    return markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "toc"], output_format="html5")


def _page(name: str) -> HTMLResponse:
    rel, title = PAGES[name]
    path = REPO / rel
    if not path.is_file():
        body = f"<h1>{html.escape(title)}</h1><p>This install has no <code>{html.escape(rel)}</code> (docs ship with the repository, not the wheel). Read it on GitHub: <a href='{GITHUB}{rel}'>{GITHUB}{rel}</a></p>"
        return HTMLResponse(_shell(title, body), status_code=404)
    body = render_markdown(path.read_text(encoding="utf-8"))
    active = {"watchtower": "watch", "craft": "craft", "gotchas": "got", "roadmap": "road"}.get(name, "")
    return HTMLResponse(_shell(f"DollyGrip - {title}", body, active))


# Live render-queue panel. Lists jobs from GET /api/v1/render/jobs every 3 s
# (status per job from GET /render/jobs/{id} when the list lacks it - real
# Resolve's GetRenderJobList carries no status), and follows the job that is
# rendering over the SSE route /render/jobs/{id}/events. SSE is read with
# fetch() streaming, not EventSource, so the bearer header can be sent: with
# --token set, open the page as /?token=... and the panel forwards it as
# `Authorization: Bearer`. Polling and the stream stop while the tab is hidden.
_RENDER_PANEL_JS = """<script>
(function(){
const API='/api/v1/render/jobs',SEP=String.fromCharCode(10,10);
const tok=new URLSearchParams(location.search).get('token');
const H=tok?{Authorization:'Bearer '+tok}:{};
const $=id=>document.getElementById(id);
let timer=null,stream=null,streamJob=null,rows=[];const live={};
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function getJSON(u){const r=await fetch(u,{headers:H,cache:'no-store'});let b={};try{b=await r.json();}catch(e){}
 if(!r.ok){const e=new Error(b.detail||('HTTP '+r.status));e.status=r.status;throw e;}return b;}
function reason(e){
 if(e.status===401)return tok?'The token in the page URL was rejected.':'This gateway requires a token: sign in with ?token=YOUR_TOKEN on this page URL.';
 if(e.status===503)return 'Resolve is not reachable ('+e.message+'). Still watching...';
 if(e.status===409)return 'No project is open in Resolve ('+e.message+'). Still watching...';
 return 'Could not read the render queue: '+e.message;}
function eta(ms){if(!ms)return '';const s=Math.round(ms/1000);return s<60?s+' s left':Math.floor(s/60)+' min '+(s%60)+' s left';}
function paint(rendering){
 const note=$('rq-note'),table=$('rq-table');
 if(!rows.length){table.hidden=true;note.className='rq-note';note.textContent='The render queue is empty.'+(rendering?' (Resolve reports a render in progress.)':'');return;}
 note.textContent='';table.hidden=false;
 $('rq-body').innerHTML=rows.map(j=>{const st=Object.assign({},j,live[j.JobId]||{});const pct=Math.max(0,Math.min(100,Number(st.CompletionPercentage)||0));
  const s=String(st.JobStatus||'unknown');const cls=s==='Complete'?'done':(s==='Failed'||s==='Cancelled')?'fail':'';
  const out=[st.TargetDir,st.OutputFilename].filter(Boolean).join('/');
  return '<tr data-job="'+esc(j.JobId)+'"><td><code>'+esc(j.JobId)+'</code><div class="rq-sub">'+esc(st.RenderJobName||'')+'</div></td><td>'+esc(st.TimelineName||'')+'</td><td>'+esc(out)+'</td><td>'+esc(s)+(st.Error?'<div class="rq-sub">'+esc(st.Error)+'</div>':'')+'</td>'
   +'<td><div class="rq-bar '+cls+'"><i style="width:'+pct+'%"></i></div><div class="rq-sub">'+pct+'% '+esc(eta(st.EstimatedTimeRemainingInMs))+'</div></td></tr>';}).join('');}
async function tick(){
 try{const d=await getJSON(API);const jobs=(d.jobs||[]).slice(0,50);
  const st=await Promise.all(jobs.map(j=>('JobStatus' in j)?{}:getJSON(API+'/'+encodeURIComponent(j.JobId)).catch(()=>({}))));
  rows=jobs.map((j,i)=>Object.assign({},j,st[i]));
  paint(d.rendering);
  const active=rows.find(r=>r.JobStatus==='Rendering');if(active)follow(active.JobId);
 }catch(e){rows=[];$('rq-table').hidden=true;const n=$('rq-note');n.className='rq-note bad';n.textContent=reason(e);}}
function stopStream(){if(stream){stream.abort();}stream=null;streamJob=null;$('rq-live').textContent='';}
async function follow(id){
 if(streamJob===id)return;stopStream();const ac=new AbortController();stream=ac;streamJob=id;
 $('rq-live').textContent='live: '+id;
 try{const r=await fetch(API+'/'+encodeURIComponent(id)+'/events?poll=1',{headers:H,signal:ac.signal});
  if(!r.ok||!r.body)throw new Error('no stream');
  const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
  for(;;){const x=await rd.read();if(x.done)break;buf+=dec.decode(x.value,{stream:true});let k;
   while((k=buf.indexOf(SEP))>=0){const blk=buf.slice(0,k);buf=buf.slice(k+2);
    const ev=(blk.match(/^event: (.*)$/m)||[])[1],data=(blk.match(/^data: (.*)$/m)||[])[1];
    if(data){try{live[id]=JSON.parse(data);paint(false);}catch(e){}}
    if(ev==='done'||ev==='timeout'){delete live[id];if(stream===ac)stopStream();tick();return;}}}
 }catch(e){}
 if(stream===ac)stopStream();}
function start(){if(timer)return;tick();timer=setInterval(tick,3000);}
function stop(){clearInterval(timer);timer=null;stopStream();}
document.addEventListener('visibilitychange',()=>document.hidden?stop():start());
start();
})();
</script>"""


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Landing page: live status and the doors into the project."""
    settings = request.app.state.settings
    body = f"""
<h1>DollyGrip</h1>
<p>A local REST gateway and MCP server for the DaVinci Resolve scripting API. This gateway is running on <code>{html.escape(str(request.base_url))}</code>.</p>
<div class="cards">
 <a class="card" href="/watchtower" style="text-decoration:none"><h3>Watchtower</h3><p>What works, what is verified, pending items, decisions, development required.</p></a>
 <a class="card" href="/docs" style="text-decoration:none"><h3>API docs</h3><p>Every operation with request/response shapes (Swagger). <code>/openapi.json</code> for machines.</p></a>
 <a class="card" href="/pages/craft" style="text-decoration:none"><h3>Video craft guide</h3><p>Read before building any video - structure, typography, motion, music, QA.</p></a>
 <a class="card" href="/pages/gotchas" style="text-decoration:none"><h3>Gotchas</h3><p>The live-verified traps of the Resolve API and how the gateway sands them off.</p></a>
 <a class="card" href="/pages/roadmap" style="text-decoration:none"><h3>Roadmap</h3><p>The longer climb.</p></a>
 <a class="card" href="/pages/readme" style="text-decoration:none"><h3>README</h3><p>Quickstart, Claude/MCP integration, security.</p></a>
</div>
<div class="rq-head"><h2>Render queue</h2><span id="rq-live" class="rq-sub"></span></div>
<div id="render-queue" data-api="/api/v1/render/jobs">
 <p id="rq-note" class="rq-note">Loading the render queue...</p>
 <table id="rq-table" hidden><thead><tr><th>Job</th><th>Timeline</th><th>Output</th><th>Status</th><th style="min-width:180px">Progress</th></tr></thead><tbody id="rq-body"></tbody></table>
</div>
{_RENDER_PANEL_JS}
<h2>This gateway</h2>
<div class="kv">
 <b>Version</b><span>{__version__}</span>
 <b>Escape hatch</b><span>{'enabled (--allow-exec)' if settings.allow_exec else 'disabled'}</span>
 <b>Bearer token</b><span>{'required' if settings.token else 'not set (localhost only)'}</span>
 <b>Health</b><span><a href="/api/v1/health">/api/v1/health</a></span>
</div>
<h2>Try it</h2>
<pre><code>curl {html.escape(str(request.base_url))}api/v1/projects/current
curl {html.escape(str(request.base_url))}api/v1/timelines/current/items</code></pre>
"""
    return HTMLResponse(_shell("DollyGrip", body, "home"))


@router.get("/watchtower", response_class=HTMLResponse)
def watchtower_page():
    """The project status board, rendered."""
    return _page("watchtower")


@router.get("/pages/{name}", response_class=HTMLResponse)
def doc_page(name: str):
    if name not in PAGES:
        return HTMLResponse(_shell("Not found", f"<h1>No such page</h1><p>Pages: {', '.join(f'<a href=/pages/{k}>{k}</a>' for k in PAGES)}</p>"), status_code=404)
    return _page(name)
