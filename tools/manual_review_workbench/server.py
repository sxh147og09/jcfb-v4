"""Dependency-free localhost HTTP UI for the manual review workbench."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .core import ActionValidationError, DuplicateSubmissionError, Workbench, WorkbenchError


HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JCFB V4 Manual Review Workbench</title>
<style>
:root{font-family:Inter,Segoe UI,system-ui,sans-serif;color:#172033;background:#f5f7fb;line-height:1.45}*{box-sizing:border-box}body{margin:0}.top{background:#162238;color:#fff;padding:18px 28px;display:flex;justify-content:space-between;gap:18px;align-items:center}.top h1{font-size:20px;margin:0}.top p{margin:4px 0 0;color:#bdc8db;font-size:12px}.top .safe{border:1px solid #5ca27a;color:#c9f4d9;border-radius:999px;padding:7px 12px;font-size:12px;white-space:nowrap}.bar{padding:14px 28px;background:#fff;border-bottom:1px solid #e3e8f0;display:flex;flex-wrap:wrap;gap:10px;align-items:center}.bar label{font-size:13px;color:#526078}.bar select,.bar input{border:1px solid #cbd4e1;border-radius:7px;padding:8px 10px;background:#fff;color:#172033}.bar input{min-width:180px}.stats{display:grid;grid-template-columns:repeat(6,minmax(90px,1fr));gap:10px;padding:18px 28px}.stat{background:#fff;border:1px solid #e4e9f1;border-radius:10px;padding:12px}.stat small{display:block;color:#65738a;font-size:11px}.stat strong{font-size:22px}.layout{display:grid;grid-template-columns:minmax(0,1fr) 400px;gap:18px;padding:0 28px 28px}.panel{background:#fff;border:1px solid #e1e7ef;border-radius:12px;padding:16px;min-width:0}.images{display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:12px}.figure{margin:0}.figure figcaption{font-size:12px;color:#596980;margin:0 0 6px}.imagebox{position:relative;border:1px solid #d8e0ec;border-radius:9px;background:#101827;min-height:310px;display:flex;align-items:center;justify-content:center;overflow:auto}.imagebox img{display:block;max-width:100%;max-height:58vh;object-fit:contain}.rawbox img{transform-origin:center center}.overlay{position:absolute;border:2px solid #31d28b;pointer-events:none}.zoom{width:100%;margin-top:8px}.meta h2{margin:0 0 8px;font-size:22px}.pill{display:inline-block;padding:4px 8px;border-radius:999px;font-size:11px;background:#eef2f8;color:#44536c;margin:0 5px 5px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:16px 0}.field{background:#f7f9fc;border-radius:8px;padding:8px}.field small{display:block;color:#718098;font-size:11px}.field code{font-family:ui-monospace,Consolas,monospace;font-size:12px;word-break:break-word}.textblock{background:#f7f9fc;border-radius:8px;padding:9px;margin:9px 0;font-size:13px;white-space:pre-wrap;word-break:break-word}.actions{border-top:1px solid #e6ebf2;padding-top:14px}.actions h3{font-size:13px;margin:0 0 8px}.actions input,.actions textarea{width:100%;border:1px solid #cbd4e1;border-radius:7px;padding:9px;font:inherit;margin-bottom:8px}.actions textarea{min-height:52px;resize:vertical}.buttons{display:flex;flex-wrap:wrap;gap:8px}.buttons button{border:0;border-radius:7px;padding:9px 11px;cursor:pointer;font-weight:600}.primary{background:#2563eb;color:#fff}.secondary{background:#e8eef8;color:#263750}.warn{background:#fff0d4;color:#774b00}.danger{background:#ffe0e0;color:#8e2323}.muted{background:#eef1f5;color:#526078}.buttons button:disabled{cursor:not-allowed;opacity:.45}.market{margin-top:14px}.marketrow{display:grid;grid-template-columns:110px 1fr 70px;gap:8px;align-items:center;font-size:12px;margin:8px 0}.track{height:7px;background:#e6ebf2;border-radius:999px;overflow:hidden}.fill{height:100%;background:#31a46f}.notice{margin:10px 0;padding:9px;border-radius:7px;background:#fff7df;color:#725200;font-size:12px}.error{background:#ffe9e9;color:#902222}.footer{padding:0 28px 28px;color:#6d7890;font-size:12px}@media(max-width:1050px){.layout{grid-template-columns:1fr}.images{grid-template-columns:1fr 220px}}@media(max-width:720px){.stats{grid-template-columns:repeat(3,1fr);padding:12px}.layout,.bar,.footer,.top{padding-left:12px;padding-right:12px}.images{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}}
</style></head><body>
<header class="top"><div><h1>JCFB V4 · Historical Official Odds Manual Review</h1><p>432-cell human visual review workbench · OCR is auxiliary evidence only</p></div><div class="safe">LOCAL / NO ARCHIVE · NO R002 · NO TRAINING</div></header>
<section class="bar"><label>Market <select id="market"><option value="">All markets</option><option>EXACT_SCORE</option><option>TOTAL_GOALS</option><option>HTFT</option><option>SPF</option><option>RQSPF</option></select></label><label><input id="remaining" type="checkbox" checked> show remaining only</label><label>Reviewer ID <input id="reviewer" placeholder="required before submit"></label><button class="secondary" id="reload">Refresh</button><span id="position" class="pill">Loading…</span></section>
<section class="stats" id="stats"></section>
<main class="layout"><section class="panel"><div class="images"><figure class="figure"><figcaption>Original immutable PNG · green box is the deterministic source cell</figcaption><div class="imagebox rawbox"><img id="raw" alt="Original official screenshot"><div id="overlay" class="overlay"></div></div><input id="zoom" class="zoom" type="range" min="0.5" max="2.5" value="1" step="0.1"></figure><figure class="figure"><figcaption>Deterministic crop / OCR auxiliary evidence</figcaption><div class="imagebox"><img id="crop" alt="Deterministic OCR crop"></div></figure></div></section>
<aside class="panel meta"><div id="item"></div><div class="actions"><h3>Human review action</h3><input id="value" placeholder="Correct value, e.g. 1.35"><textarea id="note" placeholder="Optional review note; do not record inferred values"></textarea><div class="buttons"><button id="confirm" class="primary">✓ CONFIRM OCR VALUE</button><button id="correct" class="secondary">✎ ENTER CORRECT VALUE</button><button id="unknown" class="warn">? UNKNOWN / CANNOT READ</button><button id="conflict" class="danger">! CONFLICT</button><button id="skip" class="muted">→ SKIP FOR LATER</button></div><div id="message" class="notice" hidden></div></div><div class="market"><h3>Per-market progress</h3><div id="markets"></div></div></aside></main>
<footer class="footer">Keyboard: C confirm OCR · E enter correction · U unknown · X conflict · S skip · ←/→ navigate. Every written record is append-only and hash-bound to the immutable inputs.</footer>
<script>
const $=id=>document.getElementById(id);let current=null,filteredIndex=0,filteredTotal=0;
function esc(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function params(){let p=new URLSearchParams();if($('market').value)p.set('market',$('market').value);if($('remaining').checked)p.set('remaining','1');p.set('index',filteredIndex);return p}
async function json(url,opts){let r=await fetch(url,opts);let d=await r.json();if(!r.ok)throw new Error(d.error||'Request failed');return d}
function showMessage(text,error=false){let n=$('message');n.hidden=!text;n.textContent=text;n.className=error?'notice error':'notice'}
function renderStats(s){$('stats').innerHTML=[['Total',s.candidate_cells],['Confirmed',s.confirmed],['Unknown',s.unknown],['Blocked',s.blocked],['Conflict',s.conflict],['Remaining',s.remaining]].map(x=>`<div class="stat"><small>${x[0]}</small><strong>${x[1]}</strong></div>`).join('');$('markets').innerHTML=Object.entries(s.per_market).map(([m,v])=>{let done=v.total-v.remaining,p=v.total?Math.round(done/v.total*100):0;return `<div class="marketrow"><span>${m}</span><div class="track"><div class="fill" style="width:${p}%"></div></div><span>${done}/${v.total}</span></div>`}).join('')}
function renderItem(d){current=d.item;if(!current){filteredIndex=0;filteredTotal=0;$('position').textContent='0/0';$('item').innerHTML='<h2>当前筛选没有待复核单元</h2><div class="notice">可以关闭“show remaining only”查看已处理记录，或切换 market。</div>';$('raw').removeAttribute('src');$('crop').removeAttribute('src');$('confirm').disabled=true;return}filteredIndex=d.position;filteredTotal=d.filtered_total;$('position').textContent=`${filteredTotal?filteredIndex+1:0}/${filteredTotal} · global ${current.queue_index}/432`;$('raw').src=`/asset/raw/${current.queue_item_id}`;$('crop').src=`/asset/crop/${current.queue_item_id}`;$('zoom').value=1;$('raw').style.transform='scale(1)';let c=current.normalized_coordinates.cell||{};$('overlay').style.left=(c.left*100)+'%';$('overlay').style.top=(c.top*100)+'%';$('overlay').style.width=((c.right-c.left)*100)+'%';$('overlay').style.height=((c.bottom-c.top)*100)+'%';let o=current.ocr_evidence||{};let n=Number(o.normalized_ocr_text);let canConfirm=!!(o.normalized_ocr_text&&o.normalized_ocr_text.trim()&&Number.isFinite(n)&&(current.value_kind==='HANDICAP_LINE'||n>0));$('confirm').disabled=!canConfirm;$('value').value='';$('note').value='';$('item').innerHTML=`<h2>${esc(current.outcome_label)}</h2><span class="pill">${esc(current.market)}</span><span class="pill">${esc(current.artifact_slot)}</span><span class="pill">${esc(current.prior_parser_status)}</span><div class="grid"><div class="field"><small>Cell label</small><code>${esc(current.cell_label)}</code></div><div class="field"><small>Ordering</small><code>${current.ordering_index}</code></div><div class="field"><small>Profile</small><code>${esc(current.selected_profile_identity)}</code></div><div class="field"><small>Value kind</small><code>${esc(current.value_kind)}</code></div></div><div class="textblock"><b>OCR raw</b>\n${esc(o.raw_ocr_text||'(empty)')}\n\n<b>OCR normalized</b>\n${esc(o.normalized_ocr_text||'(empty)')}\n\n<b>Prior parser</b>\n${esc(current.prior_parser_status)} · ${esc(current.prior_parser_value??'null')} · ${esc(current.prior_parser_reason)}</div><div class="textblock"><b>Cell pixels</b> ${esc(JSON.stringify(current.pixel_coordinates.cell))}<br><b>Region pixels</b> ${esc(JSON.stringify(current.pixel_coordinates.region))}<br><b>Raw SHA</b> ${esc(current.raw_image_sha256)}<br><b>Trace</b> ${esc(current.prior_trace_record_id)}</div>`}
async function load(){try{showMessage('');let d=await json('/api/item?'+params());renderItem(d);renderStats(d.summary)}catch(e){showMessage(e.message,true)}}
async function act(action){if(!current)return;let reviewer=$('reviewer').value.trim();if(!reviewer){showMessage('请先填写 Reviewer ID。',true);$('reviewer').focus();return}let value=$('value').value;try{let d=await json('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({queue_item_id:current.queue_item_id,action,value:value||null,reviewer_id:reviewer,note:$('note').value||null})});renderStats(d.summary);showMessage(d.record_created?'已追加 ledger record。':'已记录 skip，未创建 ledger record。');if(action!=='SKIP_FOR_LATER'&&$('remaining').checked&&filteredIndex>=filteredTotal-1)filteredIndex=Math.max(0,filteredIndex-1);await load()}catch(e){showMessage(e.message,true)}}
$('confirm').onclick=()=>act('CONFIRM_OCR_VALUE');$('correct').onclick=()=>act('ENTER_CORRECT_VALUE');$('unknown').onclick=()=>act('UNKNOWN');$('conflict').onclick=()=>act('CONFLICT');$('skip').onclick=()=>act('SKIP_FOR_LATER');$('reload').onclick=()=>load();$('market').onchange=()=>{filteredIndex=0;load()};$('remaining').onchange=()=>{filteredIndex=0;load()};$('zoom').oninput=e=>$('raw').style.transform=`scale(${e.target.value})`;document.onkeydown=e=>{if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName))return;if(e.key==='ArrowRight'){filteredIndex=Math.min(filteredTotal-1,filteredIndex+1);load()}else if(e.key==='ArrowLeft'){filteredIndex=Math.max(0,filteredIndex-1);load()}else if(e.key.toLowerCase()==='c')act('CONFIRM_OCR_VALUE');else if(e.key.toLowerCase()==='e')act('ENTER_CORRECT_VALUE');else if(e.key.toLowerCase()==='u')act('UNKNOWN');else if(e.key.toLowerCase()==='x')act('CONFLICT');else if(e.key.toLowerCase()==='s')act('SKIP_FOR_LATER')};$('reviewer').value=localStorage.getItem('jcfb-reviewer')||'';$('reviewer').onchange=()=>localStorage.setItem('jcfb-reviewer',$('reviewer').value);load();
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    server_version = "JCFBManualReview/1.0"

    @property
    def workbench(self) -> Workbench:
        return self.server.workbench  # type: ignore[attr-defined]

    def _send_json(self, value: Any, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self._send_json({"error": message}, status)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path in {"/", "/index.html"}:
                data = HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if parsed.path == "/api/health":
                self._send_json({"status": "ok", "workbench": self.workbench.summary()})
                return
            if parsed.path == "/api/item":
                query = parse_qs(parsed.query)
                market = query.get("market", [""])[0]
                remaining_only = query.get("remaining", ["0"])[0] == "1"
                index = max(0, int(query.get("index", ["0"])[0]))
                latest = self.workbench.latest_by_item()
                items = [row for row in self.workbench.queue if not market or row["market"] == market]
                if remaining_only:
                    items = [row for row in items if row["queue_item_id"] not in latest or latest[row["queue_item_id"]]["manual_review_status"] not in {"CONFIRMED", "UNKNOWN", "BLOCKED", "CONFLICT"}]
                if not items:
                    self._send_json({"item": None, "position": 0, "filtered_total": 0, "summary": self.workbench.summary()})
                    return
                index = min(index, len(items) - 1)
                self._send_json({"item": items[index], "position": index, "filtered_total": len(items), "summary": self.workbench.summary()})
                return
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "asset" and parts[1] in {"raw", "crop"}:
                data, content_type = self.workbench.asset(parts[2], parts[1])
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            self._error("not found", HTTPStatus.NOT_FOUND)
        except (ValueError, WorkbenchError) as exc:
            self._error(str(exc), HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/review":
            self._error("not found", HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            result = self.workbench.submit(
                queue_item_id=body.get("queue_item_id"),
                action=body.get("action"),
                value=body.get("value"),
                reviewer_id=body.get("reviewer_id"),
                note=body.get("note"),
            )
            self._send_json(result)
        except DuplicateSubmissionError as exc:
            self._error(str(exc), HTTPStatus.CONFLICT)
        except (ActionValidationError, WorkbenchError, ValueError, json.JSONDecodeError) as exc:
            self._error(str(exc), HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[manual-review] {format % args}")


def serve(workbench: Workbench, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    server.workbench = workbench  # type: ignore[attr-defined]
    print(f"JCFB V4 Manual Review Workbench: http://{host}:{port}/")
    print("Stop with Ctrl+C. No accepted payload, archive, r002, or training writes are enabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nManual Review Workbench stopped.")
    finally:
        server.server_close()
