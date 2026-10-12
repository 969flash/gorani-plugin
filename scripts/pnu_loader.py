"""주소 또는 PNU 입력을 확정된 PNU 목록으로 바꾼다.

로컬 필지 DB를 먼저 찾고, 사용자가 켠 경우에만 VWorld를 보조로 호출한다.
VWorld가 준 PNU도 로컬 DB에서 다시 확인한다.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

import constants
import lot_db
from lot_db import (
    DEFAULT_DATABASE_PATH,
    ROOT_DIR,
    _PNU_PATTERN,
    _normalize_pnus,
    _open_database,
)

@dataclass
class LotMatch:
    """주소 검색 후보. 형상은 포함하지 않는다."""

    pnu: str
    address: str
    lot_number: str
    land_category: str
    geometry_area: float
    source: str = "local"


@dataclass
class AddressResolution:
    """패널 입력 한 줄의 PNU 해석 결과."""

    query: str
    status: str
    matches: list = field(default_factory=list)
    message: str = ""

    def to_dict(self):
        return asdict(self)



def _lot_match_from_row(row, source="local"):
    return LotMatch(
        pnu=row["pnu"],
        address=row["address"] or "",
        lot_number=row["lot_number"] or "",
        land_category=row["land_category"] or "",
        geometry_area=float(row["geometry_area_sqm"]),
        source=source,
    )


def _matches_for_pnus(connection, pnus, source="local"):
    if not pnus:
        return []

    unique_pnus = []
    seen_pnus = set()
    for pnu in pnus:
        if pnu not in seen_pnus:
            seen_pnus.add(pnu)
            unique_pnus.append(pnu)

    placeholders = ",".join("?" for _ in unique_pnus)
    rows = connection.execute(
        """
        SELECT pnu, address, lot_number, land_category, geometry_area_sqm
        FROM parcels
        WHERE pnu IN (%s)
        """ % placeholders,
        unique_pnus,
    ).fetchall()
    match_by_pnu = {row["pnu"]: _lot_match_from_row(row, source) for row in rows}
    return [match_by_pnu[pnu] for pnu in unique_pnus if pnu in match_by_pnu]



def _query_lines(address_queries):
    """여러 줄 입력 또는 문자열 리스트에서 빈 줄을 제거한다."""
    if address_queries is None:
        return []
    if isinstance(address_queries, str):
        values = [address_queries]
    else:
        try:
            values = list(address_queries)
        except TypeError:
            values = [address_queries]

    queries = []
    for value in values:
        queries.extend(line.strip() for line in str(value or "").splitlines())
    return [query for query in queries if query]


def _address_parts(query):
    """서울 지번의 표기 차이를 정리하고 위치 토큰·지번을 분리한다."""
    text = str(query or "").strip()
    for hyphen in ("‐", "‑", "‒", "–", "−"):
        text = text.replace(hyphen, "-")
    text = re.sub(r"^\s*(?:서울특별시|서울시|서울)\s*", "", text)
    text = re.sub(r"\s*번지\s*$", "", text)
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"(산)\s+(?=\d)", r"\1", text)
    text = re.sub(r"(\d+)\s+(\d+)\s*$", r"\1-\2", text)
    text = re.sub(r"\s+", " ", text).strip()

    lot_match = re.search(r"(산)?(\d+)(?:-(\d+))?$", text)
    mountain = False
    main_number = None
    sub_number = None
    location_text = text
    if lot_match:
        mountain = bool(lot_match.group(1))
        main_number = str(int(lot_match.group(2)))
        sub_number = (
            str(int(lot_match.group(3))) if lot_match.group(3) is not None else None
        )
        location_text = text[: lot_match.start()].strip()

    return {
        "text": text,
        "location_tokens": re.findall(r"[가-힣]+", location_text),
        "mountain": mountain,
        "main_number": main_number,
        "sub_number": sub_number,
    }


def _local_matches(connection, query, limit):
    """지번·법정동 토큰을 이용해 로컬 DB 후보를 조회한다."""
    parts = _address_parts(query)
    if not parts["text"]:
        return [], False

    clauses = []
    values = []
    main_number = parts["main_number"]
    sub_number = parts["sub_number"]
    if main_number is not None:
        raw_lot_number = main_number
        if sub_number is not None:
            raw_lot_number = "%s-%s" % (main_number, sub_number)
            clauses.append("lot_number IN (?, ?)")
            values.extend((raw_lot_number, "산" + raw_lot_number))
        else:
            clauses.append(
                "(lot_number = ? OR lot_number LIKE ? "
                "OR lot_number = ? OR lot_number LIKE ?)"
            )
            values.extend(
                (
                    raw_lot_number,
                    raw_lot_number + "-%",
                    "산" + raw_lot_number,
                    "산" + raw_lot_number + "-%",
                )
            )

    for token in parts["location_tokens"]:
        clauses.append("address LIKE ?")
        values.append("%%%s%%" % token)

    if parts["mountain"]:
        clauses.append("substr(pnu, ?, 1) = ?")
        values.extend(
            (
                constants.PNU_LAND_TYPE_INDEX + 1,
                constants.PNU_LAND_TYPE_MOUNTAIN,
            )
        )

    if not clauses:
        return [], False

    query_sql = """
        SELECT pnu, address, lot_number, land_category, geometry_area_sqm
        FROM parcels
        WHERE %s
        ORDER BY pnu
        LIMIT ?
    """ % " AND ".join(clauses)
    rows = connection.execute(query_sql, values + [limit + 1]).fetchall()
    truncated = len(rows) > limit
    return [_lot_match_from_row(row) for row in rows[:limit]], truncated


def search_lots(query, database_path=None, limit=None):
    """주소 일부를 받아 로컬 필지 후보를 최대 limit개 반환한다."""
    limit = int(limit or constants.ADDRESS_SEARCH_MAX_RESULTS)
    if limit < 1:
        raise ValueError("주소 검색 후보 수는 1 이상이어야 합니다")

    connection = _open_database(database_path)
    try:
        matches, _truncated = _local_matches(connection, query, limit)
        return matches
    finally:
        connection.close()


def get_local_env_value(key):
    """Rhino GUI에서도 쓸 수 있도록 gitignore된 프로젝트 .env를 보조로 읽는다."""
    value = os.environ.get(key)
    if value:
        return value.strip()

    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        env_key, env_value = line.split("=", 1)
        if env_key.strip() == key:
            return env_value.strip().strip('"').strip("'")
    return ""


def _vworld_response_items(query, category, api_key, api_domain):
    """VWorld 주소 검색 1회 결과를 정규화한다. 인증키는 절대 로그에 넣지 않는다."""
    parameters = {
        "service": constants.VWORLD_SEARCH_SERVICE,
        "request": constants.VWORLD_SEARCH_REQUEST,
        "version": constants.VWORLD_SEARCH_VERSION,
        "type": constants.VWORLD_SEARCH_TYPE_ADDRESS,
        "category": category,
        "query": query,
        "format": constants.VWORLD_SEARCH_FORMAT,
        "errorformat": constants.VWORLD_SEARCH_FORMAT,
        "size": constants.VWORLD_SEARCH_SIZE,
        "page": 1,
        "key": api_key,
    }
    if api_domain:
        parameters["domain"] = api_domain
    request = urllib.request.Request(
        constants.VWORLD_SEARCH_URL + "?" + urllib.parse.urlencode(parameters)
    )
    try:
        with urllib.request.urlopen(
            request, timeout=constants.VWORLD_SEARCH_TIMEOUT_SECONDS
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return [], "online_unavailable", "VWorld 주소 검색 HTTP %s" % error.code
    except (urllib.error.URLError, TimeoutError, ValueError):
        return [], "online_unavailable", "VWorld 주소 검색에 연결하지 못했습니다"

    response = payload.get("response") or {}
    status = response.get("status")
    if status == "OK":
        return response.get("result", {}).get("items") or [], "ok", ""
    if status == "NOT_FOUND":
        return [], "not_found", ""

    error = response.get("error") or {}
    message = error.get("text") or "알 수 없는 VWorld API 오류"
    return [], "online_unavailable", "VWorld 주소 검색 오류: %s" % message


def _vworld_matches(connection, query):
    """VWorld 검색 결과의 PNU를 현재 로컬 지적 DB로 검증해 후보화한다."""
    api_key = get_local_env_value(constants.VWORLD_API_KEY_ENV)
    api_domain = get_local_env_value(constants.VWORLD_API_DOMAIN_ENV)
    if not api_key:
        return [], "online_unavailable", "VWORLD_API_KEY가 설정되지 않았습니다"
    if not api_domain:
        return [], "online_unavailable", "VWORLD_API_DOMAIN이 설정되지 않았습니다"

    candidate_pnus = []
    seen_pnus = set()
    for category in (
        constants.VWORLD_SEARCH_CATEGORY_ROAD,
        constants.VWORLD_SEARCH_CATEGORY_LOT,
    ):
        items, status, message = _vworld_response_items(
            query, category, api_key, api_domain
        )
        if status == "online_unavailable":
            return [], status, message
        if not items:
            continue

        for item in items:
            pnu = str(item.get("id") or "").strip()
            if _PNU_PATTERN.fullmatch(pnu) and pnu not in seen_pnus:
                seen_pnus.add(pnu)
                candidate_pnus.append(pnu)
        if candidate_pnus:
            break

    if not candidate_pnus:
        return [], "not_found", "VWorld 주소 검색 결과가 없습니다"

    matches = _matches_for_pnus(connection, candidate_pnus, source="vworld")
    if not matches:
        return [], "not_in_local_db", "VWorld 후보가 현재 로컬 지적 DB에 없습니다"
    return matches, "ok", "VWorld 주소 검색 후보 %d건" % len(matches)


def resolve_addresses(address_queries, use_vworld=False, database_path=None):
    """주소/PNU 입력을 해석한다. 모호한 결과는 자동으로 PNU를 확정하지 않는다."""
    queries = _query_lines(address_queries)
    if not queries:
        return []

    connection = _open_database(database_path)
    try:
        resolutions = []
        for query in queries:
            if query.isdigit() and not _PNU_PATTERN.fullmatch(query):
                resolutions.append(
                    AddressResolution(
                        query=query,
                        status="invalid",
                        message="숫자만 입력할 때는 %d자리 PNU여야 합니다"
                        % constants.PNU_LENGTH,
                    )
                )
                continue

            if _PNU_PATTERN.fullmatch(query):
                matches = _matches_for_pnus(connection, [query], source="pnu")
                resolutions.append(
                    AddressResolution(
                        query=query,
                        status="resolved" if matches else "not_in_local_db",
                        matches=matches,
                        message="" if matches else "로컬 DB에 없는 PNU입니다",
                    )
                )
                continue

            local_matches, truncated = _local_matches(
                connection, query, constants.ADDRESS_SEARCH_MAX_RESULTS
            )
            parts = _address_parts(query)
            if len(local_matches) == 1 and not truncated and parts["main_number"] is not None:
                resolutions.append(
                    AddressResolution(query=query, status="resolved", matches=local_matches)
                )
                continue
            if local_matches:
                resolutions.append(
                    AddressResolution(
                        query=query,
                        status="ambiguous",
                        matches=local_matches,
                        message="후보가 %d건입니다. 동·지번을 더 정확히 입력하세요"
                        % len(local_matches),
                    )
                )
                continue

            if not use_vworld:
                resolutions.append(
                    AddressResolution(
                        query=query,
                        status="not_found",
                        message=(
                            "로컬 DB에서 찾지 못했습니다. "
                            "도로명은 VWorld 보조 검색을 켜세요"
                        ),
                    )
                )
                continue

            online_matches, online_status, online_message = _vworld_matches(
                connection, query
            )
            resolutions.append(
                AddressResolution(
                    query=query,
                    status=(
                        "resolved"
                        if len(online_matches) == 1
                        else ("ambiguous" if online_matches else online_status)
                    ),
                    matches=online_matches,
                    message="VWorld 보조 검색 호출: " + online_message,
                )
            )
        return resolutions
    finally:
        connection.close()


def resolve_run(address_queries, use_vworld=False, database_path=None):
    """여러 줄 주소 입력 진입점. 반환 (pnus, matches_json, log)."""
    resolutions = resolve_addresses(address_queries, use_vworld, database_path)
    matches_json = json.dumps(
        [resolution.to_dict() for resolution in resolutions],
        ensure_ascii=False,
        indent=2,
    )
    if not resolutions:
        return [], matches_json, "주소 또는 PNU를 한 줄 이상 입력하세요"

    unresolved = [resolution for resolution in resolutions if resolution.status != "resolved"]
    logs = []
    for resolution in resolutions:
        if resolution.status == "resolved":
            match = resolution.matches[0]
            logs.append("%s → %s (%s)" % (resolution.query, match.address, match.source))
        else:
            logs.append("%s: %s" % (resolution.query, resolution.message))
    if unresolved:
        logs.append("미해결/모호한 입력이 있어 PNU를 출력하지 않았습니다")
        return [], matches_json, "\n".join(logs)

    pnus = []
    seen_pnus = set()
    for resolution in resolutions:
        pnu = resolution.matches[0].pnu
        if pnu not in seen_pnus:
            seen_pnus.add(pnu)
            pnus.append(pnu)
    logs.append("PNU %d건 확정" % len(pnus))
    return pnus, matches_json, "\n".join(logs)
