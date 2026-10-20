"""Rhino 문서를 만지는 유일한 모듈 — 베이크(= 3dm 생성)·원점 기록·사본 저장·재삽입·줌 (docs/code_map.md §2·§6·§7).

Rhino 안에서만 import된다. context_geometry가 만든 BakeItem(layer, geometry, attrs, name)을 받아 굽는다 — 좌표는 이미 로컬 m이고,
여기서는 문서 단위 환산(Transform.Scale 복제본)과 원점 기록(CTX::Ref UserString · doc.Strings · EarthAnchorPoint)만 한다.
모든 베이크 객체에 UDT_MANAGED=1 · UDT_LOT_KEY를 붙여 clear_previous가 같은 키의 객체만 지운다(사용자 객체 보존).

    bake(doc, items, prepared) → [Guid]           write_ref_and_origin(doc, prepared) → [Guid]
    save_copy(doc, path, object_ids, timing) → path   import_3dm(doc, result_dir, lot_key) → {ok, layers, objects, replaced, text}
    clear_previous(doc, lot_key) → (objects, layers)  zoom_to_site(doc, result_dir, center_lng_lat) → bool
"""

import hashlib
import json
import math
import os
import re
import time
import types

try:
    import Rhino
    import System
    from System.Collections.Generic import List
    from System.Drawing import Color
except ImportError:   # Blender — blender_baker가 순수 파이썬 도우미(get_lot_key·get_ref_attrs·read_meta)만 쓴다
    Rhino = System = List = Color = None

import constants
import non_rhino_utils
from context_builder import DomainError
from context_geometry import get_local_pts

_CMYK_RE = re.compile(rb"^(\S+) (\S+) (\S+) (\S+) ([kK])(?=\r?$)", re.M)   # Rhino .ai는 CRLF — \r은 남긴다


# ── 키·단위·레이어 ───────────────────────────────────────────

def get_lot_key(pnus):
    # type: (list) -> str
    """pnus 정렬 후 sha1 앞 8자리 — UDT_LOT_KEY 값."""
    return hashlib.sha1(",".join(sorted(str(p) for p in pnus)).encode("utf-8")).hexdigest()[:8]


def get_model_unit_scale(doc):
    # type: (object) -> float
    """내부 m → 문서 단위 배율. 입력: RhinoDoc. 처리: RhinoMath.UnitScale. 출력: 양수 배율. None/Custom 단위면 DomainError(doc_unit_invalid)."""
    units = doc.ModelUnitSystem
    if str(units) == "None" or units in (Rhino.UnitSystem.CustomUnits, Rhino.UnitSystem.Unset):
        raise DomainError("doc_unit_invalid", "Rhino 문서 단위는 mm, cm, m 같은 표준 단위로 설정해야 합니다")
    scale = float(Rhino.RhinoMath.UnitScale(Rhino.UnitSystem.Meters, units))
    if scale <= 0.0:
        raise DomainError("doc_unit_invalid", "Rhino 문서 단위 변환 배율을 계산할 수 없습니다")
    return scale


def get_doc_origin(doc):
    # type: (object) -> tuple
    """doc.Strings GORANI_ORIGIN_E/N → (E, N). 없거나 좌표계가 지금과 다르면(국내 문서에 해외 대상지 등) None.
    context_builder.run이 request['doc_origin']에 넣는다."""
    e, n, crs = (doc.Strings.GetValue(key) for key in constants.DOC_ORIGIN_KEYS)
    if crs and crs != non_rhino_utils.get_crs_label():
        return None
    try:
        return (float(e), float(n)) if e and n else None
    except ValueError:
        return None


def _set_doc_origin(doc, origin):
    # type: (object, tuple) -> None
    """doc.Strings 원점 3키 + EarthAnchorPoint(위경도, ModelNorth=+Y). 재사용 여부 판단은 호출자가 한다."""
    doc.Strings.SetString(constants.DOC_ORIGIN_KEYS[0], "%.3f" % origin[0])
    doc.Strings.SetString(constants.DOC_ORIGIN_KEYS[1], "%.3f" % origin[1])
    doc.Strings.SetString(constants.DOC_ORIGIN_KEYS[2], non_rhino_utils.get_crs_label())
    lng, lat = non_rhino_utils.get_wgs84_from_tm(origin[0], origin[1])
    anchor = Rhino.DocObjects.EarthAnchorPoint()
    anchor.EarthBasepointLatitude = lat
    anchor.EarthBasepointLongitude = lng
    anchor.EarthBasepointElevation = 0.0
    anchor.ModelBasePoint = Rhino.Geometry.Point3d.Origin
    anchor.ModelNorth = Rhino.Geometry.Vector3d.YAxis
    anchor.ModelEast = Rhino.Geometry.Vector3d.XAxis
    anchor.Name = "%s origin E %.0f N %.0f" % (constants.TOOL_NAME, origin[0], origin[1])
    doc.EarthAnchorPoint = anchor


