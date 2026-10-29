"""관리자 대시보드 데이터 — GA(플러그인·웹 속성)·yak·Hugging Face·국내 서버(Oracle)를 한 번에 모아 화면이 바로 쓰는 모양으로 낸다
(Rhino 밖 python3, 이 Mac에서만).

    python3 scripts/dev_stats.py [일수] [--demo]   # 결과 JSON을 찍는다(관리자 페이지 없이 확인). --demo = GA 자리에 예시 데이터

열쇠는 저장소 밖(constants.ADMIN_DIR)·이 Mac에만 있다: GA 서비스 계정 키, 국내 서버 SSH 키(~/.ssh/udt-gate.key), OCI CLI(~/.oci/config).
GA 토큰 서명(RS256)은 macOS openssl로 한다 — pip 패키지 없이 표준 라이브러리만.
파일별 다운로드 수는 Hugging Face가 주지 않는다(데이터셋 합계만) — 지역별 횟수는 GA pack_download(packs = 시군구·일본 시 코드)와
국내 서버 nginx 기록(컨텍스트·등고선 팩)으로 센다.
기간 비교: 모든 '[이번, 지난]' 쌍은 같은 길이의 바로 앞 기간과 비교한다.
"""

import base64
import collections
import concurrent.futures
import datetime
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)
import constants  # noqa: E402

GA_READ_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
GA_EDIT_SCOPE = "https://www.googleapis.com/auth/analytics.edit"
GA_ADMIN_URL = "https://analyticsadmin.googleapis.com/v1beta/"
GA_DATA_URL = "https://analyticsdata.googleapis.com/v1beta/properties/%s"
GA_BATCH_MAX = 5   # batchRunReports 한 번에 보고서 5개까지
GATE_LINE = re.compile(r'^(\S+) (\S+) (\d+) (\d+) "([^"]*)" "([^"]*)" "([^"]*)"$')   # server_gate.py log_format udt
PNU_PARAMS = ("pnus", "pnus_2", "pnus_3", "pnus_4")


def _get_json(url, body=None, headers=None, timeout=30):
    # type: (str, object, dict, int) -> dict
    """GET(body 없음)·POST(dict = JSON, str = 폼). HTTP 오류는 응답 본문의 message로 다시 던진다(GA는 켜야 할 API 주소를 알려 준다)."""
    data, headers = None, dict(headers or {})
    if isinstance(body, dict):
        data, headers["Content-Type"] = json.dumps(body).encode("utf-8"), "application/json"
    elif body is not None:
        data, headers["Content-Type"] = body.encode("utf-8"), "application/x-www-form-urlencoded"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", "replace")
        try:
            text = json.loads(text)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            pass
        raise RuntimeError("%s %s" % (error.code, text[:300])) from None


def get_period(days, today=None):
    # type: (int, datetime.date) -> dict
    """이번 기간(오늘 포함 days일)과 바로 앞 같은 길이 기간. 출력: {"dates": [ISO…], "cur": (시작, 끝), "prev": (시작, 끝)}."""
    today = today or datetime.date.today()
    start = today - datetime.timedelta(days=days - 1)
    prev_end = start - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=days - 1)
    return {"dates": [(start + datetime.timedelta(days=i)).isoformat() for i in range(days)],
            "cur": (start.isoformat(), today.isoformat()), "prev": (prev_start.isoformat(), prev_end.isoformat())}


def get_split_counts(rows, labels):
    # type: (list, dict) -> list
    """
    입력: [[값, 횟수]] — 이벤트 매개변수 하나(값이 '11110,11140'처럼 쉼표로 이어진 것 포함), labels = 코드 → 지역 이름.
    처리: 쉼표로 나눠 값마다 횟수를 더한다. '(not set)'(그 매개변수가 없는 이벤트)은 뺀다. 지역 코드면 이름을 붙인다.
    출력: [[값, 횟수]] 많은 순.
    """
    counts = collections.Counter()
    for value, count in rows:
        for part in str(value).split(","):
            part = part.strip()
            if part and part != "(not set)":
                counts[part] += count
    return [[("%s %s" % (value, labels[value])) if value in labels else value, count] for value, count in counts.most_common()]


# ── GA ──

def get_ga_token(key_path, scope=GA_READ_SCOPE):
    # type: (str, str) -> str
    """
    입력: 서비스 계정 키 JSON 경로, 권한 범위(읽기 | 맞춤 측정기준 등록은 편집).
    처리: JWT(RS256)를 만들어 openssl로 서명 — 개인 키는 표준 입력으로만 넘기고 디스크에 다시 쓰지 않는다. 구글 토큰 주소와 바꾼다.
    출력: 1시간짜리 접근 토큰.
    """
    with open(key_path, encoding="utf-8") as f:
        key = json.load(f)
    encode = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=")
    now = int(time.time())
    claim = {"iss": key["client_email"], "scope": scope, "aud": key["token_uri"], "iat": now, "exp": now + 3600}
    signing = encode(b'{"alg":"RS256","typ":"JWT"}') + b"." + encode(json.dumps(claim).encode("utf-8"))
    with tempfile.NamedTemporaryFile(suffix=".jwt") as f:
        f.write(signing)
        f.flush()
        signature = subprocess.run(["openssl", "dgst", "-sha256", "-sign", "/dev/stdin", f.name],
                                   input=key["private_key"].encode("utf-8"), capture_output=True, check=True).stdout
    assertion = (signing + b"." + encode(signature)).decode("ascii")
    body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
    return _get_json(key["token_uri"], body)["access_token"]


def get_report_rows(report):
    # type: (dict) -> list
    """runReport 응답 → [{차원·지표 이름: 값}] (지표는 숫자). 기간이 둘이면 'dateRange' 차원(cur|prev)이 붙는다."""
    names = [h["name"] for h in report.get("dimensionHeaders", [])] + [h["name"] for h in report.get("metricHeaders", [])]
    return [dict(zip(names, [v["value"] for v in row.get("dimensionValues", [])] + [float(v["value"]) for v in row.get("metricValues", [])]))
            for row in report.get("rows", [])]


