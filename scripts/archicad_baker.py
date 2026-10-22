"""Archicad 모델 베이커(사이드카 쪽) — sketchup_baker와 같은 함수 이름을 Archicad JSON 명령(host.call)으로 바꾼다. context_baker의 Archicad판.

host = cmd_archicad.ArchicadHost(api·call). 명령은 Gorani 애드온(archicad/ — Tapir에서 가져옴)의 GoraniCommand.
Archicad 쪽 모양: 레이어(CTX::Buildings …)마다 요소. 건물 = 동마다 Morph(구멍 있는 각기둥), 지형 = Mesh 하나(지형 도구 — 바깥 고리 +
분류 경계·TIN 점을 높이 선으로), 도로·녹지·수면·대상지 바닥 = 지형 위로 살짝 띄운 Morph 면, 필지·대상지·범위·도로 중심선 = 평면 폴리선.
요소마다 분류 'Gorani > Site context'와 속성 그룹 'Gorani'(GORANI_LOT_KEY + 건물 속성 14키)를 붙인다 — Archicad 사용자 속성은
분류에 매여야 값이 들어간다(분류 없는 요소는 'Not available'). 지우기는 이 분류로 찾고 GORANI_LOT_KEY로 대상지를 가린다.
좌표는 로컬 m(Archicad JSON도 m) — 실제 좌표 방식은 요소를 계산 원점만큼 옮긴다. 문서 원점은 프로젝트 정보 필드(constants.DOC_ORIGIN_KEYS),
사본은 구운 요소를 모듈(context.mod)로 저장한 것, 다시 넣기는 그 모듈을 핫링크로 놓는다.

    bake(host, items, prepared, lot_key) → [id]         write_ref_and_origin(host, prepared, lot_key) → [id, id]
    save_copy(host, path, ids, timing) → context.mod    import_mod(host, result_dir) → {ok, layers, objects, replaced, text}
    clear_previous(host, lot_key) → (objects, layers)   zoom_to_site(host, result_dir, center_lng_lat) → bool
    get_doc_origin(host) → (E, N)                       get_selected_ring(host) → ([(x, y)], 안내 글)
"""

import math
import os
import sys
import time

import constants
import non_rhino_utils
from context_baker import get_layer_rgb, get_lot_key, get_ref_attrs, read_meta
from i18n import tr

PROPERTY_GROUP = "Gorani"
CLASSIFICATION = ("Gorani", "CTX", "Site context")   # (분류 체계, 항목 id, 항목 이름)
GROUND_CLASSES = ("CTX::Terrain", "CTX::Roads", "CTX::Green", "CTX::Water", "CTX::Rail", "CTX::Site::ground", "CTX::Terrain::site_flat")


# ── 문서 원점(프로젝트 정보 필드) ─────────────────────────────

def _get_info_fields(host):
    # type: (object) -> dict
    """프로젝트 정보 필드 이름 → (id, 값)."""
    fields = host.call("GetProjectInfoFields").get("fields") or []
    return {f["projectInfoName"]: (f["projectInfoId"], f.get("projectInfoValue") or "") for f in fields}


def get_doc_origin(host):
    # type: (object) -> tuple
    """프로젝트 정보 원점 → (E, N). 없거나 좌표계가 지금과 다르면 None (sketchup_baker.get_doc_origin과 같은 규칙)."""
    fields = _get_info_fields(host)
    e, n, crs = (fields.get(key, ("", ""))[1] for key in constants.DOC_ORIGIN_KEYS)
    if crs and crs != non_rhino_utils.get_crs_label():
        return None
    try:
        return (float(e), float(n)) if e and n else None
    except ValueError:
        return None


def _set_doc_origin(host, origin):
    # type: (object, tuple) -> None
    values = dict(zip(constants.DOC_ORIGIN_KEYS, ("%.3f" % origin[0], "%.3f" % origin[1], non_rhino_utils.get_crs_label())))
    fields = _get_info_fields(host)
    missing = [{"projectInfoName": key, "projectInfoValue": value} for key, value in values.items() if key not in fields]
    if missing:
        host.call("CreateProjectInfoFields", projectInfoFields=missing)
    for key, value in values.items():
        if key in fields:
            host.call("SetProjectInfoField", projectInfoId=fields[key][0], projectInfoValue=value)


