"""
Unit tests for semantic version parsing and comparison in Vyntra updater.
"""

import unittest
from vyntra.updater.version_utils import SemVer, is_newer, normalize_tag, parse_version


class TestUpdaterVersion(unittest.TestCase):
    """Verifies SemVer parsing, tag normalization, and numerical precedence."""

    def test_parse_standard_versions(self):
        v1 = parse_version("1.2.3")
        self.assertIsNotNone(v1)
        self.assertEqual((v1.major, v1.minor, v1.patch), (1, 2, 3))
        self.assertIsNone(v1.prerelease)

        v2 = parse_version("v2.0.0")
        self.assertIsNotNone(v2)
        self.assertEqual((v2.major, v2.minor, v2.patch), (2, 0, 0))

    def test_parse_prerelease(self):
        v = parse_version("1.3.0-beta.1")
        self.assertIsNotNone(v)
        self.assertEqual((v.major, v.minor, v.patch), (1, 3, 0))
        self.assertEqual(v.prerelease, "beta.1")

    def test_parse_invalid(self):
        self.assertIsNone(parse_version(""))
        self.assertIsNone(parse_version("invalid"))
        self.assertIsNone(parse_version("1.2.3.4.5"))
        self.assertIsNone(parse_version(None))

    def test_normalize_tag(self):
        self.assertEqual(normalize_tag("v1.2.4"), "1.2.4")
        self.assertEqual(normalize_tag("V1.0.0"), "1.0.0")
        self.assertEqual(normalize_tag("1.2.4"), "1.2.4")
        self.assertEqual(normalize_tag(""), "")

    def test_numerical_comparisons(self):
        # 1.0.9 vs 1.0.10 (Numerical: 10 > 9, String: '10' < '9')
        self.assertTrue(is_newer("1.0.10", "1.0.9"))
        self.assertFalse(is_newer("1.0.9", "1.0.10"))

        # 1.0.0 vs 1.0.1
        self.assertTrue(is_newer("1.0.1", "1.0.0"))
        self.assertFalse(is_newer("1.0.0", "1.0.1"))

        # 1.2.0 vs 1.1.9
        self.assertTrue(is_newer("1.2.0", "1.1.9"))
        self.assertFalse(is_newer("1.1.9", "1.2.0"))

        # Leading 'v' handling
        self.assertTrue(is_newer("v1.2.4", "1.2.3"))
        self.assertTrue(is_newer("1.2.4", "v1.2.3"))

        # Equal versions
        self.assertFalse(is_newer("1.2.3", "1.2.3"))
        self.assertFalse(is_newer("v1.2.3", "1.2.3"))

        # Prerelease vs release
        # Stable 1.2.0 is newer than 1.2.0-beta
        self.assertTrue(is_newer("1.2.0", "1.2.0-beta"))
        self.assertFalse(is_newer("1.2.0-beta", "1.2.0"))


if __name__ == "__main__":
    unittest.main()
