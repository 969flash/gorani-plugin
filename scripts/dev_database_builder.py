"""시도별 필지 로컬 DB(data/<시도>_site.db)를 구축한다.

    python3 scripts/dev_database_builder.py --sido 11      # 서울 하나
    python3 scripts/dev_database_builder.py --sido all     # data/raw에 토지특성정보가 있는 시도 전부

이 파일은 Rhino가 아니라 개발용 Python 환경에서 실행한다.
공공 원천 데이터를 내려받아 보관하고, PNU별 공간교차 결과를 SQLite에 적재한다.
모든 공간정보는 EPSG:5186으로 변환한 뒤 좌표·거리는 m, 계산면적은 ㎡로 저장한다.
서울 외 시도는 parcel_id·overlay_id를 시도 코드 × 10^9만큼 띄워 여러 시도 DB를 한 연결로 묶어도 겹치지 않게 한다
(data_pack.open_union). 서울은 기존 배포본과 같게 0부터.
"""

import argparse
import csv
import gzip
import io
import json
import os
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pyogrio
import requests
import shapely
from shapely.geometry import mapping, shape

import constants


ROOT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT_DIR / constants.RAW_DATA_DIRNAME
DATABASE_PATH = ROOT_DIR / constants.DATABASE_PATH
SEOUL_CODE = "11"
ID_OFFSET_PER_SIDO = 10 ** 9   # 시도 하나의 필지·오버레이 수는 10억보다 훨씬 적다(경기 약 500만 필지)


def get_database_path(sido_code):
    # type: (str) -> Path
    """시도 코드 → data/<시도>_site.db."""
    return ROOT_DIR / "data" / ("%s_site.db" % constants.SIDO[sido_code][1])

SEOUL_DOWNLOAD_URL = (
    "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"
)

# 2026년 2월 공개본을 고정해 DB의 재현성을 확보한다.
# 새 공개본 검증 후 seq/reference_date/file_name을 함께 갱신한다.
# inf_id/inf_seq/seq는 열린데이터광장 파일 내려받기 폼(frmFile)의 값이며
# 데이터셋마다 다르다. 페이지가 바뀌면 여기부터 확인한다.
#
# theme — 필지에 겹치는 계획정보의 대분류. overlays 테이블에 그대로 들어간다.
#   zone     용도지역 (건폐·용적·층수·정북일조)
#   district 용도지구 (높이·경관·보호)
#   area     용도구역 (건축 가능 여부)
#   facility 도시계획시설 (대지면적 제외, 일조 기준선)
#   plan     지구단위계획
SEOUL_SOURCES = {
    "seoul_zoning": {
        "name": "서울시 용도지역(도시지역) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21136/S/1/datasetView.do",
        "inf_id": "OA-21136",
        "inf_seq": "3",
        "seq": "6",
        "file_name": "UQ111_zoning_202602.zip",
        "theme": "zone",
        "kind": "용도지역",
        "layer": "UQ111",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "건폐율·용적률·층수·정북일조 적용 여부의 기준",
    },
    "seoul_scenic_district": {
        "name": "서울시 용도지구(경관지구) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21127/S/1/datasetView.do",
        "inf_id": "OA-21127",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "UQ121_용도지구(경관지구)_202602.zip",
        "theme": "district",
        "kind": "경관지구",
        "layer": "UQ121",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "경관지구 층수·높이 상한 (서울시 도시계획 조례 제36~38조)",
    },
    "seoul_height_district": {
        "name": "서울시 용도지구(고도지구) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21128/S/1/datasetView.do",
        "inf_id": "OA-21128",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "UQ123_용도지구(고도지구)_202602.zip",
        "theme": "district",
        "kind": "고도지구",
        "layer": "UQ123",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "최고고도지구 절대높이 상한. 실제 수치는 지구별 고시 확인 필요",
    },
    "seoul_fire_district": {
        "name": "서울시 용도지구(방화지구) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21140/S/1/datasetView.do",
        "inf_id": "OA-21140",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "UQ124_용도지구(방화지구)_202602.zip",
        "theme": "district",
        "kind": "방화지구",
        "layer": "UQ124",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "구조·재료 제한. 규모검토에는 직접 쓰지 않는 참고값",
    },
    "seoul_protect_district": {
        "name": "서울시 용도지구(보호지구) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21143/S/1/datasetView.do",
        "inf_id": "OA-21143",
        "inf_seq": "2",
        "seq": "5",
        "file_name": "UQ126_용도지구(보호지구)_202602.zip",
        "theme": "district",
        "kind": "보호지구",
        "layer": "UQ126",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "역사문화환경보호지구 등. 국가유산 앙각 검토의 1차 단서",
    },
    "seoul_village_district": {
        "name": "서울시 용도지구(취락지구) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21162/S/1/datasetView.do",
        "inf_id": "OA-21162",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "UQ128_용도지구(취락지구)_202602.zip",
        "theme": "district",
        "kind": "취락지구",
        "layer": "UQ128",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "취락지구 건폐율 완화 대상 여부",
    },
    "seoul_promote_district": {
        "name": "서울시 용도지구(개발진흥지구) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21124/S/1/datasetView.do",
        "inf_id": "OA-21124",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "UQ129_용도지구(개발진흥지구)_202602.zip",
        "theme": "district",
        "kind": "개발진흥지구",
        "layer": "UQ129",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "법적 효력 없는 참고자료. 토지이음·관할 지자체 자료와 대조 필요.",
    },
    "seoul_use_limit_district": {
        "name": "서울시 용도지구(특정용도제한지구) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21165/S/1/datasetView.do",
        "inf_id": "OA-21165",
        "inf_seq": "3",
        "seq": "5",
        "file_name": "UQ130_용도지구(특정용도제한지구)_202602.zip",
        "theme": "district",
        "kind": "특정용도제한지구",
        "layer": "UQ130",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "기숙사 건축 가능 여부 확인 대상",
    },
    "seoul_other_district": {
        "name": "서울시 기타용도지구 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21133/S/1/datasetView.do",
        "inf_id": "OA-21133",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "UQ131_기타용도지구_202602.zip",
        "theme": "district",
        "kind": "기타용도지구",
        "layer": "UQ131",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "중점경관관리구역·특화경관지구 등이 여기 들어온다",
    },
    "seoul_greenbelt_area": {
        "name": "서울시 용도구역(개발제한구역) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21123/S/1/datasetView.do",
        "inf_id": "OA-21123",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "UQ141_용도구역(개발제한구역)_202602.zip",
        "theme": "area",
        "kind": "개발제한구역",
        "layer": "UQ141",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "해당하면 신축 사실상 불가 — 후보 필지 제외 판정",
    },
    "seoul_nature_park_area": {
        "name": "서울시 용도구역(도시자연공원구역) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21135/S/1/datasetView.do",
        "inf_id": "OA-21135",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "UQ142_용도구역(도시자연공원구역)_202602.zip",
        "theme": "area",
        "kind": "도시자연공원구역",
        "layer": "UQ142",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "해당하면 신축 사실상 불가 — 후보 필지 제외 판정",
    },
    "seoul_other_area": {
        "name": "서울시 기타용도구역 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21132/S/1/datasetView.do",
        "inf_id": "OA-21132",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "UQ145_기타용도구역_202602.zip",
        "theme": "area",
        "kind": "기타용도구역",
        "layer": "UQ145",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "법적 효력 없는 참고자료. 토지이음·관할 지자체 자료와 대조 필요.",
    },
    "seoul_road_facility": {
        "name": "서울시 도시계획시설(도로) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21134/S/1/datasetView.do",
        "inf_id": "OA-21134",
        "inf_seq": "3",
        "seq": "5",
        "file_name": "UQ151_도시계획시설(도로)_202602.zip",
        "theme": "facility",
        "kind": "도로",
        "layer": "UQ151",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "대지면적 제외(영 제119조1항1호), 건축선, 일조 기준선(영 제86조6항)",
    },
    "seoul_transport_facility": {
        "name": "서울시 도시계획시설(교통시설_도로외) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21130/S/1/datasetView.do",
        "inf_id": "OA-21130",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "UQ152_도시계획시설(교통시설_도로외)_202602.zip",
        "theme": "facility",
        "kind": "기타교통시설",
        "layer": "UQ152",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "철도·자동차정류장·주차장 등. 철도는 일조 기준선 의제 대상",
    },
    "seoul_space_facility": {
        "name": "서울시 도시계획시설(공간시설) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21129/S/1/datasetView.do",
        "inf_id": "OA-21129",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "UQ153_도시계획시설(공간시설)_202602.zip",
        "theme": "facility",
        "kind": "공간시설",
        "layer": "UQ153",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "광장·공원·녹지·유원지·공공공지 — 영 제86조6항 의제 대상 전부",
    },
    "seoul_health_facility": {
        "name": "서울시 도시계획시설(보건위생시설) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21141/S/1/datasetView.do",
        "inf_id": "OA-21141",
        "inf_seq": "2",
        "seq": "5",
        "file_name": "UQ157_도시계획시설(보건위생시설)_202602.zip",
        "theme": "facility",
        "kind": "보건위생시설",
        "layer": "UQ157",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "대지면적 제외 대상",
    },
    "seoul_district_plan": {
        "name": "서울시 지구단위계획구역 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21161/S/1/datasetView.do",
        "inf_id": "OA-21161",
        "inf_seq": "2",
        "seq": "5",
        "file_name": "UQ161_district_plan_202602.zip",
        "theme": "plan",
        "kind": "지구단위계획구역",
        "layer": "UQ161",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "지침 원문은 자동화 불가 — 해당 여부만 표시",
    },
    "seoul_special_plan_area": {
        "name": "서울시 지구단위계획구역(특별계획구역) 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21164/S/1/datasetView.do",
        "inf_id": "OA-21164",
        "inf_seq": "2",
        "seq": "5",
        "file_name": "UQ165_지구단위계획구역(특별계획구역)_202602.zip",
        "theme": "plan",
        "kind": "특별계획구역",
        "layer": "UQ165",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "법적 효력 없는 참고자료. 토지이음·관할 지자체 자료와 대조 필요.",
    },
    "seoul_permit_limit_area": {
        "name": "서울시 개발행위허가제한지역 공간정보",
        "page_url": "https://data.seoul.go.kr/dataList/OA-21125/S/1/datasetView.do",
        "inf_id": "OA-21125",
        "inf_seq": "1",
        "seq": "5",
        "file_name": "967_UQ171_개발행위허가제한지역_202602.zip",
        "theme": "area",
        "kind": "개발행위허가제한지역",
        "layer": "UQ171",
        "reference_date": "2026-02",
        "license": "공공누리 제1유형(출처표시)",
        "crs": "EPSG:5174",
        "note": "해당하면 사업 추진 자체를 재검토",
    },
}

