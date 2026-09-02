"""
Unit tests for Step 3: Download engine, task management, and cancellation.
"""

from pathlib import Path
import tempfile
import unittest

from vyntra.models import DownloadStatus, DownloadTask, MediaFormat, SearchResult
from vyntra.services.download_service import download_service


class TestStep3(unittest.TestCase):
    """Test suite for Step 3 download engine."""

    def test_task_creation_and_cancellation(self):
        """Verify download cancellation flag and state transitions."""
        result = SearchResult(
            video_id="test_id",
            title="Sample Track",
            channel="Sample Artist",
            duration_seconds=120,
            duration_formatted="02:00",
            thumbnail_url="",
            url="https://www.youtube.com/watch?v=test_id",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            task = DownloadTask(
                result=result,
                format=MediaFormat.MP3,
                save_directory=temp_dir,
            )

            self.assertEqual(task.status, DownloadStatus.PENDING)
            self.assertFalse(task.is_cancelled)

            # Register task in service and cancel
            with download_service._lock:
                download_service._active_tasks[task.task_id] = task

            self.assertTrue(download_service.is_downloading(task.task_id))
            
            cancelled = download_service.cancel_download(task.task_id)
            self.assertTrue(cancelled)
            self.assertTrue(task.is_cancelled)
            self.assertEqual(task.status, DownloadStatus.CANCELLED)


if __name__ == "__main__":
    unittest.main()
