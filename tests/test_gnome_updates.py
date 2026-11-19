# SPDX-License-Identifier: AGPL-3.0-only
"""Updater release selection and download integrity, with no network or installation."""
import hashlib
import io
import json
from pathlib import Path
import runpy
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

UPDATER = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/gnome-extension'))


class GnomeUpdateTests(unittest.TestCase):
    def release(self, version='v0.4.0'):
        name = UPDATER['ASSET_NAME']
        return {'tag_name': version, 'prerelease': True, 'assets': [{
            'name': name, 'size': 3, 'digest': 'sha256:' + hashlib.sha256(b'zip').hexdigest(),
            'browser_download_url': f'https://github.com/Xenophon81/omarchy-veazy/releases/download/{version}/{name.replace(chr(64), chr(37) + '40')}'}]}

    def test_previews_select_newest_and_never_downgrade(self):
        select = UPDATER['select_release']
        releases = [self.release('v0.3.0'), self.release('v0.5.0'), self.release()]
        self.assertEqual(select(releases, '0.3.0')[1], 'v0.5.0')
        self.assertIsNone(select(releases, '0.5.0'))
        releases[1]['draft'] = True
        self.assertEqual(select(releases, '0.3.0')[1], 'v0.4.0')

    def test_untrusted_or_unverified_assets_are_rejected(self):
        for field, value in [('digest', ''), ('size', 20_000_000),
                             ('browser_download_url', 'https://example.com/evil.zip')]:
            release = self.release()
            release['assets'][0][field] = value
            self.assertIsNone(UPDATER['select_release']([release], '0.3.0'))

    def test_check_only_never_downloads_and_bad_checksum_never_installs(self):
        fn = UPDATER['online_update']
        namespace = fn.__globals__
        release_data = json.dumps([self.release()]).encode()
        with patch.dict(namespace, fetch=lambda *args: release_data), patch('sys.stdout', new_callable=io.StringIO) as out:
            fn('0.3.0')
            self.assertEqual(json.loads(out.getvalue())['status'], 'available')
        calls = []
        def fetch(url, limit):
            calls.append(url)
            return release_data if len(calls) == 1 else b'bad'
        with patch.dict(namespace, fetch=fetch):
            with self.assertRaisesRegex(ValueError, 'checksum'):
                fn('0.3.0', True)

    def test_verified_download_installs_real_package_with_backup(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'release.zip'
            subprocess.run([sys.executable, root / 'scripts/gnome-extension', 'build', '--output', archive],
                           check=True, capture_output=True)
            payload = archive.read_bytes()
            release = self.release('v0.3.0')
            release['assets'][0].update(size=len(payload), digest='sha256:' + hashlib.sha256(payload).hexdigest())
            target = Path(folder) / 'data/gnome-shell/extensions' / UPDATER['UUID']
            target.mkdir(parents=True)
            (target / 'keep').write_text('previous')
            def fetch(url, limit):
                return json.dumps([release]).encode() if url == UPDATER['RELEASE_API'] else payload
            with patch.dict(os.environ, XDG_DATA_HOME=str(Path(folder) / 'data')), \
                    patch.dict(UPDATER['online_update'].__globals__, fetch=fetch), \
                    patch('sys.stdout', new_callable=io.StringIO) as out:
                UPDATER['online_update']('0.2.0', True)
                self.assertEqual(json.loads(out.getvalue())['status'], 'installed')
            self.assertEqual(json.loads((target / 'metadata.json').read_text())['version-name'], '0.3.0')
            backups = list((target.parent.parent / 'veazy-extension-backups').iterdir())
            self.assertEqual((backups[0] / 'keep').read_text(), 'previous')
