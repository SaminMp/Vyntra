"""
Asynchronous thumbnail loading, processing, and caching service.
"""

from concurrent.futures import ThreadPoolExecutor
import io
import threading
from typing import Callable, Dict, Optional, Tuple
from PIL import Image, ImageDraw

import customtkinter as ctk
import requests

from vyntra.utils.logger import logger


class ImageService:
    """Manages thread-safe thumbnail fetching and CTkImage generation."""

    def __init__(self, max_workers: int = 4, cache_limit: int = 100):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ThumbnailWorker")
        self._cache: Dict[str, Image.Image] = {}
        self._lock = threading.Lock()
        self._cache_limit = cache_limit
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
        })

    def create_placeholder(self, width: int = 160, height: int = 90) -> Image.Image:
        """Generates a stylish dark gradient placeholder thumbnail."""
        img = Image.new("RGBA", (width, height), color=(26, 32, 44, 255))
        draw = ImageDraw.Draw(img)
        # Draw subtle border
        draw.rounded_rectangle([(0, 0), (width - 1, height - 1)], radius=8, outline=(45, 55, 72, 255), width=1)
        # Draw center play icon symbol
        cx, cy = width // 2, height // 2
        r = 14
        points = [(cx - r // 2, cy - r), (cx - r // 2, cy + r), (cx + r, cy)]
        draw.polygon(points, fill=(90, 105, 120, 255))
        return img

    def get_thumbnail_async(
        self,
        url: str,
        size: Tuple[int, int],
        on_success: Callable[[ctk.CTkImage], None],
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> ctk.CTkImage:
        """
        Returns an immediate placeholder CTkImage, and submits a background task
        to fetch the real thumbnail and trigger on_success.
        """
        width, height = size
        placeholder_pil = self.create_placeholder(width, height)
        placeholder_ctk = ctk.CTkImage(light_image=placeholder_pil, dark_image=placeholder_pil, size=(width, height))

        if not url:
            return placeholder_ctk

        with self._lock:
            if url in self._cache:
                cached_pil = self._cache[url]
                cached_ctk = ctk.CTkImage(light_image=cached_pil, dark_image=cached_pil, size=(width, height))
                on_success(cached_ctk)
                return cached_ctk

        def _fetch_worker():
            try:
                resp = self._session.get(url, timeout=6)
                if resp.status_code == 200:
                    pil_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                    # Crop/resize to maintain aspect ratio
                    pil_img = self._fit_and_resize(pil_img, size)
                    
                    with self._lock:
                        if len(self._cache) >= self._cache_limit:
                            # Evict oldest entry
                            self._cache.pop(next(iter(self._cache)))
                        self._cache[url] = pil_img

                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(width, height))
                    on_success(ctk_img)
                else:
                    logger.debug("Failed fetching thumbnail: HTTP %d", resp.status_code)
            except Exception as err:
                logger.debug("Thumbnail fetch error (%s): %s", url, err)
                if on_error:
                    on_error(err)

        self._executor.submit(_fetch_worker)
        return placeholder_ctk

    def _fit_and_resize(self, image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """Resizes image to fill target size using center-crop and LANCZOS filtering."""
        target_w, target_h = target_size
        img_w, img_h = image.size

        # Compute scaling to cover target bounds
        scale = max(target_w / img_w, target_h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)

        resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Center crop
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        right = left + target_w
        bottom = top + target_h

        cropped = resized.crop((left, top, right, bottom))
        return cropped


# Global singleton instance
image_service = ImageService()
