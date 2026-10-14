"""server_gate — 하루 한도·없는 팩·설치 ID 판정."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import server_gate  # noqa: E402

CLIENT = "0f8fad5b-d9cb-469f-a165-70867728950e"
OTHER = "7c9e6679-7425-40de-944b-e07fc1f90ae7"


class GateTest(unittest.TestCase):
    def setUp(self):
        self.gate = server_gate.Gate({"11680_context.db.xz", "11680_terrain.db.xz"})

    def check(self, ip="1.1.1.1", client=CLIENT, uri="/11680_context.db.xz", day="2026-10-14"):
        return self.gate.check(ip, client, uri, day)

    def test_same_pack_limit_resets_next_day(self):
        for _ in range(server_gate.CLIENT_SAME_MAX):
            self.assertEqual(self.check(), "")
        self.assertEqual(self.check(), "limit")
        self.assertEqual(self.check(uri="/11680_terrain.db.xz"), "", "다른 팩은 된다")
        self.assertEqual(self.check(day="2026-10-15"), "")

    def test_ip_limit_catches_client_rotation(self):
        for index in range(server_gate.IP_DAY_MAX):
            client = "%08x-0000-4000-8000-000000000000" % index
            self.assertEqual(self.check(client=client), "")
        self.assertEqual(self.check(client=OTHER), "limit")
        self.assertEqual(self.check(ip="2.2.2.2", client=OTHER), "", "다른 IP는 된다")

    def test_unknown_names_then_ip_blocked(self):
        for _ in range(server_gate.IP_UNKNOWN_MAX + 1):
            self.assertEqual(self.check(uri="/99999_context.db.xz"), "unknown")
        self.assertEqual(self.check(), "limit")

    def test_missing_client_follows_switch(self):
        self.assertEqual(self.check(client=""), "no_client")
        self.assertEqual(self.check(client="not-a-uuid"), "no_client")
        server_gate.REQUIRE_CLIENT = False
        try:
            self.assertEqual(self.check(client="not-a-uuid"), "")
        finally:
            server_gate.REQUIRE_CLIENT = True

    def test_pack_names_from_manifest(self):
        manifest = {"packs": [{"name": "11680_site.db", "url": "11680_site.db.xz"},
                              {"name": "11680_context.db", "url": "http://10.0.0.1/11680_context.db.xz"}]}
        self.assertEqual(server_gate.get_pack_names(manifest), {"11680_context.db.xz"})


if __name__ == "__main__":
    unittest.main()
