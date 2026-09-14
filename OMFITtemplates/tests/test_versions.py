"""Mixed calendar/SemVer ordering and timezone-normalized publication dates."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
from OMFITlib_template_versions import semantic_version, sort_releases


class VersionTest(unittest.TestCase):
    def test_screenshot_order_uses_publication_time(self):
        rows = [dict(version=v, created='2026-09-14T' + t + ':00Z') for v, t in
                [('2026.09.14.4', '05:16'), ('2026.09.14.3', '04:45'), ('1.1.1', '09:19'),
                 ('1.1.0', '08:55'), ('1.0.1', '08:04'), ('1.0.0', '06:21')]]
        self.assertEqual([r['version'] for r in sort_releases(rows)],
                         ['1.1.1', '1.1.0', '1.0.1', '1.0.0', '2026.09.14.4', '2026.09.14.3'])

    def test_numeric_versions_prereleases_and_calendar_migration(self):
        values = ['1.9.0', '2026.09.14.4', '1.10.0-rc.2', '1.10.0', '1.10.0-rc.10', '2026.09.13.1']
        rows = [dict(version=value) for value in values]
        expected = ['1.10.0', '1.10.0-rc.10', '1.10.0-rc.2', '1.9.0', '2026.09.14.4', '2026.09.13.1']
        self.assertEqual([r['version'] for r in sort_releases(rows, 'version')], expected)
        self.assertEqual([r['version'] for r in sort_releases(rows, 'version_asc')], expected[::-1])

    def test_timezones_and_missing_dates(self):
        rows = [dict(version='1.0.0', created='2026-09-14T12:00:00+08:00'),
                dict(version='1.0.1', created='2026-09-14T05:00:00Z'),
                dict(version='9.0.0', created='invalid')]
        self.assertEqual([r['version'] for r in sort_releases(rows)], ['1.0.1', '1.0.0', '9.0.0'])

    def test_build_metadata_does_not_change_precedence(self):
        self.assertEqual(semantic_version('1.4.0+build.2'), semantic_version('1.4.0+build.3'))
        self.assertIsNone(semantic_version('1.4.0-rc.01'))
        self.assertIsNone(semantic_version('1.04.0'))
        self.assertIsNone(semantic_version('1.4'))


if __name__ == '__main__':
    unittest.main()