def _get_shift(prepared):
    # type: (object) -> tuple
    """계산 원점 − 문서 원점(실제 좌표 방식이면 계산 원점 그대로) — 요소를 옮길 양."""
    doc_origin = getattr(prepared, "doc_origin", None) or prepared.origin
    return (prepared.origin[0] - doc_origin[0], prepared.origin[1] - doc_origin[1])


def _get_lot_key(prepared, lot_key):
    # type: (object, str) -> str
    return lot_key or getattr(prepared, "target_key", "") or get_lot_key((prepared.request or {}).get("pnus") or [])


# ── 속성·레이어·표면 ──────────────────────────────────────────

def _get_ids(response):
    # type: (dict) -> list
    """Create* 응답 → 만든 요소 id 목록(실패 항목은 None — 첫 오류는 사이드카 로그에)."""
    items = (response or {}).get("elements") or []
    errors = [item["error"] for item in items if item.get("error")]
    if errors:
        print("[Gorani] Archicad: %d failed, first: %s" % (len(errors), errors[0]), file=sys.stderr)
    return [(item.get("elementId") or {}).get("guid") for item in items]


def _ensure_classification(host):
    # type: (object) -> tuple
    """분류 체계 'Gorani'와 항목 'CTX'를 (없으면 만들어) (체계 id, 항목 id)로."""
    system_name, item_id, item_name = CLASSIFICATION

    def find():
        systems = host.api("API.GetAllClassificationSystems").get("classificationSystems") or []
        system = next((x for x in systems if x.get("name") == system_name), None)
        if system is None:
            return None
        items = host.api("API.GetAllClassificationsInSystem", {"classificationSystemId": system["classificationSystemId"]}).get("classificationItems") or []
        item = next((x["classificationItem"] for x in items if x["classificationItem"].get("id") == item_id), None)
        return (system["classificationSystemId"], item["classificationItemId"]) if item else None

    found = find()
    if found is None:
        host.call("CreateClassificationSystems", classificationSystemsWithItems=[{
            "classificationSystem": {"name": system_name, "description": "Gorani site context", "source": constants.PANEL_LINKS["website_en"],
                                     "version": "1", "date": "2026-10-22"},
            "classificationItems": [{"id": item_id, "name": item_name, "description": "Gorani"}]}])
        found = find()
    if found is None:
        raise RuntimeError(tr("Archicad에 분류 'Gorani'를 만들지 못했습니다"))
    return found


def _classify(host, guids, classification):
    # type: (object, list, tuple) -> None
    """요소를 'Gorani > Site context'로 분류한다(속성 값을 넣기 전에 — 숨긴 레이어로 옮기기 전에 해야 한다)."""
    system_id, item_id = classification
    rows = [{"elementId": {"guid": g}, "classificationId": {"classificationSystemId": system_id, "classificationItemId": item_id}} for g in guids if g]
    for start in range(0, len(rows), constants.ARCHICAD_BATCH * 10):
        host.api("API.SetClassificationsOfElements", {"elementClassifications": rows[start:start + constants.ARCHICAD_BATCH * 10]})


def _ensure_properties(host, names, classification):
    # type: (object, list, tuple) -> dict
    """속성 그룹 'Gorani'의 문자열 속성들을 (없으면 만들어) 이름 → 속성 guid로. 분류 'Gorani > Site context'에서 쓸 수 있게 만든다
    (기본값이 없으면 Archicad가 거부한다 — APIERR_BADVALUE)."""
    found = host.call("GetAllProperties")
    have = {p["propertyName"]: p["propertyId"]["guid"] for p in found.get("properties") or [] if p.get("propertyGroupName") == PROPERTY_GROUP}
    missing = [name for name in names if name not in have]
    if missing:
        if not any(g.get("name") == PROPERTY_GROUP for g in found.get("propertyGroups") or []):
            host.call("CreatePropertyGroups", propertyGroups=[{"propertyGroup": {"name": PROPERTY_GROUP, "description": "Gorani site context"}}])
        made = host.call("CreatePropertyDefinitions", propertyDefinitions=[
            {"propertyDefinition": {"name": name, "description": "", "type": "string", "isEditable": True,
                                    "availability": [{"classificationItemId": classification[1]}], "group": {"name": PROPERTY_GROUP},
                                    "defaultValue": {"basicDefaultValue": {"type": "string", "status": "normal", "value": ""}}}} for name in missing])
        for name, item in zip(missing, made.get("propertyIds") or []):
            guid = (item.get("propertyId") or {}).get("guid")
            if guid:
                have[name] = guid
    return have