def _get_bm_leaf(full_path):
    # type: (str) -> str
    """'BM::07_bldg_low 건물 1~4층' → '07_bldg_low' (BM_LAYERS 이름 — 레이어명 첫 단어). BM 아래가 아니면 ""."""
    parts = full_path.split("::")
    return parts[1].split(" ")[0] if len(parts) > 1 and parts[0] == constants.BM_ROOT_LAYER else ""


def _get_zoning_rgb(group, leaf):
    # type: (str, str) -> tuple
    """CTX::Zoning::<구분>::<종류> → 현황도 11~13 범례 색(선 색, 없으면 칠 색). 모르는 칸은 Zoning 색."""
    theme = next((key for key, name in constants.ZONING_LAYERS.items() if name == group), None)
    sheet, key = {"zone": ("zone", next((k for k, label, _ in constants.SHEET_LEGENDS["zone"][1] if label == leaf), None)),
                  "district": ("district", "district"), "area": ("district", "area"), "plan": ("facility", "plan"),
                  "facility": ("facility", constants.SHEET_FACILITY_KEYS.get(leaf, "facility_etc"))}.get(theme, ("", None))
    style = next((s for k, _, s in constants.SHEET_LEGENDS[sheet][1] if k == key), {}) if sheet else {}
    color = style.get("stroke") if style.get("stroke", "none") != "none" else style.get("fill", "none")
    if not color.startswith("#"):
        return constants.CTX_LAYERS["Zoning"]
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def get_layer_rgb(full_path):
    # type: (str) -> tuple
    """레이어 FullPath → RGB. CTX는 constants.CTX_LAYERS(하위 레이어는 부모 색, Zoning 하위는 현황도 범례 색), BM은 K톤 → 회색(서브레이어는 부모 톤)."""
    root, _, rest = full_path.partition("::")
    if root == constants.CTX_ROOT_LAYER:
        names = rest.split("::")
        if names[0] == "Zoning" and len(names) == 3:
            return _get_zoning_rgb(names[1], names[2])
        return constants.CTX_LAYERS.get(rest) or constants.CTX_LAYERS.get(names[0]) or (0, 0, 0)
    if root == constants.BM_ROOT_LAYER:
        leaf = _get_bm_leaf(full_path)
        for name, _label, fill_k, line_k, _weights in constants.BM_LAYERS:
            if name == leaf:
                k = line_k if line_k is not None else (fill_k or 0)
                v = int(round(255 * (1 - k / 100.0)))
                return (v, v, v)
    return (0, 0, 0)


def _ensure_layer(doc, full_path, rgb=None, layer_cache=None):
    # type: (object, str, tuple, dict) -> int
    """'CTX::Buildings' 같은 FullPath의 레이어를 부모부터 만들고 최하위 인덱스를 돌려준다. 색은 이미 있는 레이어에도 다시 적용."""
    layer_cache = layer_cache if layer_cache is not None else {}
    names = full_path.split("::")
    parent_id = System.Guid.Empty
    index = -1
    for depth, name in enumerate(names):
        path = "::".join(names[:depth + 1])
        index = layer_cache.get(path, -1)
        if index < 0:
            index = doc.Layers.FindByFullPath(path, -1)
            if index >= 0 and doc.Layers[index].IsDeleted:   # 지운 레이어도 이름으로 찾힌다 — 거기 넣으면 추가 실패
                index = -1
        if index < 0:
            layer = Rhino.DocObjects.Layer()
            layer.Name = name
            hidden_bm = _get_bm_leaf(path) in constants.BM_HIDDEN_LAYERS
            if hidden_bm or (path.partition("::")[2] in constants.CTX_HIDDEN_LAYERS and path.startswith(constants.CTX_ROOT_LAYER + "::")):
                layer.IsVisible = False
            if path == constants.BM_ROOT_LAYER:   # 2D 도면은 3D와 겹쳐 어지럽다 — 루트만 끄면 Rhino가 자식을 숨기고, 루트를 켜면 자식도 켜진다
                layer.IsVisible = False
            if parent_id != System.Guid.Empty:
                layer.ParentLayerId = parent_id
            index = doc.Layers.Add(layer)
            if index < 0:
                raise RuntimeError("Rhino 레이어를 만들 수 없습니다: %s" % path)
            if hidden_bm:   # BM 루트를 켜도 꺼진 채로 — 꺼진 부모를 켜면 자식은 PersistentVisibility로 돌아간다(Add 전에 넣으면 무시된다)
                doc.Layers[index].SetPersistentVisibility(False)
        layer_cache[path] = index
        parent_id = doc.Layers[index].Id
    if rgb is not None:
        color = Color.FromArgb(int(rgb[0]), int(rgb[1]), int(rgb[2]))
        if doc.Layers[index].Color.ToArgb() != color.ToArgb():
            doc.Layers[index].Color = color
    return int(index)


