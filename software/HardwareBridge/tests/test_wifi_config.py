"""Private build configuration is portable and never needs tracked credentials."""
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/wifi_config.py'


class WifiConfigTests(unittest.TestCase):
    def generate(self, root, variables=None):
        class Environment:
            def subst(self, _):
                return str(root)
        with patch.dict(os.environ, variables or {}, clear=True):
            runpy.run_path(str(SCRIPT), init_globals={'env': Environment(), 'Import': lambda _: None})
        return (root / 'include/wifi_config.h').read_text()

    def test_local_settings_and_environment_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'wifi.local.json').write_text(json.dumps({'ssid': 'Test network', 'password': 'test-only'}))
            header = self.generate(root)
            self.assertIn('#define WIFI_SSID "Test network"', header)
            self.assertIn('#define WIFI_PASSWORD "test-only"', header)
            header = self.generate(root, {'CYOBOT_WIFI_SSID': 'Override', 'CYOBOT_WIFI_PASSWORD': ''})
            self.assertIn('#define WIFI_SSID "Override"', header)
            self.assertIn('#define WIFI_PASSWORD ""', header)

    def test_missing_or_incomplete_settings_do_not_generate_a_header(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, 'configure_wifi'):
                self.generate(root)
            with self.assertRaises(ValueError):
                self.generate(root, {'CYOBOT_WIFI_SSID': 'Incomplete'})
            self.assertFalse((root / 'include/wifi_config.h').exists())


if __name__ == '__main__':
    unittest.main()