def _report(period, dims, metrics, compare=False, event=None, limit=1000, exclude_dev=False):
    # type: (dict, list, list, bool, str, int, bool) -> dict
    """runReport 요청 하나. event = 그 이벤트만, exclude_dev = 개발자 표시(customEvent:dev = 1)가 붙은 이벤트를 뺀다."""
    ranges = [{"startDate": period["cur"][0], "endDate": period["cur"][1], "name": "cur"}]
    if compare:
        ranges.append({"startDate": period["prev"][0], "endDate": period["prev"][1], "name": "prev"})
    body = {"dateRanges": ranges, "dimensions": [{"name": d} for d in dims], "metrics": [{"name": m} for m in metrics], "limit": limit}
    filters = []
    if event:
        filters.append({"filter": {"fieldName": "eventName", "stringFilter": {"value": event}}})
    if exclude_dev:
        filters.append({"notExpression": {"filter": {"fieldName": "customEvent:dev", "stringFilter": {"value": "1"}}}})
    if filters:
        body["dimensionFilter"] = filters[0] if len(filters) == 1 else {"andGroup": {"expressions": filters}}
    return body


def _get_pair(rows, metric, **match):
    # type: (list, str, object) -> list
    """기간 비교 보고서에서 [이번, 지난] 값(match = 차원 조건)."""
    pick = lambda name: sum(r[metric] for r in rows if r.get("dateRange", "cur") == name and all(r.get(k) == v for k, v in match.items()))
    return [pick("cur"), pick("prev")]


def _get_ranked(rows, dim, metric, limit=20):
    # type: (list, str, str, int) -> list
    counts = collections.Counter()
    for row in rows:
        if row.get(dim) not in (None, "", "(not set)"):
            counts[row[dim]] += row[metric]
    return [[name, value] for name, value in counts.most_common(limit)]


def _get_daily(rows, dates, metric, value_dim=None, value=None):
    # type: (list, list, str, str, str) -> list
    """date 차원 보고서 → 기간 날짜마다 값(없는 날 0)."""
    by_date = collections.Counter()
    for row in rows:
        if value_dim is None or row.get(value_dim) == value:
            by_date[row["date"]] += row[metric]
    return [by_date.get(d.replace("-", ""), 0) for d in dates]


def get_dimension_counts(rows, param, labels):
    # type: (list, str, dict) -> dict
    """[eventName, customEvent:param] × eventCount 행 → {"이벤트.param": [[값, 횟수]]}. 쉼표 목록은 나눈다(packs)."""
    by_event = collections.defaultdict(list)
    for row in rows:
        by_event[row["eventName"]].append([row["customEvent:" + param], row["eventCount"]])
    counts = dict(("%s.%s" % (event, param), get_split_counts(values, labels)) for event, values in by_event.items())
    return dict((key, rows) for key, rows in counts.items() if rows)   # 그 매개변수를 보내지 않는 이벤트((not set)뿐)는 뺀다


def get_region_counts(pnu_rows, labels):
    # type: (list, dict) -> list
    """build 이벤트 pnus* 값(쉼표 PNU 목록)을 시군구(PNU 앞 5자리)로 모은다. 이벤트 하나가 같은 시군구를 여러 번 세지 않게 한다."""
    counts = collections.Counter()
    for value, count in pnu_rows:
        for code in set(p.strip()[:5] for p in str(value).split(",") if p.strip()[:5].isdigit()):
            counts[code] += count
    return [[("%s %s" % (code, labels[code])) if code in labels else code, n] for code, n in counts.most_common(30)]


def get_app_stats(run, period, metadata, labels, exclude_dev=False):
    # type: (object, dict, dict, dict, bool) -> dict
    """
    입력: run(보고서 목록 → 응답 목록), 기간, 속성 메타데이터(등록된 맞춤 측정기준·측정항목), 지역 이름.
    처리: 사용자 [이번, 지난]·이벤트별 횟수·사용자, 날짜별 사용자·이벤트, OS·언어·나라, 등록된 매개변수별 값, 대상지 점(lng·lat), 평균(소요 시간·건물 수).
    출력: 대시보드 App 모양.
    """
    dates = period["dates"]
    customs = set(d["apiName"].split(":", 1)[1] for d in metadata.get("dimensions", []) if d["apiName"].startswith("customEvent:"))
    report = lambda *args, **kwargs: _report(*args, exclude_dev=exclude_dev and "dev" in customs, **kwargs)   # dev 미등록이면 거를 수 없다
    averages = [m["apiName"] for m in metadata.get("metrics", []) if m["apiName"].startswith("averageCustomEvent:")]
    requests = [
        report(period, [], ["activeUsers", "newUsers"], compare=True),
        report(period, ["eventName"], ["eventCount", "totalUsers"], compare=True),
        report(period, ["date"], ["activeUsers", "newUsers"]),
        report(period, ["date", "eventName"], ["eventCount"], limit=10000),
        report(period, ["operatingSystem"], ["activeUsers"]),
        report(period, ["language"], ["activeUsers"]),
        report(period, ["country"], ["activeUsers"]),
    ]
    params = [p for p in constants.ADMIN_GA_DIMENSIONS["app"] if p in customs and p not in ("lng", "lat", "dev") + PNU_PARAMS]
    requests += [report(period, ["eventName", "customEvent:" + p], ["eventCount"], limit=500) for p in params]
    pnus = [p for p in PNU_PARAMS if p in customs]
    requests += [report(period, ["customEvent:" + p], ["eventCount"], event="build", limit=2000) for p in pnus]
    has_points = "lng" in customs and "lat" in customs
    if has_points:
        requests.append(report(period, ["customEvent:lng", "customEvent:lat"], ["eventCount"], event="build", limit=5000))
    if "result" in customs:
        requests.append(report(period, ["date", "customEvent:result"], ["eventCount"], event="build"))
    if averages:
        requests.append(report(period, ["eventName"], averages, event="build"))
    reports = [get_report_rows(r) for r in run(requests)]
    totals, events, daily, daily_events, oses, languages, countries = reports[:7]
    rest = reports[7:]
    dims = {}
    for param in params:
        dims.update(get_dimension_counts(rest.pop(0), param, labels))
    pnu_rows = []
    for param in pnus:
        pnu_rows += [[r["customEvent:" + param], r["eventCount"]] for r in rest.pop(0)]
    regions = get_region_counts(pnu_rows, labels)
    if regions:
        dims["build.region"] = regions
    points = []
    if has_points:
        for row in rest.pop(0):
            try:
                points.append([round(float(row["customEvent:lng"]), 4), round(float(row["customEvent:lat"]), 4), row["eventCount"]])
            except ValueError:   # (not set)
                pass
    daily_result = rest.pop(0) if "result" in customs else []
    average = {}
    if averages:
        for row in rest.pop(0):
            average = {"build." + name.split(":", 1)[1]: row[name] for name in averages}
    return {
        "totals": {"users": _get_pair(totals, "activeUsers"), "new_users": _get_pair(totals, "newUsers")},
        "events": {name: {"count": _get_pair(events, "eventCount", eventName=name), "users": _get_pair(events, "totalUsers", eventName=name)}
                   for name in set(r["eventName"] for r in events)},
        "daily": {"users": _get_daily(daily, dates, "activeUsers"), "new_users": _get_daily(daily, dates, "newUsers"),
                  "opens": _get_daily(daily_events, dates, "eventCount", "eventName", "panel_open"),
                  "builds": _get_daily(daily_events, dates, "eventCount", "eventName", "build"),
                  "errors": _get_daily(daily_events, dates, "eventCount", "eventName", "app_error"),   # 0.3.6 전 'error'는 GA4 예약어라 버려졌다
                  "build_failed": _get_daily(daily_result, dates, "eventCount", "customEvent:result", "failed") if daily_result else None},
        "dims": dims, "points": points, "average": average,
        "os": _get_ranked(oses, "operatingSystem", "activeUsers"), "language": _get_ranked(languages, "language", "activeUsers"),
        "country": _get_ranked(countries, "country", "activeUsers"),
        "missing": [p for p in constants.ADMIN_GA_DIMENSIONS["app"] if p not in customs],
    }


