"""
Unit tests for the Watch Later / Favorites persistence service and view.
"""

from pathlib import Path
import tempfile
import unittest

from vyntra.models import MediaFormat, SearchResult
from vyntra.services.watch_later_service import WatchLaterService


class TestWatchLaterService(unittest.TestCase):
    """Test suite verifying SQLite persistence, deduplication, and operations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_library.db"
        self.service = WatchLaterService(db_path=self.db_path)

        self.sample_result_1 = SearchResult(
            video_id="vid_001",
            title="Bohemian Rhapsody",
            channel="Queen Official",
            duration_seconds=359,
            duration_formatted="05:59",
            views=1200000000,
            views_formatted="1.2B views",
            thumbnail_url="https://example.com/thumb1.jpg",
            url="https://www.youtube.com/watch?v=vid_001",
        )

        self.sample_result_2 = SearchResult(
            video_id="vid_002",
            title="Hotel California",
            channel="Eagles",
            duration_seconds=390,
            duration_formatted="06:30",
            views=500000000,
            views_formatted="500M views",
            thumbnail_url="https://example.com/thumb2.jpg",
            url="https://www.youtube.com/watch?v=vid_002",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_state_empty(self):
        self.assertEqual(self.service.count(), 0)
        self.assertEqual(len(self.service.get_all()), 0)
        self.assertFalse(self.service.is_saved("vid_001"))

    def test_add_and_retrieve_item(self):
        added = self.service.add(self.sample_result_1)
        self.assertTrue(added)
        self.assertEqual(self.service.count(), 1)
        self.assertTrue(self.service.is_saved("vid_001"))

        items = self.service.get_all()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.result.video_id, "vid_001")
        self.assertEqual(item.result.title, "Bohemian Rhapsody")
        self.assertEqual(item.result.channel, "Queen Official")
        self.assertEqual(item.result.duration_seconds, 359)
        self.assertTrue(len(item.added_at) > 0)

    def test_duplicate_prevention(self):
        """Verify that adding the same video multiple times returns False and avoids duplicates."""
        self.assertTrue(self.service.add(self.sample_result_1))
        # Second add attempt should fail
        self.assertFalse(self.service.add(self.sample_result_1))
        self.assertEqual(self.service.count(), 1)

    def test_remove_item(self):
        self.service.add(self.sample_result_1)
        self.service.add(self.sample_result_2)
        self.assertEqual(self.service.count(), 2)

        removed = self.service.remove("vid_001")
        self.assertTrue(removed)
        self.assertEqual(self.service.count(), 1)
        self.assertFalse(self.service.is_saved("vid_001"))
        self.assertTrue(self.service.is_saved("vid_002"))

        # Removing nonexistent item
        self.assertFalse(self.service.remove("nonexistent_id"))

    def test_persistence_across_service_reloads(self):
        """Verify data remains stored and recoverable when service re-opens the same database."""
        self.service.add(self.sample_result_1)
        self.service.add(self.sample_result_2)

        # Create new service instance pointing to the same SQLite file
        reloaded_service = WatchLaterService(db_path=self.db_path)
        self.assertEqual(reloaded_service.count(), 2)
        self.assertTrue(reloaded_service.is_saved("vid_001"))
        self.assertTrue(reloaded_service.is_saved("vid_002"))

        items = reloaded_service.get_all()
        video_ids = [item.result.video_id for item in items]
        self.assertIn("vid_001", video_ids)
        self.assertIn("vid_002", video_ids)


if __name__ == "__main__":
    unittest.main()
