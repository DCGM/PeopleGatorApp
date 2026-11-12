#!/usr/bin/env bash
# Install this account as a self-hosted GitHub Actions runner for PeopleGator
# deployments, running as a lingering `systemctl --user` service.
#
#   deploy/runner/install.sh preview,staging     # preview/staging host
#   deploy/runner/install.sh release             # production host
#
# Run it as the deployment account. It needs Linux x86-64, curl, tar, git, flock,
# python3 with venv, Docker with Compose on the account's current context
# (`docker context use rootless`), lingering (once, as root:
# `loginctl enable-linger <account>`) and a registration token in RUNNER_TOKEN
# (Settings → Actions → Runners → New self-hosted runner), or a `gh` login with
# admin rights on the repository. RUNNER_NAME overrides the runner name.
#
# Safe to rerun: an existing registration is kept; the runner's environment,
# the job-started guard and the service are refreshed and the service restarted.
set -euo pipefail

environments=${1:?usage: install.sh preview,staging|release}
repository=${RUNNER_REPOSITORY:-DCGM/PeopleGatorApp}
name=${RUNNER_NAME:-$(hostname -s)-${environments//,/-}}
dir=$HOME/actions-runner/$name
here=$(cd "$(dirname "$0")" && pwd)
guard=$HOME/.local/libexec/people-gator/job-started.sh
units=$HOME/.config/systemd/user

fail() { echo "install.sh: $*" >&2; exit 1; }

labels=
for environment in ${environments//,/ }; do
    case $environment in
        preview | staging | release) labels+="${labels:+,}people-gator-$environment" ;;
        *) fail "unknown environment '$environment'; use preview, staging and/or release" ;;
    esac
done
[[ $name =~ ^[A-Za-z0-9._-]+$ ]] || fail "RUNNER_NAME may contain only letters, digits, '.', '_' and '-'"

# Prerequisites of the runner and of the deploy jobs it will run.
[ "$(uname -m)" = x86_64 ] || fail "the deploy jobs need an x86-64 host"
for tool in curl tar git flock python3 sha256sum docker systemctl loginctl; do
    command -v "$tool" >/dev/null || fail "missing $tool"
done
python3 -c 'import venv, ensurepip' 2>/dev/null || fail "python3 needs venv and ensurepip (Debian/Ubuntu: python3-venv)"
[ -z "${DOCKER_HOST:-}" ] || fail "unset DOCKER_HOST; select the daemon with: docker context use <name>"
docker info >/dev/null 2>&1 || fail "docker info failed on context '$(docker context show)'; for rootless Docker run: docker context use rootless"
docker compose version >/dev/null 2>&1 || fail "missing the Docker Compose plugin"
[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" = yes ] \
    || fail "enable lingering once as root, so the runner survives logout: sudo loginctl enable-linger $USER"
# Shells opened with su or sudo -u lack XDG_RUNTIME_DIR, which systemctl --user
# needs to reach the account's (lingering) user manager.
if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "/run/user/$(id -u)" ]; then
    export XDG_RUNTIME_DIR=/run/user/$(id -u)
fi
systemctl --user show-environment >/dev/null 2>&1 \
    || fail "cannot reach the systemd user manager of $USER; check lingering (loginctl show-user $USER) or log in with: sudo machinectl shell $USER@"

# 1. The official runner, verified against the release's SHA-256.
if [ ! -x "$dir/config.sh" ]; then
    release=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest)
    read -r url sha < <(python3 -c '
import json, re, sys
release = json.load(sys.stdin)
version = release["tag_name"].lstrip("v")
asset = next(a for a in release["assets"] if a["name"] == f"actions-runner-linux-x64-{version}.tar.gz")
digest = (asset.get("digest") or "").removeprefix("sha256:")
if not digest:
    found = re.search(r"<!-- BEGIN SHA linux-x64 -->([0-9a-f]{64})<!-- END", release.get("body") or "")
    digest = found.group(1) if found else ""
print(asset["browser_download_url"], digest)' <<<"$release")
    [[ $sha =~ ^[0-9a-f]{64}$ ]] || fail "the runner release lists no SHA-256 for its linux-x64 archive"
    archive=$(mktemp)
    trap 'rm -f "$archive"' EXIT
    curl -fsSL -o "$archive" "$url"
    echo "$sha  $archive" | sha256sum -c --quiet - || fail "runner archive checksum mismatch"
    install -d -m 700 "$dir"
    tar -xzf "$archive" -C "$dir"
fi

# 2. Registration with the environment labels (self-hosted, linux, x64 are added by GitHub).
if [ ! -f "$dir/.runner" ]; then
    token=${RUNNER_TOKEN:-}
    if [ -z "$token" ] && command -v gh >/dev/null; then
        token=$(gh api -X POST "repos/$repository/actions/runners/registration-token" --jq .token 2>/dev/null) || token=
    fi
    [ -n "$token" ] || fail "set RUNNER_TOKEN (Settings → Actions → Runners → New self-hosted runner) or log in with gh"
    (cd "$dir" && ./config.sh --unattended --url "https://github.com/$repository" --token "$token" \
        --name "$name" --labels "$labels" --work _work --replace)
fi

# 3. Job-started guard outside the runner directory, and the runner's environment.
install -D -m 755 "$here/job-started.sh" "$guard"
(cd "$dir" && ./env.sh >/dev/null)  # records PATH and locale for jobs
sed -i '/^ACTIONS_RUNNER_HOOK_JOB_STARTED=/d;/^PEOPLE_GATOR_RUNNER_/d' "$dir/.env"
cat >>"$dir/.env" <<EOF
ACTIONS_RUNNER_HOOK_JOB_STARTED=$guard
PEOPLE_GATOR_RUNNER_ENVIRONMENT=$environments
PEOPLE_GATOR_RUNNER_REPOSITORY=$repository
EOF
cp "$dir/bin/runsvc.sh" "$dir/runsvc.sh"

# 4. The lingering user service.
install -D -m 644 "$here/github-runner@.service" "$units/github-runner@.service"
systemctl --user daemon-reload
systemctl --user enable "github-runner@$name.service" >/dev/null
systemctl --user restart "github-runner@$name.service"
sleep 3
systemctl --user is-active --quiet "github-runner@$name.service" \
    || fail "the service did not start; see: journalctl --user -u github-runner@$name"
echo "Runner $name ($labels) is running: systemctl --user status github-runner@$name"