def get_web_stats(run, period, metadata, labels, exclude_dev=False):
    # type: (object, dict, dict, dict, bool) -> dict
    """웹사이트 속성 — 방문자·세션·참여 [이번, 지난], 날짜별, 채널·출처·나라·페이지·기기·언어, 이벤트(설치 의도), 등록된 매개변수."""
    dates = period["dates"]
    customs = set(d["apiName"].split(":", 1)[1] for d in metadata.get("dimensions", []) if d["apiName"].startswith("customEvent:"))
    params = [p for p in constants.ADMIN_GA_DIMENSIONS["web"] if p in customs and p != "dev"]
    report = lambda *args, **kwargs: _report(*args, exclude_dev=exclude_dev and "dev" in customs, **kwargs)
    requests = [
        report(period, [], ["activeUsers", "newUsers", "sessions", "averageSessionDuration", "engagementRate"], compare=True),
        report(period, ["eventName"], ["eventCount", "totalUsers"], compare=True),
        report(period, ["date"], ["activeUsers", "sessions"]),
        report(period, ["sessionDefaultChannelGroup"], ["sessions"]),
        report(period, ["sessionSource"], ["sessions"]),
        report(period, ["country"], ["activeUsers"]),
        report(period, ["pagePath"], ["screenPageViews"]),
        report(period, ["deviceCategory"], ["activeUsers"]),
        report(period, ["language"], ["activeUsers"]),
    ] + [report(period, ["eventName", "customEvent:" + p], ["eventCount"], limit=200) for p in params]
    reports = [get_report_rows(r) for r in run(requests)]
    totals, events, daily, channels, sources, countries, pages, devices, languages = reports[:9]
    dims = {}
    for param, rows in zip(params, reports[9:]):
        dims.update(get_dimension_counts(rows, param, labels))
    return {
        "totals": {"users": _get_pair(totals, "activeUsers"), "new_users": _get_pair(totals, "newUsers"), "sessions": _get_pair(totals, "sessions"),
                   "engagement": _get_pair(totals, "averageSessionDuration"), "engaged_rate": _get_pair(totals, "engagementRate")},
        "events": {name: {"count": _get_pair(events, "eventCount", eventName=name), "users": _get_pair(events, "totalUsers", eventName=name)}
                   for name in set(r["eventName"] for r in events)},
        "daily": {"users": _get_daily(daily, dates, "activeUsers"), "sessions": _get_daily(daily, dates, "sessions")},
        "channels": _get_ranked(channels, "sessionDefaultChannelGroup", "sessions"), "sources": _get_ranked(sources, "sessionSource", "sessions"),
        "country": _get_ranked(countries, "country", "activeUsers"), "pages": _get_ranked(pages, "pagePath", "screenPageViews"),
        "devices": _get_ranked(devices, "deviceCategory", "activeUsers"), "language": _get_ranked(languages, "language", "activeUsers"),
        "dims": dims, "missing": [p for p in constants.ADMIN_GA_DIMENSIONS["web"] if p not in customs],
    }


def get_property_kinds(token):
    # type: (str) -> list
    """서비스 계정이 볼 수 있는 속성 → [(속성 번호, 이름, rhino|sketchup|web)]. 측정 ID로 구분하고 모르는 속성(옛 Blender)은 뺀다."""
    headers = {"Authorization": "Bearer " + token}
    kinds = dict((ids[0], host) for host, ids in constants.GA_STREAMS.items())
    kinds[constants.ADMIN_GA_WEB_ID] = "web"
    found = []
    for account in _get_json(GA_ADMIN_URL + "accountSummaries?pageSize=200", headers=headers).get("accountSummaries", []):
        for prop in account.get("propertySummaries", []):
            property_id = prop["property"].split("/")[-1]
            streams = _get_json(GA_ADMIN_URL + "properties/%s/dataStreams" % property_id, headers=headers).get("dataStreams", [])
            kind = next((kinds[s["webStreamData"]["measurementId"]] for s in streams
                         if (s.get("webStreamData") or {}).get("measurementId") in kinds), None)
            if kind:
                found.append((property_id, prop.get("displayName") or property_id, kind))
    return found


