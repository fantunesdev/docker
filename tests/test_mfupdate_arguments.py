"""Atualizações de branches não devem executar o deploy nem registrar versão."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
UPDATE_CASES = [
    (('-tc',), ['transaction_classifier']),
    (('-d',), ['']),
    (('-a',), ['myfinance', 'transaction_classifier', '']),
    (('-d', '-tc'), ['transaction_classifier', '']),
    (('-tc', '-tc'), ['transaction_classifier']),
    (('-tc', '-a', '-d', '-a'), ['myfinance', 'transaction_classifier', '']),
]


class UpdateArgumentsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mfupdate-arguments-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.project = self.base / 'project'
        self.project.mkdir()
        shutil.copy2(ROOT / 'mfupdate', self.project / 'mfupdate')
        self.binaries = self.base / 'bin'
        self.binaries.mkdir()
        self.calls = self.base / 'calls.jsonl'
        mock = self.binaries / 'mock'
        mock.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
with open(os.environ['CALLS'], 'a') as output:
    output.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
if name == 'git':
    if os.environ.get('REPLACE_SCRIPT') and sys.argv[2] == os.environ['BASEDIR']:
        Path(os.environ['BASEDIR'], 'mfupdate').write_text('invalid replacement script')
    sys.exit(int(os.environ.get('GIT_STATUS', '0')))
if name == 'ssh' and os.environ.get('EXECUTE_SSH'):
    import subprocess
    sys.exit(subprocess.call(['sh', '-c', sys.argv[-1]]))
if name != 'ssh':
    sys.exit('Comando inesperado em atualização de branch: ' + name)
''')
        mock.chmod(0o755)
        for name in ('git', 'ssh', 'docker', 'sudo'):
            (self.binaries / name).symlink_to(mock)
        self.env = {**os.environ, 'BASEDIR': str(self.project), 'CALLS': str(self.calls),
                    'PATH': str(self.binaries) + os.pathsep + os.environ['PATH']}

    def run_script(self, *args, launcher=False, **variables):
        return subprocess.run(['bash' if launcher else 'sh',
                               str(ROOT / 'deploy/mfupdate-remote' if launcher else self.project / 'mfupdate'),
                               *args], env={**self.env, **variables}, capture_output=True, text=True, timeout=10)

    def recorded_calls(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def test_flags_select_only_requested_repositories_and_deduplicate(self):
        for flags, paths in UPDATE_CASES:
            with self.subTest(flags=flags):
                self.calls.unlink(missing_ok=True)
                result = self.run_script(*flags)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.recorded_calls(), [
                    ['git', '-C', str(self.project / path), 'pull', '--ff-only'] for path in paths])
                self.assertFalse((self.project / '.mfdeploy/lock').exists())

    def test_failure_stops_updates_releases_lock_and_preserves_exit_code(self):
        for launcher in (False, True):
            with self.subTest(launcher=launcher):
                self.calls.unlink(missing_ok=True)
                result = self.run_script('-a', launcher=launcher, EXECUTE_SSH='1', GIT_STATUS='7')
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertEqual(sum(call[0] == 'git' for call in self.recorded_calls()), 1)
                self.assertFalse((self.project / '.mfdeploy/lock').exists())

    def test_branch_updates_share_deploy_lock(self):
        (self.project / '.mfdeploy/lock').mkdir(parents=True)
        for launcher in (False, True):
            with self.subTest(launcher=launcher):
                self.calls.unlink(missing_ok=True)
                result = self.run_script('-d', launcher=launcher, EXECUTE_SSH='1')
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(call[0] == 'git' for call in self.recorded_calls()))
                self.assertTrue((self.project / '.mfdeploy/lock').exists())

    def test_infrastructure_update_can_replace_running_script(self):
        result = self.run_script('-a', REPLACE_SCRIPT='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.project / 'mfupdate').read_text(), 'invalid replacement script')
        self.assertFalse((self.project / '.mfdeploy/lock').exists())

    def test_help_and_invalid_flags_do_not_connect_or_mutate(self):
        for launcher in (False, True):
            for args, expected in ((('--help',), 0), (('--invalid',), 1)):
                with self.subTest(launcher=launcher, args=args):
                    result = self.run_script(*args, launcher=launcher)
                    self.assertEqual(result.returncode, expected)
                    self.assertEqual(self.recorded_calls(), [])
                    self.assertFalse((self.project / '.mfdeploy').exists())

    def test_launcher_updates_selected_branches_without_running_legacy_remote_script(self):
        # Reproduz a VM antiga: ignora os argumentos e inicia um build.
        (self.project / 'mfupdate').write_text(
            '#!/bin/sh\ntouch "$BASEDIR/legacy-deploy-started"\ndocker build .\n')
        for flags, paths in UPDATE_CASES:
            with self.subTest(flags=flags):
                self.calls.unlink(missing_ok=True)
                result = self.run_script(*flags, launcher=True, EXECUTE_SSH='1')
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = self.recorded_calls()
                self.assertEqual(calls[0][:3], ['ssh', '-t', 'producao'])
                self.assertNotIn('Version.objects', calls[0][-1])
                self.assertEqual(calls[1:], [
                    ['git', '-C', str(self.project / path), 'pull', '--ff-only'] for path in paths])
                self.assertFalse((self.project / 'legacy-deploy-started').exists())
                self.assertFalse((self.project / '.mfdeploy/lock').exists())

    def test_launcher_without_flags_keeps_myfinance_deploy(self):
        result = self.run_script(launcher=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        command = self.recorded_calls()[0][-1]
        self.assertIn('"$BASEDIR/mfupdate"', command)
        self.assertIn('Version.objects.create', command)
