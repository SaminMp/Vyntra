"""
Integration test for real media download flow with progress callback verification.
"""

from pathlib import Path
import tempfile
import threading
import time
import unittest

from vyntra.models import DownloadStatus, DownloadTask, MediaFormat, ProgressInfo, SearchResult
from vyntra.services.download_service import download_service


class TestDownloadIntegration(unittest.TestCase):
    """Integration test verifying end-to-end media download and callbacks."""

    def test_live_download_short_clip(self):
        """Downloads a short test audio clip to verify hooks and output file creation."""
        result = SearchResult(
            video_id="dQw4w9WgXcQ",
            title="Rick Astley - Never Gonna Give You Up",
            channel="Rick Astley",
            duration_seconds=212,
            duration_formatted="03:32",
            thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            task = DownloadTask(
                result=result,
                format=MediaFormat.MP3,
                save_directory=temp_dir,
            )

            progress_events = []
            completion_event = threading.Event()
            completed_file = []
            error_holder = []

            def _on_progress(prog: ProgressInfo):
                progress_events.append(prog)

            def _on_complete(out_path: str):
                completed_file.append(out_path)
                completion_event.set()

            def _on_error(err: Exception):
                error_holder.append(err)
                completion_event.set()

            download_service.start_download(
                task=task,
                on_progress=_on_progress,
                on_complete=_on_complete,
                on_error=_on_error,
            )

            # Wait up to 25 seconds for the short 19-sec video download
            finished = completion_event.wait(timeout=25)
            self.assertTrue(finished, "Download timed out")
            self.assertEqual(len(error_holder), 0, f"Download failed with error: {error_holder}")
            self.assertEqual(len(completed_file), 1)
            self.assertTrue(Path(completed_file[0]).exists())
            self.assertGreater(Path(completed_file[0]).stat().st_size, 1000)
            self.assertGreater(len(progress_events), 0)


if __name__ == "__main__":
    unittest.main()