def get_ga(period, labels, exclude_dev=False):
    # type: (dict, dict, bool) -> dict
    """
    출력: {"apps": {host: App}, "web": Web|None, "status": 연결 상태 문장, "ok": bool, "properties": [(번호, 이름, 종류)]}.
    키가 없거나 막히면 ok False와 상태 문장 — 다른 출처는 그대로 보인다.
    """
    result = {"apps": {}, "web": None, "ok": False, "properties": [], "status": ""}
    if not os.path.exists(constants.ADMIN_GA_KEY_PATH):
        result["status"] = "서비스 계정 키가 없습니다"
        return result
    try:
        token = get_ga_token(constants.ADMIN_GA_KEY_PATH)
        result["properties"] = get_property_kinds(token)
    except Exception as error:
        result["status"] = "연결하지 못했습니다: %s" % error
        return result
    if not result["properties"]:
        result["status"] = "서비스 계정이 볼 수 있는 Gorani 속성이 없습니다 — 각 속성에 서비스 계정 이메일을 추가하세요"
        return result
    headers = {"Authorization": "Bearer " + token}
    errors = []
    for property_id, name, kind in result["properties"]:
        def run(requests, property_id=property_id):
            reports = []
            for start in range(0, len(requests), GA_BATCH_MAX):
                body = {"requests": requests[start:start + GA_BATCH_MAX]}
                reports += _get_json(GA_DATA_URL % property_id + ":batchRunReports", body, headers)["reports"]
            return reports
        try:
            metadata = _get_json(GA_DATA_URL % property_id + "/metadata", headers=headers)
            stats = (get_web_stats if kind == "web" else get_app_stats)(run, period, metadata, labels, exclude_dev)
            stats.update(property=property_id, name=name)
            if kind == "web":
                result["web"] = stats
            else:
                result["apps"][kind] = stats
        except Exception as error:
            errors.append("%s: %s" % (name, error))
    result["ok"] = not errors
    result["status"] = " · ".join(errors) or "속성 %d개 연결됨" % len(result["properties"])
    return result


def register_dimensions():
    # type: () -> list
    """
    처리: 연결된 속성마다 ADMIN_GA_DIMENSIONS·ADMIN_GA_METRICS 중 아직 없는 것을 이벤트 범위 맞춤 정의로 만든다.
          서비스 계정이 그 속성의 '편집자'여야 한다(뷰어면 403).
    출력: 한 일 문장 목록.
    """
    token = get_ga_token(constants.ADMIN_GA_KEY_PATH, GA_EDIT_SCOPE)
    headers = {"Authorization": "Bearer " + token}
    done = []
    for property_id, name, kind in get_property_kinds(token):
        group = "web" if kind == "web" else "app"
        base = GA_ADMIN_URL + "properties/%s/" % property_id
        have = set(d["parameterName"] for d in _get_json(base + "customDimensions?pageSize=200", headers=headers).get("customDimensions", []))
        have_metrics = set(m["parameterName"] for m in _get_json(base + "customMetrics?pageSize=200", headers=headers).get("customMetrics", []))
        added = []
        for param in constants.ADMIN_GA_DIMENSIONS[group]:
            if param not in have:
                _get_json(base + "customDimensions", {"parameterName": param, "displayName": param, "scope": "EVENT"}, headers)
                added.append(param)
        for param, unit in constants.ADMIN_GA_METRICS[group]:
            if param not in have_metrics:
                _get_json(base + "customMetrics", {"parameterName": param, "displayName": param, "scope": "EVENT", "measurementUnit": unit}, headers)
                added.append(param)
        done.append("%s: %s" % (name, ("등록 " + ", ".join(added)) if added else "이미 모두 등록됨"))
    return done


def get_demo_ga(period, labels, exclude_dev=False):
    # type: (dict, dict, bool) -> dict
    """GA 연결 전 화면 확인용 예시 데이터(고정 시드). 화면은 '예시 데이터' 띠를 띄운다 — 실제 숫자가 아니다."""
    rand = random.Random(7)
    days = len(period["dates"])
    wave = lambda base, spread: [max(0, int(base + spread * rand.random() - (spread / 2 if i % 7 in (5, 6) else 0))) for i in range(days)]
    pair = lambda cur, ratio: [cur, int(cur / ratio)]
    region = lambda code: "%s %s" % (code, labels.get(code, ""))
    codes = ["11110", "11680", "11200", "26350", "41135", "11440", "jp13101", "28185"]

    def app(scale, korea_share, name):
        users = wave(14 * scale, 10 * scale)
        builds = [int(u * (1.4 + rand.random())) for u in users]
        return {
            "name": name, "property": "-",
            "totals": {"users": pair(int(sum(users) * .45), 1.12), "new_users": pair(int(sum(users) * .18), 1.3)},
            "events": {"panel_open": {"count": pair(sum(users) * 2, 1.15), "users": pair(int(sum(users) * .45), 1.12)},
                       "build": {"count": pair(sum(builds), 1.2), "users": pair(int(sum(users) * .3), 1.18)},
                       "pack_download": {"count": pair(int(sum(builds) * .6), 1.1), "users": pair(int(sum(users) * .2), 1.1)},
                       "app_error": {"count": pair(int(sum(builds) * .05), .8), "users": pair(int(sum(users) * .04), .9)}},
            "daily": {"users": users, "new_users": [int(u * .3) for u in users], "opens": [u * 2 for u in users], "builds": builds,
                      "errors": [int(b * .05 + rand.random()) for b in builds], "build_failed": [int(b * .07) for b in builds]},
            "dims": {"panel_open.version": [["0.3.2", 40 * scale], ["0.3.1", 22 * scale], ["0.2.2", 9 * scale], ["0.1.0", 4 * scale]],
                     "panel_open.rhino": [["8.24", 30 * scale], ["8.21", 12 * scale], ["7.37", 6 * scale], ["8.9", 4 * scale]],
                     "build.mode": [["lots", 60 * scale], ["point", 31 * scale], ["area", 14 * scale]],
                     "build.result": [["ok", 93 * scale], ["failed", 7 * scale], ["cancelled", 5 * scale]],
                     "build.korea": [["1", int(100 * korea_share * scale)], ["0", int(100 * (1 - korea_share) * scale)]],
                     "build.radius": [["500", 48 * scale], ["300", 30 * scale], ["1000", 18 * scale], ["2000", 6 * scale]],
                     "build.placement": [["local", 80 * scale], ["world", 21 * scale]],
                     "build.error": [["terrain_split", 4 * scale], ["overpass_timeout", 2 * scale], ["no_lot", 1 * scale]],
                     "error.context": [["generate", 5 * scale], ["make_2d", 3 * scale], ["download", 2 * scale]],
                     "error.error": [["TimeoutError", 4 * scale], ["ValueError", 3 * scale], ["KeyError", 1 * scale]],
                     "pack_download.packs": [[region(c), (9 - i) * 3 * scale] for i, c in enumerate(codes)],
                     "build.region": [[region(c), (9 - i) * 4 * scale] for i, c in enumerate(codes) if c.isdigit()]},
            "points": [[126.97 + rand.gauss(0, .08), 37.56 + rand.gauss(0, .06), rand.randint(1, 6)] for _ in range(30 * scale)]
            + [[129.07 + rand.gauss(0, .05), 35.17 + rand.gauss(0, .04), rand.randint(1, 3)] for _ in range(6 * scale)]
            + [[139.7 + rand.gauss(0, .1), 35.68 + rand.gauss(0, .08), rand.randint(1, 3)] for _ in range(5 * scale)]
            + [[rand.uniform(-120, 150), rand.uniform(-35, 55), 1] for _ in range(8)],
            "average": {"build.elapsed_s": 41.5 + 10 * rand.random(), "build.buildings": 1830 + 400 * rand.random()},
            "os": [["Windows", 70 * scale], ["Macintosh", 26 * scale]],
            "language": [["ko-kr", 61 * scale], ["en-us", 22 * scale], ["ja-jp", 9 * scale]], "country": [], "missing": [],
        }

    web_users = wave(60, 40)
    total = sum(web_users)
    web = {
        "name": "Gorani 웹 (예시)", "property": "-",
        "totals": {"users": pair(total, 1.25), "new_users": pair(int(total * .8), 1.3), "sessions": pair(int(total * 1.3), 1.2),
                   "engagement": [74.0, 61.0], "engaged_rate": [.58, .52]},
        "events": {"page_view": {"count": pair(total * 2, 1.2), "users": pair(total, 1.2)},
                   "install_tab": {"count": pair(int(total * .3), 1.1), "users": pair(int(total * .22), 1.1)},
                   "copy_command": {"count": pair(int(total * .12), 1.05), "users": pair(int(total * .1), 1.05)},
                   "demo_play": {"count": pair(int(total * .35), 1.3), "users": pair(int(total * .3), 1.3)}},
        "daily": {"users": web_users, "sessions": [int(u * 1.3) for u in web_users]},
        "channels": [["Organic Search", 520], ["Direct", 410], ["Referral", 230], ["Organic Social", 120]],
        "sources": [["google", 480], ["(direct)", 410], ["food4rhino.com", 160], ["github.com", 70], ["naver", 40]],
        "country": [["South Korea", 820], ["Japan", 140], ["United States", 90], ["Germany", 30]],
        "pages": [["/gorani/", 1200], ["/gorani/en/", 420], ["/gorani/ja/", 160]],
        "devices": [["desktop", 900], ["mobile", 230], ["tablet", 20]], "language": [["ko-kr", 800], ["en-us", 260], ["ja-jp", 130]],
        "dims": {"install_tab.host": [["rhino", 210], ["sketchup", 120], ["blender", 60]]}, "missing": [],
    }
    return {"apps": {"rhino": app(3, .78, "Gorani Rhino (예시)"), "sketchup": app(1, .9, "Gorani SketchUp (예시)")},
            "web": web, "ok": True, "properties": [], "status": "예시 데이터 — 실제 숫자가 아닙니다"}


