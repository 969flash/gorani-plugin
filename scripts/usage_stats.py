"""사용 통계 — GA4 Measurement Protocol로 이벤트를 보낸다(서버 없음, 표준 라이브러리만).

끄는 설정은 두지 않는다(무료 도구 — 쓰면 보낸다). 보내는 항목 고지는 docs/install.md. 측정 ID·API secret이 비어 있으면(constants) 아무것도 보내지 않는다.
보내는 것: 설치마다 무작위 client_id, 패널 버전·OS, 생성 대상지(필지 PNU·중심 경위도, 구역은 중심·면적·크기만), 결과·소요 시간.
보내기는 데몬 스레드에서 하고 실패는 버린다 — 통계 때문에 패널이 멈추거나 죽으면 안 된다.
"""

import json
import locale
import os
import platform
import threading
import urllib.request
import uuid

import constants
import context_builder
import non_rhino_utils
import site_prefs

CLIENT_ID_PATH = os.path.join(site_prefs.PREFS_DIR, "client_id")
PNUS_PER_PARAM = constants.GA_PARAM_VALUE_MAX // 20   # PNU 19자 + 쉼표


def get_client_id(path=CLIENT_ID_PATH):
    # type: (str) -> str
    """설치마다 한 번 만든 무작위 UUID. 파일이 없거나 비면 새로 만들어 쓴다."""
    try:
        with open(path, encoding="utf-8") as f:
            value = f.read().strip()
        if value:
            return value
    except OSError:
        pass
    value = str(uuid.uuid4())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(value)
    return value


def get_payload(name, params, client_id):
    # type: (str, dict, str) -> dict
    """
    입력: 이벤트 이름, 매개변수 dict(None 값은 뺀다 — session_id는 호출 쪽이 패널 하나마다 정해 넣는다. loader.load가 모듈을 다시 읽어
          모듈 전역은 명령마다 초기화된다), client_id.
    처리: 문자열은 GA_PARAM_VALUE_MAX로 자르고 bool은 0/1. engagement_time_msec를 붙여 실시간·사용자 보고서에 잡히게 한다.
    출력: Measurement Protocol 요청 본문 dict.
    """
    clean = {"engagement_time_msec": 1}
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = int(value)
        elif not isinstance(value, (int, float)):
            value = str(value)[:constants.GA_PARAM_VALUE_MAX]
        clean[key] = value
    return {
        "client_id": client_id,
        "events": [{"name": name, "params": clean}],
        "device": {"category": "desktop", "operating_system": platform.system(), "operating_system_version": platform.release(),
                   "language": (locale.getlocale()[0] or "").replace("_", "-")},
    }


def get_target_params(target, lots=None):
    # type: (dict, list) -> dict
    """
    입력: 생성 요청 target(mode lots|area|point, EPSG:5186 또는 해외 지역 TM), lots = lot_db.LotInfo 목록(필지 방식).
    처리: 필지는 PNU(앞 GA_PNU_PARAMS × PNUS_PER_PARAM필지)·필지 수·면적·중심, 구역은 중심·면적·경계상자 가로세로만(링은 크다), 위치는 그 점.
          TM → 경위도는 현재 투영(set_projection — 패널이 대상지를 정할 때 맞춰 둔다)으로 바꾼다.
    출력: {mode, lng, lat, korea, pnus?, lot_count?, area?, width?, height?}.
    """
    mode = target.get("mode")
    params = {"mode": mode}
    if mode == "lots":
        pnus = [str(p) for p in target.get("pnus") or []]
        params["lot_count"] = len(pnus)
        for index in range(constants.GA_PNU_PARAMS):   # pnus, pnus_2, … 값 하나에 PNUS_PER_PARAM개
            chunk = pnus[index * PNUS_PER_PARAM:(index + 1) * PNUS_PER_PARAM]
            if chunk:
                params["pnus" if index == 0 else "pnus_%d" % (index + 1)] = ",".join(chunk)
        center = context_builder.get_lots_center(lots) if lots else None
        if lots:
            params["area"] = round(sum(lot.area for lot in lots), 1)
    elif mode == "area":
        ring = [tuple(p) for p in target.get("ring") or []]
        min_x, min_y, max_x, max_y = (min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring))
        center = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
        params.update(area=round(non_rhino_utils.get_ring_area(ring), 1), width=round(max_x - min_x, 1), height=round(max_y - min_y, 1))
    else:
        center = target.get("center")
    if center:
        lng, lat = non_rhino_utils.get_wgs84_from_tm(float(center[0]), float(center[1]))
        params.update(lng=round(lng, 6), lat=round(lat, 6), korea=non_rhino_utils.is_korea(lng, lat))
    return params


def is_enabled():
    # type: () -> bool
    return bool(constants.GA_MEASUREMENT_ID and constants.GA_API_SECRET)


def send_event(name, params=None):
    # type: (str, dict) -> bool
    """이벤트 하나를 백그라운드로 보낸다. 꺼져 있거나 준비 중 예외면 False(패널 흐름은 그대로)."""
    try:
        if not is_enabled():
            return False
        body = json.dumps(get_payload(name, params, get_client_id())).encode("utf-8")
    except Exception:
        return False
    url = "%s?measurement_id=%s&api_secret=%s" % (constants.GA_ENDPOINT, constants.GA_MEASUREMENT_ID, constants.GA_API_SECRET)

    def post():
        try:
            request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(request, timeout=constants.GA_TIMEOUT_SECONDS).close()
        except Exception:
            pass

    threading.Thread(target=post, daemon=True).start()
    return True
