"""국내 서버 문지기 — 컨텍스트·등고선 팩 요청을 규칙으로 거른다(절차는 docs/domestic_gate.md).

춘천 Always Free VM 한 대에서 nginx 뒤에 돈다. nginx가 팩 요청마다 이 서버에 허락을 묻고(auth_request) 통과하면 비공개 버킷에서
PAR(인증 없이 읽는 비밀 주소)로 가져와 돌려준다. PAR은 VM에만 있고 매니페스트에는 VM 주소만 적힌다.
Rhino 플러그인이 아니라 서버에서 도는 python3 — 표준 라이브러리만.

    sudo python3 server_gate.py install [PAR 주소]   # nginx 설정·systemd 등록. PAR을 생략하면 지난번 것
    python3 server_gate.py serve                    # systemd가 실행한다

한도는 하루(한국 시간 자정까지) 단위로 센다. 거절은 nginx가 사용자에게 403(설치 ID 없음)·404(없는 팩)·429(한도)로 돌려준다.
"""

import collections
import datetime
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

# 비정상 요청 기준 — 실측(2026-10-14 매니페스트): 생성 한 번에 컨텍스트·등고선 팩 2~16개(광화문 반경 2 km가 16개),
# 받은 팩은 PC에 남아 다시 받지 않는다. 전국 전체는 510개.
CLIENT_DAY_MAX = 60       # 설치 하나가 하루에 받는 팩 — 생성 4번 분량
CLIENT_SAME_MAX = 3       # 설치 하나가 같은 팩을 하루에 받는 횟수 — 실패 뒤 다시 받기
IP_DAY_MAX = 150          # IP 하나가 하루에 받는 팩 — 사무실·학교는 IP를 나눠 쓴다(10명 분량). 설치 ID를 바꿔 가며 받는 경우의 안전망
IP_UNKNOWN_MAX = 20       # IP 하나가 매니페스트에 없는 팩 이름을 하루에 묻는 횟수 — 넘으면 그날 그 IP 전부 거절(주소 훑기)
REQUIRE_CLIENT = True     # 설치 ID 없는 요청 거절 — 헤더를 보내는 판이 첫 배포라(2026-10) 옛 판 사용자가 없다
CONN_PER_IP = 4           # IP 하나의 동시 연결(nginx limit_conn)

MANIFEST_URL = "https://huggingface.co/datasets/hooooooooon/urbandesigntool-data/resolve/main/manifest.json"   # constants.DATA_MANIFEST_URL
MANIFEST_REFRESH_SECONDS = 3600
KST = datetime.timezone(datetime.timedelta(hours=9))
PORT = 8081
CLIENT_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")   # usage_stats.get_client_id(uuid4)
INSTALL_DIR = "/opt/udt"

NGINX_CONF = r"""# server_gate.py install이 쓴다 — 고치려면 server_gate.py를 고쳐 다시 install
limit_conn_zone $binary_remote_addr zone=udt_ip:10m;
log_format udt '$time_iso8601 $remote_addr $status $body_bytes_sent "$uri" "$http_user_agent" "$http_x_udt_client"';

server {
    listen 80 default_server;
    server_tokens off;
    access_log /var/log/nginx/udt.log udt;
    limit_conn udt_ip @CONN@;
    resolver 169.254.169.254 valid=300s;   # OCI VCN 내부 DNS — proxy_pass에 변수가 있으면 필요하다

    location ~ "^/([0-9]{5}_(context|terrain)\.db\.xz)$" {
        set $pack $1;
        auth_request /_gate;
        auth_request_set $gate_reason $upstream_http_x_gate_reason;
        error_page 403 = @denied;
        proxy_pass @PAR@$pack;
        proxy_ssl_server_name on;
        proxy_buffering off;
    }

    location = /_gate {
        internal;
        proxy_pass http://127.0.0.1:@PORT@;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Original-URI $request_uri;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location @denied {
        if ($gate_reason = limit) { return 429; }
        if ($gate_reason = unknown) { return 404; }
        return 403;
    }

    location / { return 404; }
}
"""

SYSTEMD_UNIT = """[Unit]
Description=UrbanDesignTool domestic gate
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 %s/server_gate.py serve
Restart=always
DynamicUser=yes

[Install]
WantedBy=multi-user.target
""" % INSTALL_DIR


class Gate:
    """하루치 요청 수를 세어 통과·거절을 정한다. 메모리에만 둔다 — 재시작하면 0부터."""

    def __init__(self, names=None):
        self.names = names     # 매니페스트의 국내 팩 파일 이름 set. None = 아직 못 받음(이름 검사 생략)
        self.day = None
        self.counts = collections.Counter()
        self.lock = threading.Lock()

    def check(self, ip, client, uri, day):
        # type: (str, str, str, str) -> str
        """
        입력: 요청 IP, X-UDT-Client 헤더, 요청 경로(/11680_context.db.xz), 오늘(한국 시간 날짜 문자열).
        처리: 날짜가 바뀌면 센 것을 비운다. 설치 ID 꼴이 아니면 없는 것으로 본다.
        출력: "" = 통과, 아니면 거절 이유 — no_client(설치 ID 없음, REQUIRE_CLIENT일 때만)·unknown(없는 팩)·limit(한도).
        """
        name = uri.split("?")[0].rsplit("/", 1)[-1]
        client = client if CLIENT_RE.match(client or "") else ""
        with self.lock:
            if day != self.day:
                self.day, self.counts = day, collections.Counter()
            if self.counts["unknown", ip] > IP_UNKNOWN_MAX:
                return "limit"
            if not client and REQUIRE_CLIENT:
                return "no_client"
            if self.names is not None and name not in self.names:
                self.counts["unknown", ip] += 1
                return "unknown"
            rules = [("ip", ip, IP_DAY_MAX)]
            if client:
                rules += [("client", client, CLIENT_DAY_MAX), ("same", client + name, CLIENT_SAME_MAX)]
            for kind, key, _limit in rules:
                self.counts[kind, key] += 1
            return "limit" if any(self.counts[kind, key] > limit for kind, key, limit in rules) else ""


