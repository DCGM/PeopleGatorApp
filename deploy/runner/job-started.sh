#!/bin/sh
# Job-started guard for self-hosted PeopleGator deployment runners.
#
# Runner labels only select a runner: in a public repository any workflow in a
# pull request, branch or tag can request them. This hook runs before every job
# and admits only this repository's own events for the runner's environment:
#
#   preview  same-repository pull requests (refs/pull/<n>/merge) and main (pruning)
#   staging  main
#   release  v* tags whose commit is already on main
#
# Pull requests from forks are refused whatever the workflow says. Install a copy
# from reviewed main outside the runner directory and set, in each runner's .env,
# the environments whose labels the runner carries:
#
#   ACTIONS_RUNNER_HOOK_JOB_STARTED=/absolute/path/to/job-started.sh
#   PEOPLE_GATOR_RUNNER_ENVIRONMENT=preview,staging   # any of preview, staging, release
#
# Optional settings (runner .env): PEOPLE_GATOR_RUNNER_REPOSITORY (owner/name),
# PEOPLE_GATOR_RUNNER_REMOTE (Git URL) and PEOPLE_GATOR_RUNNER_CACHE (directory).
set -eu

repository="${PEOPLE_GATOR_RUNNER_REPOSITORY:-DCGM/PeopleGatorApp}"
remote="${PEOPLE_GATOR_RUNNER_REMOTE:-https://github.com/$repository.git}"
cache="${PEOPLE_GATOR_RUNNER_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/people-gator-runner-guard}"
environments="$(printf '%s' "${PEOPLE_GATOR_RUNNER_ENVIRONMENT:-}" | tr ',' ' ')"
event="${GITHUB_EVENT_NAME:-}"
ref="${GITHUB_REF:-}"
sha="${GITHUB_SHA:-}"

refuse() {
    echo "people-gator runner guard: refused ${event:-unknown event} on ${ref:-unknown ref}: $1" >&2
    exit 1
}

[ "${GITHUB_REPOSITORY:-}" = "$repository" ] || refuse "this runner serves only $repository"
[ -n "$environments" ] || refuse "set PEOPLE_GATOR_RUNNER_ENVIRONMENT (preview, staging and/or release) in the runner .env"
for environment in $environments; do
    case "$environment" in
        preview | staging | release) ;;
        *) refuse "unknown environment '$environment' in PEOPLE_GATOR_RUNNER_ENVIRONMENT" ;;
    esac
done

case "$event" in
    pull_request | pull_request_target)
        # The workflow file comes from the pull request itself, so its own
        # conditions cannot be trusted: read the head repository from the event.
        head_repository="$(python3 -c 'import json, sys
with open(sys.argv[1]) as stream:
    head = json.load(stream)["pull_request"]["head"]
print((head.get("repo") or {}).get("full_name", ""))' "${GITHUB_EVENT_PATH:?}" 2>/dev/null)" \
            || refuse "cannot read the pull request event"
        [ "$head_repository" = "$repository" ] || refuse "pull requests from other repositories never run here"
        ;;
esac

tagged_release=0
for environment in $environments; do
    case "$environment:$event:$ref" in
        preview:pull_request:refs/pull/*/merge) exit 0 ;;
        preview:push:refs/heads/main | preview:schedule:refs/heads/main | preview:workflow_dispatch:refs/heads/main) exit 0 ;;
        staging:push:refs/heads/main | staging:workflow_dispatch:refs/heads/main) exit 0 ;;
        release:push:refs/tags/v* | release:workflow_dispatch:refs/tags/v*) tagged_release=1 ;;
    esac
done
[ "$tagged_release" = 1 ] || refuse "this runner ($environments) does not serve this event"

# A tag can point at any commit, including an unreviewed workflow. Accept it
# only when the tagged commit is already part of main's history.
printf '%s\n' "$sha" | grep -Eqx '[0-9a-f]{40}' || refuse "missing tagged commit"
mkdir -p "$cache"
exec 9>"$cache/lock"
flock 9
mirror="$cache/repository.git"
if [ ! -d "$mirror" ]; then
    git clone --quiet --bare --filter=blob:none "$remote" "$mirror.tmp" 2>/dev/null \
        || { rm -rf "$mirror.tmp"; refuse "cannot read $remote"; }
    mv "$mirror.tmp" "$mirror"
fi
git -C "$mirror" fetch --quiet --no-tags "$remote" "+refs/heads/main:refs/heads/main" 2>/dev/null \
    || refuse "cannot fetch main from $remote"
git -C "$mirror" merge-base --is-ancestor "$sha" refs/heads/main 2>/dev/null \
    || refuse "tagged commit $sha is not on main"
