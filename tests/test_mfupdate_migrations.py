import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MOCK = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
state_file = Path(os.environ['MOCK_STATE'])
state = json.loads(state_file.read_text())
state['calls'].append([name, *args])
scenario = state['scenario']
status = 0
if name in ('docker', 'docker-compose'):
    compose = name == 'docker-compose' or args[0] == 'compose'
    if compose:
        if args == ['compose', 'version'] and os.environ.get('MOCK_V1'): status = 1
        if 'ps' in args:
            print(state['current'])
        if any('mysqldump' in a for a in args):
            if scenario == 'backup-failure': status = 9
            elif scenario != 'empty-backup': print('-- synthetic backup\nCREATE TABLE fixture (id INT);')
        if 'up' in args and args[-1].startswith('app-myfin-'):
            state['candidate'] = args[-1]
        if 'up' in args and args[-1] == 'investment-history': state['worker_updated'] = True
    elif args[0] == 'inspect':
        if 'Running' in args[2]: print('true')
        else: print('sha256:new' if args[-1] == state.get('candidate') else 'sha256:old')
    elif args[:2] == ['image', 'inspect']: print('sha256:new')
    elif args[0] == 'exec':
        if 'migrate' in args:
            if '--check' in args:
                status = 0 if scenario == 'no-migrations' or state.get('migrated') else 1
            elif scenario == 'migration-failure': status = 7
            else: state['migrated'] = True
        elif 'python' in args and '-' in args:
            sys.stdin.read()
            proxy = args[-1] in ('blue', 'green')
            if scenario == 'readiness-failure' or (scenario == 'proxy-failure' and proxy): status = 1
        elif 'nginx' in args and '-t' in args:
            state['nginx_tests'] = state.get('nginx_tests', 0) + 1
            if scenario == 'nginx-config-failure' and state['nginx_tests'] == 1: status = 1
        elif 'nginx' in args and 'reload' in args:
            state['reloads'] = state.get('reloads', 0) + 1
            if scenario == 'reload-failure' and state['reloads'] == 1: status = 1
        elif args[-1].startswith('ps |'): status = 1
    elif args[0] == 'stop': state['stopped'] = args[-1]
