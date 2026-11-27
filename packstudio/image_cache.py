"""Bounded, content-keyed QImage cache. Returned images detach on mutation."""
from collections import OrderedDict
from threading import RLock
from PySide6.QtGui import QImage


class ImageCache:
    def __init__(self, budget=128 * 1024 * 1024):
        self.budget = budget
        self.entries = OrderedDict()
        self.bytes = 0
        self.hits = self.misses = 0
        self.lock = RLock()

    def get(self, data):
        with self.lock:
            entry = self.entries.get(data)
            if entry is None:
                self.misses += 1
                return None
            self.hits += 1
            self.entries.move_to_end(data)
            return QImage(entry[0])

    def put(self, data, image):
        size = len(data) + image.sizeInBytes()
        with self.lock:
            previous = self.entries.pop(data, None)
            if previous:
                self.bytes -= previous[1]
            if size > self.budget:
                return
            while self.entries and self.bytes + size > self.budget:
                _, (_, cost) = self.entries.popitem(last=False)
                self.bytes -= cost
            self.entries[data] = (QImage(image), size)
            self.bytes += size

    def clear(self):
        with self.lock:
            self.entries.clear()
            self.bytes = self.hits = self.misses = 0


images = ImageCache()
