"""Linux startup, XDG paths, desktop-entry encoding and menu registration."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE))
sys.path.insert(0, str(MODULE / 'LIB'))
import install_desktop
from OMFITlib_template_paths import applications_directory, default_library, preferences_path


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux desktop integration suite')
class LinuxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='omfit-linux-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_xdg_overrides_and_relative_values(self):
        with patch('pathlib.Path.home', return_value=self.base), patch.dict(os.environ,
            {'XDG_CONFIG_HOME': str(self.base / 'config'), 'XDG_DATA_HOME': str(self.base / 'data')}):
            self.assertEqual(preferences_path(), self.base / 'config/omfit-template-manager/settings.json')
            self.assertEqual(default_library(), self.base / 'data/omfit-template-manager/templates')
            self.assertEqual(applications_directory(), self.base / 'data/applications')
        with patch('pathlib.Path.home', return_value=self.base), patch.dict(os.environ,
            {'XDG_CONFIG_HOME': 'relative/config', 'XDG_DATA_HOME': ''}):
            self.assertEqual(preferences_path(), self.base / '.config/omfit-template-manager/settings.json')
            self.assertEqual(default_library(), self.base / '.local/share/omfit-template-manager/templates')

    def test_legacy_library_is_reused(self):
        old = self.base / '.omfit-template-library'
        old.mkdir()
        with patch('pathlib.Path.home', return_value=self.base):
            self.assertEqual(default_library(), old)

    def test_launcher_from_another_directory_with_selected_python(self):
        result = subprocess.run(['sh', str(MODULE / 'start_manager.sh'), '--check'], cwd=self.base,
            env=dict(os.environ, OMFIT_TEMPLATE_PYTHON=sys.executable), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertEqual(info['platform'], 'Linux')
        self.assertEqual(info['executable'], sys.executable)
        self.assertTrue(info['tk'].startswith('8.'))

    def test_cli_does_not_require_display(self):
        environment = dict(os.environ)
        environment.pop('DISPLAY', None)
        environment.pop('WAYLAND_DISPLAY', None)
        result = subprocess.run([sys.executable, str(MODULE / 'launch.py'), '--library', str(self.base / 'library'), 'list'],
            env=environment, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['releases'], [])

    def test_missing_display_has_clear_error(self):
        environment = dict(os.environ)
        environment.pop('DISPLAY', None)
        environment.pop('WAYLAND_DISPLAY', None)
        result = subprocess.run([sys.executable, str(MODULE / 'launch.py'), '--check'], env=environment,
                                capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DISPLAY', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_repair_cli_without_display(self):
        from test_templates import fixture
        from OMFITlib_template_archive import Project
        source, output = self.base / 'old.zip', self.base / 'fixed.zip'
        fixture(source)
        environment = dict(os.environ)
        environment.pop('DISPLAY', None)
        environment.pop('WAYLAND_DISPLAY', None)
        command = [sys.executable, str(MODULE / 'launch.py'), 'repair', str(source), str(output)]
        result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), str(output))
        with Project(output) as project:
            project.require_entry_first()
        repeated = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=15)
        self.assertNotEqual(repeated.returncode, 0)
        self.assertNotIn('Traceback', repeated.stderr)

    def test_desktop_registration_update_and_remove(self):
        target = install_desktop.install(MODULE, sys.executable, self.base)
        self.assertTrue(target.is_file())
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)
        first = target.read_text(encoding='utf-8')
        self.assertIn('Terminal=false', first)
        install_desktop.install(MODULE, sys.executable, self.base, library=self.base / 'new-library')
        self.assertIn('--library', target.read_text(encoding='utf-8'))
        self.assertFalse((self.base / 'new-library').exists())
        install_desktop.install(MODULE, sys.executable, self.base, uninstall=True)
        self.assertFalse(target.exists())

    def test_unrelated_desktop_entry_is_not_overwritten(self):
        target = self.base / 'org.omfit.TemplateManager.desktop'
        target.write_text('unrelated', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '不属于本工具'):
            install_desktop.install(MODULE, sys.executable, self.base)
        self.assertEqual(target.read_text(), 'unrelated')

    def test_desktop_exec_handles_spaces_unicode_and_metacharacters(self):
        module = self.base / '模板 space % $ ` quote" back\\slash'
        module.mkdir()
        record = self.base / 'record.json'
        (module / 'launch.py').write_text('import sys, json\nfrom pathlib import Path\nPath(' + repr(str(record)) +
            ').write_text(json.dumps(sys.argv[1:],ensure_ascii=False),encoding="utf-8")\n', encoding='utf-8')
        shutil.copyfile(MODULE / 'omfit-templates.svg', module / 'omfit-templates.svg')
        library = self.base / '共享 results % $ ` " \\'
        target = install_desktop.install(module, sys.executable, self.base / 'applications', library=library)
        validator = shutil.which('desktop-file-validate')
        if validator is None or shutil.which('gio') is None:
            self.skipTest('desktop-file-utils and gio needed for actual desktop-entry validation')
        result = subprocess.run([validator, str(target)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        launched = subprocess.run(['gio', 'launch', str(target)], capture_output=True, text=True, timeout=10)
        self.assertEqual(launched.returncode, 0, launched.stdout + launched.stderr)
        deadline = time.monotonic() + 5
        while not record.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue(record.exists())
        self.assertEqual(json.loads(record.read_text(encoding='utf-8')), ['--library', str(library)])


if __name__ == '__main__':
    unittest.main(verbosity=2)