state_file.write_text(json.dumps(state))
sys.exit(status)
'''


class MigrationDeploymentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mfupdate-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        for directory in ('myfinance', 'static', 'nginx', 'deploy'):
            (self.project / directory).mkdir()
        for filename in ('mfcompose', 'docker-compose.yml', 'myfinance.init.d',
                         'nginx/default.conf', 'nginx/bluegreen.conf.template', 'deploy/healthcheck.py'):
            shutil.copy2(ROOT / filename, self.project / filename)
        (self.project / 'static/old.css').write_text('old-style')
        binaries = self.root / 'bin'
        binaries.mkdir()
        mock = binaries / 'mock'
        mock.write_text(MOCK)
        mock.chmod(0o755)
        for command in ('docker', 'docker-compose', 'git', 'sudo'):
            (binaries / command).symlink_to(mock)
        self.state_file = self.root / 'state.json'
        self.backups = self.root / 'backups'
        self.env = {**os.environ, 'PATH': str(binaries) + os.pathsep + os.environ['PATH'],
                    'BASEDIR': str(self.project), 'TEST_TIMEOUT': '3', 'DRAIN_TIMEOUT': '1',
                    'MOCK_STATE': str(self.state_file), 'MIGRATION_BACKUP_DIR': str(self.backups)}

    def run_update(self, scenario='pending', active='legacy'):
        self.state_file.write_text(json.dumps({'scenario': scenario, 'calls': [],
                                              'current': 'app-myfin' if active == 'legacy' else f'app-myfin-{active}'}))
        if active != 'legacy':
            state_dir = self.project / '.mfdeploy'
            (state_dir / 'nginx').mkdir(parents=True, exist_ok=True)
            (state_dir / 'active').write_text(active + '\n')
            (state_dir / f'{active}.yml').write_text('services: {}\n')
            (state_dir / 'nginx/default.conf').write_text('previous nginx config\n')
            (state_dir / f'{active}.nginx.conf').write_text('previous nginx config\n')
        result = subprocess.run(['sh', str(ROOT / 'mfupdate')], env=self.env,
                                text=True, capture_output=True, timeout=20)
        return result, json.loads(self.state_file.read_text())

    def assert_old_preserved(self, state):
        self.assertNotIn('stopped', state)
        self.assertFalse(state.get('worker_updated'))
        self.assertFalse(any('down' in call or 'rc-service' in call for call in state['calls']))

    def test_backup_precedes_migrations_and_switch_precedes_old_stop(self):
        result, state = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        dumps = list(self.backups.glob('*.sql'))
        self.assertEqual(len(dumps), 1)
        self.assertEqual(dumps[0].stat().st_mode & 0o777, 0o600)
        self.assertTrue(state['migrated'])
        self.assertTrue(state['worker_updated'])
        calls = state['calls']
        dump = next(i for i, a in enumerate(calls) if any('mysqldump' in x for x in a))
        migration = next(i for i, a in enumerate(calls) if 'migrate' in a and '--noinput' in a)
        reload = next(i for i, a in enumerate(calls) if 'reload' in a)
        stop = next(i for i, a in enumerate(calls) if a[:2] == ['docker', 'stop'])
        self.assertLess(dump, migration)
        self.assertLess(migration, reload)
        self.assertLess(reload, stop)
        self.assertEqual((self.project / '.mfdeploy/active').read_text().strip(), 'blue')
        self.assertIn('172.18.0.8:8000', (self.project / '.mfdeploy/nginx/default.conf').read_text())
        self.assertEqual((self.project / '.mfdeploy/assets/legacy/static/old.css').read_text(), 'old-style')
        self.assertFalse(any('down' in a or 'rc-service' in a for a in calls))
        self.assertFalse((self.project / '.mfdeploy/lock').exists())

    def test_up_to_date_database_does_not_dump_or_apply_migrations(self):
        result, state = self.run_update('no-migrations')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.backups.exists())
        self.assertFalse(any('--noinput' in a for a in state['calls']))

    def test_backup_failures_prevent_migrations_and_promotion(self):
        for scenario in ('backup-failure', 'empty-backup'):
            with self.subTest(scenario=scenario):
                result, state = self.run_update(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assert_old_preserved(state)
                self.assertFalse(any('--noinput' in a for a in state['calls']))
                self.assertEqual(list(self.backups.iterdir()), [])

    def test_migration_failure_keeps_backup(self):
        result, state = self.run_update('migration-failure')
        self.assertNotEqual(result.returncode, 0)
        self.assert_old_preserved(state)
        self.assertEqual(len(list(self.backups.glob('*.sql'))), 1)

    def test_readiness_failure_does_not_change_nginx(self):
        result, state = self.run_update('readiness-failure', active='blue')
        self.assertNotEqual(result.returncode, 0)
        self.assert_old_preserved(state)
        self.assertNotIn('reloads', state)
        self.assertEqual((self.project / '.mfdeploy/active').read_text().strip(), 'blue')

    def test_failed_cutover_restores_proxy_and_persisted_state(self):
        for scenario in ('nginx-config-failure', 'reload-failure', 'proxy-failure'):
            with self.subTest(scenario=scenario):
                result, state = self.run_update(scenario, active='blue')
                self.assertNotEqual(result.returncode, 0)
                self.assert_old_preserved(state)
                self.assertEqual((self.project / '.mfdeploy/active').read_text().strip(), 'blue')
                self.assertEqual((self.project / '.mfdeploy/nginx/default.conf').read_text(), 'previous nginx config\n')
                self.assertTrue(state['reloads'])

    def test_slots_alternate_without_recreating_nginx_or_dependencies(self):
        for active, expected in (('blue', 'green'), ('green', 'blue')):
            with self.subTest(active=active):
                result, state = self.run_update(active=active)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(state['stopped'], f'app-myfin-{active}')
                self.assertEqual((self.project / '.mfdeploy/active').read_text().strip(), expected)
                ups = [a for a in state['calls'] if 'up' in a]
                self.assertEqual([a[-1] for a in ups], [f'app-myfin-{expected}', 'investment-history', 'password-reset-email'])
                self.assertTrue(all('--no-deps' in a for a in ups))
                override = (self.project / f'.mfdeploy/{expected}.yml').read_text()
                self.assertEqual(override.count('image: myfinance-release:'), 3)

    def test_boot_loads_active_slot_and_pinned_images_with_compose_v1_and_v2(self):
        for v1 in ('', '1'):
            with self.subTest(v1=v1):
                result, state = self.run_update(active='blue')
                self.assertEqual(result.returncode, 0, result.stderr)
                (self.project / '.mfdeploy/nginx/default.conf').write_text('interrupted switch\n')
                env = {**self.env, 'MOCK_V1': v1}
                result = subprocess.run([str(self.project / 'mfcompose'), 'up', '-d'], env=env, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((self.project / '.mfdeploy/nginx/default.conf').read_text(),
                                 (self.project / '.mfdeploy/green.nginx.conf').read_text())
                call = next(call for call in reversed(json.loads(self.state_file.read_text())['calls']) if 'up' in call)
                self.assertEqual(call[-2:], ['up', '-d'])
                self.assertEqual(call[call.index('--profile') + 1], 'green')
                self.assertIn(str(self.project / '.mfdeploy/green.yml'), call)

    def test_concurrent_deploy_is_rejected(self):
        lock = self.project / '.mfdeploy/lock'
        lock.mkdir(parents=True)
        result = subprocess.run(['sh', str(ROOT / 'mfupdate')], env=self.env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(lock.exists())
        self.assertFalse(self.state_file.exists())


class ComposeConfigurationTests(unittest.TestCase):
    def test_profiles_and_pinned_overrides_render_without_daemon(self):
        if not shutil.which('docker'):
            self.skipTest('Docker CLI ausente')
        version = subprocess.run(['docker', 'compose', 'version'], capture_output=True)
        if version.returncode:
            self.skipTest('Compose v2 ausente')
        variables = re.findall(r'\$\{([A-Z0-9_]+)', (ROOT / 'docker-compose.yml').read_text())
        environment = {**os.environ, **{key: 'fixture' for key in variables}}
        with tempfile.TemporaryDirectory() as temporary:
            override = Path(temporary) / 'slot.yml'
            for slot in ('blue', 'green'):
                with self.subTest(slot=slot):
                    override.write_text(f"""services:
  app-myfin-{slot}:
    image: myfinance-release:fixture
  investment-history:
    image: myfinance-release:fixture
  password-reset-email:
    image: myfinance-release:fixture
  nginx-myfin:
    volumes:
      - {temporary}/nginx:/etc/nginx/conf.d:ro
""")
                    result = subprocess.run(['docker', 'compose', '--env-file', '/dev/null',
                                             '-f', str(ROOT / 'docker-compose.yml'), '--profile', slot,
                                             '-f', str(override), 'config', '--format', 'json'],
                                            env=environment, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    services = json.loads(result.stdout)['services']
                    self.assertNotIn('app-myfin', services)
                    self.assertNotIn('app-myfin-' + ('green' if slot == 'blue' else 'blue'), services)
                    app = services[f'app-myfin-{slot}']
                    self.assertNotIn('build', app)
                    self.assertEqual(app['image'], 'myfinance-release:fixture')
                    self.assertEqual(services['investment-history']['image'], app['image'])
                    self.assertEqual(services['password-reset-email']['image'], app['image'])
                    mounts = [v for v in services['nginx-myfin']['volumes'] if v['target'] == '/etc/nginx/conf.d']
                    self.assertEqual(len(mounts), 1)
                    self.assertEqual(mounts[0]['source'], temporary + '/nginx')
                    self.assertEqual(services['nginx-myfin']['networks']['myfin-net']['aliases'], ['app-myfin'])


if __name__ == '__main__':
    unittest.main()
