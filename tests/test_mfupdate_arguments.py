"""Atualizações de branches não devem executar o deploy nem registrar versão."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


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
        cases = [(('-tc',), ['transaction_classifier']), (('-d',), ['']),
                 (('-d', '-tc'), ['transaction_classifier', '']),
                 (('-tc', '-tc'), ['transaction_classifier'])]
        for flags, paths in cases:
            with self.subTest(flags=flags):
                self.calls.unlink(missing_ok=True)
                result = self.run_script(*flags)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.recorded_calls(), [
                    ['git', '-C', str(self.project / path), 'pull', '--ff-only'] for path in paths])
                self.assertFalse((self.project / '.mfdeploy/lock').exists())

    def test_failure_stops_updates_releases_lock_and_preserves_exit_code(self):
        result = self.run_script('-tc', '-d', GIT_STATUS='7')
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(len(self.recorded_calls()), 1)
        self.assertFalse((self.project / '.mfdeploy/lock').exists())

    def test_branch_updates_share_deploy_lock(self):
        (self.project / '.mfdeploy/lock').mkdir(parents=True)
        result = self.run_script('-d')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.recorded_calls(), [])
        self.assertTrue((self.project / '.mfdeploy/lock').exists())

    def test_infrastructure_update_can_replace_running_script(self):
        result = self.run_script('-d', REPLACE_SCRIPT='1')
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

    def test_launcher_forwards_flags_without_deploy_or_version_registration(self):
        result = self.run_script('-tc', '-d', launcher=True, EXECUTE_SSH='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.recorded_calls()
        self.assertEqual(calls[0][:3], ['ssh', '-t', 'producao'])
        self.assertNotIn('Version.objects', calls[0][-1])
        self.assertEqual(calls[1:], [
            ['git', '-C', str(self.project / 'transaction_classifier'), 'pull', '--ff-only'],
            ['git', '-C', str(self.project), 'pull', '--ff-only'],
        ])

    def test_launcher_without_flags_keeps_myfinance_deploy(self):
        result = self.run_script(launcher=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        command = self.recorded_calls()[0][-1]
        self.assertIn('"$BASEDIR/mfupdate"', command)
        self.assertIn('Version.objects.create', command)