LAND_CHAR_SOURCE = {
    "source_id": "vworld_land_char",
    "name": "국토교통부 토지특성정보 (국가중점데이터)",
    "page_url": "https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?dsId=4&svcCde=NA",
    "license": "공공누리 제1유형(출처표시)",
    "crs": "EPSG:5186",
    "note": (
        "시군구별 SHP. VWorld 로그인이 필요해 수동으로 내려받는다. 반기 갱신. "
        "지목·용도지역·등록면적은 대장 값이라 공간교차로 만들지 않는다. "
        "다만 제2종일반주거의 7층이하 지정 구분은 없어 UQ111로 보조 판정한다. "
        "UQ111 공간교차는 그 판정과 대지가 걸칠 때의 면적 분할에만 쓴다."
    ),
}

LAND_USE_SOURCE = {
    "source_id": constants.LAND_USE_SOURCE_ID,
    "name": "국토교통부 토지이용계획정보",
    "page_url": "https://www.data.go.kr/data/15045900/fileData.do",
    "license": "공공누리 제1유형(출처표시)",
    "crs": "",
    "note": (
        "필지별 지역지구등 지정 현황. 시도별 CSV(AL_D155_<시도>_*)에서 그 시도 것만 쓴다. "
        "고유번호가 PNU라 공간교차 없이 붙는다. 토지이음 화면과 같은 원천이다. "
        "용량이 커 수동으로 내려받아 data/raw/전국_토지이용계획정보에 풀어 둔다."
    ),
}


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _save_metadata(folder, metadata):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "metadata.json"
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def _load_metadata(folder):
    path = folder / "metadata.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def download_seoul_source(source_id, refresh=False):
    """서울 열린데이터광장의 고정 SHP 스냅샷을 내려받고 경로를 반환한다."""
    source = SEOUL_SOURCES[source_id]
    folder = RAW_DIR / source_id / source["reference_date"]
    zip_path = folder / source["file_name"]
    extract_dir = folder / "extracted"

    if refresh or not zip_path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        response = requests.post(
            SEOUL_DOWNLOAD_URL,
            data={
                "infId": source["inf_id"],
                "infSeq": source["inf_seq"],
                "seqNo": source["seq"],
                "seq": source["seq"],
            },
            timeout=120,
        )
        response.raise_for_status()
        if not response.content.startswith(b"PK"):
            raise RuntimeError("%s 다운로드 결과가 ZIP이 아닙니다" % source["name"])
        zip_path.write_bytes(response.content)
        _save_metadata(
            folder,
            {
                "source_id": source_id,
                "name": source["name"],
                "page_url": source["page_url"],
                "reference_date": source["reference_date"],
                "acquired_at": _now(),
                "license": source["license"],
                "crs": source["crs"],
                "note": source["note"],
                "original_file_name": response.headers.get("Content-Disposition", ""),
            },
        )

    if refresh or not list(extract_dir.rglob("*.shp")):
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extract_dir)

    shp_paths = list(extract_dir.rglob("*.shp"))
    if len(shp_paths) != 1:
        raise RuntimeError(
            "%s SHP 파일을 하나로 특정할 수 없습니다: %s" % (source["name"], shp_paths)
        )
    return shp_paths[0], _load_metadata(folder)