def _get_layer_indexes(doc, root_name):
    # type: (object, str) -> list
    """root_name 레이어와 그 아래 전부의 인덱스 — 깊은 것부터(자식을 먼저 지워야 부모가 지워진다)."""
    indexes = [layer.Index for layer in doc.Layers
               if not layer.IsDeleted and (layer.FullPath == root_name or layer.FullPath.startswith(root_name + "::"))]
    return sorted(indexes, key=lambda i: -doc.Layers[i].FullPath.count("::"))


def _get_layer_indexes_with_parents(doc, indexes):
    # type: (object, set) -> set
    """레이어 인덱스 집합 + 그 조상 전부. 부모가 꺼진 서브레이어(BM::02b_landuse::detached)의 객체는 자기 레이어만 켜도 선택이 안 된다(job 1007-232707-656b)."""
    out = set()
    for index in indexes:
        while index >= 0 and index not in out:
            out.add(index)
            parent_id = doc.Layers[index].ParentLayerId
            parent = doc.Layers.FindId(parent_id) if parent_id != System.Guid.Empty else None
            index = parent.Index if parent is not None else -1
    return out


def _set_layer_states(doc, states):
    # type: (object, dict) -> None
    """{index: (visible, locked[, plot_weight])} 적용 — 부모부터(얕은 → 깊은). Rhino는 부모를 켤 때 자식을 PersistentVisibility로 되돌리므로
    자식을 먼저 끄면 뒤에 부모(BM 루트 포함, True→True여도)를 만지는 순간 다시 켜진다(job 1007-233219-dff6)."""
    for index in sorted(states, key=lambda i: doc.Layers[i].FullPath.count("::")):
        layer = doc.Layers[index]
        state = states[index]
        if layer.IsVisible != bool(state[0]):   # 같은 값도 다시 넣으면 꺼진 부모 아래 자식의 PersistentVisibility가 지워진다
            layer.IsVisible = bool(state[0])
        layer.IsLocked = bool(state[1])
        if len(state) > 2 and state[2]:
            layer.PlotWeight = state[2]


def _get_objects(doc):
    # type: (object) -> list
    """숨김·잠금 포함 문서 객체 전부(BM 레이어는 기본 off·잠금이라 기본 열거에서 빠진다)."""
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.HiddenObjects = True
    settings.LockedObjects = True
    settings.IncludeLights = False
    settings.IncludeGrips = False
    return list(doc.Objects.GetObjectList(settings))


# ── 지우기·베이크 ────────────────────────────────────────────

def clear_previous(doc, lot_key=None):
    # type: (object, str) -> tuple
    """UDT_MANAGED 객체(lot_key를 주면 같은 UDT_LOT_KEY만) 삭제 + 빈 CTX·BM 레이어 정리. 출력 (지운 객체 수, 지운 레이어 수). 사용자 객체는 남긴다."""
    deleted = 0
    # Rhino 내장 UserString 검색 — 파이썬으로 문서 전체를 훑으면 객체 17만 개 문서에서 9.8 s 걸렸다(2026-10-08 실측)
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.HiddenObjects = True
    settings.LockedObjects = True
    key, value = (constants.UDT_LOT_KEY, lot_key) if lot_key is not None else (constants.UDT_MANAGED_KEY, "1")
    found = doc.Objects.FindByUserString(key, value, True, False, True, settings) or []
    redraw = doc.Views.RedrawEnabled
    doc.Views.RedrawEnabled = False
    try:
        for rhino_object in found:
            if rhino_object.Attributes.GetUserString(constants.UDT_MANAGED_KEY) == "1" and doc.Objects.Delete(rhino_object, True, True):
                deleted += 1
    finally:
        doc.Views.RedrawEnabled = redraw
    layers = 0
    indexes = _get_layer_indexes(doc, constants.CTX_ROOT_LAYER) + _get_layer_indexes(doc, constants.BM_ROOT_LAYER)
    if doc.Layers.CurrentLayerIndex in indexes:
        doc.Layers.SetCurrentLayerIndex(0, True)
    for index in indexes:
        layer = doc.Layers[index]
        if layer.GetChildren() or doc.Objects.FindByLayer(layer):   # Delete는 객체가 있으면 실패하지만 자식 검사는 직접
            continue
        if doc.Layers.Delete(index, True):
            layers += 1
    return deleted, layers