# ── 데이터 팩·배포 ──

def get_pack_labels(manifests):
    # type: (list) -> dict
    """매니페스트 팩 → {'11110': '서울특별시 종로구', 'jp01100': '札幌市', '11110_context.db': '… 건물·도로·수계'(팩 이름 그대로)}."""
    labels = {}
    for manifest in manifests:
        for pack in manifest.get("packs", []):
            labels[pack["name"].split("_")[0]] = pack.get("label", "").rsplit(" ", 1)[0]
            labels[pack["name"]] = pack.get("label", "")
    return labels


def get_inventory(manifests):
    # type: (list) -> list
    """올린 팩 종류별 [종류, 곳, 팩 수, 압축 크기]. 일본 팩 이름 = jp + 코드."""
    kinds = collections.OrderedDict([("site", ["한국 필지", "Hugging Face"]), ("context", ["한국 건물·도로·수계", "국내 서버"]),
                                     ("terrain", ["한국 등고선", "국내 서버"]), ("jp", ["일본 건물·도로", "Hugging Face"])])
    sums = collections.defaultdict(lambda: [0, 0])
    for manifest in manifests:
        for pack in manifest.get("packs", []):
            key = "jp" if pack["name"].startswith("jp") else pack["name"].rsplit("_", 1)[-1].split(".")[0]
            sums[key][0] += 1
            sums[key][1] += pack.get("xz_size", 0)
    return [kinds[k] + sums[k] for k in kinds if sums[k][0]]


def get_yak_builds(version):
    # type: (dict) -> list
    """yak 버전 하나의 배포판 이름 — rh8_0-any → 'Rhino 8', rh7_0-mac → 'Rhino 7 mac'. Rhino 8판과 7판은 같은 버전으로 같이 올린다."""
    return sorted(("Rhino %s%s" % (d["rhino_version"][2:].split("_")[0], "" if d["platform"] == "any" else " " + d["platform"])
                   for d in version.get("distributions", [])), reverse=True)


def get_yak():
    # type: () -> dict
    versions = _get_json(constants.ADMIN_YAK_VERSIONS_URL)
    package = _get_json(constants.ADMIN_YAK_VERSIONS_URL.replace("/versions/", "/packages/"))
    return {"total": max(sum(v.get("download_count", 0) for v in versions), package.get("download_count", 0)), "latest": package.get("version"),
            "versions": [[v["version"], v["created_at"][:10], v.get("download_count", 0), get_yak_builds(v)] for v in versions]}


def get_stores():
    # type: () -> dict
    """프로그램별 배포 상태 {rhino|sketchup|blender: {"url", "live"}} — 주소가 비면 심사 중, Blender는 스토어 페이지가 열리면 공개."""
    stores = {}
    for host, url in constants.ADMIN_STORE_URLS.items():
        live = bool(url)
        if url and host == "blender":
            try:
                urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=10).close()
            except Exception:   # 404 = 아직 심사 중
                live = False
        stores[host] = {"url": url, "live": live}
    return stores


def get_hf():
    # type: () -> dict
    data = _get_json(constants.ADMIN_HF_API_URL)
    return {"downloads": data.get("downloads", 0), "downloads_all": data.get("downloadsAllTime", 0), "storage": data.get("usedStorage", 0)}


# ── 국내 서버(Oracle) ──