def _read_seoul_shapefile(shp_path):
    data = gpd.read_file(shp_path, encoding="cp949")
    if data.crs is None:
        data = data.set_crs(epsg=constants.SEOUL_SOURCE_CRS)
    data = data.to_crs(epsg=constants.DATABASE_CRS)
    invalid = ~data.geometry.is_valid
    if invalid.any():
        data.loc[invalid, "geometry"] = data.loc[invalid, "geometry"].buffer(0)
    return data


def _connect_database(database_path=DATABASE_PATH, fast_build=False):
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    connection.execute("PRAGMA foreign_keys = ON")
    lot_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(parcels)").fetchall()
    }
    if lot_columns and "parcel_id" not in lot_columns:
        connection.close()
        raise RuntimeError(
            "기존 DB 스키마에는 공간 인덱스가 없습니다. "
            "--cadastral-shp로 서울 전체 DB를 다시 구축하세요"
        )

    if fast_build:
        connection.execute("PRAGMA journal_mode = MEMORY")
        connection.execute("PRAGMA synchronous = OFF")
        connection.execute("PRAGMA temp_store = MEMORY")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS data_sources (
            source_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            page_url TEXT NOT NULL,
            reference_date TEXT,
            acquired_at TEXT NOT NULL,
            crs TEXT,
            license TEXT,
            note TEXT
        );

        -- 필지. 도형과 속성 모두 토지특성정보(AL_D194)에서 온다.
        -- 지목·용도지역·등록면적은 대장 값이라 공간교차로 만들지 않는다.
        CREATE TABLE IF NOT EXISTS parcels (
            parcel_id INTEGER PRIMARY KEY,
            pnu TEXT NOT NULL UNIQUE,
            address TEXT,
            lot_number TEXT,
            land_category TEXT,          -- A11 지목명
            registered_area_sqm REAL,    -- A12 대장 등록면적. 건축법 대지면적의 기준
            geometry_area_sqm REAL NOT NULL,  -- 도형 계산면적. 등록면적과 다르다
            zone_code TEXT,              -- A13을 UPIS 코드로 옮긴 값
            zone_name TEXT,              -- A14 원천 용도지역명
            zone_code_2 TEXT,            -- A15 (두 용도지역에 걸친 필지)
            zone_name_2 TEXT,            -- A16
            land_use_status TEXT,        -- A18 토지이용상황 (단독/연립/주거나지 …)
            terrain_height TEXT,         -- A20 지형높이 (저지/평지/완경사/급경사/고지)
            terrain_shape TEXT,          -- A22 지형형상 (정방형/부정형/자루형 …)
            road_contact TEXT,           -- A24 도로접면 (광대로한면/소로각지/맹지 …)
            land_price_won REAL,         -- A25 공시지가 원/㎡
            reference_date TEXT,         -- A26 데이터기준일자
            geometry_json TEXT NOT NULL,
            geometry_crs INTEGER NOT NULL,
            source_id TEXT NOT NULL,
            min_x REAL NOT NULL,
            max_x REAL NOT NULL,
            min_y REAL NOT NULL,
            max_y REAL NOT NULL,
            FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
        );

        -- 계획 오버레이 — 용도지역·용도지구·용도구역·도시계획시설·지구단위계획을
        -- 한 테이블에 담는다. 층별 건축가능영역 계산은 겹침 여부만이 아니라
        -- 도로·공원의 도형 자체를 쓰므로 geometry_json을 함께 보관한다.
        CREATE TABLE IF NOT EXISTS overlays (
            overlay_id INTEGER PRIMARY KEY,
            source_id TEXT NOT NULL,
            theme TEXT NOT NULL,
            layer TEXT NOT NULL,
            kind TEXT NOT NULL,
            code TEXT,
            name TEXT,
            feature_id TEXT,
            notice_number TEXT,
            created_date TEXT,
            attrs_json TEXT,
            area_sqm REAL NOT NULL,
            geometry_json TEXT NOT NULL,
            geometry_crs INTEGER NOT NULL,
            min_x REAL NOT NULL,
            max_x REAL NOT NULL,
            min_y REAL NOT NULL,
            max_y REAL NOT NULL,
            FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
        );

        -- 필지 x 오버레이 교차. DB 구축 시 선계산해 Rhino에서는 조회만 한다.
        CREATE TABLE IF NOT EXISTS parcel_overlays (
            pnu TEXT NOT NULL,
            overlay_id INTEGER NOT NULL,
            overlap_area_sqm REAL NOT NULL,
            overlap_ratio REAL NOT NULL,
            PRIMARY KEY (pnu, overlay_id),
            FOREIGN KEY (pnu) REFERENCES parcels(pnu),
            FOREIGN KEY (overlay_id) REFERENCES overlays(overlay_id)
        );

        -- 사람이 DB를 직접 열어볼 때 쓰는 뷰. 필지 한 줄 + 붙은 계획 한 줄씩.
        -- 겹침은 필지 기준이다: 겹친면적 / 필지면적. 계획 도형은 가로·구역 전체라
        -- 계획 도형을 분모로 잡으면 의미가 없다(필지 하나가 0.x%로 나온다).
        -- 코드는 이 뷰를 쓰지 않는다. lot_db.py는 원본 테이블을 읽는다.
        CREATE VIEW IF NOT EXISTS lot_overview AS
        SELECT lot.pnu,
               lot.address,
               lot.land_category AS 지목,
               lot.zone_name AS 용도지역,
               ROUND(lot.registered_area_sqm, 2) AS 등록면적,
               ROUND(lot.geometry_area_sqm, 2) AS 필지면적,
               lot.road_contact AS 도로접면,
               overlay.theme AS 구분,
               overlay.kind AS 종별,
               overlay.code AS 코드,
               overlay.name AS 원천명칭,
               ROUND(link.overlap_area_sqm, 2) AS 겹친면적,
               ROUND(link.overlap_ratio * 100, 1) AS 필지대비퍼센트,
               ROUND(overlay.area_sqm, 1) AS 계획도형전체면적,
               overlay.layer AS 원천레이어,
               overlay.notice_number AS 고시번호,
               overlay.created_date AS 결정일
        FROM parcels lot
        LEFT JOIN parcel_overlays link ON link.pnu = lot.pnu
        LEFT JOIN overlays overlay ON overlay.overlay_id = link.overlay_id;

        CREATE TABLE IF NOT EXISTS parcel_land_use (
            pnu TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            conflict TEXT NOT NULL,
            source_id TEXT NOT NULL,
            PRIMARY KEY (pnu, code, conflict)
        ) WITHOUT ROWID;

        CREATE INDEX IF NOT EXISTS idx_parcel_overlays_pnu
            ON parcel_overlays(pnu);
        CREATE INDEX IF NOT EXISTS idx_overlays_theme
            ON overlays(theme, kind);
        CREATE INDEX IF NOT EXISTS idx_parcels_lot_number
            ON parcels(lot_number);
        CREATE INDEX IF NOT EXISTS idx_parcels_zone
            ON parcels(zone_code, land_category);

        -- 주변 필지·오버레이 150m 조회용 경계상자 인덱스. RTree를 쓰지 않는 이유는
        -- Rhino 8 Windows CPython의 SQLite에 rtree 모듈이 없기 때문이다.
        CREATE INDEX IF NOT EXISTS idx_parcels_bbox
            ON parcels(min_x, max_x, min_y, max_y);
        CREATE INDEX IF NOT EXISTS idx_overlays_bbox
            ON overlays(min_x, max_x, min_y, max_y);
        """
    )
    connection.execute("PRAGMA user_version = %d" % constants.DATABASE_SCHEMA_VERSION)
    return connection


def _validate_overlay_links(connection):
    """parcel_overlays가 실재하는 오버레이만 가리키는지 확인한다."""
    orphan_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM parcel_overlays link
        LEFT JOIN overlays overlay ON overlay.overlay_id = link.overlay_id
        WHERE overlay.overlay_id IS NULL
        """
    ).fetchone()[0]
    if orphan_count:
        raise RuntimeError("오버레이 링크 불일치: orphan=%d" % orphan_count)