def _get_dim_style_id(doc, height, style_cache):
    # type: (object, float, dict) -> object
    """문자 높이(문서 단위)에 맞는 치수 스타일 'Gorani_<높이>'를 찾거나 만들어 Id. 객체 TextHeight 오버라이드는 Objects.Add에서 사라진다(job 1007-233219-dff6) —
    높이를 스타일에 두는 방식."""
    name = constants.BM_DIM_STYLE_FORMAT % height
    if name not in style_cache:
        style = doc.DimStyles.FindName(name)
        if style is None:
            style = Rhino.DocObjects.DimensionStyle()
            style.Name = name
            style.TextHeight = float(height)
            style = doc.DimStyles[doc.DimStyles.Add(style, False)]
        style_cache[name] = style.Id
    return style_cache[name]


def bake(doc, items, prepared, lot_key=None):
    # type: (object, list, object, str) -> list
    """BakeItem 목록을 문서에 넣는다. 출력: 추가된 Guid 목록(실패 항목은 빠진다 — 수를 비교해 경고).

    입력: items[i].layer FullPath, .geometry(로컬 m RhinoCommon 객체 — Point3d면 Point로 감싼다), .attrs {UserString}, .name.
    처리: RedrawEnabled 끄고 → 레이어 ensure(색 CTX_LAYERS/BM_LAYERS) → (실제 좌표 방식이면 계산 원점 − 문서 원점만큼 Translation)
          → m→문서 단위 Transform.Scale 복제본 → UserString + UDT_MANAGED·UDT_LOT_KEY → Add.
          옮길 때 메시는 배정밀도 정점으로 바꾼다 — 단정밀도는 서울 좌표(55만 m)에서 6 cm 단위로 뭉개진다.
    """
    scale = get_model_unit_scale(doc)
    lot_key = lot_key or getattr(prepared, "target_key", "") or get_lot_key((prepared.request or {}).get("pnus") or [])
    doc_origin = getattr(prepared, "doc_origin", None) or prepared.origin
    shift = (prepared.origin[0] - doc_origin[0], prepared.origin[1] - doc_origin[1])
    moved = abs(shift[0]) > 1e-9 or abs(shift[1]) > 1e-9
    xform = Rhino.Geometry.Transform.Scale(Rhino.Geometry.Point3d.Origin, scale) if abs(scale - 1.0) > 1e-12 else None
    if moved:   # A*B는 B 먼저 — 로컬 m에서 옮기고 단위를 바꾼다
        translation = Rhino.Geometry.Transform.Translation(shift[0], shift[1], 0.0)
        xform = translation if xform is None else xform * translation
    layer_cache, style_cache, ids = {}, {}, []
    redraw = doc.Views.RedrawEnabled
    doc.Views.RedrawEnabled = False
    try:
        for item in items:
            geometry = item.geometry
            if isinstance(geometry, Rhino.Geometry.Point3d):
                geometry = Rhino.Geometry.Point(geometry)
            geometry = geometry.Duplicate()
            if moved and isinstance(geometry, Rhino.Geometry.Mesh):
                geometry.Vertices.UseDoublePrecisionVertices = True
            if xform is not None:
                geometry.Transform(xform)
            if isinstance(geometry, Rhino.Geometry.TextEntity):   # Transform은 평면만 옮긴다 — 높이는 item.text_height(m)에서 문서 단위로
                height = float(getattr(item, "text_height", 0.0) or geometry.TextHeight) * scale
                justification = geometry.Justification   # 스타일을 바꾸면 TopLeft로 돌아간다(job 1012-224150-e615 BM::12_labels)
                geometry.DimensionStyleId = _get_dim_style_id(doc, height, style_cache)
                geometry.TextHeight = height
                geometry.Justification = justification
            attributes = doc.CreateDefaultAttributes()
            attributes.LayerIndex = _ensure_layer(doc, item.layer, get_layer_rgb(item.layer), layer_cache)
            if getattr(item, "name", ""):
                attributes.Name = str(item.name)
            for key, value in (item.attrs or {}).items():
                attributes.SetUserString(str(key), "" if value is None else str(value))
            attributes.SetUserString(constants.UDT_MANAGED_KEY, "1")
            attributes.SetUserString(constants.UDT_LOT_KEY, lot_key)
            guid = doc.Objects.Add(geometry, attributes)
            if guid != System.Guid.Empty:
                ids.append(guid)
    finally:
        doc.Views.RedrawEnabled = redraw
        doc.Views.Redraw()
    return ids


