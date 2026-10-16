"""Real PostgreSQL/S3 operator roundtrip; only disposable synthetic resources."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "preview" / "tests"))
from s3_fixture import S3Fixture


@unittest.skipUnless(os.environ.get("BACKUP_TEST_IMAGE"), "Set BACKUP_TEST_IMAGE to a built backup worker")
class RoundtripTests(unittest.TestCase):
    @classmethod
    def docker(cls, *args, data=None, check=True):
        return subprocess.run(["docker", *args], input=data, capture_output=True, check=check, timeout=180)

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
        cls.docker("exec", cls.database, "sh", "-c", "until pg_isready -U fixture; do sleep 0.2; done")
        cls.sql("CREATE DATABASE source; CREATE DATABASE recovered;")
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


if __name__ == "__main__":
    unittest.main()