def _upsert_source(connection, source_id, metadata, note=""):
    connection.execute(
        """
        INSERT INTO data_sources
            (source_id, name, page_url, reference_date, acquired_at, crs, license, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            name=excluded.name,
            page_url=excluded.page_url,
            reference_date=excluded.reference_date,
            acquired_at=excluded.acquired_at,
            crs=excluded.crs,
            license=excluded.license,
            note=excluded.note
        """,
        (
            source_id,
            metadata.get("name", source_id),
            metadata.get("page_url", ""),
            metadata.get("reference_date"),
            metadata.get("acquired_at", _now()),
            metadata.get("crs"),
            metadata.get("license"),
            note or metadata.get("note", ""),
        ),
    )


def _bulk_text(value):
    text = "" if value is None else str(value).strip()
    return "" if text.lower() in ("nan", "none", "nat") else text


LAND_CHAR_COLUMNS = (
    "A1",   # 고유번호 PNU
    "A3",   # 법정동명
    "A4",   # 대장구분코드 1:일반 2:산 3:가번지 4:구번지 5:구획정리 6:하천 7:무번지
    "A6",   # 지번
    "A11",  # 지목명
    "A12",  # 토지면적(㎡) — 대장 등록면적
    "A13",  # 용도지역코드1
    "A14",  # 용도지역명1
    "A15",  # 용도지역코드2
    "A16",  # 용도지역명2
    "A18",  # 토지이용상황명
    "A20",  # 지형높이명
    "A22",  # 지형형상명
    "A24",  # 도로접면명
    "A25",  # 공시지가
    "A26",  # 데이터기준일자
)


def _zone_code(land_char_code):
    # type: (object) -> str
    """토지특성정보 용도지역코드를 UPIS 코드로 옮긴다.

    입력:
        land_char_code: A13 또는 A15. "13", "14"처럼 두 자리 문자열.
    처리:
        constants.LAND_CHAR_ZONE_CODES에서 찾는다. 표에 없으면 용도지역이
        아니거나(개발제한구역·용도미지정) 비도시지역이라 확정하지 않는다.
    출력:
        "UQA122" 같은 UPIS 코드. 확정 못 하면 "".
    """
    text = _bulk_text(land_char_code).zfill(2)
    return constants.LAND_CHAR_ZONE_CODES.get(text, "")


def _lot_number(land_ledger_code, jibun):
    """대장구분코드와 지번으로 표시용 지번을 만든다. 산번지는 '산'을 붙인다."""
    jibun = _bulk_text(jibun)
    prefix = "산" if _bulk_text(land_ledger_code).zfill(2) == "02" else ""
    return "%s%s" % (prefix, jibun) if jibun else ""


def _to_float(value):
    try:
        number = float(_bulk_text(value))
    except ValueError:
        return None
    return number


def _prepare_land_char_chunk(data, sido_code=SEOUL_CODE, legacy_sgg=None):
    """토지특성정보 한 묶음을 좌표계·도형·PNU까지 정리한다. 다른 시도 PNU가 섞여 있으면 ValueError.
    legacy_sgg(옛 시군구 → 새 시군구)가 있으면 PNU 앞 5자리를 새 코드로 바꾼다."""
    missing_columns = set(LAND_CHAR_COLUMNS).difference(data.columns)
    if missing_columns:
        raise ValueError(
            "토지특성정보 SHP 필수 컬럼이 없습니다: %s"
            % ", ".join(sorted(missing_columns))
        )

    # .prj가 ESRI:102082로 적혀 있어 to_epsg()가 None을 낸다. 파라미터는 EPSG:5186과 같다.
    data = data.set_crs(epsg=constants.DATABASE_CRS, allow_override=True)

    data = data[data.geometry.notna() & ~data.geometry.is_empty].copy()
    invalid = ~data.geometry.is_valid
    if invalid.any():
        data.loc[invalid, "geometry"] = data.loc[invalid, "geometry"].buffer(0)

    data["pnu_value"] = data["A1"].map(_bulk_text)
    if legacy_sgg:
        data["pnu_value"] = data["pnu_value"].map(lambda pnu: legacy_sgg.get(pnu[:5], pnu[:5]) + pnu[5:])
    pnu_pattern = r"\d{%d}" % constants.PNU_LENGTH
    valid = data["pnu_value"].str.fullmatch(pnu_pattern, na=False)
    if not valid.all():
        # 원천 오류 행은 건너뛴다 — 예: 충북 영동군 AL_D194_43740 '437403202402080001'(18자리)
        print("  유효하지 않은 PNU %d건 건너뜀: %s" % ((~valid).sum(), data.loc[~valid, "pnu_value"].tolist()[:5]), flush=True)
        data = data[valid].copy()
    if not data["pnu_value"].str.startswith(sido_code).all():
        raise ValueError("%s가 아닌 PNU가 SHP에 포함되어 있습니다" % constants.SIDO[sido_code][0])

    data["lot_area"] = data.geometry.area
    return data[data["lot_area"] > 0.0]


