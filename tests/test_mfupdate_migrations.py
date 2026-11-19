import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'mfupdate'
MOCK = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
state_file = Path(os.environ['MOCK_STATE'])
state = json.loads(state_file.read_text())
state['calls'].append([name, *args])
status = 0
if name == 'docker':
    if args[0] == 'compose':
        if 'ps' in args:
            print('current-app')
        if any('mysqldump' in a for a in args):
            if state['scenario'] == 'backup-failure': status = 9
            elif state['scenario'] != 'empty-backup': print('-- synthetic backup\nCREATE TABLE fixture (id INT);')
    elif args[0] == 'inspect':
        if 'Running' in args[2]: print('true')
        else: print('sha256:new' if args[-1].startswith('myfinance-update-test-') or state.get('deployed') else 'sha256:old')
    elif args[0] == 'exec':
        if 'migrate' in args:
            if '--check' in args:
                status = 0 if state['scenario'] == 'no-migrations' or state.get('migrated') else 1
            elif state['scenario'] == 'migration-failure': status = 7
            else: state['migrated'] = True
        elif args[-1] == '-': sys.stdin.read()
elif name == 'sudo' and args[-2:] == ['myfinance', 'start']:
    state['deployed'] = True
state_file.write_text(json.dumps(state))
sys.exit(status)
'''


class MigrationDeploymentTests(unittest.TestCase):
    def run_update(self, scenario):
        temporary = tempfile.TemporaryDirectory(prefix='mfupdate-test-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        project = root / 'project'
        project.mkdir()
        (project / 'myfinance').mkdir()
        binaries = root / 'bin'
        binaries.mkdir()
        mock = binaries / 'mock'
        mock.write_text(MOCK)
        mock.chmod(0o755)
        for command in ['docker', 'git', 'sudo']:
            (binaries / command).symlink_to(mock)
        state_file = root / 'state.json'
        state_file.write_text(json.dumps({'scenario': scenario, 'calls': []}))
        backup_dir = root / 'backups'
        environment = {**os.environ, 'PATH': str(binaries) + os.pathsep + os.environ['PATH'],
                       'BASEDIR': str(project), 'TEST_TIMEOUT': '5', 'MOCK_STATE': str(state_file),
                       'MIGRATION_BACKUP_DIR': str(backup_dir), 'TMPDIR': str(root)}
        result = subprocess.run(['sh', str(SCRIPT)], env=environment, text=True, capture_output=True, timeout=15)
        state = json.loads(state_file.read_text())
        return result, state, backup_dir

    def test_pending_migrations_have_private_backup_and_finish_before_service_restart(self):
        result, state, backups = self.run_update('pending')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(state['migrated'])
        self.assertTrue(state['deployed'])
        dumps = list(backups.glob('*.sql'))
        self.assertEqual(len(dumps), 1)
        self.assertEqual(dumps[0].stat().st_mode & 0o777, 0o600)
        self.assertIn('synthetic backup', dumps[0].read_text())
        calls = state['calls']
        migration = next(i for i, a in enumerate(calls) if 'migrate' in a and '--noinput' in a)
        stop = next(i for i, a in enumerate(calls) if a[:2] == ['sudo', 'rc-service'] and 'stop' in a)
        self.assertLess(migration, stop)
        self.assertEqual(len([a for a in calls if 'migrate' in a and '--check' in a]), 2)

    def test_up_to_date_database_does_not_dump_or_apply_migrations(self):
        result, state, backups = self.run_update('no-migrations')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(state['deployed'])
        self.assertFalse(backups.exists())
        self.assertFalse(any('--noinput' in a for a in state['calls']))

    def test_backup_failure_prevents_migration_and_keeps_current_service(self):
        result, state, backups = self.run_update('backup-failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(state.get('deployed'))
        self.assertFalse(any('--noinput' in a for a in state['calls']))
        self.assertEqual(list(backups.iterdir()), [])

    def test_empty_backup_is_rejected_before_migration(self):
        result, state, backups = self.run_update('empty-backup')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(state.get('deployed'))
        self.assertFalse(any('--noinput' in a for a in state['calls']))
        self.assertEqual(list(backups.iterdir()), [])

    def test_migration_failure_keeps_backup_and_does_not_restart_service(self):
        result, state, backups = self.run_update('migration-failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(state.get('deployed'))
        self.assertEqual(len(list(backups.glob('*.sql'))), 1)
        self.assertFalse(any(a[:2] == ['sudo', 'rc-service'] for a in state['calls']))


if __name__ == '__main__':
    unittest.main()
