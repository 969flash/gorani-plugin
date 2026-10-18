"""SketchUp 모델 베이커(사이드카 쪽) — blender_baker와 같은 함수 이름을 SketchUp 호출(host.call)로 바꾼다. context_baker의 SketchUp판.

사이드카(번들 파이썬)는 SketchUp 모델을 직접 만지지 못한다. host = cmd_sketchup의 호출 창구(call(method, **args) → 결과)이고
모델 변경은 sketchup_ext.rb의 rpc_<method>가 한다. BakeItem처럼 큰 데이터는 임시 JSON 파일로 넘긴다.
SketchUp 쪽 모양: 대상지마다 최상위 그룹 하나('UrbanSite <대상지명>', 속성 URBANSITE_LOT_KEY) 안에 레이어(태그 'CTX::Buildings')마다 그룹,
건물은 동마다 그룹. 좌표는 로컬 m(SketchUp이 인치로 바꾼다) — 실제 좌표 방식은 대상지 그룹을 계산 원점만큼 옮긴다.
문서 원점은 모델 속성(constants.DOC_ORIGIN_KEYS), 사본은 대상지 그룹 정의를 context.skp로 저장한 것(로컬 좌표, 원점 = context.json origin).

    bake(host, items, prepared, lot_key) → [id]         write_ref_and_origin(host, prepared, lot_key) → [id, id]
    save_copy(host, path, ids, timing) → context.skp    import_skp(host, result_dir) → {ok, layers, objects, replaced, text}
    clear_previous(host, lot_key) → (objects, layers)   zoom_to_site(host, result_dir, center_lng_lat) → bool
"""

import json
import math
import os
import tempfile
import time

import constants
import non_rhino_utils
from context_baker import get_layer_rgb, get_lot_key, get_ref_attrs, read_meta


# ── 원점 ───────────────────────────────────────────────────

def get_doc_origin(host):
    # type: (object) -> tuple
    """모델 속성 원점 → (E, N). 없거나 좌표계가 지금과 다르면 None (blender_baker.get_doc_origin과 같은 규칙)."""
    e, n, crs = host.call("get_model_attrs", keys=list(constants.DOC_ORIGIN_KEYS))
    if crs and crs != non_rhino_utils.get_crs_label():
        return None
    try:
        return (float(e), float(n)) if e and n else None
    except ValueError:
        return None


def _set_doc_origin(host, origin):
    # type: (object, tuple) -> None
    values = ("%.3f" % origin[0], "%.3f" % origin[1], non_rhino_utils.get_crs_label())
    host.call("set_model_attrs", values=dict(zip(constants.DOC_ORIGIN_KEYS, values)))


def _get_shift(prepared):
    # type: (object) -> list
    """계산 원점 − 문서 원점(실제 좌표 방식이면 계산 원점 그대로) — 대상지 그룹 위치."""
    doc_origin = getattr(prepared, "doc_origin", None) or prepared.origin
    return [prepared.origin[0] - doc_origin[0], prepared.origin[1] - doc_origin[1]]


def _get_lot_key(prepared, lot_key):
    # type: (object, str) -> str
    return lot_key or getattr(prepared, "target_key", "") or get_lot_key((prepared.request or {}).get("pnus") or [])


# ── 지우기·베이크 ────────────────────────────────────────────

def clear_previous(host, lot_key=None):
    # type: (object, str) -> tuple
    """이 도구가 만든 대상지 그룹(lot_key를 주면 그 대상지만) 삭제. 출력 (지운 그룹 수, 0) — 태그는 사용자 것과 섞여 지우지 않는다."""
    return tuple(host.call("clear", lot_key=lot_key))


def _get_payload(item):
    # type: (object) -> dict
    """BakeItem → JSON 한 항목(레이어 색·숨김 포함 — Ruby는 constants를 모른다)."""
    return {"layer": item.layer, "name": item.name, "rgb": list(get_layer_rgb(item.layer)),
            "hidden": item.layer.partition("::")[2] in constants.CTX_HIDDEN_LAYERS,
            "verts": item.verts, "faces": item.faces, "polylines": item.polylines, "prisms": item.prisms,
            "attrs": {str(k): "" if v is None else str(v) for k, v in (item.attrs or {}).items()}}