def _insert_land_char_lots(connection, lot_data):
    """정리한 토지특성정보를 parcels에 넣는다."""
    rows = []
    for row in lot_data.itertuples(index=False):
        lot_number = _lot_number(row.A4, row.A6)
        legal_dong_name = _bulk_text(row.A3)
        address = " ".join(v for v in (legal_dong_name, lot_number) if v)
        min_x, min_y, max_x, max_y = row.geometry.bounds
        rows.append(
            (
                row.pnu_value,
                address,
                lot_number,
                _bulk_text(row.A11),
                _to_float(row.A12),
                round(float(row.lot_area), 3),
                _zone_code(row.A13),
                _bulk_text(row.A14),
                _zone_code(row.A15),
                _bulk_text(row.A16),
                _bulk_text(row.A18),
                _bulk_text(row.A20),
                _bulk_text(row.A22),
                _bulk_text(row.A24),
                _to_float(row.A25),
                _text_or_date(row.A26),
                json.dumps(mapping(row.geometry), ensure_ascii=False),
                constants.DATABASE_CRS,
                LAND_CHAR_SOURCE["source_id"],
                float(min_x),
                float(max_x),
                float(min_y),
                float(max_y),
            )
        )
    connection.executemany(
        """
        INSERT INTO parcels
            (pnu, address, lot_number, land_category, registered_area_sqm,
             geometry_area_sqm, zone_code, zone_name, zone_code_2, zone_name_2,
             land_use_status, terrain_height, terrain_shape, road_contact,
             land_price_won, reference_date, geometry_json, geometry_crs,
             source_id, min_x, max_x, min_y, max_y)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pnu) DO NOTHING
        """,
        rows,
    )
    return len(rows)


LAND_USE_COLUMNS = ("고유번호", "용도지역지구코드", "용도지역지구명", "저촉여부")
LAND_USE_DATE_COLUMN = "데이터기준일자"   # 없는 판이면 기준일을 비운다


def _get_land_use_paths(land_use_dir, prefix):
    # type: (Path, str) -> list
    """토지이용계획 CSV 경로 — 원본 .csv 또는 보관용으로 압축한 .csv.gz(전국 42 GB → 수 GB)."""
    return sorted(list(land_use_dir.glob(prefix + "*.csv")) + list(land_use_dir.glob(prefix + "*.csv.gz")))


def _open_land_use(path):
    # type: (Path) -> object
    """CSV 텍스트 핸들(cp949). .gz면 풀면서 읽는다."""
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding=constants.LAND_USE_ENCODING, errors="replace", newline="")
    return io.open(path, encoding=constants.LAND_USE_ENCODING, errors="replace", newline="")


def load_land_use(connection, land_use_dir=None, chunk_size=200000, sido_code=SEOUL_CODE):
    # type: (object, object, int, str) -> int
    """토지이용계획정보 CSV를 parcel_land_use에 적재한다.

    입력:
        connection: DB 연결. land_use_dir: CSV 폴더. chunk_size: 커밋 단위 행 수.
    처리:
        시도별 파일 중 sido_code 것만 읽는다. 고유번호가 곧 PNU라 공간교차가 필요 없다.
        같은 (필지, 지역지구, 저촉여부)가 여러 번 나오므로 기본키로 걷어낸다.
        데이터기준일자 최댓값을 data_sources 기준일로 적는다.
        원천 파일에 인코딩 표기가 없어 cp949로 읽는다.
    출력:
        적재한 행 수. 파일이 없으면 FileNotFoundError를 발생시킨다.
    """
    land_use_dir = Path(land_use_dir or (ROOT_DIR / constants.LAND_USE_DIRNAME))
    prefix = constants.LAND_USE_FILE_FORMAT % sido_code
    paths = _get_land_use_paths(land_use_dir, prefix)
    if not paths:
        raise FileNotFoundError(
            "토지이용계획정보 CSV가 없습니다: %s/%s*.csv\n"
            "공공데이터포털 국토교통부_토지이용계획정보(15045900)에서 받아 풀어 두세요."
            % (land_use_dir, prefix)
        )
    source_id = LAND_USE_SOURCE["source_id"]
    _upsert_source(connection, source_id, LAND_USE_SOURCE)
    connection.execute("DELETE FROM parcel_land_use")
    total = 0
    reference_date = ""
    for path in paths:
        with _open_land_use(path) as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            missing = [name for name in LAND_USE_COLUMNS if name not in header]
            if missing:
                raise ValueError(
                    "%s에 필요한 열이 없습니다: %s" % (path.name, ", ".join(missing))
                )
            # DictReader는 행마다 dict를 만들어 1천만 행에서 몇 배 느리다
            pnu_at, code_at, name_at, conflict_at = (
                header.index(name) for name in LAND_USE_COLUMNS
            )
            width = max(pnu_at, code_at, name_at, conflict_at) + 1
            date_at = header.index(LAND_USE_DATE_COLUMN) if LAND_USE_DATE_COLUMN in header else None
            rows = []
            for record in reader:
                if len(record) < width:
                    continue
                if date_at is not None and date_at < len(record) and record[date_at] > reference_date:
                    reference_date = record[date_at]
                pnu = record[pnu_at].strip()
                code = record[code_at].strip()
                name = record[name_at].strip()
                conflict = record[conflict_at].strip()
                if len(pnu) != constants.PNU_LENGTH or not code or not name:
                    continue
                rows.append((pnu, code, name, conflict, source_id))
                if len(rows) >= chunk_size:
                    total += _insert_land_use(connection, rows)
                    rows = []
            if rows:
                total += _insert_land_use(connection, rows)
    connection.execute("UPDATE data_sources SET reference_date = ? WHERE source_id = ?", (reference_date or None, source_id))
    connection.commit()
    return total


