#!/bin/sh
set -eu

# The production entrypoint always validates PostgreSQL; it never bootstraps.
export PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__SCHEMA_MODE=validate
export PEOPLE_GATOR_API__DEBUG=false
export PEOPLE_GATOR_API__RELOAD=false

if [ "$#" -eq 0 ]; then
    set -- api
fi

case "$1" in
    api)
        if [ "$#" -ne 1 ]; then
            echo "Configure API options through PEOPLE_GATOR_API__ environment variables" >&2
            exit 2
        fi
        # Lifespan waits for PostgreSQL and validates its schema before serving.
        # exec makes the API process receive container termination signals.
        exec people-gator-api
        ;;
    migrate)
        shift
        exec python -m people_gator_api.cli.database migrate "$@"
        ;;
    seed)
        shift
        exec python -m people_gator_api.cli.seed "$@"
        ;;
    check)
        shift
        exec python -m people_gator_api.cli.database check "$@"
        ;;
    *)
        echo "Usage: container-entrypoint.sh [api|migrate|seed|check [--schema-only]]" >&2
        exit 2
        ;;
esac
