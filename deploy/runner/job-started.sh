#!/bin/sh
# Job-started guard for self-hosted PeopleGator lifecycle runners.
#
# Runner labels only select a runner: in a public repository any workflow in a
# pull request, branch or tag can request them. This hook runs before every job
# and refuses all but the reviewed lifecycle workflows, so other code never runs
# on the deployment account. Install a copy from reviewed main and set, in each
# runner's .env file:
#
#   ACTIONS_RUNNER_HOOK_JOB_STARTED=/absolute/path/to/job-started.sh
#
# Optional settings (runner .env): PEOPLE_GATOR_RUNNER_REPOSITORY (owner/name),
# PEOPLE_GATOR_RUNNER_REMOTE (Git URL) and PEOPLE_GATOR_RUNNER_CACHE (directory).
set -eu

repository="${PEOPLE_GATOR_RUNNER_REPOSITORY:-DCGM/PeopleGatorApp}"
remote="${PEOPLE_GATOR_RUNNER_REMOTE:-https://github.com/$repository.git}"
cache="${PEOPLE_GATOR_RUNNER_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/people-gator-runner-guard}"
workflow_ref="${GITHUB_WORKFLOW_REF:-}"
workflow_sha="${GITHUB_WORKFLOW_SHA:-}"

refuse() {
    echo "people-gator runner guard: refused '${workflow_ref:-unknown workflow}': $1" >&2
    exit 1
}

[ "${GITHUB_REPOSITORY:-}" = "$repository" ] || refuse "this runner serves only $repository"

workflows="$repository/.github/workflows"
case "$workflow_ref" in
    "$workflows/pr-preview.yml@refs/heads/main" | \
    "$workflows/staging.yml@refs/heads/main" | \
    "$workflows/release.yml@refs/heads/main")
        exit 0
        ;;
    "$workflows/release.yml@refs/tags/v"*)
        ;;
    *)
        refuse "only reviewed main lifecycle workflows may run here"
        ;;
esac

# A tag can point at any commit, including an unreviewed release.yml. Accept it
# only when that workflow commit is already part of main's history.
printf '%s\n' "$workflow_sha" | grep -Eqx '[0-9a-f]{40}' || refuse "missing workflow commit"
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
git -C "$mirror" merge-base --is-ancestor "$workflow_sha" refs/heads/main 2>/dev/null \
    || refuse "tagged commit $workflow_sha is not on main"
