// Gorani 웹판 워커 — Pyodide에서 엔진(cmd_web.py)을 돌린다. 페이지(web_app.html)와 postMessage로만 말한다.
//   페이지 → 워커  {boot: {scripts, files, manifest}}   scripts.zip을 풀고 cmd_web.start
//                  {cmd: {...}}                        패널 명령 하나(docs/panel_ui.md) → cmd_web.handle
//   워커 → 페이지  {type: "web_boot", text, ready}      불러오기 진행
//                  패널 푸시(dict)                      그대로 패널로
//                  {type: "web_open", name, bytes, view} 파일 내용(폴더는 zip) — 페이지가 내려받기·새 탭·3D 뷰어
//                  {type: "web_model", bytes}           생성이 끝난 context.glb — 페이지 뷰어가 바로 그린다
//                  {type: "web_persist", files}         ~/.gorani(설정·최근 대상지·설치 ID)가 바뀌면 — 페이지가 localStorage에
//                  {type: "web_idle"}                   명령 하나를 다 처리했다(페이지가 생성 중 취소를 판단한다)
"use strict";
const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";   // numpy·shapely 2.1+가 든 판(2026-10-19 확인)
const APP_DIR = "/gorani";
const PREFS_DIR = "/home/pyodide/.gorani";   // site_prefs.PREFS_DIR(~ = /home/pyodide)
importScripts(PYODIDE_URL + "pyodide.js");

let py = null, cmdWeb = null, persisted = "";
const queue = [];

function post(msg, transfer) { self.postMessage(msg, transfer || []); }

function readPrefs() {
  const files = {};
  for (const name of py.FS.readdir(PREFS_DIR)) {
    if (name === "." || name === "..") continue;
    const path = PREFS_DIR + "/" + name;
    if (py.FS.isFile(py.FS.stat(path).mode)) files[name] = py.FS.readFile(path, { encoding: "utf8" });
  }
  return files;
}

function persist() {
  const files = readPrefs(), text = JSON.stringify(files);
  if (text !== persisted) { persisted = text; post({ type: "web_persist", files }); }
}

function onPush(text) {
  const msg = JSON.parse(text);
  if (msg.type === "web_open" && msg.path) {   // 파일 내용을 실어 보낸다 — 페이지는 가상 파일계를 모른다
    const bytes = py.FS.readFile(msg.path);
    post({ type: "web_open", name: msg.name || msg.path.split("/").pop(), path: msg.path, view: !!msg.view, bytes }, [bytes.buffer]);
    return;
  }
  post(msg);
  if (msg.type === "done" && msg.ok && msg.context && msg.context.path) {
    const bytes = py.FS.readFile(msg.context.path);
    post({ type: "web_model", path: msg.context.path, bytes }, [bytes.buffer]);
  }
}

async function boot(cfg) {
  post({ type: "web_boot", text: "파이썬 엔진 받는 중" });
  py = await loadPyodide({ indexURL: PYODIDE_URL, env: { HOME: "/home/pyodide", GORANI_HOST: "web" } });
  post({ type: "web_boot", text: "numpy·shapely 받는 중" });
  await py.loadPackage(["numpy", "shapely"], { messageCallback: () => {} });
  post({ type: "web_boot", text: "Gorani 불러오는 중" });
  const zip = await (await fetch(cfg.scripts)).arrayBuffer();
  py.unpackArchive(zip, "zip", { extractDir: APP_DIR + "/scripts" });
  py.FS.mkdirTree(PREFS_DIR);
  for (const [name, text] of Object.entries(cfg.files || {})) py.FS.writeFile(PREFS_DIR + "/" + name, text);
  persisted = JSON.stringify(readPrefs());
  py.runPython(`import sys; sys.path.insert(0, "${APP_DIR}/scripts")`);
  cmdWeb = py.pyimport("cmd_web");
  cmdWeb.start(onPush, JSON.stringify({ manifest: cfg.manifest || "" }));
  post({ type: "web_boot", text: "", ready: true });
  while (queue.length) run(queue.shift());
}

function run(cmd) {
  try {
    cmdWeb.handle(JSON.stringify(cmd));
  } catch (e) {   // 컨트롤러 _guard 밖 — 워커가 죽지 않게 패널 오류로
    post({ type: "error", context: cmd.cmd === "generate" ? "generate" : "init", text: "예상 밖 오류", detail: String(e) });
  }
  persist();
  post({ type: "web_idle" });
}

self.onmessage = (e) => {
  const m = e.data;
  if (m.boot) { boot(m.boot).catch((err) => post({ type: "web_boot", text: "엔진을 불러오지 못했습니다: " + err, failed: true })); return; }
  if (m.cmd) { if (cmdWeb) run(m.cmd); else queue.push(m.cmd); }
};
