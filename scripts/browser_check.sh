#!/bin/bash
# Linux: reuse a non-root Docker Chromium namespace/seccomp sandbox.
# Python dependencies are installed on the host, never into the browser image.
set -euo pipefail
project_root=$(cd "$(dirname "$0")/.." && pwd)
qa_dir=${1:-/tmp/multibox-browser}
mkdir -p "$qa_dir"
qa_dir=$(cd "$qa_dir" && pwd)
shift $(( $# > 0 ? 1 : 0 ))
multibox_python=${MULTIBOX_PYTHON:-python}
if [ "$("$multibox_python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != 3.12 ]; then
  echo 'The pinned browser container uses Python 3.12. Select an installed 3.12 environment with MULTIBOX_PYTHON.' >&2
  exit 2
fi
python_site=$("$multibox_python" -c 'import site; print(site.getsitepackages()[0])')
if [ ! -f "$project_root/tests/browser/node_modules/playwright/cli.js" ]; then
  echo 'Install the pinned browser test dependencies first: npm ci --prefix tests/browser' >&2
  exit 2
fi
multibox_docker=(env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock)
"${multibox_docker[@]}" info >/dev/null
image='mcr.microsoft.com/playwright@sha256:f1e7e01021efd65dd1a2c56064be399f3e4de00fd021ac561325f2bfbb2b837a'
cat > "$qa_dir/run-container.sh" <<'INNER'
#!/bin/bash
set -euo pipefail
export PYTHONPATH=/app/src:/python-packages
python3 -m multibox.game_server --port 8000 > /qa/server.log 2>&1 &
server_one=$!
MULTIBOX_ALLOWED_ORIGINS=http://localhost:8000 python3 -m multibox.game_server --port 8001 > /qa/server-second.log 2>&1 &
server_two=$!
trap 'kill "$server_one" "$server_two" 2>/dev/null || true' EXIT
node --input-type=module -e 'for(let i=0;i<100;i++){try{if((await fetch("http://localhost:8000/health")).ok&&(await fetch("http://localhost:8001/health")).ok)process.exit(0);}catch{}await new Promise(r=>setTimeout(r,100));}process.exit(1);'
node node_modules/playwright/cli.js test "$@"
INNER
exec "${multibox_docker[@]}" run --rm --init --user "$(id -u):$(id -g)" \
  --security-opt no-new-privileges --security-opt "seccomp=$project_root/tests/browser/seccomp.json" \
  --shm-size=1g --mount "type=bind,src=$project_root,dst=/app,readonly" \
  --mount "type=bind,src=$python_site,dst=/python-packages,readonly" \
  --mount "type=bind,src=$qa_dir,dst=/qa" --workdir /app/tests/browser \
  -e MULTIBOX_URL=http://localhost:8000 -e MULTIBOX_QA_DIR=/qa \
  "$image" bash /qa/run-container.sh "$@"
