"""Exercise a disposable image without network or production credentials/data."""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from argon2 import PasswordHasher

PASSWORD = "container-only-synthetic-owner-passphrase"
ROOT = Path(__file__).resolve().parents[1]


def docker(*arguments, data=None, check=True):
    result = subprocess.run(
        ["docker", *arguments],
        input=data,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(
            "Disposable container operation failed; inspect only its sanitized status."
        )
    return result.stdout.strip()


CLIENT = """
import json, os, time, urllib.request, urllib.error
from pathlib import Path
from http.cookiejar import CookieJar
origin = os.environ['APP_ORIGIN']
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
csrf = ''
def request(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {'Origin': origin, 'Content-Type': 'application/json'}
    if csrf: headers['X-CSRF-Token'] = csrf
    result = client.open(urllib.request.Request('http://127.0.0.1:8000'+path, data=data, headers=headers), timeout=5)
    raw = result.read()
    return json.loads(raw) if result.headers.get('content-type','').startswith('application/json') else raw
assert request('/api/health/ready')['status'] == 'ok'
assert b'<html' in request('/').lower()
for path in ['/api/auth/session','/api/images/jobs']:
    try: request(path)
    except urllib.error.HTTPError as error: assert error.code == 401
    else: raise AssertionError('Private route was public')
assert os.getuid() == 10001
for name in ['.env','.env.local','.git','private','docs','IMPLEMENTATION_PLAN.local.md']:
    assert not (Path('/app')/name).exists()
if os.environ['PROVIDER_MODE'] == 'mock':
    csrf = request('/api/auth/login', {'password':'container-only-synthetic-owner-passphrase'})['csrf_token']
    state = Path('/data/smoke-state.json')
    if not state.exists():
        conversation = request('/api/conversations', {'title':'Disposable smoke check'})
        run = request('/api/runs', {'conversation_id':conversation['id'], 'model_id':'mock/steady',
            'prompt':'Synthetic container fixture','max_tokens':32,'idempotency_key':'container-text-idempotency'})
        for _ in range(100):
            saved = request('/api/runs/'+run['id'])
            if saved['status'] == 'succeeded': break
            time.sleep(.05)
        assert saved['status'] == 'succeeded'
        job = request('/api/images/jobs', {'model_id':'mock/image-studio','provider_tag':'local',
            'prompt':'Synthetic container image','count':1,
            'options':{'resolution':'1K','aspect_ratio':'1:1','output_format':'png'},
            'idempotency_key':'container-image-idempotency'})
        for _ in range(100):
            saved = request('/api/images/jobs/'+job['id'])
            if saved['status'] == 'succeeded': break
            time.sleep(.05)
        assert saved['status'] == 'succeeded' and saved['assets'][0]['width'] == 1024
        state.write_text(json.dumps({'job':job['id'],'conversation':conversation['id']}))
    state = json.loads(state.read_text())
    jobs = request('/api/images/jobs')
    assert len(jobs)==1 and jobs[0]['id']==state['job'] and jobs[0]['status']=='succeeded'
    image = request('/api/media/'+jobs[0]['assets'][0]['id']+'?download=true')
    assert image[:4] == b'RIFF'
    assert request('/api/conversations/'+state['conversation'])['runs'][0]['status']=='succeeded'
print(json.dumps({'ready':True,'private_routes_guarded':True,'non_root':True,'private_sources_absent':True,
    'mock_persistence_checked':os.environ['PROVIDER_MODE']=='mock'}))
"""


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: scripts/smoke-image.py IMAGE")
    image = sys.argv[1]
    identifier = "labchatbot-smoke-" + uuid4().hex
    volume = identifier + "-data"
    names = []
    root_hash = PasswordHasher().hash(PASSWORD)
    with tempfile.TemporaryDirectory(prefix="lab-container-") as temporary:
        environment = Path(temporary) / "container.env"
        environment.touch(mode=0o600)
        docker("volume", "create", volume)
        try:
            for mode in ["mock", "openrouter"]:
                name = identifier + "-" + mode
                content = {
                    "APP_ENV": "development" if mode == "mock" else "production",
                    "APP_ORIGIN": "http://127.0.0.1:8000"
                    if mode == "mock"
                    else "https://container.invalid",
                    "PROVIDER_MODE": mode,
                    "AUTH_MODE": "password",
                    "AUTH_PASSWORD_HASH": root_hash,
                    "SPEND_CONTROL": "provider",
                    "DATA_DIR": "/data",
                    "OPENROUTER_API_KEY": "synthetic-unusable-container-key",
                }
                environment.write_text(
                    "".join(f"{key}={value}\n" for key, value in content.items())
                )
                docker(
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--memory",
                    "2g",
                    "--cpus",
                    "1",
                    "--tmpfs",
                    "/tmp:rw,nosuid,nodev,size=256m",
                    "--env-file",
                    str(environment),
                    "--mount",
                    f"type=volume,src={volume},dst=/data",
                    image,
                )
                names.append(name)
                for restart in range(2 if mode == "mock" else 1):
                    ready = False
                    for _ in range(40):
                        status = json.loads(docker("inspect", name))[0]["State"]
                        if not status["Running"]:
                            raise RuntimeError("Container failed startup.")
                        if (
                            subprocess.run(
                                [
                                    "docker",
                                    "exec",
                                    name,
                                    "python",
                                    "-c",
                                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready',timeout=1)",
                                ],
                                capture_output=True,
                                check=False,
                            ).returncode
                            == 0
                        ):
                            ready = True
                            break
                        time.sleep(0.25)
                    if not ready:
                        raise RuntimeError("Container readiness timed out.")
                    evidence = json.loads(
                        docker("exec", "-i", name, "python", "-", data=CLIENT)
                    )
                    assert evidence["private_routes_guarded"] and evidence["non_root"]
                    if mode == "mock" and restart == 0:
                        docker("restart", name)
                docker("stop", "--time", "35", name)
            print(
                json.dumps(
                    {
                        "image": image,
                        "network": "none",
                        "root_readonly": True,
                        "non_root_uid": 10001,
                        "real_restart_and_persistence": True,
                        "production_startup": True,
                        "paid_requests": 0,
                    }
                )
            )
        finally:
            for name in names:
                docker("rm", "-f", name, check=False)
            docker("volume", "rm", volume, check=False)


if __name__ == "__main__":
    main()