def _set_properties(host, rows, classification):
    # type: (object, list, tuple) -> None
    """[(요소 id, {이름: 값})] → 분류를 붙이고 속성 값. 한 번에 보낸다(ARCHICAD_BATCH 단위)."""
    names = sorted({name for _guid, attrs in rows for name in attrs})
    if not names:
        return
    _classify(host, [guid for guid, _attrs in rows], classification)
    ids = _ensure_properties(host, names, classification)
    values = [{"elementId": {"guid": guid}, "propertyId": {"guid": ids[name]}, "propertyValue": {"value": str(value)}}
              for guid, attrs in rows if guid for name, value in attrs.items() if name in ids and value not in (None, "")]
    for start in range(0, len(values), constants.ARCHICAD_BATCH * 10):
        host.call("SetPropertyValuesOfElements", elementPropertyValues=values[start:start + constants.ARCHICAD_BATCH * 10])


def _get_layer_name(layer):
    # type: (str) -> str
    """'CTX::Buildings' → Archicad 레이어 이름. 콜론을 그대로 둔다(Rhino·SketchUp과 같은 이름 — 찾기 쉽게)."""
    return layer


def _ensure_layers(host, layers):
    # type: (object, list) -> dict
    """레이어 이름들을 (없으면 만들어) 이름 → 레이어 번호로. 끈 채 시작할 레이어(CTX_HIDDEN_LAYERS)는 새로 만들 때만 숨긴다."""
    def read():
        found = host.call("GetAttributesByType", attributeType="Layer")
        return {a["name"]: int(a["index"]) for a in found.get("attributes") or []}
    have = read()
    missing = [name for name in layers if _get_layer_name(name) not in have]
    if missing:
        host.call("CreateLayers", layerDataArray=[{"name": _get_layer_name(name),
                                                   "isHidden": name.partition("::")[2] in constants.CTX_HIDDEN_LAYERS} for name in missing])
        have = read()
    return {name: have[_get_layer_name(name)] for name in layers if _get_layer_name(name) in have}


def _open_layers(host, states):
    # type: (object, dict) -> None
    """레이어 상태 {이름: (숨김, 잠금)}로 되돌리거나 연다(값 None = 연다). 숨기거나 잠근 레이어의 요소는 Archicad가 지우지 못한다."""
    if states:
        host.call("CreateLayers", overwriteExisting=True, layerDataArray=[
            {"name": name, "isHidden": bool(state and state[0]), "isLocked": bool(state and state[1])} for name, state in states.items()])


def _get_closed_layers(host):
    # type: (object) -> dict
    """숨기거나 잠근 CTX 레이어 → {이름: (숨김, 잠금)}."""
    heads = [a for a in host.call("GetAttributesByType", attributeType="Layer").get("attributes") or []
             if a["name"].startswith(constants.CTX_ROOT_LAYER + "::")]
    if not heads:
        return {}
    found = host.api("API.GetLayerAttributes", {"attributeIds": [{"attributeId": a["attributeId"]} for a in heads]}).get("attributes") or []
    layers = [item.get("layerAttribute") or {} for item in found]
    return {a["name"]: (a.get("isHidden"), a.get("isLocked")) for a in layers if a.get("isHidden") or a.get("isLocked")}


def _ensure_surfaces(host, layers):
    # type: (object, list) -> dict
    """레이어 색으로 표면(재질) 'Gorani <레이어>'를 만들거나 고친다. 레이어 → 표면 guid."""
    names = ["Gorani " + layer for layer in layers]
    made = host.call("CreateSurfaces", overwriteExisting=True, surfaceDataArray=[
        {"name": name, "materialType": "General", "surfaceColor": dict(zip("rgb", (c / 255.0 for c in get_layer_rgb(layer))))}
        for name, layer in zip(names, layers)])
    ids = [(item.get("attributeId") or {}).get("guid") for item in made.get("attributeIds") or []]
    return {layer: guid for layer, guid in zip(layers, ids) if guid}