def _insert_land_use(connection, rows):
    # type: (object, list) -> int
    """지역지구 행 묶음을 넣는다. 같은 키가 이미 있으면 건너뛴다.

    입력:
        connection: DB 연결. rows: ``(pnu, code, name, conflict, source_id)`` 목록.
    처리:
        executemany로 한 번에 넣고 중복은 기본키로 무시한다.
    출력:
        시도한 행 수.
    """
    connection.executemany(
        """
        INSERT OR IGNORE INTO parcel_land_use (pnu, code, name, conflict, source_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def _spatial_join(lot_data, area_data, columns):
    left = lot_data[["pnu_value", "lot_area", "geometry"]]
    right = area_data[columns + ["geometry"]]
    joined = gpd.sjoin(left, right, how="inner", predicate="intersects")
    if joined.empty:
        return joined

    right_geometries = area_data.geometry.loc[
        joined["index_right"].to_numpy()
    ].to_numpy()
    overlap_geometries = shapely.intersection(
        joined.geometry.to_numpy(), right_geometries
    )
    joined["overlap_area"] = shapely.area(overlap_geometries)
    return joined[
        joined["overlap_area"] > constants.SPATIAL_OVERLAP_MIN_AREA
    ]


OVERLAY_ATTR_COLUMNS = ("FAR", "ROAD_TY", "ROAD_NO", "ROAD_ROLE", "EXCUT_SE", "RESTRICT_N")

# 원천 SHP에서 읽어오는 UPIS 공통 속성. 레이어마다 있는 컬럼이 조금씩 다르다.
OVERLAY_BASE_COLUMNS = (
    "PRESENT_SN",   # 원천 고유번호
    "LCLAS_CL",     # 대분류 코드 — 도시계획시설 세부 종별 판정에 쓴다
    "ATRB_SE",      # 속성구분 코드 — 용도지역 코드·도로 등급이 여기 들어온다
    "DGM_NM",       # 도형 명칭 (원천 자유 텍스트, 오타·인코딩 깨짐 있음)
    "NTFC_SN",      # 고시번호
    "CREATE_DAT",   # 결정일
)


def _text_or_date(value):
    """CREATE_DAT처럼 날짜로 읽히기도 하는 값을 문자열로 통일한다.

    원천에 빈 날짜(NaT)가 섞여 있어 strftime을 바로 부르면 터진다.
    """
    if value is None or value != value:  # NaN·NaT
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return _bulk_text(value)


def _overlay_kind(source, row):
    # type: (dict, object) -> str
    """오버레이 한 건의 세부 종별을 정한다.

    입력:
        source: SEOUL_SOURCES의 원천 정의. row: SHP 한 행(namedtuple).
    처리:
        도시계획시설은 대분류 코드(LCLAS_CL)로 도로·공원·녹지 등을 가른다.
        표에 없거나 도시계획시설이 아니면 원천에 적힌 기본 kind를 쓴다.
    출력:
        "도로", "공원", "고도지구" 같은 종별 문자열.
    """
    if source["theme"] == constants.OVERLAY_THEME_FACILITY:
        code = _bulk_text(getattr(row, "LCLAS_CL", ""))
        kind = constants.FACILITY_KINDS.get(code)
        if kind:
            return kind
    return source["kind"]


def _drop_duplicate_geometries(data):
    """같은 도형이 여러 번 들어온 행을 하나만 남긴다.

    UPIS 원천에는 고시·도형이 똑같고 `PRESENT_SN`만 다른 행이 섞여 있다
    (서울 전체 1,063건). 그대로 두면 필지 x 오버레이 교차가 중복 계산돼
    중첩비가 100%를 넘는다. 결정일이 최신인 행을 남긴다.
    """
    if data.empty:
        return data
    keys = data.geometry.to_wkb()
    if "CREATE_DAT" in data.columns:
        order = data["CREATE_DAT"].map(_text_or_date)
        data = data.assign(_geometry_key=keys, _created=order)
        data = data.sort_values("_created", ascending=False)
    else:
        data = data.assign(_geometry_key=keys)
    data = data[~data["_geometry_key"].duplicated()]
    return data.drop(columns=[
        name for name in ("_geometry_key", "_created") if name in data.columns
    ])


def _insert_overlays(connection, source_id, source, data):
    """한 레이어의 도형을 overlays에 넣고 overlay_id를 붙인 GeoDataFrame을 돌려준다."""
    data = _drop_duplicate_geometries(data)
    if data.empty:
        return data.assign(overlay_id=[])

    # 같은 원천을 다시 적재할 때 기존 행이 남지 않게 먼저 지운다.
    connection.execute(
        """
        DELETE FROM parcel_overlays
        WHERE overlay_id IN (SELECT overlay_id FROM overlays WHERE source_id = ?)
        """,
        (source_id,),
    )
    connection.execute("DELETE FROM overlays WHERE source_id = ?", (source_id,))
    # overlay_id를 직접 매겨 GeoDataFrame과 DB가 같은 값을 쓰도록 보장한다.
    next_id = connection.execute(
        "SELECT COALESCE(MAX(overlay_id), 0) FROM overlays"
    ).fetchone()[0] + 1
    overlay_ids = list(range(next_id, next_id + len(data)))

    attr_columns = [name for name in OVERLAY_ATTR_COLUMNS if name in data.columns]
    rows = []
    for overlay_id, row in zip(overlay_ids, data.itertuples(index=False)):
        min_x, min_y, max_x, max_y = row.geometry.bounds
        attrs = {
            name: _text_or_date(getattr(row, name))
            for name in attr_columns
            if _text_or_date(getattr(row, name))
        }
        rows.append(
            (
                overlay_id,
                source_id,
                source["theme"],
                source["layer"],
                _overlay_kind(source, row),
                _bulk_text(getattr(row, "ATRB_SE", "")),
                _bulk_text(getattr(row, "DGM_NM", "")),
                _bulk_text(getattr(row, "PRESENT_SN", "")),
                _bulk_text(getattr(row, "NTFC_SN", "")),
                _text_or_date(getattr(row, "CREATE_DAT", "")),
                json.dumps(attrs, ensure_ascii=False) if attrs else None,
                round(float(row.geometry.area), 3),
                json.dumps(mapping(row.geometry), ensure_ascii=False),
                constants.DATABASE_CRS,
                float(min_x),
                float(max_x),
                float(min_y),
                float(max_y),
            )
        )

    connection.executemany(
        """
        INSERT INTO overlays
            (overlay_id, source_id, theme, layer, kind, code, name, feature_id,
             notice_number, created_date, attrs_json, area_sqm,
             geometry_json, geometry_crs, min_x, max_x, min_y, max_y)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return data.assign(overlay_id=overlay_ids)


def _link_parcel_overlays(connection, lot_data, overlay_data):
    """필지 묶음과 오버레이의 교차를 계산해 parcel_overlays에 넣는다."""
    if lot_data.empty or overlay_data.empty:
        return 0

    joined = _spatial_join(lot_data, overlay_data, ["overlay_id"])
    if joined.empty:
        return 0

    rows = [
        (
            row.pnu_value,
            int(row.overlay_id),
            round(float(row.overlap_area), 3),
            round(float(row.overlap_area) / float(row.lot_area), 6),
        )
        for row in joined.itertuples(index=False)
    ]
    connection.executemany(
        """
        INSERT OR REPLACE INTO parcel_overlays
            (pnu, overlay_id, overlap_area_sqm, overlap_ratio)
        VALUES (?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def load_overlay_sources(
    connection,
    refresh=False,
    source_ids=None,
    skip_existing=False,
):
    # type: (object, bool, list, bool) -> object
    """모든 계획 레이어를 내려받아 overlays에 적재한다.

    입력:
        connection: 대상 DB. refresh: 원천 재다운로드 여부.
        source_ids: 일부만 적재할 때의 원천 목록. None이면 전부.
        skip_existing: 이미 적재된 원천은 건너뛴다.
    처리:
        원천마다 SHP를 EPSG:5186으로 읽어 overlays에 넣고 data_sources를 갱신한다.
        도형이 없는 레이어(예: 특정용도제한지구)는 원천만 기록하고 건너뛴다.
    출력:
        overlay_id가 붙은 GeoDataFrame 목록. 필지 교차 계산에 그대로 쓴다.
    """
    frames = []
    for source_id in (source_ids or SEOUL_SOURCES):
        source = SEOUL_SOURCES[source_id]
        if skip_existing and connection.execute(
            "SELECT 1 FROM overlays WHERE source_id = ? LIMIT 1", (source_id,)
        ).fetchone():
            continue
        path, metadata = download_seoul_source(source_id, refresh)
        _upsert_source(connection, source_id, metadata, source.get("note", ""))
        data = _read_seoul_shapefile(path)
        data = data[data.geometry.notna() & ~data.geometry.is_empty]
        if data.empty:
            print("  %-26s %s 도형 0건 — 건너뜁니다" % (source_id, source["layer"]))
            continue
        frames.append(_insert_overlays(connection, source_id, source, data))
        print(
            "  %-26s %-6s %6d건 적재"
            % (source_id, source["layer"], len(data)),
            flush=True,
        )
    connection.commit()
    return frames


def _get_land_char_paths(sido_code):
    # type: (str) -> list
    """그 시도의 토지특성정보 SHP 경로(정렬). 받은 zip(AL_D194_<시군구>_<기준일>.zip)이 아직 안 풀렸으면 같은 이름 폴더에 푼다."""
    land_char_dir = ROOT_DIR / constants.LAND_CHAR_DIRNAME
    paths = []
    for code in (sido_code,) + constants.SIDO_LEGACY_CODES.get(sido_code, ()):   # 통합 시도는 옛 코드 파일도 함께
        prefix = "AL_D194_%s" % code
        for zip_path in sorted(land_char_dir.glob(prefix + "*.zip")):
            folder = zip_path.with_suffix("")
            if not folder.exists():
                with zipfile.ZipFile(zip_path) as archive:
                    archive.extractall(folder)
        paths += sorted(land_char_dir.glob(prefix + "*/*.shp"))
    return paths


def get_legacy_sgg_map(sido_code, shp_paths, land_use_dir=None):
    # type: (str, list, object) -> dict
    """옛 시군구 코드 5자리 → 새 코드 5자리. 통합 시도가 아니면 빈 dict.

    새 코드·이름은 토지이용계획 CSV(법정동코드·법정동명), 옛 코드·이름은 토지특성 SHP 첫 행(A3)에서 읽어 시군구 이름으로 맞춘다.
    """
    if sido_code not in constants.SIDO_LEGACY_CODES:
        return {}
    land_use_dir = Path(land_use_dir or (ROOT_DIR / constants.LAND_USE_DIRNAME))
    new_by_name = {}
    for path in _get_land_use_paths(land_use_dir, constants.LAND_USE_FILE_FORMAT % sido_code):
        with _open_land_use(path) as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            code_at, name_at = header.index("법정동코드"), header.index("법정동명")
            for record in reader:
                parts = record[name_at].split()
                if len(parts) > 1:
                    new_by_name.setdefault(parts[1], record[code_at][:5])
    mapping = {}
    for shp_path in shp_paths:
        old = shp_path.parent.name.split("_")[2]
        if old[:2] == sido_code or old in mapping:
            continue
        first = pyogrio.read_dataframe(shp_path, columns=["A3"], max_features=1, read_geometry=False, encoding=constants.LAND_CHAR_ENCODING)
        name = _bulk_text(first["A3"].iloc[0]).split()[1]
        if name not in new_by_name:
            raise ValueError("새 시군구 코드를 찾지 못했습니다: %s %s" % (old, name))
        mapping[old] = new_by_name[name]
    return mapping


def _get_derived_kind(code):
    # type: (str) -> tuple
    """토지이용계획 코드 → (theme, kind, layer). 대상이 아니면 None."""
    for prefix, theme, kind, layer in constants.DERIVED_OVERLAY_CODES:
        if code.startswith(prefix):
            return (theme, kind, layer) if theme else None
    return None


def derive_overlays(connection):
    # type: (object) -> int
    """parcel_land_use(포함·저촉) 필지를 코드 × 1 km 격자로 합쳐 overlays·parcel_overlays를 만든다. 넣은 도형 수를 돌려준다.

    서울은 UPIS 계획 도형을 쓰고, 다른 시도는 이것으로 대신한다 — 경계가 도로 중심이 아니라 필지 경계라는 차이가 있다.
    parcel_overlays는 필지 전체가 그 지정에 든 것으로 적는다(겹침 비율 1). ponytail: 저촉 필지의 실제 겹침 면적은 원천에 없다.
    """
    groups = {}
    rows = connection.execute(
        """SELECT link.code, link.name, lot.pnu, lot.geometry_json, (lot.min_x + lot.max_x) / 2, (lot.min_y + lot.max_y) / 2,
                  lot.geometry_area_sqm
           FROM parcel_land_use link JOIN parcels lot ON lot.pnu = link.pnu
           WHERE link.conflict IN ('포함', '저촉')""")
    for code, name, pnu, geometry_json, x, y, area in rows:
        target = _get_derived_kind(code)
        if target is None:
            continue
        key = (code, int(x // constants.DERIVED_OVERLAY_TILE), int(y // constants.DERIVED_OVERLAY_TILE))
        group = groups.setdefault(key, {"target": target, "name": name, "pnus": [], "geometries": [], "areas": []})
        group["pnus"].append(pnu)
        group["geometries"].append(geometry_json)
        group["areas"].append(area)
    next_id = connection.execute("SELECT COALESCE(MAX(overlay_id), 0) FROM overlays").fetchone()[0] + 1
    overlay_rows, link_rows = [], []
    for overlay_id, ((code, _tx, _ty), group) in enumerate(sorted(groups.items()), start=next_id):
        theme, kind, layer = group["target"]
        geometry = shapely.make_valid(shapely.union_all(shapely.make_valid(shapely.from_geojson(group["geometries"]))))
        min_x, min_y, max_x, max_y = geometry.bounds
        overlay_rows.append((overlay_id, LAND_USE_SOURCE["source_id"], theme, layer, kind, code, group["name"], None, None, None,
                             None, round(float(geometry.area), 3), json.dumps(mapping(geometry), ensure_ascii=False),
                             constants.DATABASE_CRS, float(min_x), float(max_x), float(min_y), float(max_y)))
        link_rows.extend((pnu, overlay_id, area, 1.0) for pnu, area in zip(group["pnus"], group["areas"]))
    connection.executemany(
        """INSERT INTO overlays (overlay_id, source_id, theme, layer, kind, code, name, feature_id, notice_number, created_date,
               attrs_json, area_sqm, geometry_json, geometry_crs, min_x, max_x, min_y, max_y)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", overlay_rows)
    connection.executemany(
        "INSERT OR IGNORE INTO parcel_overlays (pnu, overlay_id, overlap_area_sqm, overlap_ratio) VALUES (?, ?, ?, ?)", link_rows)
    connection.commit()
    return len(overlay_rows)


def _offset_ids(connection, offset):
    # type: (object, int) -> None
    """parcel_id·overlay_id를 offset만큼 띄운다(시도 DB 여러 개를 한 연결로 묶을 때 겹치지 않게). 외래키를 잠시 끈다."""
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("UPDATE parcels SET parcel_id = parcel_id + ?", (offset,))
    connection.execute("UPDATE overlays SET overlay_id = overlay_id + ?", (offset,))
    connection.execute("UPDATE parcel_overlays SET overlay_id = overlay_id + ?", (offset,))
    connection.commit()
    connection.execute("PRAGMA foreign_keys = ON")


def build(sido_code=SEOUL_CODE, refresh=False, chunk_size=50000):
    # type: (str, bool, int) -> object
    """한 시도의 필지 DB를 새로 만든다.

    입력:
        sido_code: PNU 앞 2자리(constants.SIDO). refresh: 서울 열린데이터광장 원천을 다시 내려받을지 여부.
        chunk_size: 필지를 몇 건씩 읽어 처리할지.
    처리:
        1) 계획 오버레이 — 서울은 UPIS 계획 레이어 19종(열린데이터광장). 다른 시도는 아직 없음(전국 원천 확정 전).
        2) data/raw/vworld_토지특성정보의 그 시도 시군구 SHP를 훑어 parcels에 넣고 오버레이와의 교차를 계산한다.
        3) 토지이용계획정보 CSV(그 시도)를 parcel_land_use에 넣는다.
        4) 서울 외 시도는 id를 시도 코드 × 10^9만큼 띄운다.
        토지특성정보는 VWorld 로그인이 필요해 자동 다운로드하지 않는다. 수동으로 받아 위 폴더에 둔다(zip 그대로도 된다).
    출력:
        완성한 DB 경로. 검증을 통과해야만 기존 DB를 교체한다.
    """
    shp_paths = _get_land_char_paths(sido_code)
    if not shp_paths:
        raise FileNotFoundError(
            "%s 토지특성정보 SHP가 없습니다: %s/AL_D194_%s*\n"
            "VWorld 국가중점데이터(dsId=4)에서 시군구별로 내려받아 두세요."
            % (constants.SIDO[sido_code][0], ROOT_DIR / constants.LAND_CHAR_DIRNAME, sido_code)
        )
    if chunk_size <= 0:
        raise ValueError("chunk_size는 1 이상이어야 합니다")

    legacy_sgg = get_legacy_sgg_map(sido_code, shp_paths)
    if legacy_sgg:
        print("옛 시군구 코드 → 새 코드: %s" % legacy_sgg, flush=True)
    database_path = get_database_path(sido_code)
    build_path = database_path.with_suffix(".building.db")
    if build_path.exists():
        build_path.unlink()
    connection = _connect_database(build_path, fast_build=True)
    try:
        # parcels.source_id가 data_sources를 참조하므로 필지보다 먼저 등록한다.
        first_data = pyogrio.read_dataframe(
            shp_paths[0],
            columns=["A26"],
            max_features=1,
            read_geometry=False,
            encoding=constants.LAND_CHAR_ENCODING,
        )
        reference_date = _text_or_date(
            first_data["A26"].iloc[0] if len(first_data) else ""
        )
        _upsert_source(
            connection,
            LAND_CHAR_SOURCE["source_id"],
            {
                "name": LAND_CHAR_SOURCE["name"],
                "page_url": LAND_CHAR_SOURCE["page_url"],
                "reference_date": reference_date,
                "acquired_at": _now(),
                "crs": LAND_CHAR_SOURCE["crs"],
                "license": LAND_CHAR_SOURCE["license"],
                "note": LAND_CHAR_SOURCE["note"],
            },
        )

        overlay_frames = []
        if sido_code == SEOUL_CODE:
            print("계획 오버레이 적재", flush=True)
            overlay_frames = load_overlay_sources(connection, refresh)

        lot_count = overlap_count = 0
        for index, shp_path in enumerate(shp_paths, start=1):
            info = pyogrio.read_info(
                shp_path, encoding=constants.LAND_CHAR_ENCODING
            )
            feature_count = int(info["features"])
            for start_index in range(0, feature_count, chunk_size):
                data = pyogrio.read_dataframe(
                    shp_path,
                    columns=list(LAND_CHAR_COLUMNS),
                    skip_features=start_index,
                    max_features=chunk_size,
                    encoding=constants.LAND_CHAR_ENCODING,
                )
                lot_data = _prepare_land_char_chunk(data, sido_code, legacy_sgg)
                lot_count += _insert_land_char_lots(connection, lot_data)
                for overlay_data in overlay_frames:
                    overlap_count += _link_parcel_overlays(
                        connection, lot_data, overlay_data
                    )
            connection.commit()
            print(
                "토지특성정보 %2d/%d %s — 필지 %d / 오버레이 교차 %d"
                % (index, len(shp_paths), shp_path.stem, lot_count, overlap_count),
                flush=True,
            )

        print("토지이용계획 %d행" % load_land_use(connection, sido_code=sido_code), flush=True)
        if sido_code != SEOUL_CODE:
            print("계획 도형(토지이용계획 코드로 필지 합침) %d개" % derive_overlays(connection), flush=True)
        if sido_code != SEOUL_CODE:
            _offset_ids(connection, int(sido_code) * ID_OFFSET_PER_SIDO)
        connection.execute("ANALYZE")
        connection.commit()
        _validate_overlay_links(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError("생성 DB 무결성 검사 실패: %s" % integrity)
    finally:
        connection.close()

    os.replace(build_path, database_path)
    if sido_code != SEOUL_CODE:   # 받은 zip은 남기고 푼 폴더만 지운다 — 전국을 풀어 두면 디스크가 모자란다
        for shp_path in shp_paths:
            if shp_path.parent.with_suffix(".zip").exists():
                shutil.rmtree(shp_path.parent, ignore_errors=True)
    return database_path


def main():
    parser = argparse.ArgumentParser(
        description="시도별 필지 로컬 DB 구축 (토지특성정보 + 토지이용계획 + 서울은 UPIS 계획 레이어)"
    )
    parser.add_argument(
        "--sido",
        default=SEOUL_CODE,
        help="PNU 앞 2자리 시도 코드(기본 11 서울). all = 토지특성정보가 있는 시도 전부",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="서울 열린데이터광장 계획 레이어를 다시 내려받음",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=50000, help="필지 청크 크기(기본 50000)"
    )
    args = parser.parse_args()
    codes = sorted(constants.SIDO) if args.sido == "all" else [args.sido]
    for code in codes:
        if code not in constants.SIDO:
            parser.exit(1, "모르는 시도 코드: %s\n" % code)
        if args.sido == "all" and not _get_land_char_paths(code):
            continue
        print("== %s" % constants.SIDO[code][0], flush=True)
        try:
            path = build(code, refresh=args.refresh, chunk_size=args.chunk_size)
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            parser.exit(1, "DB 생성 중단: %s\n" % error)
        print("DB 생성 완료: %s" % path)


if __name__ == "__main__":
    main()