GATE = Gate()


def get_today():
    # type: () -> str
    return datetime.datetime.now(KST).date().isoformat()


def get_pack_names(manifest):
    # type: (dict) -> set
    """매니페스트에서 국내 서버로 받는 팩(필지 팩 제외)의 파일 이름."""
    return {pack["url"].rsplit("/", 1)[-1] for pack in manifest["packs"] if not pack["name"].endswith("_site.db")}


def refresh_names():
    """매니페스트를 한 시간마다 다시 읽어 팩 이름을 바꾼다. 실패하면 있던 것을 쓴다."""
    while True:
        try:
            with urllib.request.urlopen(MANIFEST_URL, timeout=30) as response:
                GATE.names = get_pack_names(json.loads(response.read().decode("utf-8")))
        except Exception as exc:
            print("manifest 읽기 실패: %s" % exc, flush=True)
        time.sleep(MANIFEST_REFRESH_SECONDS)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        ip = self.headers.get("X-Real-IP", "")
        client = self.headers.get("X-UDT-Client", "")
        uri = self.headers.get("X-Original-URI", "")
        reason = GATE.check(ip, client, uri, get_today())
        if reason:
            print("거절 %s ip=%s client=%s %s" % (reason, ip, client or "-", uri), flush=True)
        self.send_response(403 if reason else 204)
        if reason:
            self.send_header("X-Gate-Reason", reason)
        self.end_headers()

    def log_message(self, *args):
        pass   # 요청마다 남기는 기록은 nginx access log(/var/log/nginx/udt.log)


def serve():
    threading.Thread(target=refresh_names, daemon=True).start()
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


def install(par_url=None):
    # type: (str) -> None
    """
    입력: 버킷 PAR 주소(.../p/<토큰>/n/<ns>/b/<bucket>/o/). None이면 지난번 것.
    처리: 이 파일을 INSTALL_DIR에 복사, nginx 사이트·systemd 서비스를 쓰고 nginx -t가 통과해야 다시 읽힌다. 80번 포트를 연다(OCI Ubuntu 이미지의 iptables).
    """
    par_path = os.path.join(INSTALL_DIR, "par")
    os.makedirs(INSTALL_DIR, exist_ok=True)
    if par_url:
        if not re.match(r"^https://[^/]+/p/[^/]+/n/[^/]+/b/[^/]+/o/$", par_url):
            sys.exit("PAR 주소 꼴이 아닙니다(…/o/로 끝나는 버킷 PAR): %s" % par_url)
        with open(os.open(par_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            f.write(par_url)
    with open(par_path) as f:
        par_url = f.read().strip()
    if os.path.abspath(__file__) != os.path.join(INSTALL_DIR, "server_gate.py"):   # 설치본으로 다시 install할 때는 복사하지 않는다
        shutil.copy(os.path.abspath(__file__), os.path.join(INSTALL_DIR, "server_gate.py"))
    conf = NGINX_CONF.replace("@PAR@", par_url).replace("@PORT@", str(PORT)).replace("@CONN@", str(CONN_PER_IP))
    with open(os.open("/etc/nginx/sites-available/udt", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(conf)   # PAR이 들어 있어 root만 읽는다
    if not os.path.exists("/etc/nginx/sites-enabled/udt"):
        os.symlink("/etc/nginx/sites-available/udt", "/etc/nginx/sites-enabled/udt")
    if os.path.lexists("/etc/nginx/sites-enabled/default"):
        os.remove("/etc/nginx/sites-enabled/default")
    with open("/etc/systemd/system/udt-gate.service", "w") as f:
        f.write(SYSTEMD_UNIT)
    for command in (["systemctl", "daemon-reload"], ["systemctl", "enable", "udt-gate"], ["systemctl", "restart", "udt-gate"],
                    ["nginx", "-t"], ["systemctl", "reload", "nginx"]):
        subprocess.run(command, check=True)
    if subprocess.run(["iptables", "-C", "INPUT", "-p", "tcp", "--dport", "80", "-j", "ACCEPT"], stderr=subprocess.DEVNULL).returncode:
        subprocess.run(["iptables", "-I", "INPUT", "1", "-p", "tcp", "--dport", "80", "-j", "ACCEPT"], check=True)
        subprocess.run(["netfilter-persistent", "save"], check=True)
    print("설치 끝 — 거절 기록: journalctl -u udt-gate, 요청 기록: /var/log/nginx/udt.log")


if __name__ == "__main__":
    if sys.argv[1:2] == ["serve"]:
        serve()
    elif sys.argv[1:2] == ["install"]:
        install(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        sys.exit(__doc__)