def get_gate_lines():
    # type: () -> tuple
    """
    처리: SSH로 nginx 기록(udt.log·회전된 .1·.gz)과 디스크 사용량을 받아, 이 Mac 사본(ADMIN_GATE_LOG_PATH)에 없는 줄만 이어 붙인다.
          팩 요청 줄만 남긴다. 서버는 2주만 남기므로 사본이 오래된 기록을 지킨다.
    출력: (사본 전체 줄 목록, [디스크 사용 바이트, 전체 바이트] | None).
    """
    user, key_path = constants.ADMIN_GATE_SSH
    host = urllib.parse.urlsplit(constants.DATA_DOMESTIC_BASE_URL).hostname
    command = ("sudo -n cat /var/log/nginx/udt.log.1 /var/log/nginx/udt.log 2>/dev/null; "
               "sudo -n sh -c 'zcat /var/log/nginx/udt.log.*.gz' 2>/dev/null; echo DF $(df -B1 --output=used,size / | tail -1)")
    result = subprocess.run(["ssh", "-i", key_path, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "%s@%s" % (user, host), command],
                            capture_output=True, text=True, timeout=60)
    lines = result.stdout.splitlines()
    disk = next(([int(x) for x in line.split()[1:3]] for line in lines if line.startswith("DF ") and len(line.split()) == 3), None)
    fetched = [line for line in lines if GATE_LINE.match(line) and '.db.xz"' in line]   # 팩 요청만 — 나머지는 스캐너(하루 수백 줄)
    if not disk and result.returncode:
        raise RuntimeError(result.stderr.strip()[-300:] or "ssh 실패")
    known = []
    if os.path.exists(constants.ADMIN_GATE_LOG_PATH):
        with open(constants.ADMIN_GATE_LOG_PATH, encoding="utf-8") as f:
            known = f.read().splitlines()
    known_set = set(known)
    new = sorted(set(line for line in fetched if line not in known_set))
    if new:
        os.makedirs(os.path.dirname(constants.ADMIN_GATE_LOG_PATH), exist_ok=True)
        with open(constants.ADMIN_GATE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in new))
        os.chmod(constants.ADMIN_GATE_LOG_PATH, 0o600)   # IP·설치 ID가 들어 있다
    return known + new, disk


