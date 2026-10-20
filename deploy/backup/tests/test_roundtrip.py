"""Real PostgreSQL/S3 operator roundtrip; only disposable synthetic resources."""
import hashlib
import copy
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "people-gator-deploy" / "tests"))
from s3_fixture import S3Fixture


@unittest.skipUnless(os.environ.get("BACKUP_TEST_IMAGE"), "Set BACKUP_TEST_IMAGE to a built backup worker")
class RoundtripTests(unittest.TestCase):
    @classmethod
    def docker(cls, *args, data=None, check=True):
        result = subprocess.run(["docker", *args], input=data, capture_output=True, timeout=180)
        if check and result.returncode:
            raise RuntimeError("Disposable Docker fixture command failed: " + result.stderr.decode())
        return result

    @classmethod
    def setUpClass(cls):
        cls.network = "backup-fixture-" + secrets.token_hex(6)
        cls.database = cls.network + "-db"
        cls.docker("network", "create", cls.network)
        cls.addClassCleanup(lambda: cls.docker("network", "rm", cls.network, check=False))
        cls.docker("run", "-d", "--rm", "--name", cls.database, "--network", cls.network,
                   "--network-alias", "backup-db", "--log-driver", "none", "--tmpfs", "/var/lib/postgresql/data",
                   "-e", "POSTGRES_USER=fixture", "-e", "POSTGRES_PASSWORD=fixture", "pgvector/pgvector:pg16")
        cls.addClassCleanup(lambda: cls.docker("rm", "-f", cls.database, check=False))
        cls.docker("exec", cls.database, "sh", "-c", "until pg_isready -h 127.0.0.1 -U fixture; do sleep 0.2; done")
        cls.certificates = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.certificates.cleanup)
        cls.ca = Path(cls.certificates.name) / "server.crt"
        key = Path(cls.certificates.name) / "server.key"
        subprocess.run(["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048", "-days", "1",
                        "-keyout", str(key), "-out", str(cls.ca), "-subj", "/CN=backup-db",
                        "-addext", "subjectAltName=DNS:backup-db"], capture_output=True, check=True)
        for path in (cls.ca, key):
            cls.docker("exec", "--user", "postgres", "-i", cls.database, "sh", "-c",
                       "umask 077; cat > /var/lib/postgresql/data/" + path.name, data=path.read_bytes())
        cls.sql("ALTER SYSTEM SET ssl = 'on';")
        cls.sql("SELECT pg_reload_conf();")
        cls.sql("CREATE DATABASE source; CREATE DATABASE recovered;")
        cls.sql("CREATE ROLE recovery_owner LOGIN PASSWORD 'target-secret'; CREATE ROLE outsider LOGIN PASSWORD 'outsider';")
        cls.sql("""CREATE EXTENSION vector;
CREATE TABLE alembic_version(version_num text PRIMARY KEY);
INSERT INTO alembic_version VALUES ('fixture_revision');
CREATE TABLE models(id text PRIMARY KEY, dimension int NOT NULL);
INSERT INTO models VALUES ('synthetic', 3);
CREATE TABLE entities(id int PRIMARY KEY, name text);
INSERT INTO entities VALUES (1, 'Retain exactly: synthetic fixture');
CREATE TABLE faces(id int PRIMARY KEY, entity_id int REFERENCES entities(id), model_id text REFERENCES models(id), embedding vector(3));
INSERT INTO faces VALUES (1, 1, 'synthetic', '[0.1,0.2,0.3]');
CREATE INDEX fixture_vector ON faces USING hnsw (embedding vector_cosine_ops);
""", "source")
        cls.provider = S3Fixture(cls.network).__enter__()
        cls.addClassCleanup(lambda: cls.provider.__exit__(None, None, None))
        cls.storage = {**cls.provider.source_config}
        cls.storage["bucket"] = cls.storage.pop("bucket_name")
        cls.storage["prefix"] = "production/db-backups/"
        cls.config = {"database": {"host": "backup-db", "port": 5432, "user": "fixture", "password": "fixture",
                                    "database": "source", "sslmode": "disable"},
                      "storage": cls.storage, "application_revision": "a" * 40}

    @classmethod
    def sql(cls, query, database="postgres"):
        return cls.docker("exec", "-i", cls.database, "psql", "-XqAt", "-U", "fixture", "-d", database,
                          "-v", "ON_ERROR_STOP=1", data=query.encode()).stdout.decode().strip()

    def worker(self, *args, config=None, entrypoint=None):
        command = ["run", "--rm", "-i", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                   "--network", self.network, "--log-driver", "none", "--tmpfs", "/tmp:size=256m,mode=1777",
                   "--mount", f"type=bind,src={self.provider.ca},dst=/test-ca.crt,readonly",
                   "--mount", f"type=bind,src={self.ca},dst=/test-db-ca.crt,readonly",
                   "-e", "AWS_CA_BUNDLE=/test-ca.crt"]
        if entrypoint:
            command += ["--entrypoint", entrypoint]
        return self.docker(*command, os.environ["BACKUP_TEST_IMAGE"], *args,
                           data=json.dumps(config or self.config).encode(), check=False)

    def test_publish_real_custom_archive_and_full_restore_preserve_data_vectors_and_revision(self):
        result = self.worker("publish", "--config", "-")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        objects = self.provider.source.list_objects_v2(Bucket=self.storage["bucket"], Prefix=self.storage["prefix"])["Contents"]
        self.assertEqual(len(objects), 1)
        key = objects[0]["Key"]
        response = self.provider.source.get_object(Bucket=self.storage["bucket"], Key=key)
        raw = response["Body"].read()
        response["Body"].close()
        self.assertEqual(raw[:5], b"PGDMP")
        self.assertEqual(response["Metadata"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(response["Metadata"]["application-revision"], "a" * 40)
        self.docker("exec", "-i", self.database, "pg_restore", "--single-transaction", "--exit-on-error",
                    "--no-owner", "--no-privileges", "-U", "fixture", "-d", "recovered", data=raw)
        for query in ("SELECT version_num FROM alembic_version", "SELECT * FROM entities",
                      "SELECT * FROM models", "SELECT id, entity_id, model_id, embedding::text FROM faces"):
            self.assertEqual(self.sql(query, "source"), self.sql(query, "recovered"))
        before = response["ETag"]
        duplicate = self.worker("publish", "--config", "-")
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn(b"already exists", duplicate.stderr)
        self.assertEqual(self.provider.source.head_object(Bucket=self.storage["bucket"], Key=key)["ETag"], before)
        self.assertEqual(self.sql("SELECT count(*) FROM faces", "source"), "1")

    def test_real_multipart_publication_refuses_concurrent_replacement(self):
        program = """
import json, tempfile, secrets, sys
from pathlib import Path
from people_gator_api.backup.core import client_for, upload_archive, digest_file, BackupExists
storage=json.load(sys.stdin)['storage']
client=client_for(storage)
with tempfile.TemporaryDirectory() as work:
    path=Path(work)/'archive'
    path.write_bytes(secrets.token_bytes(11*1024*1024))
    metadata={'sha256':digest_file(path),'application-revision':'a'*40}
    upload_archive(client,storage,'multipart-fixture',path,metadata,part_size=5*1024*1024)
    try:
        upload_archive(client,storage,'multipart-fixture',path,metadata,part_size=5*1024*1024)
    except BackupExists:
        pass
    else:
        raise AssertionError('existing multipart object was replaced')
"""
        result = self.worker("-c", program, entrypoint="python")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        pending = self.provider.source.list_multipart_uploads(Bucket=self.storage["bucket"])
        self.assertFalse(pending.get("Uploads"))

    def test_restore_loader_preserves_original_data_and_refuses_existing_or_bad_targets(self):
        publisher = copy.deepcopy(self.config)
        publisher["storage"]["prefix"] = "restore-fixture/"
        published = self.worker("publish", "--config", "-", config=publisher)
        self.assertEqual(published.returncode, 0, published.stderr.decode())
        config = {"storage": publisher["storage"], "database": {**publisher["database"], "database": "postgres"},
                  "target": {"database": "recovered_loader", "user": "recovery_owner", "password": "target-secret"}}
        command = "mkdir -m 700 /tmp/report && python -m people_gator_api.backup restore --config - --report /tmp/report/provenance.json"
        result = self.worker("-c", command, config=config, entrypoint="sh")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        for query in ("SELECT version_num FROM alembic_version", "SELECT * FROM entities",
                      "SELECT * FROM models", "SELECT id, entity_id, model_id, embedding::text FROM faces"):
            self.assertEqual(self.sql(query, "source"), self.sql(query, "recovered_loader"))
        self.assertEqual(self.sql("SELECT has_database_privilege('outsider','recovered_loader','CONNECT')"), "f")
        duplicate = self.worker("-c", command, config=config, entrypoint="sh")
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn(b"existing target", duplicate.stderr)
        config["target"].update(database="failed_loader", password="wrong-password")
        failure = self.worker("-c", command, config=config, entrypoint="sh")
        self.assertNotEqual(failure.returncode, 0)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_database WHERE datname='failed_loader'"), "0")
        self.assertEqual(self.sql("SELECT count(*) FROM faces", "recovered_loader"), "1")
        # A validly named newer corrupt object must fail, without older fallback.
        bad = b"PGDMP corrupt latest"
        self.provider.source.put_object(Bucket=self.storage["bucket"], Key="restore-fixture/peoplegator-prod-2099-10-17.dump",
            Body=bad, Metadata={"sha256": hashlib.sha256(bad).hexdigest(), "application-revision": "a" * 40})
        config["target"].update(database="corrupt_loader", password="target-secret")
        corrupt = self.worker("-c", command, config=config, entrypoint="sh")
        self.assertNotEqual(corrupt.returncode, 0)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_database WHERE datname='corrupt_loader'"), "0")

    def test_verified_postgres_tls_accepts_explicit_ca_and_rejects_untrusted_or_wrong_hostname(self):
        for scenario in ("trusted", "untrusted", "wrong-hostname"):
            config = copy.deepcopy(self.config)
            config["storage"]["prefix"] = scenario + "/"
            config["database"].update(sslmode="verify-full", sslrootcert="/test-db-ca.crt")
            if scenario == "untrusted":
                config["database"]["sslrootcert"] = "system"
            if scenario == "wrong-hostname":
                config["database"]["host"] = self.database
            result = self.worker("publish", "--config", "-", config=config)
            if scenario == "trusted":
                self.assertEqual(result.returncode, 0, result.stderr.decode())
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"PostgreSQL tool failed", result.stderr)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertFalse(self.provider.source.list_objects_v2(Bucket=self.storage["bucket"],
                                 Prefix=config["storage"]["prefix"]).get("Contents"))

    def test_scheduled_compose_agent_uses_private_config_and_shared_lock(self):
        root = Path(__file__).resolve().parents[3]
        project = "backup-agent-fixture-" + secrets.token_hex(6)
        with tempfile.TemporaryDirectory() as work:
            private = Path(work)
            config = copy.deepcopy(self.config)
            config["storage"]["prefix"] = "schedule-fixture/"
            source = private / "publisher.json"
            source.write_text(json.dumps(config))
            source.chmod(0o600)
            # Match UID0's private bind ownership in both rootful/rootless Docker;
            # this changes only this synthetic fixture file, never operator inputs.
            self.docker("run", "--rm", "--user", "0", "--entrypoint", "chown",
                        "--mount", f"type=bind,src={source},dst=/publisher.json",
                        os.environ["BACKUP_TEST_IMAGE"], "0:0", "/publisher.json")
            override = private / "override.json"
            override.write_text(json.dumps({"services": {"backup-agent": {"environment": {"AWS_CA_BUNDLE": "/test-ca.crt"},
                "volumes": [{"type": "bind", "source": str(self.provider.ca), "target": "/test-ca.crt", "read_only": True}]}}}))
            environment = {**os.environ, "BACKUP_WORKER_IMAGE": os.environ["BACKUP_TEST_IMAGE"],
                           "BACKUP_DATABASE_NETWORK": self.network, "BACKUP_PUBLISHER_CONFIG": str(source),
                           "BACKUP_AT_UTC": "00:00", "BACKUP_RETRY_SECONDS": "1", "BACKUP_RUN_UID": "0", "BACKUP_RUN_GID": "0"}
            command = ["docker", "compose", "--project-name", project, "--project-directory", str(root),
                       "--env-file", "/dev/null", "-f", str(root / "deploy/backup/compose.agent.yaml"),
                       "-f", str(override), "--profile", "backups"]
            def compose(*args, check=True):
                return subprocess.run([*command, *args], env=environment, capture_output=True, check=check, timeout=120)
            def wait_log(message):
                for _ in range(100):
                    logs = compose("logs", "--no-color", "backup-agent").stdout
                    if message in logs:
                        self.assertNotIn(config["storage"]["secret_access_key"].encode(), logs)
                        return
                    time.sleep(0.2)
                self.fail("Disposable scheduled agent did not reach expected safe status")
            try:
                compose("up", "--no-build", "-d", "--no-deps", "backup-agent")
                wait_log(b"Backup published and verified")
                objects = self.provider.source.list_objects_v2(Bucket=self.storage["bucket"], Prefix="schedule-fixture/")["Contents"]
                self.assertEqual(len(objects), 1)
                before = objects[0]["ETag"]
                competing = compose("run", "--rm", "--no-deps", "backup-agent", "publish", "--config", "/run/backup-publisher.json",
                                    "--lock-file", "/state/agent/controller.lock", check=False)
                self.assertNotEqual(competing.returncode, 0)
                self.assertIn(b"Another backup operation", competing.stderr)
                compose("up", "--no-build", "-d", "--no-deps", "--force-recreate", "backup-agent")
                wait_log(b"Existing dated backup metadata verified")
                self.assertEqual(self.provider.source.head_object(Bucket=self.storage["bucket"], Key=objects[0]["Key"])["ETag"], before)
            finally:
                compose("down", "--volumes", "--remove-orphans", check=False)


if __name__ == "__main__":
    unittest.main()
