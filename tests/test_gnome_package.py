# SPDX-License-Identifier: AGPL-3.0-only
"""Real package/installer checks in temporary user directories; no shell/BLE."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
UUID = 'veazy@xenophon81.github.io'
SCRIPT = ROOT / 'scripts/gnome-extension'


class GnomePackageTests(unittest.TestCase):
    def test_build_install_update_and_idle_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            archive = temp / 'veazy.zip'
            subprocess.run([sys.executable, SCRIPT, 'build', '--output', archive], check=True, capture_output=True)
            with zipfile.ZipFile(archive) as package:
                files = set(package.namelist())
                self.assertEqual(json.loads(package.read('metadata.json'))['shell-version'], ['46'])
                for name in ('extension.js', 'backend.js', 'scripts/run-backend', 'scripts/setup-backend', 'requirements.txt', 'LICENSE', 'NOTICE'):
                    self.assertIn(name, files)
                self.assertFalse(any('__pycache__' in f or f.endswith('.qml') or 'venv/' in f for f in files))
            env = os.environ | {'XDG_DATA_HOME': str(temp / 'data'), 'OMARCHY_VEAZY_WORKER_SESSION': 'package-test'}
            subprocess.run([sys.executable, SCRIPT, 'update', archive], env=env, check=True, capture_output=True)
            target = temp / 'data/gnome-shell/extensions' / UUID
            (target / 'old-installation').write_text('preserve me')
            subprocess.run([sys.executable, SCRIPT, 'install', archive], env=env, check=True, capture_output=True)
            backups = list((temp / 'data/gnome-shell/veazy-extension-backups').iterdir())
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / 'old-installation').read_text(), 'preserve me')
            self.assertFalse((target / 'old-installation').exists())
            # Packaged paths must resolve correctly; EOF exits without importing BLE.
            worker = subprocess.run(['bash', target / 'scripts/run-backend'], input='', env=env, text=True,
                                    capture_output=True, timeout=5, check=True)
            messages = [json.loads(line) for line in worker.stdout.splitlines()]
            self.assertEqual(messages[0]['data']['state'], 'disconnected')
            self.assertIsNone(messages[1]['data']['heater_mode'])
            self.assertTrue(all(message['session'] == 'package-test' for message in messages))
            self.assertEqual(worker.stderr, '')

    def test_traversal_archive_does_not_replace_installed_extension(self):
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            target = temp / 'data/gnome-shell/extensions' / UUID
            target.mkdir(parents=True)
            (target / 'keep').write_text('original')
            archive = temp / 'malicious.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('../outside', 'bad')
            result = subprocess.run([sys.executable, SCRIPT, 'install', archive],
                                    env=os.environ | {'XDG_DATA_HOME': str(temp / 'data')}, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((target / 'keep').read_text(), 'original')
            self.assertFalse((target.parent / 'outside').exists())
