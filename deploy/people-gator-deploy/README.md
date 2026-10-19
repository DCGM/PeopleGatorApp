# people-gator-deploy

Independent standard-library-only deployment utility for Linux, Python 3.11+
(with venv/ensurepip), Git, Docker Engine and Docker Compose v2.32+.
The bootstrap builds a normal wheel in an isolated build environment; initial
installation needs access to the configured Python package index for setuptools.
No API dependencies are installed on the host.

From a reviewed checkout, select its exact commit:

```sh
python3 deploy/install.py --user --revision <40-character-reviewed-sha>
# Custom user prefix, including paths with spaces:
python3 deploy/install.py --user --prefix '/absolute/path/deployment tools' --revision <sha>
# Operator only; routine commands run as the specified unprivileged account:
sudo python3 deploy/install.py --system --revision <sha> --run-as <deployment-user>
```

The installer prints JSON including the versioned executable, descriptor/state
roots, scope and PATH readiness. Add its bin directory to PATH as needed. Keep
that absolute versioned executable for the entire lifetime of a CI job. Existing
versions are retained, including those referenced by bind mounts. Reinstalling
uses the same path and verifies integrity. Publication failures leave the old
entry point available. Older commits can be installed/pinned without moving a
newer interactive default backwards. Configuration and retained data are outside
the version directories. No host service is changed by package installation.

Run package tests from the repository root:

```sh
PYTHONPATH=deploy/people-gator-deploy/src python3 -B -m unittest discover -s deploy/people-gator-deploy/tests -v
uv build --wheel deploy/people-gator-deploy
```
