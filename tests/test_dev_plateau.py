"""dev_plateau — 네트워크 없이: CityGML 조각 → 건물 행(위도·경도 뒤집기, 외곽 고르기, PLATEAU '모름' 값, BuildingPart), 면적."""

import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import constants  # noqa: E402
import dev_plateau  # noqa: E402

# 위도·경도·표고 순(EPSG:6697). A = lod0RoofEdge·실측 높이, B = lod1Solid만·층수 9999·높이 -9999, C = BuildingPart 둘
GML_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0" xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
  xmlns:gml="http://www.opengis.net/gml" xmlns:app="http://www.opengis.net/citygml/appearance/2.0">
 <core:cityObjectMember>
  <bldg:Building gml:id="bldg_a">
   <gml:name>A</gml:name>
   <bldg:usage>411</bldg:usage>
   <bldg:measuredHeight uom="m">12.3</bldg:measuredHeight>
   <bldg:storeysAboveGround>4</bldg:storeysAboveGround>
   <bldg:storeysBelowGround>1</bldg:storeysBelowGround>
   <bldg:lod0RoofEdge><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
    <gml:posList>35.680000001 139.700000001 0 35.680000001 139.70011 0 35.68009 139.70011 0 35.68009 139.700000001 0 35.680000001 139.700000001 0</gml:posList>
   </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod0RoofEdge>
  </bldg:Building>
 </core:cityObjectMember>
 <core:cityObjectMember>
  <bldg:Building gml:id="bldg_b">
   <bldg:usage>461</bldg:usage>
   <bldg:measuredHeight uom="m">-9999</bldg:measuredHeight>
   <bldg:storeysAboveGround>9999</bldg:storeysAboveGround>
   <bldg:storeysBelowGround>9999</bldg:storeysBelowGround>
   <bldg:lod1Solid><gml:Solid><gml:exterior><gml:CompositeSurface>
    <gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
     <gml:posList>35.6801 139.7001 10 35.6802 139.7001 10 35.6802 139.7002 10 35.6801 139.7002 10 35.6801 139.7001 10</gml:posList>
    </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember>
    <gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
     <gml:posList>35.6801 139.7001 16 35.6801 139.7002 16 35.6802 139.7002 16 35.6802 139.7001 16 35.6801 139.7001 16</gml:posList>
    </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember>
    <gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
     <gml:posList>35.6801 139.7001 10 35.6801 139.7002 10 35.6801 139.7002 16 35.6801 139.7001 16 35.6801 139.7001 10</gml:posList>
    </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember>
   </gml:CompositeSurface></gml:exterior></gml:Solid></bldg:lod1Solid>
  </bldg:Building>
 </core:cityObjectMember>
 <core:cityObjectMember>
  <bldg:Building gml:id="bldg_c">
   <bldg:usage>412</bldg:usage>
   <bldg:consistsOfBuildingPart><bldg:BuildingPart gml:id="part_1">
    <bldg:measuredHeight uom="m">30</bldg:measuredHeight>
    <bldg:lod0FootPrint><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
     <gml:posList>35.69 139.71 0 35.69 139.7101 0 35.6901 139.7101 0 35.69 139.71 0</gml:posList>
    </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod0FootPrint>
   </bldg:BuildingPart></bldg:consistsOfBuildingPart>
   <bldg:consistsOfBuildingPart><bldg:BuildingPart gml:id="part_2">
    <bldg:storeysAboveGround>2</bldg:storeysAboveGround>
    <bldg:lod0FootPrint><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
     <gml:posList>35.6902 139.71 0 35.6902 139.7101 0 35.6903 139.7101 0 35.6902 139.71 0</gml:posList>
    </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></bldg:lod0FootPrint>
   </bldg:BuildingPart></bldg:consistsOfBuildingPart>
  </bldg:Building>
 </core:cityObjectMember>
 <app:appearanceMember><app:Appearance/></app:appearanceMember>
</core:CityModel>
"""


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.buildings = {b["id"]: b for b in dev_plateau.iter_buildings(io.BytesIO(GML_SAMPLE))}

    def test_ids_and_parts(self):
        self.assertEqual(sorted(self.buildings), ["bldg_a", "bldg_b", "part_1", "part_2"])
        self.assertEqual(self.buildings["part_1"]["usage"], "412")   # 부분에 없는 속성은 건물 것을 물려받는다

    def test_roof_edge_row(self):
        row = dev_plateau.get_row(self.buildings["bldg_a"], 7)
        geometry = json.loads(row[19])
        self.assertEqual(geometry["type"], "Polygon")
        self.assertEqual(geometry["coordinates"][0][0], [139.7, 35.68])   # 경도·위도로 뒤집고 소수 6자리
        self.assertEqual(geometry["coordinates"][0][0], geometry["coordinates"][0][-1])
        self.assertEqual(row[8:11], (12.3, "plateau_height", "B"))
        self.assertEqual((row[5], row[6], row[14], row[15]), (4, 1, "A", "411"))
        self.assertAlmostEqual(row[17], 10.0 * 10.0, delta=2.0)   # 0.00011° × 0.00009° ≈ 10 m × 10 m
        self.assertEqual((row[20], row[21], row[22]), (4326, "plateau", None))

    def test_unknown_values_and_solid_bottom(self):
        row = dev_plateau.get_row(self.buildings["bldg_b"], 8)
        self.assertEqual(row[8:11], (constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"))   # 9999층·-9999 m를 값으로 쓰지 않는다
        self.assertEqual((row[5], row[6]), (0, 0))
        ring = json.loads(row[19])["coordinates"][0]
        self.assertEqual(len(ring), 5)
        self.assertEqual(ring[0], [139.7001, 35.6801])   # 바닥면(표고 10) — 지붕·벽이 아니다

    def test_levels_height(self):
        row = dev_plateau.get_row(self.buildings["part_2"], 9)
        base, per = constants.FLOOR_HEIGHT_DEFAULT
        self.assertEqual(row[8:11], (round(base + per * 2, 2), "plateau_levels", "C"))

    def test_outside_japan(self):
        building = dict(self.buildings["bldg_a"], polygons=[[[[35.68, 139.7], [35.681, 139.7], [35.681, 139.701], [35.68, 139.7]]]])
        self.assertIsNone(dev_plateau.get_row(building, 1))   # 축 순서가 뒤집힌 원천 좌표

    def test_clean_ring(self):
        self.assertIsNone(dev_plateau.get_clean_ring([(139.7, 35.6, 0), (139.7000001, 35.6, 0), (139.7, 35.6, 0)]))
        self.assertEqual(dev_plateau.get_clean_ring([(1, 2), (3, 4), (5, 6)]), [[1, 2], [3, 4], [5, 6], [1, 2]])


if __name__ == "__main__":
    unittest.main()