def get_ref_attrs(prepared):
    # type: (object) -> dict
    """CTX::Ref 원점 마커 UserString(code_map §7.1 Ref 행). 값은 전부 문자열. UDT_LOT_KEY는 bake가 붙인다."""
    stats = prepared.stats or {}
    align = stats.get("align") or {}
    meta = prepared.meta or {}
    dates = meta.get("dates") or {}
    num = lambda v: "" if v is None else "%g" % v
    return {
        "CRS": non_rhino_utils.get_crs_label(), "ORIGIN_E": "%.3f" % prepared.origin[0], "ORIGIN_N": "%.3f" % prepared.origin[1],
        "RADIUS_M": num(prepared.radius), "SHAPE": str(prepared.shape or ""), "SRC_SHEETS": ",".join(stats.get("sheets") or []),
        "BUILT_AT": str(meta.get("built_at") or ""), "TOOL_VERSION": constants.PANEL_VERSION,
        "ALIGN_MEDIAN_M": num(align.get("median")), "ALIGN_P90_M": num(align.get("p90")), "ALIGN_N": str(align.get("n") or 0),
        "ALIGN_DX_DY": "%s,%s" % (num(align.get("dx")), num(align.get("dy"))), "TOPO_YEAR": str(dates.get("terrain") or ""),
        "TRANSFORM": constants.REF_TRANSFORM, "VDATUM": constants.REF_VDATUM,
        "DATE_LOT": str(dates.get("lot") or ""), "DATE_BUILDING": str(dates.get("building") or ""),
        "DATE_TERRAIN": str(dates.get("terrain") or ""), "DATE_UPIS": str(dates.get("upis") or ""),
        "META_LINES": "\n".join(meta.get("meta_lines") or []),
        "PLACEMENT": str(getattr(prepared, "placement", "origin")),
    }


def write_ref_and_origin(doc, prepared, lot_key=None):
    # type: (object, object, str) -> list
    """원점 기록 세 곳 중 ①②(code_map §6): CTX::Ref 원점 Point+TextDot(UserString 전부) 베이크, doc.Strings 3키 + EarthAnchorPoint.
    원점이 재사용(prepared.origin_reused)이면 문서 수준 기록은 덮지 않는다. 출력: Ref 객체 Guid 목록."""
    attrs = get_ref_attrs(prepared)
    origin_pt = Rhino.Geometry.Point3d.Origin
    layer = constants.CTX_ROOT_LAYER + "::Ref"
    items = [types.SimpleNamespace(layer=layer, geometry=Rhino.Geometry.Point(origin_pt), attrs=attrs, name="origin"),
             types.SimpleNamespace(layer=layer, geometry=Rhino.Geometry.TextDot("ORIGIN E %.0f N %.0f" % prepared.origin, origin_pt),
                                   attrs=attrs, name="origin_label")]
    ids = bake(doc, items, prepared, lot_key)
    if not prepared.origin_reused:
        _set_doc_origin(doc, getattr(prepared, "doc_origin", None) or prepared.origin)
    return ids


