"""Latest S3 selection and private, pinned staging preparation."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from people_gator_deploy import snapshots, staging
from people_gator_deploy.core import DeployError
from test_staging import FakeStaging

STORAGE = {"endpoint_url": "https://backup.invalid", "region": "us-east-1", "bucket": "backup-fixture",
           "prefix": "production/db-backups/", "access_key_id": "fixture-reader", "secret_access_key": "fixture-secret"}
PREFIX = STORAGE["prefix"]
OLD = PREFIX + "peoplegator-prod-2026-10-23.dump"
NEW = PREFIX + "peoplegator-prod-2026-10-25.dump"
RAW = b"PGDMP newest synthetic archive"


class S3:
    def __init__(self):
        self.pages = [[OLD], [NEW]]
        self.objects = {}
        self.gets = []
        self.on_get = None
        self.put(OLD, b"PGDMP old")
        self.put(NEW, RAW)

    def put(self, key, data):
        self.objects[key] = {"ContentLength": len(data), "ETag": '"' + hashlib.md5(data).hexdigest() + '"',
            "VersionId": "version-1", "Metadata": {"Sha256": hashlib.sha256(data).hexdigest(),
            "Application-Revision": "a" * 40}, "data": data}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, **kwargs):
        assert kwargs == {"Bucket": STORAGE["bucket"], "Prefix": PREFIX}
        for keys in self.pages:
            yield {"Contents": [{"Key": key} for key in keys]}
        yield {}  # empty final page

    def head_object(self, Bucket, Key):
        return {k: copy.deepcopy(v) for k, v in self.objects[Key].items() if k != "data"}

    def get_object(self, **kwargs):
        self.gets.append(kwargs)
        response = self.head_object(kwargs["Bucket"], kwargs["Key"])
        self.body = io.BytesIO(self.objects[kwargs["Key"]]["data"])
        response["Body"] = self.body
        if self.on_get:
            self.on_get(self, response)
        return response


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.s3 = S3()

    def download(self):
        return snapshots.download(self.s3, STORAGE, NEW, self.root / "snapshot.dump")

    def test_all_pages_calendar_order_and_strict_names(self):
        self.s3.pages = [[NEW, PREFIX + "peoplegator-prod-2099-02-30.dump"], [OLD,
            PREFIX + "peoplegator-prod-2099-01-01.dump.tmp", PREFIX + "tmp/peoplegator-prod-2099-01-01.dump",
            "elsewhere/peoplegator-prod-2099-01-01.dump", PREFIX + "peoplegator-prod-2026-1-01.dump",
            PREFIX + "notes.txt"]]
        self.assertEqual(snapshots.select_backup(self.s3, STORAGE), NEW)
        self.s3.pages = [[], [PREFIX + "unrelated"]]
        with self.assertRaisesRegex(DeployError, "No completed dated backup"):
            snapshots.select_backup(self.s3, STORAGE)

    def test_private_download_pins_version_etag_size_and_metadata(self):
        report = self.download()
        self.assertEqual((self.root / "snapshot.dump").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "snapshot.dump").read_bytes(), RAW)
        self.assertEqual(report["application_revision"], "a" * 40)
        self.assertEqual(report["size"], len(RAW))
        self.assertEqual(self.s3.gets, [{"Bucket": STORAGE["bucket"], "Key": NEW,
            "IfMatch": report["etag"], "VersionId": "version-1"}])
        self.assertTrue(self.s3.body.closed)

    def test_unversioned_download_still_pins_etag(self):
        self.s3.objects[NEW].pop("VersionId")
        self.assertIsNone(self.download()["version_id"])
        self.assertNotIn("VersionId", self.s3.gets[0])

    def test_missing_invalid_or_conflicting_metadata_never_downloads(self):
        for metadata in ({}, {"sha256": "bad", "application-revision": "a" * 40},
            {"sha256": "a" * 64, "application-revision": "main"},
            {"sha256": "a" * 64, "Sha256": "b" * 64, "application-revision": "a" * 40}):
            self.s3.objects[NEW]["Metadata"] = metadata
            with self.subTest(metadata=metadata), self.assertRaises(DeployError):
                self.download()
            self.assertEqual(self.s3.gets, [])

    def test_missing_identity_or_invalid_size_fails_before_download(self):
        for field, value in (("ETag", ""), ("ETag", None), ("ContentLength", -1),
                             ("ContentLength", True), ("ContentLength", "123")):
            self.s3 = S3()
            self.s3.objects[NEW][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(DeployError):
                self.download()
            self.assertEqual(self.s3.gets, [])

    def test_checksum_truncation_format_and_identity_fail_closed(self):
        def corrupt(client, response):
            response["Body"] = io.BytesIO(b"PGDMP broken same size".ljust(len(RAW), b"!"))
        def truncate(client, response):
            response["Body"] = io.BytesIO(RAW[:-1])
        def excess(client, response):
            response["Body"] = io.BytesIO(RAW + b"!")
        def replace(client, response):
            client.objects[NEW]["VersionId"] = "version-2"
        def metadata(client, response):
            client.objects[NEW]["Metadata"]["Sha256"] = "0" * 64
        def response_identity(client, response):
            response["ETag"] = "changed"
        for mutation in (corrupt, truncate, excess, replace, metadata, response_identity):
            self.s3 = S3()
            self.s3.on_get = mutation
            with self.subTest(mutation=mutation.__name__), self.assertRaises(DeployError):
                self.download()
            (self.root / "snapshot.dump").unlink(missing_ok=True)
        self.s3 = S3()
        self.s3.put(NEW, b"not a custom archive")
        with self.assertRaisesRegex(DeployError, "custom archive"):
            self.download()

    def controller(self):
        controller = FakeStaging(self.root)
        source = self.root / "source.json"
        source.write_text(json.dumps(STORAGE))
        source.chmod(0o600)
        del controller.config["snapshot"]
        controller.config["snapshot_source_file"] = str(source)
        controller.prepare = staging.Staging.prepare.__get__(controller)
        controller.provision = lambda values: controller.events.append("provision")
        def private(args, **kwargs):
            raw = kwargs["input_file"].read()
            self.assertEqual(raw, self.s3.objects[self.s3.gets[-1]["Key"]]["data"])
            controller.events.append("inspect" if args[-1] == "--list" else "restore")
        controller.private_command = private
        return controller

    def test_successive_operations_discover_new_upload_without_descriptor_edit(self):
        controller = self.controller()
        self.s3.pages = [[OLD]]
        with patch.object(snapshots, "client_for", return_value=self.s3):
            controller.deploy(refresh=True)
            first = json.loads((controller.staging_root / "state.json").read_text())
            self.s3.pages.append([NEW])
            controller.deploy(refresh=True)
            second = json.loads((controller.staging_root / "state.json").read_text())
            self.assertEqual(first["provenance"]["key"], OLD)
            self.assertEqual(second["provenance"]["key"], NEW)
            self.assertEqual(second["provenance"]["sha256"], hashlib.sha256(RAW).hexdigest())
            self.assertEqual(second["provenance"]["source_application_revision"], "a" * 40)
            self.assertNotIn("path", second["provenance"])
            self.assertNotIn("fixture-secret", json.dumps(second))
            self.assertFalse(list(controller.staging_root.glob("snapshot-*")))
            for path in controller.staging_root.glob("generation-*/provenance.json"):
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            # Normal update needs neither an archive nor readable backup credentials.
            Path(controller.config["snapshot_source_file"]).unlink()
            with patch.object(snapshots, "client_for", side_effect=AssertionError("Unexpected S3 access")):
                controller.deploy()

    def test_broken_latest_or_access_failure_preserves_active_state_and_cleans_archive(self):
        controller = self.controller()
        with patch.object(snapshots, "client_for", return_value=self.s3):
            controller.deploy(refresh=True)
            active = (controller.staging_root / "state.json").read_bytes()
            environment = (controller.staging_root / "compose.env").read_bytes()
            for failure in ("access", "metadata", "checksum", "format", "archive-list"):
                self.s3 = S3()
                controller.events.clear()
                if failure == "access":
                    self.s3.get_paginator = lambda name: (_ for _ in ()).throw(RuntimeError("private-sentinel"))
                elif failure == "metadata":
                    self.s3.objects[NEW]["Metadata"] = {}
                elif failure == "checksum":
                    self.s3.objects[NEW]["Metadata"]["Sha256"] = "0" * 64
                elif failure == "format":
                    self.s3.put(NEW, b"not an archive")
                else:
                    self.s3.put(NEW, b"PGDMP corrupt body")
                    controller.private_command = lambda *args, **kwargs: (_ for _ in ()).throw(DeployError("Archive listing failed"))
                with patch.object(snapshots, "client_for", return_value=self.s3):
                    with self.subTest(failure=failure), self.assertRaises(DeployError) as raised:
                        controller.deploy(refresh=True)
                self.assertNotIn("private-sentinel", str(raised.exception))
                self.assertEqual((controller.staging_root / "state.json").read_bytes(), active)
                self.assertEqual((controller.staging_root / "compose.env").read_bytes(), environment)
                self.assertNotIn("provision", controller.events)
                self.assertFalse(list(controller.staging_root.glob("snapshot-*")))
                self.assertTrue(all(request["Key"] == NEW for request in self.s3.gets))

    def test_replacement_during_restore_blocks_activation_but_newer_upload_does_not(self):
        controller = self.controller()
        with patch.object(snapshots, "client_for", return_value=self.s3):
            controller.deploy(refresh=True)
            active = (controller.staging_root / "state.json").read_bytes()
            private = controller.private_command
            def replace(args, **kwargs):
                private(args, **kwargs)
                if "--single-transaction" in args:
                    self.s3.objects[NEW]["VersionId"] = "replacement"
            controller.private_command = replace
            controller.events.clear()
            with self.assertRaisesRegex(DeployError, "changed during restore"):
                controller.deploy(refresh=True)
            self.assertEqual((controller.staging_root / "state.json").read_bytes(), active)
            self.assertFalse(any(event.startswith("up ") for event in controller.events))
            def publish(args, **kwargs):
                private(args, **kwargs)
                self.s3.pages.append([PREFIX + "peoplegator-prod-2026-10-27.dump"])
            controller.private_command = publish
            controller.deploy(refresh=True)
            self.assertEqual(json.loads((controller.staging_root / "state.json").read_text())["provenance"]["key"], NEW)

    def test_source_file_requires_private_explicit_configuration(self):
        path = self.root / "source.json"
        path.write_text(json.dumps(STORAGE))
        path.chmod(0o644)
        with self.assertRaisesRegex(DeployError, "private"):
            snapshots.read_source(path)
        path.chmod(0o600)
        self.assertEqual(snapshots.read_source(path), STORAGE)
        for changes in ({"endpoint_url": "http://unsafe.invalid"}, {"prefix": "../bad/"},
                        {"secret_access_key": ""}, {"database": {}}):
            path.write_text(json.dumps({**STORAGE, **changes}))
            with self.subTest(changes=changes), self.assertRaises(DeployError):
                snapshots.read_source(path)


if __name__ == "__main__":
    unittest.main()