def _set_layer(host, guids, layer_index):
    # type: (object, list, int) -> None
    """Morph·Mesh는 만들 때 레이어를 못 정해(현재 레이어로 들어간다) 만든 뒤 옮긴다."""
    rows = [{"elementId": {"guid": guid}, "details": {"layerIndex": layer_index}} for guid in guids if guid]
    for start in range(0, len(rows), constants.ARCHICAD_BATCH * 10):
        host.call("SetDetailsOfElements", elementsWithDetails=rows[start:start + constants.ARCHICAD_BATCH * 10])


# ── 형상 → JSON ──────────────────────────────────────────────

def _xyz(x, y, z):
    return {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4)}


def get_prism_body(parts, base_z, height):
    # type: (list, float, float) -> dict
    """파트 [[외곽 링, 구멍 링…]…](로컬 2D) → MorphBody(정점 + 면). 위·아래 면은 구멍을 그대로, 옆면은 사각형.
    외곽은 반시계(위 법선 +Z), 구멍은 시계 — 입력 방향은 고쳐서 쓴다."""
    vertices, polygons = [], []
    for part in parts:
        rings = [ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else list(ring) for ring in part]
        rings = [ring for ring in rings if len(ring) >= 3]
        if not rings:
            continue
        rings = [ring if (non_rhino_utils.get_signed_area(ring) > 0) == (k == 0) else list(reversed(ring)) for k, ring in enumerate(rings)]
        starts, n = [], len(vertices)
        for ring in rings:
            starts.append(len(vertices) - n)
            vertices += [_xyz(x, y, base_z) for x, y in ring]
        count = len(vertices) - n
        vertices += [_xyz(v["x"], v["y"], base_z + height) for v in vertices[n:]]
        loops = [[n + starts[k] + i for i in range(len(ring))] for k, ring in enumerate(rings)]
        polygons.append({"vertexIds": [i + count for i in loops[0]], "holes": [{"vertexIds": [i + count for i in loop]} for loop in loops[1:]]})
        polygons.append({"vertexIds": list(reversed(loops[0])), "holes": [{"vertexIds": list(reversed(loop))} for loop in loops[1:]]})
        for loop in loops:
            for a, b in zip(loop, loop[1:] + loop[:1]):
                polygons.append({"vertexIds": [a, b, b + count, a + count]})
    return {"vertices": vertices, "polygons": polygons, "edgeDefault": "SoftHidden"}