def save_copy(doc, path, object_ids=None, timing=None):
    # type: (object, str, list, dict) -> str
    """문서를 사본으로 저장(문서 경로는 안 바뀜). object_ids를 주면 그 객체만(WriteSelectedObjectsOnly — 잠금·숨김 레이어도 선택). 실패는 RuntimeError.
    timing dict를 주면 select_s·write_s·objects·bytes를 채운다(run이 log.txt에 남긴다).

    실측(job 1007-230823-e9bc, 8,672객체): 객체별 Select(True)를 RedrawEnabled 켠 채 돌리면 전체 10~11 s(job 1007-225327) →
    Redraw 끄고 Guid 벌크 선택 0.19 s + WriteFile 2.4 s → IncludeRenderMeshes=False면 WriteFile 1.3 s(13.6 MB). File3dm 직접 쓰기는 3.1 s라 버림."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    options = Rhino.FileIO.FileWriteOptions()
    options.UpdateDocumentPath = False
    options.SuppressDialogBoxes = True
    options.IncludeRenderMeshes = False    # 재삽입·표시 때 다시 계산된다 — 쓰기 2.4 → 1.3 s
    options.IncludePreviewImage = False
    timing = timing if timing is not None else {}
    if not object_ids:
        t = time.time()
        if not doc.WriteFile(path, options):
            raise RuntimeError("Rhino 파일을 저장할 수 없습니다: %s" % path)
        timing.update(select_s=0.0, write_s=round(time.time() - t, 2), objects=doc.Objects.Count, bytes=os.path.getsize(path))
        return path
    options.WriteSelectedObjectsOnly = True
    objects = [rhino_object for rhino_object in (doc.Objects.FindId(guid) for guid in object_ids) if rhino_object is not None]
    saved, persistent = {}, {}   # 숨김·잠금 레이어(BM 기본값)의 객체는 선택이 안 되므로 잠시 켜고 푼다 — Select의 ignoreLayer* 인자로는 WriteFile에 안 잡혔다(job 1007-221324-b346)
    redraw = doc.Views.RedrawEnabled
    doc.Views.RedrawEnabled = False
    try:
        for index in _get_layer_indexes_with_parents(doc, {rhino_object.Attributes.LayerIndex for rhino_object in objects}):
            saved[index] = (doc.Layers[index].IsVisible, doc.Layers[index].IsLocked)
            persistent[index] = doc.Layers[index].GetPersistentVisibility()   # 켰다 끄면 켜짐으로 바뀐다(꺼 둔 BM 10b가 BM 루트를 켤 때 같이 켜졌다)
        _set_layer_states(doc, {index: (True, False) for index in saved})
        doc.Objects.UnselectAll()
        t = time.time()
        # 해치가 아닌 객체는 Guid 벌크 선택(Objects.Select(List[Guid])는 해치에 실패했음 — code_map §7.3), 나머지·실패분은 객체별 Select
        plain = [o for o in objects if not isinstance(o, Rhino.DocObjects.HatchObject)]
        if plain:
            doc.Objects.Select(List[System.Guid]([o.Id for o in plain]), True)
        selected = sum(1 for o in objects if o.IsSelected(False) or o.Select(True))
        timing["select_s"] = round(time.time() - t, 2)
        if selected != len(objects):
            raise RuntimeError("저장할 객체 선택 실패 %d/%d" % (selected, len(objects)))
        t = time.time()
        if not doc.WriteFile(path, options):
            raise RuntimeError("Rhino 파일을 저장할 수 없습니다: %s" % path)
        timing.update(write_s=round(time.time() - t, 2), objects=len(objects), bytes=os.path.getsize(path))
    finally:
        doc.Objects.UnselectAll()
        _set_layer_states(doc, saved)
        for index, visible in persistent.items():
            if doc.Layers[index].GetPersistentVisibility() != visible:
                doc.Layers[index].SetPersistentVisibility(visible)
        doc.Views.RedrawEnabled = redraw
        doc.Views.Redraw()
    if path.lower().endswith(".3dm"):   # .dwg는 레이어를 켠 채 둔다 — 2D만 따로 내보낸 파일이라 꺼 둘 이유가 없다
        _set_file_layer_states(doc, path, saved)
    return path


def save_dwg_from_3dm(model_path, dwg_path, layer_root):
    # type: (str, str, str) -> str
    """방금 쓴 3dm 사본을 헤드리스 문서로 열어 layer_root(BM) 아래 객체만 .dwg로 쓴다. 실패는 RuntimeError.
    활성 문서에서 바로 .dwg를 쓰면 Mac Rhino 8이 돌아오지 않았다(2026-10-14 job 1014-152140: 무교동 BM 1,026객체, 10분+ CPU 1 %,
    패널 생성은 12분 뒤 실패) — 같은 객체를 헤드리스 문서에서는 0.2 s(job 1014-152115). 단위는 파일 그대로(OpenHeadless)."""
    doc = Rhino.RhinoDoc.OpenHeadless(model_path)
    if doc is None:
        raise RuntimeError("3dm을 열 수 없습니다: %s" % model_path)
    try:
        for layer in doc.Layers:   # 꺼지거나 잠긴 레이어의 객체는 선택이 안 된다 — 헤드리스 사본이라 되돌리지 않는다
            layer.IsVisible, layer.IsLocked = True, False
        settings = Rhino.DocObjects.ObjectEnumeratorSettings()
        settings.HiddenObjects, settings.LockedObjects, settings.VisibleFilter = True, True, False
        objects = [o for o in doc.Objects.GetObjectList(settings)
                   if doc.Layers.FindIndex(o.Attributes.LayerIndex).FullPath.split("::")[0] == layer_root]
        if not objects:
            raise RuntimeError("%s 레이어에 객체가 없습니다" % layer_root)
        for rhino_object in objects:
            rhino_object.Select(True)
        options = Rhino.FileIO.FileWriteOptions()
        options.SuppressDialogBoxes, options.UpdateDocumentPath, options.WriteSelectedObjectsOnly = True, False, True
        if not doc.WriteFile(dwg_path, options):
            raise RuntimeError("DWG를 저장할 수 없습니다: %s" % dwg_path)
    finally:
        doc.Dispose()
    return dwg_path


def save_dwg(items, prepared, dwg_path):
    # type: (list, object, str) -> str
    """2D 선 도면(BM:: BakeItem, context_geometry.build_basemap_2d)을 .dwg로 — 결과 화면 '2D 만들기'(make_2d). 활성 문서는 건드리지 않는다.
    새 헤드리스 문서(m)에 구워 임시 .3dm으로 쓰고, 실측된 save_dwg_from_3dm(헤드리스로 다시 열어 BM만 .dwg, 0.14 s)에 넘긴다 —
    활성 문서에서 .dwg를 쓰면 Mac에서 멈췄다(save_dwg_from_3dm 주석). 좌표는 3D 베이크와 같다(bake가 옮긴다)."""
    if Rhino is None:
        raise RuntimeError("DWG는 Rhino에서만 저장할 수 있습니다")
    if not items:
        raise RuntimeError("2D 선 도면이 비었습니다")
    temp_path = os.path.splitext(dwg_path)[0] + "_dwg_tmp.3dm"
    doc = Rhino.RhinoDoc.CreateHeadless(None)
    if doc is None:
        raise RuntimeError("DWG용 빈 문서를 만들 수 없습니다")
    try:
        doc.ModelUnitSystem = Rhino.UnitSystem.Meters
        if not bake(doc, items, prepared):
            raise RuntimeError("2D 선 도면을 굽지 못했습니다")
        options = Rhino.FileIO.FileWriteOptions()
        options.SuppressDialogBoxes, options.UpdateDocumentPath = True, False
        if not doc.WriteFile(temp_path, options):
            raise RuntimeError("DWG용 임시 3dm을 저장할 수 없습니다: %s" % temp_path)
    finally:
        doc.Dispose()
    try:
        return save_dwg_from_3dm(temp_path, dwg_path, constants.BM_ROOT_LAYER)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _set_file_layer_states(doc, path, indexes):
    # type: (object, str, object) -> None
    """save_copy가 선택하려고 켠 레이어를 파일에서도 문서 상태(끔·잠금·PersistentVisibility)로 되돌린다 — WriteFile은 켠 순간의 상태로 쓴다.
    BM 루트(기본 off)·CTX_HIDDEN_LAYERS가 파일에서 켜져 나오던 것을 막는다. 전부 켜진 상태면 파일을 다시 쓰지 않는다. File3dm 읽고 쓰기 ≈0.01 s(1012-223825-624e)."""
    layers = {doc.Layers[i].FullPath: doc.Layers[i] for i in indexes}
    if all(layer.IsVisible and not layer.IsLocked for layer in layers.values()):
        return
    model = Rhino.FileIO.File3dm.Read(path)
    for layer in model.AllLayers:
        src = layers.get(layer.FullPath)
        if src is not None:
            layer.IsVisible, layer.IsLocked = src.IsVisible, src.IsLocked
            layer.SetPersistentVisibility(src.GetPersistentVisibility())
    if not model.Write(path, 0):
        raise RuntimeError("Rhino 파일 레이어 상태를 저장할 수 없습니다: %s" % path)


# ── 재삽입·줌 ────────────────────────────────────────────────

def read_meta(result_dir):
    # type: (str) -> dict
    try:
        with open(os.path.join(result_dir, constants.CONTEXT_META_FILE_NAME), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def import_3dm(doc, result_dir, lot_key=None):
    # type: (object, str, str) -> dict
    """<result_dir>/context.3dm을 문서에 다시 넣는다(panel_ui.md import_context). 출력 {ok, layers, objects, replaced, text, shift}.
    같은 lot_key(없으면 context.json pnus로 계산) 객체를 먼저 지운다. context.json.origin ≠ 문서 원점이면 차이만큼 Transform.Translation,
    차이 > ORIGIN_MAX_OFFSET이면 거부. 문서에 원점이 없으면 파일 원점을 기록한다."""
    path = os.path.join(result_dir, constants.CONTEXT_MODEL_FILE_NAME)
    result = {"ok": False, "layers": 0, "objects": 0, "replaced": False, "text": "", "shift": [0.0, 0.0]}
    if not os.path.exists(path):
        result["text"] = "파일이 없습니다: %s" % path
        return result
    meta = read_meta(result_dir)
    file_origin = tuple(float(v) for v in (meta.get("doc_origin") or meta.get("origin") or [])) or None   # 파일 좌표의 원점(world면 0,0)
    doc_origin = get_doc_origin(doc)
    if file_origin and doc_origin and (file_origin == (0.0, 0.0)) != (doc_origin == (0.0, 0.0)):
        result["text"] = "좌표 방식이 다른 문서입니다(원점 이동 / 실제 좌표) — 새 문서에서 넣으세요"
        return result
    if file_origin and doc_origin and math.hypot(file_origin[0] - doc_origin[0], file_origin[1] - doc_origin[1]) > constants.ORIGIN_MAX_OFFSET:
        result["text"] = "다른 지역 문서입니다 — 새 문서에서 넣으세요 (원점 차이 > %.0f m)" % constants.ORIGIN_MAX_OFFSET
        return result
    lot_key = lot_key or meta.get("lot_key") or (get_lot_key(meta["pnus"]) if meta.get("pnus") else None)
    if lot_key:
        result["replaced"] = clear_previous(doc, lot_key)[0] > 0
    before = {rhino_object.Id for rhino_object in _get_objects(doc)}
    ok = Rhino.RhinoApp.RunScript('_-Import "%s" _Enter' % path, False)
    new_objects = [rhino_object for rhino_object in _get_objects(doc) if rhino_object.Id not in before]
    result["objects"] = len(new_objects)
    result["layers"] = len(_get_layer_indexes(doc, constants.CTX_ROOT_LAYER)) + len(_get_layer_indexes(doc, constants.BM_ROOT_LAYER))
    if not ok or not new_objects:
        result["text"] = "Rhino가 파일을 넣지 못했습니다 — %s 를 직접 Import할 수 있습니다" % path
        return result
    if file_origin and doc_origin and file_origin != doc_origin:
        scale = get_model_unit_scale(doc)
        dx, dy = file_origin[0] - doc_origin[0], file_origin[1] - doc_origin[1]   # 세계 = 로컬 + ORIGIN → 로컬' = 로컬 + (파일 원점 − 문서 원점)
        xform = Rhino.Geometry.Transform.Translation(dx * scale, dy * scale, 0.0)
        for rhino_object in new_objects:
            doc.Objects.Transform(rhino_object, xform, True)
        result["shift"] = [dx, dy]
    elif file_origin and not doc_origin:
        _set_doc_origin(doc, file_origin)
    doc.Objects.UnselectAll()
    doc.Views.Redraw()
    result["ok"] = True
    return result


def zoom_to_site(doc, result_dir, center_lng_lat=None):
    # type: (object, str, list) -> bool
    """CTX::Site 객체(또는 경위도 center 주변 100 m)로 활성 뷰 줌. center는 문서 원점(doc.Strings, 없으면 context.json origin) 기준
    get_local_pts로 로컬 환산 — import_3dm이 Translation 보정한 문서(파일 원점 ≠ 문서 원점)에서도 같은 자리."""
    view = doc.Views.ActiveView
    if view is None:
        return False
    scale = get_model_unit_scale(doc)
    meta = read_meta(result_dir)
    index = doc.Layers.FindByFullPath(constants.CTX_ROOT_LAYER + "::Site", -1)
    objects = None if center_lng_lat or index < 0 else doc.Objects.FindByLayer(doc.Layers[index])
    if objects and meta.get("lot_key"):   # 같은 문서의 다른 대상지 Site는 빼고 이번 결과만
        objects = [o for o in objects if o.Attributes.GetUserString(constants.UDT_LOT_KEY) == meta["lot_key"]]
    if center_lng_lat or not objects:   # 경위도 지정, 또는 Site가 없는 위치 방식 — context.json 중심 주변
        origin = get_doc_origin(doc) or meta.get("doc_origin") or meta.get("origin") or [0.0, 0.0]
        if center_lng_lat:
            world, half = non_rhino_utils.get_tm_from_wgs84(float(center_lng_lat[0]), float(center_lng_lat[1])), 100.0
        elif meta.get("center"):
            world, half = meta["center"], 500.0
        else:
            return False
        local = get_local_pts([world], origin)[0]
        cx, cy, half = local.X * scale, local.Y * scale, half * scale
        box = Rhino.Geometry.BoundingBox(cx - half, cy - half, -half, cx + half, cy + half, half)
    else:
        box = Rhino.Geometry.BoundingBox.Empty
        for rhino_object in objects:
            box.Union(rhino_object.Geometry.GetBoundingBox(True))
        box.Inflate(box.Diagonal.Length * 0.5)
    view.ActiveViewport.ZoomBoundingBox(box)
    view.Redraw()
    return True


# ── 베이스맵 ────────────────────────────────────────────────