def get_mac_client_id():
    # type: () -> str
    """이 Mac 설치본의 설치 ID(site_prefs.CLIENT_ID_PATH = ~/.gorani/client_id) — 늘 내 시험으로 본다. 없으면 빈 문자열."""
    try:
        with open(os.path.join(os.path.expanduser("~"), ".gorani", "client_id"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def get_marked_clients():
    # type: () -> set
    """[연결]에서 '내 시험'으로 표시한 설치 ID(ADMIN_DEV_CLIENTS_PATH)."""
    try:
        with open(constants.ADMIN_DEV_CLIENTS_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def get_dev_clients():
    # type: () -> set
    """'내 시험' 설치 ID — 이 Mac 설치 ID + 표시한 것."""
    return (get_marked_clients() | {get_mac_client_id()}) - {""}


def set_dev_client(client_id, is_dev):
    # type: (str, bool) -> None
    """설치 ID 하나를 '내 시험' 목록에 넣거나 뺀다."""
    ids = get_marked_clients()
    (ids.add if is_dev else ids.discard)(client_id)
    os.makedirs(os.path.dirname(constants.ADMIN_DEV_CLIENTS_PATH), exist_ok=True)
    with open(constants.ADMIN_DEV_CLIENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, indent=1)


def is_test_line(match, dev_clients):
    # type: (object, set) -> bool
    """nginx 기록 한 줄이 내 시험인지 — 표시한 설치 ID이거나 시험용 User-Agent(curl·HeadlessChrome)."""
    return match.group(7) in dev_clients or any(agent in match.group(6) for agent in constants.ADMIN_TEST_AGENTS)


def get_gate_clients(lines, dev_clients):
    # type: (list, set) -> list
    """
    설치 ID별 [ID, 받기, 처음 날, 마지막 날, 마지막 프로그램, 내 시험 이유] — 많이 받은 순. 설치 ID 없는 요청은 '-'.
    이유: "mac" = 이 Mac, "ua" = 시험용 User-Agent(curl·HeadlessChrome), "marked" = 표시함, "" = 실제 사용자로 봄.
    """
    found, mac = {}, get_mac_client_id()
    for line in lines:
        match = GATE_LINE.match(line)
        if not match or not match.group(5).endswith(".db.xz") or int(match.group(3)) not in (200, 206):
            continue
        client, day, agent = match.group(7) or "-", match.group(1)[:10], match.group(6)
        row = found.setdefault(client, [client, 0, day, day, "", ""])
        row[1] += 1
        row[2], row[3] = min(row[2], day), max(row[3], day)
        row[4] = "HeadlessChrome" if "HeadlessChrome" in agent else agent.split(" ")[0]
        if any(test in agent for test in constants.ADMIN_TEST_AGENTS):
            row[5] = "ua"
        elif not row[5]:
            row[5] = "mac" if client == mac else "marked" if client in dev_clients else ""
    return sorted(found.values(), key=lambda r: -r[1])


def get_gate_summary(lines, period, labels, now=None, dev_clients=None):
    # type: (list, dict, dict, datetime.datetime, set) -> dict
    """
    입력: nginx 기록 줄(server_gate.py log_format udt), 기간(get_period), 팩 이름 → 라벨, 기준 시각(테스트용, 기본 지금),
          dev_clients = 뺄 설치 ID(None = 빼지 않음 — 주면 시험용 User-Agent도 뺀다).
    처리: 팩 요청(.db.xz)만 센다. 200·206 = 받기(바이트 합 = 서버 전송량), 403·429 = 문지기 거절. 날짜는 한국 시간.
          이번 달 전송량은 기간과 상관없이 따로 센다(Always Free 월 한도).
    출력: {"downloads"·"bytes"·"installs": [이번, 지난], "month_bytes", "rejected": {"403", "429"}, "daily": {downloads, bytes},
           "packs": [[라벨, 받기, 바이트]], "agents": [[프로그램, 받기]], "kinds": {context|terrain: 받기}}.
    """
    kst = datetime.timezone(datetime.timedelta(hours=9))
    now = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone(kst)
    index = dict((d, i) for i, d in enumerate(period["dates"]))
    downloads, sent, clients = [0, 0], [0, 0], [set(), set()]
    daily_downloads, daily_bytes = [0] * len(index), [0] * len(index)
    packs, pack_bytes, agents, kinds, rejected = (collections.Counter() for _ in range(5))
    month_bytes = 0
    for line in lines:
        match = GATE_LINE.match(line)
        if not match or not match.group(5).endswith(".db.xz") or (dev_clients is not None and is_test_line(match, dev_clients)):
            continue
        when = datetime.datetime.fromisoformat(match.group(1)).astimezone(kst)
        status, size, name = int(match.group(3)), int(match.group(4)), os.path.basename(match.group(5))[:-3]
        ok = status in (200, 206)
        if ok and (when.year, when.month) == (now.year, now.month):
            month_bytes += size
        day = when.date().isoformat()
        slot = 0 if period["cur"][0] <= day <= period["cur"][1] else 1 if period["prev"][0] <= day <= period["prev"][1] else None
        if slot is None:
            continue
        if slot == 0 and status in (403, 429):
            rejected[str(status)] += 1
        if not ok:
            continue
        downloads[slot] += 1
        sent[slot] += size
        if match.group(7) not in ("", "-"):
            clients[slot].add(match.group(7))
        if slot == 0:
            daily_downloads[index[day]] += 1
            daily_bytes[index[day]] += size
            packs[name] += 1
            pack_bytes[name] += size
            agents["HeadlessChrome" if "HeadlessChrome" in match.group(6) else match.group(6).split(" ")[0]] += 1
            kinds[name.rsplit("_", 1)[-1].split(".")[0]] += 1
    return {"downloads": downloads, "bytes": sent, "installs": [len(c) for c in clients], "month_bytes": month_bytes,
            "rejected": {"403": rejected["403"], "429": rejected["429"]},
            "daily": {"downloads": daily_downloads, "bytes": daily_bytes},
            "packs": [[labels.get(n) or n, c, pack_bytes[n]] for n, c in packs.most_common(30)],
            "agents": agents.most_common(), "kinds": dict(kinds)}


def get_bucket():
    # type: () -> dict
    """OCI CLI로 국내 버킷 대략 크기·객체 수(~/.oci/config)."""
    parts = constants.DATA_DOMESTIC_BUCKET_URL.rstrip("/").split("/")
    result = subprocess.run(["oci", "os", "bucket", "get", "-ns", parts[-4], "-bn", parts[-2], "--fields", "approximateSize",
                             "--fields", "approximateCount"], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-300:])
    data = json.loads(result.stdout)["data"]
    return {"size": data["approximate-size"], "count": data["approximate-count"], "limit": constants.ADMIN_ORACLE_FREE_STORAGE}


def get_manifests():
    # type: () -> list
    manifests = []
    for url in (constants.DATA_MANIFEST_URL, constants.DATA_JP_MANIFEST_URL):
        try:
            manifests.append(_get_json(url))
        except Exception:   # 매니페스트가 없으면 라벨 없이 코드만 보인다
            pass
    return manifests


# ── 인사이트 ──

def _change(pair):
    # type: (list) -> float
    """[이번, 지난] → 변화율(지난이 0이면 None)."""
    return (pair[0] - pair[1]) / float(pair[1]) if pair and pair[1] else None


def get_insights(stats):
    # type: (dict) -> list
    """
    입력: get_stats 결과.
    처리: CEO·마케팅·운영이 먼저 볼 것을 규칙으로 고른다 — 활성 사용자 변화, 활성화율(패널 연 사람 중 3D 만든 사람), 생성 성공률,
          오류 급증, 최신 버전 사용률, 해외 비중, 웹 → 설치 의도, yak 최신 판의 Rhino 7판 누락, 서버 용량·월 전송량, 하루 한도 거절.
    출력: [{"level": good|warning|serious|info, "area": 영역, "text": 문장, "page": 자세히 볼 화면}] — 나쁜 것 먼저.
    """
    out = []
    ga = stats.get("ga") or {}
    apps = list(ga.get("apps", {}).values())
    if apps:
        users = [sum(a["totals"]["users"][i] for a in apps) for i in (0, 1)]
        change = _change(users)
        if change is not None:
            out.append({"level": "good" if change >= 0 else "serious", "area": "사용자", "page": "rhino",
                        "text": "활성 사용자 %d명 — 지난 기간보다 %+.0f%%" % (users[0], change * 100)})
        event_users = lambda name: sum(a["events"].get(name, {}).get("users", [0, 0])[0] for a in apps)
        if event_users("panel_open"):
            rate = event_users("build") / float(event_users("panel_open"))
            out.append({"level": "good" if rate >= .5 else "warning", "area": "활성화", "page": "rhino",
                        "text": "패널을 연 사용자 중 %.0f%%가 3D를 만들었습니다" % (rate * 100)
                        + ("" if rate >= .5 else " — 첫 화면에서 막히는지 확인하세요")})
        results = collections.Counter()
        versions = collections.Counter()
        korea = collections.Counter()
        for app in apps:
            for value, count in app["dims"].get("build.result", []):
                results[value] += count
            for value, count in app["dims"].get("panel_open.version", []):
                versions[value] += count
            for value, count in app["dims"].get("build.korea", []):
                korea["abroad" if str(value).lower() in ("0", "false") else "korea"] += count
        if results["ok"] + results["failed"]:
            rate = results["ok"] / float(results["ok"] + results["failed"])
            out.append({"level": "good" if rate >= .95 else "warning" if rate >= .85 else "serious", "area": "품질", "page": "rhino",
                        "text": "3D 생성 성공률 %.1f%% (실패 %d건)" % (rate * 100, results["failed"])})
        errors = [sum(a["events"].get("app_error", {}).get("count", [0, 0])[i] for a in apps) for i in (0, 1)]
        if errors[0] >= 5 and errors[0] > errors[1] * 1.5:
            out.append({"level": "serious", "area": "품질", "page": "rhino",
                        "text": "오류 %d건 — 지난 기간(%d건)보다 크게 늘었습니다" % tuple(errors)})
        if sum(versions.values()):
            share = versions[constants.PANEL_VERSION] / float(sum(versions.values()))
            out.append({"level": "good" if share >= .6 else "warning", "area": "버전", "page": "rhino",
                        "text": "최신 %s 사용률 %.0f%%" % (constants.PANEL_VERSION, share * 100)
                        + ("" if share >= .6 else " — [공지·버전]에서 업데이트 안내를 고려하세요")})
        if korea["abroad"]:
            out.append({"level": "info", "area": "시장", "page": "rhino",
                        "text": "해외 대상지 생성 비중 %.0f%%" % (100.0 * korea["abroad"] / sum(korea.values()))})
    web = ga.get("web")
    if web and web["totals"]["users"][0]:
        copied = web["events"].get("copy_command", {}).get("users", [0, 0])[0]
        out.append({"level": "info", "area": "유입", "page": "web",
                    "text": "웹 방문자 %d명 중 %.1f%%가 설치 명령을 복사했습니다" % (web["totals"]["users"][0], 100.0 * copied / web["totals"]["users"][0])})
    yak = stats.get("yak") or {}
    latest = [v for v in yak.get("versions", []) if v[0] == yak.get("latest")]
    missing = [p for p in ("mac", "win") if latest and "Rhino 7 " + p not in latest[0][3]]   # dev_deploy.RHINO7_PLATFORMS
    if missing:
        out.append({"level": "warning", "area": "배포", "page": "rhino",
                    "text": "yak 최신 %s에 Rhino 7판(%s)이 없습니다 — Rhino 7 사용자가 받을 수 없습니다(dev_deploy.py rhino7)" % (latest[0][0], "·".join(missing))})
    bucket = stats.get("bucket")
    if bucket and bucket["size"] >= bucket["limit"] * .65:
        share = bucket["size"] / float(bucket["limit"])
        out.append({"level": "serious" if share >= .85 else "warning", "area": "서버", "page": "infra",
                    "text": "국내 버킷 %.0f%% 사용 — 20 GB를 넘으면 유료입니다" % (share * 100)})
    gate = stats.get("gate")
    if gate:
        if gate["month_bytes"] >= constants.ADMIN_ORACLE_FREE_EGRESS * .5:
            out.append({"level": "warning", "area": "서버", "page": "infra", "text": "이번 달 전송량이 무료 한도(10 TB)의 절반을 넘었습니다"})
        if gate["rejected"]["429"]:
            out.append({"level": "warning", "area": "서버", "page": "infra",
                        "text": "하루 한도에 걸린 요청 %d건 — 한도가 실제 사용에 비해 낮은지 보세요" % gate["rejected"]["429"]})
    rank = {"serious": 0, "warning": 1, "info": 2, "good": 3}
    return sorted(out, key=lambda x: rank[x["level"]])


def _try(work, *args):
    # type: (object, object) -> tuple
    """(결과, 오류 문장) — 출처 하나가 실패해도 나머지는 보인다."""
    try:
        return work(*args), ""
    except Exception as error:
        return None, str(error) or type(error).__name__


def get_stats(days=30, demo=False, exclude_dev=False):
    # type: (int, bool, bool) -> dict
    """
    입력: 최근 일수(GA·국내 서버 기록 — yak·HF는 누적·30일 고정), demo = GA 자리에 예시 데이터,
          exclude_dev = 내 시험 빼기(GA dev 표시 이벤트, 국내 서버 표시한 설치 ID·시험용 User-Agent).
    처리: 매니페스트(지역 이름)를 먼저 받고 GA·yak·HF·국내 서버 기록·버킷을 동시에 모은다. 출처마다 성공·실패를 sources에 남긴다.
    출력: {"days", "updated", "period", "ga", "yak", "hf", "gate", "vm_disk", "bucket", "inventory", "sources", "insights", ...}.
    """
    period = get_period(days)
    manifests = get_manifests()
    labels = get_pack_labels(manifests)
    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        jobs = {"ga": pool.submit(_try, get_demo_ga if demo else get_ga, period, labels, exclude_dev), "yak": pool.submit(_try, get_yak),
                "hf": pool.submit(_try, get_hf), "stores": pool.submit(_try, get_stores), "gate": pool.submit(_try, get_gate_lines), "bucket": pool.submit(_try, get_bucket)}
        results = dict((key, job.result()) for key, job in jobs.items())
    ga, ga_error = results["ga"]
    dev_clients = get_dev_clients()
    gate_lines, gate_error = results["gate"]
    stats = {"days": days, "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "period": period, "demo": demo,
             "latest_version": constants.PANEL_VERSION, "ga": ga, "yak": results["yak"][0], "hf": results["hf"][0], "stores": results["stores"][0] or {},
             "gate": get_gate_summary(gate_lines[0], period, labels, dev_clients=dev_clients if exclude_dev else None) if gate_lines else None,
             "gate_clients": get_gate_clients(gate_lines[0], dev_clients) if gate_lines else [], "exclude_dev": exclude_dev,
             "vm_disk": gate_lines[1] if gate_lines else None, "bucket": results["bucket"][0], "inventory": get_inventory(manifests),
             "egress_limit": constants.ADMIN_ORACLE_FREE_EGRESS, "ga_key_path": constants.ADMIN_GA_KEY_PATH,
             "ga_dimensions": constants.ADMIN_GA_DIMENSIONS}
    stats["sources"] = [
        {"key": "ga", "name": "Google Analytics", "ok": bool(ga and ga["ok"]), "text": ga_error or (ga or {}).get("status", "")},
        {"key": "yak", "name": "yak (Rhino 패키지 서버)", "ok": not results["yak"][1], "text": results["yak"][1] or "공개 API"},
        {"key": "hf", "name": "Hugging Face 데이터셋", "ok": not results["hf"][1], "text": results["hf"][1] or constants.DATA_REPO_ID},
        {"key": "gate", "name": "국내 서버 기록 (SSH)", "ok": not gate_error,
         "text": gate_error or "기록 %d줄 보관 · %s" % (len(gate_lines[0]), constants.ADMIN_GATE_LOG_PATH)},
        {"key": "bucket", "name": "국내 버킷 (OCI CLI)", "ok": not results["bucket"][1], "text": results["bucket"][1] or "~/.oci/config"},
        {"key": "manifest", "name": "데이터 매니페스트", "ok": bool(manifests), "text": "팩 %d개" % sum(len(m.get("packs", [])) for m in manifests)},
    ]
    stats["insights"] = get_insights(stats)
    return stats


if __name__ == "__main__":
    arguments = [a for a in sys.argv[1:] if a != "--demo"]
    print(json.dumps(get_stats(int(arguments[0]) if arguments else 30, "--demo" in sys.argv), ensure_ascii=False, indent=1))