def get_surface_body(verts, faces, lift):
    # type: (list, list, float) -> dict
    """삼각형·사각형 면 → 열린 MorphBody(면 방향 위). lift만큼 띄운다(지형 Mesh와 겹쳐 깜박이지 않게).
    사각형은 삼각형 둘로 나누고 넓이 0인 삼각형은 뺀다 — 높이 0 옹벽 사각형이 섞이면 Archicad가 Morph를 통째로 거부했다
    (성수 333-139 R=500 CTX::Terrain::site_wall, 2026-10-22)."""
    tris = []
    for face in faces:
        for tri in ([face] if len(face) == 3 else [(face[0], face[1], face[2]), (face[0], face[2], face[3])]):
            a, b, c = (verts[i] for i in tri)
            cross = ((b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1]), (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2]),
                     (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            if sum(v * v for v in cross) > 1e-10:
                tris.append(list(tri))
    return {"bodyType": "Surface", "edgeDefault": "SoftHidden",
            "vertices": [_xyz(x, y, z + lift) for x, y, z in verts], "polygons": [{"vertexIds": tri} for tri in tris]}


def get_polyline_coords(pts, closed, shift):
    # type: (list, bool, tuple) -> list
    """로컬 점 → Archicad 2D 폴리선 좌표(닫힘이면 첫 점을 되풀이). 1 mm 안 같은 점 연속은 하나로 — Archicad가 IRREGULARPOLY로 거부했다
    (용도지역 경계, 2026-10-22). 쓸 점이 모자라면 []."""
    coords = []
    for p in pts:
        xy = (round(p[0] + shift[0], 3), round(p[1] + shift[1], 3))
        if not coords or xy != coords[-1]:
            coords.append(xy)
    if closed:
        coords = coords[:-1] if len(coords) > 1 and coords[0] == coords[-1] else coords
        if len(coords) < 3:
            return []
        coords.append(coords[0])
    return [{"x": x, "y": y} for x, y in coords] if len(coords) >= 2 else []


def get_ground_mesh(items, outer):
    # type: (list, list) -> dict
    """지면 분류 메시들(지형·도로·녹지·수면…) → Archicad Mesh 하나의 입력(바깥 고리 3D + 안쪽 점). outer = 범위 링(로컬 2D — Ref 'extent' 항목).
    바깥 고리 점의 높이 = 같은 자리 TIN 정점(범위 링은 CDT 제약이라 정점으로 있다), 없으면 가장 가까운 정점.
    안쪽은 TIN 정점을 점 하나짜리 높이 선으로 — Archicad가 같은 점으로 다시 삼각분할한다. 분류 경계는 넘기지 않는다:
    분류 메시끼리 경계가 T자로 이어져(같은 변을 나눠 갖지 않는다) 줄이 끊기고, 메시 외곽을 이으면 같은 점을 두 번 지나 Archicad가 거부했다
    (성수 333-139 R=500, 2026-10-22 — 'Failed to create new Mesh')."""
    zs = {}
    for item in items:
        for x, y, z in item.verts:
            zs.setdefault((round(x, 3), round(y, 3)), z)
    if not zs or len(outer) < 3:
        return None
    ring = [(round(p[0], 3), round(p[1], 3)) for p in outer]
    ring = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring   # 닫는 점
    ring = [p for k, p in enumerate(ring) if k == 0 or p != ring[k - 1]]   # 같은 점 연속

    def z_at(key):
        if key in zs:
            return zs[key]
        return min(zs.items(), key=lambda kv: (kv[0][0] - key[0]) ** 2 + (kv[0][1] - key[1]) ** 2)[1]

    on_ring = set(ring)
    return {"outer": [(x, y, z_at((x, y))) for x, y in ring], "holes": [],
            "sublines": [[(x, y, z)] for (x, y), z in zs.items() if (x, y) not in on_ring]}


# ── 지우기·베이크 ────────────────────────────────────────────

def _find_lot_elements(host, lot_key):
    # type: (object, str) -> list
    """분류 'Gorani > Site context' 요소 중 속성 GORANI_LOT_KEY가 lot_key인 것(lot_key None이면 전부) id."""
    classification = _ensure_classification(host)
    found = host.api("API.GetElementsByClassification", {"classificationItemId": classification[1]}).get("elements") or []
    guids = [e["elementId"]["guid"] for e in found]
    if lot_key is None or not guids:
        return guids
    prop = _ensure_properties(host, [constants.UDT_LOT_KEY], classification)[constants.UDT_LOT_KEY]
    matched = []
    for start in range(0, len(guids), constants.ARCHICAD_BATCH * 10):
        chunk = guids[start:start + constants.ARCHICAD_BATCH * 10]
        values = host.call("GetPropertyValuesOfElements", elements=[{"elementId": {"guid": g}} for g in chunk],
                           properties=[{"propertyId": {"guid": prop}}]).get("propertyValuesForElements") or []
        for guid, row in zip(chunk, values):
            value = (((row.get("propertyValues") or [{}])[0]).get("propertyValue") or {}).get("value") or ""
            if value == lot_key:
                matched.append(guid)
    return matched


def clear_previous(host, lot_key=None):
    # type: (object, str) -> tuple
    """이 도구가 만든 요소(lot_key를 주면 그 대상지만) 삭제. 숨기거나 잠근 CTX 레이어는 잠깐 열었다가 되돌린다.
    출력 (지운 요소 수, 0) — 레이어는 사용자 것과 섞여 지우지 않는다."""
    guids = _find_lot_elements(host, lot_key)
    if guids:
        closed = _get_closed_layers(host)
        _open_layers(host, dict.fromkeys(closed))
        try:
            for start in range(0, len(guids), constants.ARCHICAD_BATCH * 10):
                host.call("DeleteElements", elements=[{"elementId": {"guid": g}} for g in guids[start:start + constants.ARCHICAD_BATCH * 10]])
        finally:
            _open_layers(host, closed)
    if lot_key:
        host.baked.pop(lot_key, None)
    return (len(guids), 0)


def _create_morphs(host, morphs):
    # type: (object, list) -> list
    """[(MorphBody, 표면 guid)] → 요소 id(실패는 None). ARCHICAD_BATCH 개씩."""
    ids = []
    for start in range(0, len(morphs), constants.ARCHICAD_BATCH):
        data = [dict({"basePoint": _xyz(0, 0, 0), "body": body, "floorIndex": 0}, **({"surfaceId": {"guid": surface}} if surface else {}))
                for body, surface in morphs[start:start + constants.ARCHICAD_BATCH]]
        ids += _get_ids(host.call("CreateMorphs", morphsData=data))
    return ids


def _create_surface(host, verts, faces, lift, surface):
    # type: (object, list, list, float, str) -> list
    """면 메시 → Morph 하나. Archicad가 거부하면(한 변을 세 면이 나눠 갖는 옹벽 메시 — 성수 333-139 R=500 site_wall, 2026-10-22)
    면마다 Morph로 나눈다(ARCHICAD_SPLIT_MAX 면까지 — 지형 분류 면은 한 덩어리로 들어간다)."""
    guids = _create_morphs(host, [(get_surface_body(verts, faces, lift), surface)])
    if guids and guids[0] or len(faces) > constants.ARCHICAD_SPLIT_MAX:
        return guids
    bodies = [get_surface_body(verts, [face], lift) for face in faces]
    return _create_morphs(host, [(body, surface) for body in bodies if body["polygons"]])   # 넓이 0 면은 뺀다


def _shifted(points, shift):
    return [(p[0] + shift[0], p[1] + shift[1]) + tuple(p[2:]) for p in points]


def bake(host, items, prepared, lot_key=None):
    # type: (object, list, object, str) -> list
    """BakeItem 목록을 Archicad 요소로. 출력: 항목마다 대표 id 하나(실패 항목은 빠진다 — run이 수를 비교해 경고).
    한 항목이 여러 요소(건물 동마다 Morph·필지마다 폴리선)여도 id 하나로 센다 — 전부는 host.baked[lot_key]에."""
    lot_key = _get_lot_key(prepared, lot_key)
    shift = _get_shift(prepared)
    layers = sorted({item.layer for item in items})
    layer_index = _ensure_layers(host, layers)
    surfaces = _ensure_surfaces(host, [layer for layer in layers if any(i.layer == layer and (i.faces or i.prisms) for i in items)])
    classification = _ensure_classification(host)
    baked = host.baked.setdefault(lot_key, [])
    host.last_lot = lot_key
    out, rows, moves = [], [], []
    ground = [item for item in items if item.layer in GROUND_CLASSES and item.faces]
    for item in items:
        guids = []
        moved = [(x + shift[0], y + shift[1], z) for x, y, z in item.verts]
        if item.prisms:
            morphs, attrs = [], []
            for parts, base_z, height, building_attrs, _name in item.prisms:
                parts = [[_shifted(ring, shift) for ring in part] for part in parts]
                morphs.append((get_prism_body(parts, base_z, height), surfaces.get(item.layer)))
                attrs.append(building_attrs)
            guids = _create_morphs(host, morphs)
            rows += [(guid, dict(a, **{constants.UDT_LOT_KEY: lot_key})) for guid, a in zip(guids, attrs)]
        elif item.faces and item in ground:
            lift = 0.0 if item.layer == "CTX::Terrain" else constants.ARCHICAD_SURFACE_LIFT
            if item.layer != "CTX::Terrain":   # 지형은 아래 Mesh 하나 — 나머지 분류는 색 면으로 덮는다
                guids = _create_surface(host, moved, item.faces, lift, surfaces.get(item.layer))
        elif item.faces:   # 대상지 옹벽·원지형 등 지면 밖 메시
            guids = _create_surface(host, moved, item.faces, 0.0, surfaces.get(item.layer))
        elif item.polylines:
            data = [{"coordinates": coords, "layerIndex": layer_index.get(item.layer), "floorInd": 0}
                    for coords in (get_polyline_coords(pts, closed, shift) for pts, closed in item.polylines) if coords]
            for start in range(0, len(data), constants.ARCHICAD_BATCH * 10):
                guids += _get_ids(host.call("CreatePolylines", polylinesData=data[start:start + constants.ARCHICAD_BATCH * 10]))
        if item.faces or item.prisms:   # 레이어는 분류·속성을 넣은 뒤에 옮긴다(숨긴 레이어 요소는 고칠 수 없다)
            moves.append((guids, layer_index.get(item.layer)))
        if not item.prisms:
            rows += [(guid, dict(item.attrs or {}, NAME=item.name, **{constants.UDT_LOT_KEY: lot_key})) for guid in guids]
        good = [g for g in guids if g]
        baked += good
        if good:
            out.append(good[0])
    if ground:
        extent = next((pts for item in items if item.layer == "CTX::Ref" and item.name == "extent" for pts, _closed in item.polylines), [])
        mesh_id = _create_ground_mesh(host, ground, extent, shift)
        if mesh_id:   # 지형 항목의 몫(지형 항목은 위 반복에서 요소를 만들지 않는다)
            baked.append(mesh_id)
            rows.append((mesh_id, {constants.UDT_LOT_KEY: lot_key, "NAME": "terrain"}))
            moves.append(([mesh_id], layer_index.get("CTX::Terrain")))
            out.append(mesh_id)
    _set_properties(host, rows, classification)
    for guids, index in moves:
        if index is not None:
            _set_layer(host, guids, index)
    return out


def _create_ground_mesh(host, ground, extent, shift):
    # type: (object, list, list, tuple) -> str
    """지면 분류 메시들 → Archicad Mesh 하나(get_ground_mesh). 실패하면 None — 분류 면 Morph는 남는다."""
    mesh = get_ground_mesh(ground, extent)
    if not mesh:
        return None
    def coords(points):
        return [_xyz(x + shift[0], y + shift[1], z) for x, y, z in points]
    data = {"polygonCoordinates": coords(mesh["outer"]), "level": 0.0, "floorIndex": 0, "skirtType": "SurfaceOnlyWithoutSkirt",
            "ridges": "AllSmooth", "showLines": False}
    if mesh["holes"]:
        data["holes"] = [{"polygonCoordinates": coords(loop)} for loop in mesh["holes"]]
    if mesh["sublines"]:
        data["sublines"] = [{"coordinates": coords(line)} for line in mesh["sublines"]]
    return (_get_ids(host.call("CreateMeshes", meshesData=[data])) or [None])[0]


def write_ref_and_origin(host, prepared, lot_key=None):
    # type: (object, object, str) -> list
    """원점 표식(CTX::Ref — 핫스팟 + 'ORIGIN E … N …' 글자, 속성 = Ref 속성 전부)을 대상지 원점에. 문서 원점은 재사용이 아니면 기록.
    출력: id 2개(context_baker와 같은 수 — run이 베이크 실패를 센다)."""
    lot_key = _get_lot_key(prepared, lot_key)
    shift = _get_shift(prepared)
    layer = constants.CTX_ROOT_LAYER + "::Ref"
    index = _ensure_layers(host, [layer]).get(layer)
    spot = _get_ids(host.call("CreateHotspots", hotspotsData=[{"position": {"x": shift[0], "y": shift[1]}, "layerIndex": index, "floorInd": 0}]))
    text = _get_ids(host.call("CreateTexts", textsData=[{"coordinate": _xyz(shift[0], shift[1], 0.0), "layerIndex": index, "floorIndex": 0,
                                                         "text": "ORIGIN E %.0f N %.0f" % tuple(prepared.origin), "height": 2.0}]))
    ids = [g for g in spot + text if g]
    _set_properties(host, [(g, dict(get_ref_attrs(prepared), **{constants.UDT_LOT_KEY: lot_key})) for g in ids], _ensure_classification(host))
    host.baked.setdefault(lot_key, []).extend(ids)
    if not prepared.origin_reused:
        _set_doc_origin(host, getattr(prepared, "doc_origin", None) or prepared.origin)
    return ids


def save_copy(host, path, names=None, timing=None):
    # type: (object, str, list, dict) -> str
    """마지막으로 구운 대상지 요소를 모듈 사본 context.mod로 쓴다(path의 파일 이름은 무시하고 같은 폴더). 원점은 context.json."""
    path = os.path.join(os.path.dirname(path), constants.ARCHICAD_MODEL_FILE_NAME)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    timing = timing if timing is not None else {}
    guids = host.baked.get(host.last_lot, [])
    t = time.time()
    host.call("SaveAsModuleFile", moduleFilePath=path, elements=[{"elementId": {"guid": g}} for g in guids])
    timing.update(select_s=0.0, write_s=round(time.time() - t, 2), objects=len(guids), bytes=os.path.getsize(path) if os.path.exists(path) else 0)
    return path


# ── 다시 넣기·줌·커브 ─────────────────────────────────────────

def import_mod(host, result_dir):
    # type: (object, str) -> dict
    """<result_dir>/context.mod를 핫링크로 놓는다(sketchup_baker.import_skp와 같은 원점 규칙). 같은 lot_key 요소는 먼저 지운다."""
    path = os.path.join(result_dir, constants.ARCHICAD_MODEL_FILE_NAME)
    result = {"ok": False, "layers": 0, "objects": 0, "replaced": False, "text": "", "shift": [0.0, 0.0]}
    if not os.path.exists(path):
        result["text"] = tr("파일이 없습니다: {0}", path)
        return result
    meta = read_meta(result_dir)
    origin = tuple(float(v) for v in (meta.get("origin") or [])) or None
    file_doc_origin = tuple(float(v) for v in (meta.get("doc_origin") or [])) or origin
    doc_origin = get_doc_origin(host)
    if file_doc_origin and doc_origin and (file_doc_origin == (0.0, 0.0)) != (doc_origin == (0.0, 0.0)):
        result["text"] = tr("좌표 방식이 다른 모델입니다(원점 이동 / 실제 좌표) — 새 모델에서 넣으세요")
        return result
    if file_doc_origin and doc_origin and math.hypot(file_doc_origin[0] - doc_origin[0], file_doc_origin[1] - doc_origin[1]) > constants.ORIGIN_MAX_OFFSET:
        result["text"] = tr("다른 지역 모델입니다 — 새 모델에서 넣으세요 (원점 차이 > {0:.0f} m)", constants.ORIGIN_MAX_OFFSET)
        return result
    lot_key = meta.get("lot_key") or (get_lot_key(meta["pnus"]) if meta.get("pnus") else "")
    if lot_key:
        result["replaced"] = clear_previous(host, lot_key)[0] > 0
    target = doc_origin or file_doc_origin
    shift = [file_doc_origin[0] - target[0], file_doc_origin[1] - target[1]] if file_doc_origin and target else [0.0, 0.0]
    node = (host.call("CreateHotlinkNodes", hotlinkNodes=[{"sourceLocation": path, "name": meta.get("lot_name") or os.path.basename(result_dir)}])
            .get("hotlinkNodes") or [{}])[0]
    node_id = node.get("hotlinkNodeId")
    if not node_id:
        result["text"] = tr("모듈을 넣지 못했습니다: {0}", path)
        return result
    placed = _get_ids(host.call("CreateHotlinkInstances", hotlinkInstances=[{"hotlinkNodeId": node_id, "origin": {"x": shift[0], "y": shift[1]}}]))
    if file_doc_origin and not doc_origin:
        _set_doc_origin(host, file_doc_origin)
    result.update(ok=bool(placed and placed[0]), objects=len([g for g in placed if g]), layers=1, shift=shift,
                  text="" if placed and placed[0] else tr("모듈을 넣지 못했습니다: {0}", path))
    return result


def zoom_to_site(host, result_dir, center_lng_lat=None):
    # type: (object, str, list) -> bool
    """이번 결과의 요소(없으면 전체)가 화면에 들어오게 한다. Archicad는 범위 지정 줌이 없어 요소 맞춤으로 대신한다."""
    meta = read_meta(result_dir) if result_dir else {}
    guids = host.baked.get(meta.get("lot_key") or "", []) if not center_lng_lat else []
    host.call("FitInWindow", **({"elements": [{"elementId": {"guid": g}} for g in guids]} if guids else {}))
    return True


def get_selected_ring(host):
    # type: (object) -> tuple
    """선택한 요소 하나(폴리선·채우기·슬래브·영역·메시)의 바깥 고리 → ([(x, y)], ''). 못 쓰면 ([], 사용자 안내)."""
    selected = host.call("GetSelectedElements").get("elements") or []
    if len(selected) != 1:
        return [], (tr("Archicad에서 폴리선·채우기·슬래브 하나를 먼저 선택하고 다시 누르세요") if not selected
                    else tr("하나만 선택하세요({0}개 선택됨)", len(selected)))
    details = (host.call("GetDetailsOfElements", elements=selected).get("detailsOfElements") or [{}])[0]
    specific = details.get("details") or details.get("typeSpecificDetails") or {}
    points = specific.get("coordinates") or specific.get("polygonCoordinates") or specific.get("polygonOutline") or []
    ring = [(float(p["x"]), float(p["y"])) for p in points if isinstance(p, dict) and "x" in p]
    if len(ring) < 3:
        return [], tr("닫힌 폴리선·채우기·슬래브·영역만 받습니다")
    return ring, ""