def bake(host, items, prepared, lot_key=None):
    # type: (object, list, object, str) -> list
    """BakeItem 목록을 대상지 그룹 안에 넣는다. 출력: 만든 그룹 id 목록(실패 항목은 빠진다 — run이 수를 비교해 경고)."""
    data = {"lot_key": _get_lot_key(prepared, lot_key), "lot_name": prepared.lot_name, "shift": _get_shift(prepared),
            "items": [_get_payload(item) for item in items]}
    handle, path = tempfile.mkstemp(prefix="urbansite_bake_", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        return host.call("bake", path=path)
    finally:
        os.remove(path)


def write_ref_and_origin(host, prepared, lot_key=None):
    # type: (object, object, str) -> list
    """원점 표식(CTX::Ref — 구성점 + 'ORIGIN E … N …' 글자, 속성 = Ref 속성 전부)을 대상지 그룹 원점에. 모델 원점은 재사용이 아니면 기록.
    출력: id 2개(context_baker와 같은 수 — run이 베이크 실패를 센다)."""
    ids = host.call("ref", lot_key=_get_lot_key(prepared, lot_key), lot_name=prepared.lot_name, shift=_get_shift(prepared),
                    layer=constants.CTX_ROOT_LAYER + "::Ref", rgb=list(get_layer_rgb(constants.CTX_ROOT_LAYER + "::Ref")),
                    label="ORIGIN E %.0f N %.0f" % tuple(prepared.origin), attrs=get_ref_attrs(prepared))
    if not prepared.origin_reused:
        _set_doc_origin(host, getattr(prepared, "doc_origin", None) or prepared.origin)
    return ids


def save_copy(host, path, names=None, timing=None):
    # type: (object, str, list, dict) -> str
    """마지막으로 구운 대상지 그룹 정의를 사본 context.skp로 쓴다(path의 파일 이름은 무시하고 같은 폴더). 좌표는 로컬 — 원점은 context.json."""
    path = os.path.join(os.path.dirname(path), constants.SKETCHUP_MODEL_FILE_NAME)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    timing = timing if timing is not None else {}
    t = time.time()
    objects = host.call("save", path=path)
    timing.update(select_s=0.0, write_s=round(time.time() - t, 2), objects=objects, bytes=os.path.getsize(path))
    return path


# ── 다시 넣기·줌 ─────────────────────────────────────────────

def import_skp(host, result_dir):
    # type: (object, str) -> dict
    """<result_dir>/context.skp를 모델에 다시 넣는다(blender_baker.import_blend와 같은 규칙). 같은 lot_key 그룹을 먼저 지우고,
    파일 원점(context.json origin) − 모델 원점만큼 옮긴다(차이 > ORIGIN_MAX_OFFSET이면 거부). 모델에 원점이 없으면 파일의 문서 원점을 기록."""
    path = os.path.join(result_dir, constants.SKETCHUP_MODEL_FILE_NAME)
    result = {"ok": False, "layers": 0, "objects": 0, "replaced": False, "text": "", "shift": [0.0, 0.0]}
    if not os.path.exists(path):
        result["text"] = "파일이 없습니다: %s" % path
        return result
    meta = read_meta(result_dir)
    origin = tuple(float(v) for v in (meta.get("origin") or [])) or None
    file_doc_origin = tuple(float(v) for v in (meta.get("doc_origin") or [])) or origin
    doc_origin = get_doc_origin(host)
    if file_doc_origin and doc_origin and (file_doc_origin == (0.0, 0.0)) != (doc_origin == (0.0, 0.0)):
        result["text"] = "좌표 방식이 다른 모델입니다(원점 이동 / 실제 좌표) — 새 모델에서 넣으세요"
        return result
    if file_doc_origin and doc_origin and math.hypot(file_doc_origin[0] - doc_origin[0], file_doc_origin[1] - doc_origin[1]) > constants.ORIGIN_MAX_OFFSET:
        result["text"] = "다른 지역 모델입니다 — 새 모델에서 넣으세요 (원점 차이 > %.0f m)" % constants.ORIGIN_MAX_OFFSET
        return result
    lot_key = meta.get("lot_key") or (get_lot_key(meta["pnus"]) if meta.get("pnus") else "")
    if lot_key:
        result["replaced"] = clear_previous(host, lot_key)[0] > 0
    target = doc_origin or file_doc_origin
    shift = [origin[0] - target[0], origin[1] - target[1]] if origin and target else [0.0, 0.0]
    placed = host.call("import", path=path, lot_key=lot_key, lot_name=meta.get("lot_name") or os.path.basename(result_dir), shift=shift)
    if file_doc_origin and not doc_origin:
        _set_doc_origin(host, file_doc_origin)
    result.update(ok=placed["objects"] > 0, layers=placed["layers"], objects=placed["objects"], shift=shift,
                  text="" if placed["objects"] else "파일에 객체가 없습니다: %s" % path)
    return result


def zoom_to_site(host, result_dir, center_lng_lat=None):
    # type: (object, str, list) -> bool
    """이번 결과의 CTX::Site(없으면 context.json 중심 500 m, 경위도를 주면 그 주변 100 m)로 카메라를 옮긴다."""
    meta = read_meta(result_dir)
    box = None
    origin = get_doc_origin(host) or meta.get("doc_origin") or meta.get("origin") or [0.0, 0.0]
    if center_lng_lat:
        world, half = non_rhino_utils.get_tm_from_wgs84(float(center_lng_lat[0]), float(center_lng_lat[1])), 100.0
    else:
        world, half = meta.get("center"), 500.0
    if world:
        box = [world[0] - origin[0], world[1] - origin[1], half]
    return bool(host.call("zoom", lot_key=None if center_lng_lat else meta.get("lot_key"), box=box))
