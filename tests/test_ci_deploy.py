"""O login temporário não deve persistir, mesmo se o deploy falhar."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RegistryAuthenticationTests(unittest.TestCase):
    def test_login_cleanup_and_deploy_exit_status(self):
        for login_status, deploy_status in ((0, 0), (0, 7), (9, 0)):
            with self.subTest(login=login_status, deploy=deploy_status), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                binaries = base / 'bin'
                binaries.mkdir()
                docker = binaries / 'docker'
                docker.write_text('''#!/bin/sh
set -eu
printf '%s' "$DOCKER_CONFIG" > "$BASEDIR/config-path"
cat > "$DOCKER_CONFIG/config.json"
exit "$LOGIN_STATUS"
''')
                docker.chmod(0o755)
                update = base / 'mfupdate'
                update.write_text('''#!/bin/sh
set -eu
test -f "$DOCKER_CONFIG/config.json"
printf '%s\\n%s' "$DEPLOY_IMAGE" "$DEPLOY_COMMIT" > "$BASEDIR/deployed"
exit "$DEPLOY_STATUS"
''')
                update.chmod(0o755)
                environment = {**os.environ,
                               'PATH': str(binaries) + os.pathsep + os.environ['PATH'],
                               'BASEDIR': str(base), 'DEPLOY_IMAGE': 'fixture-image',
                               'DEPLOY_COMMIT': 'a' * 40, 'REGISTRY_USER': 'fixture',
                               'LOGIN_STATUS': str(login_status), 'DEPLOY_STATUS': str(deploy_status)}
                result = subprocess.run(['sh', str(ROOT / 'deploy/ci-deploy.sh')],
                                        env=environment, input='private-fixture-token',
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, login_status or deploy_status)
                self.assertNotIn('private-fixture-token', result.stdout + result.stderr)
                self.assertFalse(Path((base / 'config-path').read_text()).exists())
                self.assertEqual((base / 'deployed').exists(), login_status == 0)
                if login_status == 0:
                    self.assertEqual((base / 'deployed').read_text(), 'fixture-image\n' + 'a' * 40)
