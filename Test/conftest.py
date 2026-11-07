"""Make lib/oven.py importable off the Pi: put the repo root (config.py) and
lib/ on the path and stub the Blinka hardware modules it imports."""
import os
import sys
import types
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
for p in (ROOT, os.path.join(ROOT, 'lib')):
    if p not in sys.path:
        sys.path.insert(0, p)

for name in ('digitalio', 'busio', 'board', 'adafruit_bitbangio',
             'adafruit_max31855', 'adafruit_max31856'):
    if name not in sys.modules:
        sys.modules[name] = mock.MagicMock(name=name)
