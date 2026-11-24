import base64
import importlib.util
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from PIL import Image


class PromptVaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_directory = Path.cwd()
        cls.previous_database_path = os.environ.get("DATABASE_PATH")
        cls.workspace = tempfile.TemporaryDirectory()
        os.environ["DATABASE_PATH"] = str(Path(cls.workspace.name) / "prompts.db")
        os.chdir(cls.workspace.name)
        spec = importlib.util.spec_from_file_location(
            "promptvault_app", Path(__file__).with_name("app.py")
        )
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        workspace_static = Path(cls.workspace.name) / "static"
        workspace_uploads = Path(cls.workspace.name) / "data" / "uploads"
        workspace_static.mkdir(parents=True, exist_ok=True)
        workspace_uploads.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            Path(__file__).resolve().parent / "static" / "styles.css",
            workspace_static / "styles.css",
        )
        cls.module.app.static_folder = str(workspace_static)
        cls.module.app.config.update(
            TESTING=True,
            SECRET_KEY="test-only-not-a-deployment-secret",
            UPLOAD_FOLDER=str(workspace_uploads),
        )

    @classmethod
    def tearDownClass(cls):
        cls.module.db._disconnect()
        cls.module.db._engine.dispose()
        if cls.previous_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = cls.previous_database_path
        os.chdir(cls.previous_directory)
        cls.workspace.cleanup()

    def setUp(self):
        self.client = self.module.app.test_client()
        self.module.db.execute("DELETE FROM images")
        upload_root = Path(self.module.app.config["UPLOAD_FOLDER"])
        for child in upload_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    def csrf_token(self):
        page = self.client.get("/add").get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)

    def upload(
        self,
        filename="example.png",
        contents=None,
        category="Examples",
        prompt_text="A test image",
    ):
        if contents is None:
            stream = io.BytesIO()
            Image.new("RGB", (4, 4), "white").save(stream, format="PNG")
            contents = stream.getvalue()
        return self.client.post(
            "/add",
            data={
                "csrf_token": self.csrf_token(),
                "image_file": (io.BytesIO(contents), filename),
                "prompt_text": prompt_text,
                "category": category,
            },
            content_type="multipart/form-data",
        )

    def test_gallery_and_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_gallery_pagination_and_rel_links(self):
        for idx in range(1, 27):
            self.module.db.execute(
                "INSERT INTO images (image_path, prompt_text, category, timestamp) "
                "VALUES (?, ?, ?, ?)",
                f"Paginated/img_{idx:02d}.png",
                f"Paginated prompt {idx:02d}",
                "Paginated",
                f"2026-01-01 00:00:{idx:02d}",
            )

        page1 = self.client.get("/")
        self.assertEqual(page1.status_code, 200)
        html1 = page1.get_data(as_text=True)
        self.assertEqual(html1.count('<article class="card">'), 24)
        ds1_match = re.search(
            r'<script type="application/json" id="promptDataset">([^<]+)</script>', html1
        )
        self.assertIsNotNone(ds1_match)
        ds1 = json.loads(ds1_match.group(1))
        self.assertEqual(len(ds1), 24)
        self.assertEqual(ds1[0]["promptText"], "Paginated prompt 26")
        self.assertIn('<link rel="next" href="http://localhost/?page=2">', html1)
        self.assertNotIn('<link rel="prev"', html1)
        self.assertIn('<link rel="canonical" href="http://localhost/">', html1)
        self.assertIn('<meta name="robots" content="index, follow">', html1)

        page2 = self.client.get("/?page=2")
        self.assertEqual(page2.status_code, 200)
        html2 = page2.get_data(as_text=True)
        self.assertEqual(html2.count('<article class="card">'), 2)
        ds2 = json.loads(
            re.search(
                r'<script type="application/json" id="promptDataset">([^<]+)</script>', html2
            ).group(1)
        )
        self.assertEqual(len(ds2), 2)
        self.assertEqual(
            [item["promptText"] for item in ds2], ["Paginated prompt 02", "Paginated prompt 01"]
        )
        self.assertIn('<link rel="prev" href="http://localhost/">', html2)
        self.assertNotIn('<link rel="next"', html2)
        self.assertIn('<link rel="canonical" href="http://localhost/?page=2">', html2)
        self.assertIn('<meta name="robots" content="index, follow">', html2)

        overflow = self.client.get("/?page=99")
        self.assertEqual(overflow.status_code, 302)
        self.assertEqual(overflow.headers["Location"], "/?page=2")

        filtered_overflow = self.client.get("/?category=Paginated&sort=oldest&page=99")
        self.assertEqual(filtered_overflow.status_code, 302)
        self.assertEqual(
            filtered_overflow.headers["Location"], "/?category=Paginated&sort=oldest&page=2"
        )

        invalid_page = self.client.get("/?page=abc").get_data(as_text=True)
        self.assertEqual(invalid_page.count('<article class="card">'), 24)

        filtered_p2 = self.client.get("/?category=Paginated&sort=oldest&page=2").get_data(
            as_text=True
        )
        self.assertEqual(filtered_p2.count('<article class="card">'), 2)
        self.assertIn('<meta name="robots" content="noindex, follow">', filtered_p2)
        self.assertIn('<link rel="canonical" href="http://localhost/">', filtered_p2)
        self.assertIn(
            '<link rel="prev" href="http://localhost/?category=Paginated&amp;sort=oldest">',
            filtered_p2,
        )

        self.module.db.execute("DELETE FROM images")
        empty_overflow = self.client.get("/?page=5")
        self.assertEqual(empty_overflow.status_code, 302)
        self.assertEqual(empty_overflow.headers["Location"], "/")

    def test_missing_csrf_is_rejected(self):
        self.assertEqual(self.client.post("/add", data={}).status_code, 400)
        self.assertEqual(self.client.post("/delete/1").status_code, 400)
        self.assertEqual(self.client.post("/favorite/1").status_code, 400)
        self.assertEqual(self.client.post("/edit/1").status_code, 400)

    def test_valid_image_upload_and_download(self):
        self.assertEqual(self.upload().status_code, 302)
        row = self.module.db.execute("SELECT * FROM images")[0]
        self.assertEqual(row["image_path"], "Examples/example.png")
        with self.module.app.test_request_context():
            public_url = self.module.image_url(row)
        with self.client.get(public_url) as static_res:
            self.assertEqual(static_res.status_code, 200)
        with self.client.get("/download/" + row["image_path"]) as response:
            self.assertEqual(response.status_code, 200)

    def test_legacy_image_path_migration(self):
        legacy_rows = [
            ("/static/uploads/Art%20Style/old.png", "Art Style/old.png"),
            ("/pv/static/uploads/%D8%AA%D8%B5%D9%85%D9%8A%D9%85/pic.png", "تصميم/pic.png"),
            ("static/uploads/Simple/a.png", "Simple/a.png"),
        ]
        for raw_path, _ in legacy_rows:
            self.module.db.execute(
                "INSERT INTO images (image_path, prompt_text, category) VALUES (?, ?, ?)",
                raw_path,
                "Legacy prompt",
                "Legacy",
            )
        self.module.migrate_legacy_image_paths()
        migrated = [
            row["image_path"]
            for row in self.module.db.execute("SELECT image_path FROM images ORDER BY id")
        ]
        self.assertEqual(migrated, [expected for _, expected in legacy_rows])

    def test_legacy_static_uploads_migrated_on_startup(self):
        repo_dir = Path(__file__).resolve().parent
        prev_db_env = os.environ.get("DATABASE_PATH")
        prev_upload_env = os.environ.get("UPLOAD_FOLDER")
        mod = None
        mod_name = "promptvault_legacy_file_test"

        with tempfile.TemporaryDirectory() as tmp:
            app_root = Path(tmp) / "app_root"
            app_root.mkdir()
            shutil.copy2(repo_dir / "app.py", app_root / "app.py")
            shutil.copytree(repo_dir / "templates", app_root / "templates")
            shutil.copytree(repo_dir / "static", app_root / "static")

            stream = io.BytesIO()
            Image.new("RGB", (6, 6), "teal").save(stream, format="PNG")
            legacy_png = stream.getvalue()

            legacy_file = app_root / "static" / "uploads" / "Legacy" / "old.png"
            legacy_file.parent.mkdir(parents=True, exist_ok=True)
            legacy_file.write_bytes(legacy_png)

            empty_legacy_dir = app_root / "static" / "uploads" / "EmptyOld"
            empty_legacy_dir.mkdir(parents=True, exist_ok=True)

            # Seed an existing target file to verify migration does not overwrite it.
            existing_target = app_root / "data" / "uploads" / "Keep" / "same.png"
            existing_target.parent.mkdir(parents=True, exist_ok=True)
            existing_target.write_bytes(b"new-version")
            legacy_dup = app_root / "static" / "uploads" / "Keep" / "same.png"
            legacy_dup.parent.mkdir(parents=True, exist_ok=True)
            legacy_dup.write_bytes(b"old-version")

            db_file = app_root / "prompts.db"
            conn = sqlite3.connect(db_file)
            conn.execute(
                """
                CREATE TABLE images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_path TEXT NOT NULL,
                    prompt_text TEXT NOT NULL,
                    category TEXT NOT NULL,
                    is_favorite INTEGER DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "INSERT INTO images (image_path, prompt_text, category) VALUES (?, ?, ?)",
                ("/static/uploads/Legacy/old.png", "Legacy artwork", "Legacy"),
            )
            conn.commit()
            conn.close()

            os.environ["DATABASE_PATH"] = str(db_file)
            os.environ["UPLOAD_FOLDER"] = str(app_root / "data" / "uploads")
            spec = importlib.util.spec_from_file_location(mod_name, app_root / "app.py")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            try:
                with self.assertLogs(mod_name, level=logging.INFO) as log_cm:
                    spec.loader.exec_module(mod)

                mod.app.config.update(TESTING=True, SECRET_KEY="test-only-not-a-deployment-secret")
                client = mod.app.test_client()

                row = mod.db.execute("SELECT image_path FROM images")[0]
                self.assertEqual(row["image_path"], "Legacy/old.png")

                with client.get("/media/Legacy/old.png") as media_res:
                    self.assertEqual(media_res.status_code, 200)
                    self.assertEqual(media_res.data, legacy_png)

                with client.get("/static/uploads/Legacy/old.png") as static_res:
                    self.assertEqual(static_res.status_code, 404)

                self.assertFalse(legacy_file.exists())
                self.assertFalse(legacy_file.parent.exists())
                self.assertFalse(empty_legacy_dir.exists())
                self.assertEqual(existing_target.read_bytes(), b"new-version")

                moved_logs = [m for m in log_cm.output if "Legacy/old.png" in m]
                self.assertEqual(len(moved_logs), 1)

                collision_warnings = [
                    m
                    for m in log_cm.output
                    if m.startswith("WARNING:") and "Keep/same.png" in m and "static/uploads/" in m
                ]
                self.assertEqual(len(collision_warnings), 1)

                # Simulate another worker moving a file mid-migration (FileNotFoundError -> silent).
                raced_file = app_root / "static" / "uploads" / "Race" / "vanished.png"
                raced_file.parent.mkdir(parents=True, exist_ok=True)
                raced_file.write_bytes(b"race")
                with (
                    patch.object(mod.shutil, "move", side_effect=FileNotFoundError),
                    self.assertLogs(mod_name, level=logging.WARNING) as race_cm,
                ):
                    mod.migrate_legacy_upload_files()
                self.assertFalse(
                    any("Race/vanished.png" in m for m in race_cm.output), race_cm.output
                )

                # Simulate another OSError during move (logs warning, does not raise).
                with (
                    patch.object(mod.shutil, "move", side_effect=PermissionError("locked")),
                    self.assertLogs(mod_name, level=logging.WARNING) as err_cm,
                ):
                    mod.migrate_legacy_upload_files()
                self.assertTrue(any("Race/vanished.png" in m for m in err_cm.output), err_cm.output)
            finally:
                if mod is not None and hasattr(mod, "db"):
                    mod.db._disconnect()
                    mod.db._engine.dispose()
                sys.modules.pop(mod_name, None)
                if prev_db_env is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = prev_db_env
                if prev_upload_env is None:
                    os.environ.pop("UPLOAD_FOLDER", None)
                else:
                    os.environ["UPLOAD_FOLDER"] = prev_upload_env

    def test_script_name_prefix_add_and_delete(self):
        base_url = "http://localhost/pv"
        add_page = self.client.get("/add", base_url=base_url).get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', add_page).group(1)

        stream = io.BytesIO()
        Image.new("RGB", (4, 4), "red").save(stream, format="PNG")
        res = self.client.post(
            "/add",
            data={
                "csrf_token": token,
                "image_file": (io.BytesIO(stream.getvalue()), "prefixed.png"),
                "prompt_text": "Subpath test",
                "category": "Prefixed",
            },
            content_type="multipart/form-data",
            base_url=base_url,
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers["Location"], "/pv/")

        row = self.module.db.execute("SELECT * FROM images")[0]
        self.assertEqual(row["image_path"], "Prefixed/prefixed.png")
        saved_file = Path(self.module.resolve_upload_path(row["image_path"]))
        self.assertTrue(saved_file.exists())

        gallery_html = self.client.get("/", base_url=base_url).get_data(as_text=True)
        self.assertIn('src="/pv/media/Prefixed/prefixed.png"', gallery_html)

        with self.client.get("/media/Prefixed/prefixed.png", base_url=base_url) as img_res:
            self.assertEqual(img_res.status_code, 200)

        del_res = self.client.post(
            f"/delete/{row['id']}",
            data={"csrf_token": token},
            base_url=base_url,
        )
        self.assertEqual(del_res.status_code, 302)
        self.assertEqual(del_res.headers["Location"], "/pv/")
        self.assertEqual(self.module.db.execute("SELECT * FROM images"), [])
        self.assertFalse(saved_file.exists())

    def test_default_paths_work_from_different_cwd(self):
        repo_dir = Path(__file__).resolve().parent
        prev_cwd = Path.cwd()
        prev_db_env = os.environ.get("DATABASE_PATH")
        mod = None

        with tempfile.TemporaryDirectory() as tmp:
            app_root = Path(tmp) / "app_root"
            other_cwd = Path(tmp) / "other_cwd"
            app_root.mkdir()
            other_cwd.mkdir()

            shutil.copy2(repo_dir / "app.py", app_root / "app.py")
            shutil.copytree(repo_dir / "templates", app_root / "templates")
            shutil.copytree(
                repo_dir / "static",
                app_root / "static",
                ignore=shutil.ignore_patterns("uploads"),
            )
            (app_root / "data" / "uploads").mkdir(parents=True, exist_ok=True)

            os.environ.pop("DATABASE_PATH", None)
            os.chdir(other_cwd)
            spec = importlib.util.spec_from_file_location(
                "promptvault_cwd_test", app_root / "app.py"
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            try:
                spec.loader.exec_module(mod)
                mod.app.config.update(TESTING=True, SECRET_KEY="test-only-not-a-deployment-secret")
                client = mod.app.test_client()

                self.assertEqual(Path(mod.database_path), (app_root / "prompts.db").resolve())
                self.assertEqual(
                    Path(mod.app.config["UPLOAD_FOLDER"]),
                    (app_root / "data" / "uploads").resolve(),
                )
                self.assertFalse((other_cwd / "prompts.db").exists())
                self.assertFalse((other_cwd / "data").exists())

                stream = io.BytesIO()
                Image.new("RGB", (4, 4), "blue").save(stream, format="PNG")
                png_bytes = stream.getvalue()

                add_page = client.get("/add").get_data(as_text=True)
                token = re.search(r'name="csrf_token" value="([^"]+)"', add_page).group(1)
                upload_res = client.post(
                    "/add",
                    data={
                        "csrf_token": token,
                        "image_file": (io.BytesIO(png_bytes), "cwd_check.png"),
                        "prompt_text": "Loaded from another working directory",
                        "category": "Examples",
                    },
                    content_type="multipart/form-data",
                )
                self.assertEqual(upload_res.status_code, 302)

                row = mod.db.execute("SELECT * FROM images")[0]
                with mod.app.test_request_context():
                    img_url = mod.image_url(row)
                with client.get(img_url) as img_res:
                    self.assertEqual(img_res.status_code, 200)
                    self.assertEqual(img_res.data, png_bytes)
            finally:
                if mod is not None and hasattr(mod, "db"):
                    mod.db._disconnect()
                    mod.db._engine.dispose()
                sys.modules.pop("promptvault_cwd_test", None)
                os.chdir(prev_cwd)
                if prev_db_env is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = prev_db_env

    def test_fake_image_rejected(self):
        self.assertEqual(self.upload("fake.png", b"not an image").status_code, 400)
        self.assertEqual(self.module.db.execute("SELECT * FROM images"), [])

    def test_mismatched_extension_rejected(self):
        self.assertEqual(self.upload("wrong.jpg").status_code, 400)
        self.assertEqual(self.module.db.execute("SELECT * FROM images"), [])

    def test_invalid_category_rejected(self):
        invalid_categories = [
            "Fish #1",
            "a/b",
            "../outside",
            "..",
            "foo.",
            "Example\n",
            "tab\there",
            "foo\x00bar",
            "\u200f",
            "Arab\u200fic",
            "\u200c",
            "---",
            "   ",
        ]
        for category in invalid_categories:
            with self.subTest(category=category):
                self.assertFalse(self.module.valid_category(category))
                res = self.upload(category=category)
                self.assertEqual(res.status_code, 400)
                self.assertEqual(self.module.db.execute("SELECT * FROM images"), [])

    def test_valid_unicode_and_spaced_categories_served(self):
        cases = [
            ("تصميم", "تصميم"),
            ("فن رقمي", "فن رقمي"),
            ("العَرَبِيَّة", "العَرَبِيَّة"),
            ("می\u200cخواهم", "می\u200cخواهم"),
            ("Cafe\u0301", "Café"),
            ("  a   b  ", "A B"),
            ("Sci-Fi_Art 1", "Sci-Fi_Art 1"),
        ]
        for raw_category, expected_stored in cases:
            with self.subTest(category=raw_category):
                self.assertTrue(self.module.valid_category(raw_category))
                self.assertEqual(self.module.normalize_category(raw_category), expected_stored)
                res = self.upload(filename="unicode.png", category=raw_category)
                self.assertEqual(res.status_code, 302)
                row = self.module.db.execute(
                    "SELECT * FROM images WHERE category = ? ORDER BY id DESC LIMIT 1",
                    expected_stored,
                )[0]
                self.assertEqual(row["category"], expected_stored)
                self.assertNotIn("#", row["image_path"])
                with self.module.app.test_request_context():
                    img_url = self.module.image_url(row)
                with self.client.get(img_url) as img_res:
                    self.assertEqual(img_res.status_code, 200)
                with self.client.get("/download/" + row["image_path"]) as dl_res:
                    self.assertEqual(dl_res.status_code, 200)

    def test_bidi_dir_auto_attributes_present(self):
        self.upload(
            category="العَرَبِيَّة",
            prompt_text="صورة مستقبلية لمدينة في الصحراء — AI art",
        )
        row = self.module.db.execute("SELECT id FROM images")[0]

        gallery_html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="searchInput"', gallery_html)
        self.assertRegex(gallery_html, r'<input[^>]+id="searchInput"[^>]+dir="auto"')
        self.assertIn('<span class="category-badge" dir="auto">', gallery_html)
        self.assertIn('<p class="prompt-text" dir="auto"', gallery_html)
        self.assertIn(
            '<span id="modalCategory" class="category-badge" dir="auto"></span>', gallery_html
        )
        self.assertIn('<p id="modalPromptText" dir="auto"></p>', gallery_html)

        add_html = self.client.get("/add").get_data(as_text=True)
        self.assertRegex(add_html, r'<textarea[^>]+id="prompt_text"[^>]+dir="auto"')
        self.assertRegex(add_html, r'<input[^>]+id="category"[^>]+dir="auto"')

        edit_html = self.client.get(f"/edit/{row['id']}").get_data(as_text=True)
        self.assertRegex(edit_html, r'<textarea[^>]+id="prompt_text"[^>]+dir="auto"')
        self.assertRegex(edit_html, r'<input[^>]+id="category"[^>]+dir="auto"')

    def test_favorite_filter_survives_sort(self):
        self.upload()
        identifier = self.module.db.execute("SELECT id FROM images")[0]["id"]
        self.client.post(f"/favorite/{identifier}", data={"csrf_token": self.csrf_token()})
        html = self.client.get("/?favorites=1").get_data(as_text=True)
        self.assertIn("sort=oldest", html)
        self.assertIn("favorites=1", html)
        fav = self.module.db.execute("SELECT is_favorite FROM images")[0]["is_favorite"]
        self.assertEqual(fav, 1)

    def test_edit_and_delete(self):
        self.upload()
        row = self.module.db.execute("SELECT * FROM images")[0]
        image_path = Path(self.module.resolve_upload_path(row["image_path"]))
        self.assertTrue(image_path.exists())
        response = self.client.post(
            f"/edit/{row['id']}",
            data={
                "csrf_token": self.csrf_token(),
                "prompt_text": "Updated",
                "category": "Revised",
            },
        )
        self.assertEqual(response.status_code, 302)
        updated_prompt = self.module.db.execute("SELECT prompt_text FROM images")[0]["prompt_text"]
        self.assertEqual(updated_prompt, "Updated")
        updated_row = self.module.db.execute(
            "SELECT image_path FROM images WHERE id = ?", row["id"]
        )[0]
        moved_path = Path(self.module.resolve_upload_path(updated_row["image_path"]))
        self.assertTrue(moved_path.exists())
        self.client.post(f"/delete/{row['id']}", data={"csrf_token": self.csrf_token()})
        self.assertEqual(self.module.db.execute("SELECT * FROM images"), [])
        self.assertFalse(moved_path.exists())
        self.assertFalse(image_path.exists())

    def test_edit_category_moves_image_file(self):
        self.assertEqual(self.upload(category="Examples").status_code, 302)
        row = self.module.db.execute("SELECT * FROM images")[0]
        old_path = Path(self.module.resolve_upload_path(row["image_path"]))
        self.assertTrue(old_path.exists())

        response = self.client.post(
            f"/edit/{row['id']}",
            data={
                "csrf_token": self.csrf_token(),
                "prompt_text": "A test image",
                "category": "Revised",
            },
        )
        self.assertEqual(response.status_code, 302)

        updated = self.module.db.execute("SELECT * FROM images WHERE id = ?", row["id"])[0]
        new_path = Path(self.module.resolve_upload_path(updated["image_path"]))
        self.assertEqual(updated["category"], "Revised")
        self.assertNotEqual(updated["image_path"], row["image_path"])
        self.assertTrue(new_path.exists())
        self.assertFalse(old_path.exists())

    def test_request_size_limit(self):
        original_limit = self.module.app.config["MAX_CONTENT_LENGTH"]
        token = self.csrf_token()
        self.module.app.config["MAX_CONTENT_LENGTH"] = 512
        try:
            response = self.client.post(
                "/add",
                data={
                    "csrf_token": token,
                    "prompt_text": "x" * 2048,
                },
            )
            self.assertEqual(response.status_code, 413)
            body = response.get_data(as_text=True)
            self.assertIn("413 - Upload Too Large", body)
            self.assertIn("<title>Upload Too Large (413) | PromptVault</title>", body)
        finally:
            self.module.app.config["MAX_CONTENT_LENGTH"] = original_limit

    def test_method_not_allowed_renders_405_template(self):
        res = self.client.get("/delete/1")
        self.assertEqual(res.status_code, 405)
        body = res.get_data(as_text=True)
        self.assertIn("405 - Method Not Allowed", body)
        self.assertIn("<title>Method Not Allowed (405) | PromptVault</title>", body)

    def test_download_traversal_rejected(self):
        traversal_paths = [
            "/download/../prompts.db",
            "/download/%2e%2e%2fprompts.db",
            "/download/%252e%252e%252fprompts.db",
            "/download/..%5cprompts.db",
            "/download/Examples%5c..%5cprompts.db",
            "/download/Examples/%2e%2e%2fprompts.db",
            "/media/../prompts.db",
            "/media/%2e%2e%2fprompts.db",
            "/media/%252e%252e%252fprompts.db",
            "/media/..%5cprompts.db",
        ]
        for path in traversal_paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_search_filtering(self):
        self.upload(filename="scifi1.png", category="SciFi", prompt_text="Orbital station")
        self.upload(filename="art1.png", category="Art", prompt_text="Oil portrait")
        self.upload(filename="pct.png", category="Wild", prompt_text="100% cotton texture")
        self.upload(filename="nonpct.png", category="Wild", prompt_text="100x cotton texture")
        self.upload(filename="under.png", category="Wild", prompt_text="snake_case style")
        self.upload(filename="nonunder.png", category="Wild", prompt_text="snakexcase style")

        res = self.client.get("/?q=SciFi")
        self.assertEqual(res.status_code, 200)
        self.assertIn("SciFi", res.get_data(as_text=True))

        res_empty = self.client.get("/?q=NonExistentQuery123")
        self.assertEqual(res_empty.status_code, 200)
        self.assertIn("No results matching query", res_empty.get_data(as_text=True))

        res_pct = self.client.get("/?q=100%25")
        self.assertEqual(res_pct.status_code, 200)
        pct_body = res_pct.get_data(as_text=True)
        self.assertIn("100% cotton texture", pct_body)
        self.assertNotIn("100x cotton texture", pct_body)

        res_under = self.client.get("/?q=snake_case")
        self.assertEqual(res_under.status_code, 200)
        under_body = res_under.get_data(as_text=True)
        self.assertIn("snake_case style", under_body)
        self.assertNotIn("snakexcase style", under_body)

    def test_add_validation_errors_return_400(self):
        cases = [
            {"csrf_token": self.csrf_token(), "prompt_text": "", "category": "Examples"},
            {"csrf_token": self.csrf_token(), "prompt_text": "Valid prompt", "category": ""},
            {
                "csrf_token": self.csrf_token(),
                "prompt_text": "Missing file",
                "category": "Examples",
            },
        ]
        for data in cases:
            res = self.client.post("/add", data=data, content_type="multipart/form-data")
            self.assertEqual(res.status_code, 400)
        self.assertEqual(self.upload(filename="note.txt", contents=b"hello").status_code, 400)
        self.assertEqual(self.module.db.execute("SELECT * FROM images"), [])

    def test_add_cleans_up_file_if_db_insert_fails(self):
        original_execute = self.module.db.execute
        stream = io.BytesIO()
        Image.new("RGB", (4, 4), "green").save(stream, format="PNG")

        def fail_on_insert(sql, *args, **kwargs):
            if sql.lstrip().upper().startswith("INSERT"):
                raise RuntimeError("Simulated DB failure")
            return original_execute(sql, *args, **kwargs)

        with patch.object(self.module.db, "execute", side_effect=fail_on_insert):
            self.module.app.config["PROPAGATE_EXCEPTIONS"] = False
            try:
                res = self.client.post(
                    "/add",
                    data={
                        "csrf_token": self.csrf_token(),
                        "image_file": (io.BytesIO(stream.getvalue()), "orphan_check.png"),
                        "prompt_text": "Cleanup test",
                        "category": "OrphanTest",
                    },
                    content_type="multipart/form-data",
                )
            finally:
                self.module.app.config["PROPAGATE_EXCEPTIONS"] = None
        self.assertEqual(res.status_code, 500)
        cat_dir = Path(self.module.app.config["UPLOAD_FOLDER"]) / "Orphantest"
        self.assertFalse(cat_dir.exists())

    def test_edit_missing_file_refuses_category_change(self):
        self.assertEqual(self.upload(category="Examples").status_code, 302)
        row = self.module.db.execute("SELECT * FROM images")[0]
        file_path = Path(self.module.resolve_upload_path(row["image_path"]))
        file_path.unlink()

        res = self.client.post(
            f"/edit/{row['id']}",
            data={
                "csrf_token": self.csrf_token(),
                "prompt_text": "Changed prompt",
                "category": "Revised",
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("missing on disk", res.get_data(as_text=True))
        current = self.module.db.execute("SELECT * FROM images WHERE id = ?", row["id"])[0]
        self.assertEqual(current["category"], "Examples")

    def test_favorite_and_delete_nonexistent_id_return_404(self):
        self.assertEqual(
            self.client.post("/favorite/99999", data={"csrf_token": self.csrf_token()}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/delete/99999", data={"csrf_token": self.csrf_token()}).status_code,
            404,
        )

    def test_favorite_redirects_only_same_origin(self):
        self.upload()
        identifier = self.module.db.execute("SELECT id FROM images")[0]["id"]

        external = self.client.post(
            f"/favorite/{identifier}",
            data={"csrf_token": self.csrf_token()},
            headers={"Referer": "https://evil.example/phish"},
        )
        self.assertEqual(external.status_code, 302)
        self.assertEqual(external.headers["Location"], "/")

        same_origin = self.client.post(
            f"/favorite/{identifier}",
            data={"csrf_token": self.csrf_token()},
            headers={"Referer": "http://localhost/?favorites=1&sort=oldest"},
        )
        self.assertEqual(same_origin.status_code, 302)
        self.assertEqual(same_origin.headers["Location"], "/?favorites=1&sort=oldest")

    def test_animated_gif_frame_pixel_limit(self):
        small_frame = Image.new("RGB", (4, 4), "red")
        valid_buf = io.BytesIO()
        small_frame.save(valid_buf, format="GIF", save_all=True, append_images=[small_frame])

        large_frame = Image.new("RGB", (6, 6), "blue")
        oversized_buf = io.BytesIO()
        large_frame.save(oversized_buf, format="GIF", save_all=True, append_images=[small_frame])

        # Build a 2-frame GIF whose 4x4 logical screen fits, while frame 2 declares a 10x10 tile.
        frame1 = Image.new("RGB", (4, 4), "red")
        frame2 = Image.new("RGB", (10, 10), "blue")
        tmp_buf = io.BytesIO()
        frame2.save(tmp_buf, format="GIF")
        raw_frame2 = tmp_buf.getvalue()
        img_sep_idx = raw_frame2.find(b"\x2c")
        f1_buf = io.BytesIO()
        frame1.save(f1_buf, format="GIF")
        raw_f1 = bytearray(f1_buf.getvalue())
        # Append second frame descriptor (with 10x10 width/height) before GIF trailer byte ';'.
        crafted_gif = bytes(raw_f1[:-1]) + raw_frame2[img_sep_idx:]

        with patch.object(self.module, "MAX_IMAGE_PIXELS", 25):
            ok_res = self.upload("ok.gif", valid_buf.getvalue(), category="Animated")
            self.assertEqual(ok_res.status_code, 302)

            bad_res = self.upload("too_big.gif", oversized_buf.getvalue(), category="Animated")
            self.assertEqual(bad_res.status_code, 400)

            crafted_res = self.upload("crafted.gif", crafted_gif, category="Animated")
            self.assertEqual(crafted_res.status_code, 400)

    def test_hsts_only_on_https(self):
        http_res = self.client.get("/")
        self.assertNotIn("Strict-Transport-Security", http_res.headers)

        https_res = self.client.get("/", base_url="https://localhost/")
        self.assertIn("Strict-Transport-Security", https_res.headers)
        hsts = https_res.headers["Strict-Transport-Security"]
        self.assertIn("max-age=63072000", hsts)
        self.assertNotIn("preload", hsts)

    def test_security_headers_and_csp(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        csp = res.headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", csp)
        directives = {
            part.strip().split()[0]: part.strip().split()[1:]
            for part in csp.split(";")
            if part.strip()
        }
        self.assertIn("script-src", directives)
        self.assertNotIn("'unsafe-inline'", directives["script-src"])
        self.assertEqual(directives["script-src"], ["'self'"])
        self.assertEqual(directives["img-src"], ["'self'", "data:", "blob:"])
        self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertIn("Permissions-Policy", res.headers)

    def test_cache_control_headers_and_static_versioning(self):
        self.upload(category="CacheTest")
        row = self.module.db.execute("SELECT id FROM images")[0]

        for path in ["/", "/add", f"/edit/{row['id']}"]:
            with self.subTest(path=path):
                page = self.client.get(path)
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page.headers.get("Cache-Control"), "no-store")

        home_html = self.client.get("/").get_data(as_text=True)
        expected_v = f"styles.css?v={self.module.STATIC_VERSION}"
        self.assertIn(expected_v, home_html)

        with self.client.get(f"/static/styles.css?v={self.module.STATIC_VERSION}") as versioned:
            self.assertEqual(versioned.status_code, 200)
            self.assertEqual(
                versioned.headers.get("Cache-Control"),
                "public, max-age=31536000, immutable",
            )

        with self.client.get("/static/styles.css") as unversioned:
            self.assertEqual(unversioned.status_code, 200)
            self.assertEqual(unversioned.headers.get("Cache-Control"), "public, max-age=86400")

        uploaded = self.module.db.execute("SELECT image_path FROM images WHERE id = ?", row["id"])[
            0
        ]
        media_url = f"/media/{uploaded['image_path']}"
        with self.client.get(media_url) as media_res:
            self.assertEqual(media_res.status_code, 200)
            self.assertEqual(
                media_res.headers.get("Cache-Control"),
                "public, max-age=3600, must-revalidate",
            )
            etag = media_res.headers.get("ETag")
            self.assertTrue(etag)

        with self.client.get(media_url, headers={"If-None-Match": etag}) as revalidated:
            self.assertEqual(revalidated.status_code, 304)

    def test_prompt_xss_attribute_injection_prevented(self):
        payload = '" onfocus=alert(1) x=" <script>evil()</script> & \u0639\u0631\u0628\u064a'
        res = self.upload(prompt_text=payload, category="Examples")
        self.assertEqual(res.status_code, 302)

        gallery = self.client.get("/")
        self.assertEqual(gallery.status_code, 200)
        body = gallery.get_data(as_text=True)

        class AttrInspector(HTMLParser):
            def __init__(self):
                super().__init__()
                self.attrs = []

            def handle_starttag(self, tag, attrs):
                self.attrs.extend(attrs)

        inspector = AttrInspector()
        inspector.feed(body)
        attr_names = {name.lower() for name, _ in inspector.attrs}
        self.assertNotIn("onfocus", attr_names)
        self.assertNotIn("onclick", attr_names)
        self.assertNotIn("x", attr_names)
        self.assertNotIn("<script>evil()</script>", body)
        for name, value in inspector.attrs:
            if name.lower().startswith("on"):
                self.fail(f"Unexpected inline event handler: {name}={value}")

    def test_robots_and_sitemap(self):
        self.upload(category="Examples")
        robots_res = self.client.get("/robots.txt")
        self.assertEqual(robots_res.status_code, 200)
        self.assertEqual(robots_res.mimetype, "text/plain")
        robots_text = robots_res.get_data(as_text=True)
        self.assertIn("Disallow: /add", robots_text)
        self.assertIn("Disallow: /delete/", robots_text)
        self.assertIn("Sitemap:", robots_text)

        sitemap_res = self.client.get("/sitemap.xml")
        self.assertEqual(sitemap_res.status_code, 200)
        self.assertEqual(sitemap_res.mimetype, "application/xml")
        sitemap_text = sitemap_res.get_data(as_text=True)
        self.assertIn("<urlset", sitemap_text)
        locs = re.findall(r"<loc>([^<]+)</loc>", sitemap_text)
        self.assertEqual(locs, ["http://localhost/", "http://localhost/about"])
        lastmods = re.findall(r"<lastmod>(\d{4}-\d{2}-\d{2})</lastmod>", sitemap_text)
        self.assertEqual(len(lastmods), 2)
        self.assertEqual(lastmods[1], self.module.ABOUT_LASTMOD)
        self.assertNotIn("<changefreq>", sitemap_text)
        self.assertNotIn("<priority>", sitemap_text)

        static_sitemap = (Path(__file__).resolve().parent / "sitemap.xml").read_text(
            encoding="utf-8"
        )
        self.assertRegex(static_sitemap, r"<lastmod>\d{4}-\d{2}-\d{2}</lastmod>")
        self.assertNotIn("<changefreq>", static_sitemap)
        self.assertNotIn("<priority>", static_sitemap)

    def test_seo_metadata_headings_and_accessibility(self):
        self.upload(category="Examples")
        pages = [
            ("/", "Gallery | PromptVault", "index, follow"),
            ("/about", "About | PromptVault", "index, follow"),
            ("/add", "Add prompt | PromptVault", "noindex, follow"),
            ("/?q=test", "Gallery | PromptVault", "noindex, follow"),
            ("/?category=Examples", "Gallery | PromptVault", "noindex, follow"),
            ("/?sort=oldest", "Gallery | PromptVault", "noindex, follow"),
        ]
        seen_descriptions = set()
        for url, expected_title, expected_robots in pages:
            with self.subTest(url=url):
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200)
                html = res.get_data(as_text=True)
                self.assertIn(f"<title>{expected_title}</title>", html)
                self.assertNotIn('<meta name="keywords"', html)
                self.assertIn(f'<meta name="robots" content="{expected_robots}"', html)
                self.assertEqual(len(re.findall(r"<h1\b", html)), 1)
                self.assertIn(
                    'property="og:image" content="http://localhost/static/og-card.png"', html
                )
                self.assertIn('property="og:image:width" content="1200"', html)
                self.assertIn('property="og:image:height" content="630"', html)
                desc_match = re.search(r'<meta name="description" content="([^"]+)"', html)
                self.assertIsNotNone(desc_match)
                if not url.startswith("/?"):
                    seen_descriptions.add(desc_match.group(1))
                if url.startswith("/?"):
                    self.assertIn('<link rel="canonical" href="http://localhost/">', html)

        self.assertEqual(len(seen_descriptions), 3)

        gallery_html = self.client.get("/").get_data(as_text=True)
        self.assertNotIn('class="card-overlay" aria-hidden="true"', gallery_html)
        self.assertNotIn('role="tablist"', gallery_html)
        self.assertNotIn('role="tab"', gallery_html)
        self.assertNotIn('role="banner"', gallery_html)
        self.assertNotIn('role="main"', gallery_html)
        self.assertNotIn('role="contentinfo"', gallery_html)
        self.assertNotIn("Live Search Bar", gallery_html)
        self.assertNotIn('aria-label="Add new prompt"', gallery_html)
        self.assertNotIn('aria-label="PromptVault Home"', gallery_html)
        self.assertNotIn('aria-label="Sort by newest first"', gallery_html)
        self.assertIn('id="navToggle"', gallery_html)
        self.assertIn('aria-expanded="false"', gallery_html)
        self.assertIn('aria-controls="mainNav"', gallery_html)
        self.assertIn('data-placeholder-mobile="Search prompts..."', gallery_html)
        self.assertIn('aria-current="true"', gallery_html)

        repo_dir = Path(__file__).resolve().parent
        main_js = (repo_dir / "static" / "js" / "main.js").read_text(encoding="utf-8")
        gallery_js = (repo_dir / "static" / "js" / "gallery.js").read_text(encoding="utf-8")
        demo_js = (repo_dir / "static" / "js" / "demo.js").read_text(encoding="utf-8")
        self.assertIn("createModalController", main_js)
        self.assertIn('event.key === "Tab"', main_js)
        self.assertIn("createModalController", gallery_js)
        self.assertIn("createModalController", demo_js)
        self.assertNotIn(".modal-overlay.active", main_js)

        static_dir = Path(__file__).resolve().parent / "static"
        with Image.open(static_dir / "og-card.png") as og_img:
            self.assertEqual(og_img.size, (1200, 630))
        for icon_name, expected_size in [
            ("icon-192.png", (192, 192)),
            ("icon-512.png", (512, 512)),
            ("icon-maskable-512.png", (512, 512)),
            ("apple-touch-icon.png", (180, 180)),
        ]:
            with Image.open(static_dir / icon_name) as icon_img:
                self.assertEqual(icon_img.size, expected_size)

    def test_static_demo_assets_hardened(self):
        repo_dir = Path(__file__).resolve().parent
        demo_html = (repo_dir / "index.html").read_text(encoding="utf-8")
        demo_js = (repo_dir / "static" / "js" / "demo.js").read_text(encoding="utf-8")
        err_html = (repo_dir / "404.html").read_text(encoding="utf-8")

        self.assertIn("<title>Gallery Demo | PromptVault</title>", demo_html)
        self.assertNotIn('<meta name="keywords"', demo_html)
        self.assertEqual(len(re.findall(r"<h1\b", demo_html)), 1)
        self.assertIn("<noscript>", demo_html)
        self.assertNotIn("onclick=", demo_html)
        self.assertNotIn('role="banner"', demo_html)
        self.assertNotIn('role="main"', demo_html)
        self.assertNotIn('role="contentinfo"', demo_html)
        self.assertNotIn('role="banner"', err_html)
        self.assertNotIn('role="main"', err_html)
        self.assertNotIn('role="contentinfo"', err_html)
        self.assertIn('id="navToggle"', demo_html)
        self.assertIn("og-card.png", demo_html)
        self.assertIn("isSafeImageDataUrl", demo_js)
        self.assertIn("&quot;", demo_js)
        self.assertIn("&#39;", demo_js)
        self.assertEqual(err_html.count("styles.css"), 1)
        self.assertIn("<title>Page Not Found (404) | PromptVault</title>", err_html)

        dev_reqs = (repo_dir / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertRegex(dev_reqs, r"(?m)^ruff==\d+\.\d+\.\d+$")
        self.assertRegex(dev_reqs, r"(?m)^pip-audit==\d+\.\d+\.\d+$")
        ci_yml = (repo_dir / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("pip install -r requirements-dev.txt", ci_yml)
        self.assertIn("pip-audit -r requirements.txt", ci_yml)
        self.assertIn("docker run", ci_yml)
        self.assertIn("curl -fsS http://127.0.0.1:5000/", ci_yml)

        dependabot_yml = (repo_dir / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        self.assertIn('package-ecosystem: "pip"', dependabot_yml)
        self.assertIn('package-ecosystem: "github-actions"', dependabot_yml)
        self.assertIn('interval: "weekly"', dependabot_yml)

        compose_yml = (repo_dir / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("promptvault_data:/app/data", compose_yml)
        self.assertNotIn("promptvault_uploads", compose_yml)

        for ignore_name in (".gitignore", ".dockerignore"):
            ignore_text = (repo_dir / ignore_name).read_text(encoding="utf-8")
            self.assertNotIn("static/uploads", ignore_text)
            self.assertIn("data/uploads/*", ignore_text)

    def test_schema_json_ld_present(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("application/ld+json", body)
        self.assertIn('"@type": "WebApplication"', body)
        self.assertIn('"@type": "ImageGallery"', body)

    def test_custom_404_template(self):
        res = self.client.get("/nonexistent-page-path-404")
        self.assertEqual(res.status_code, 404)
        self.assertIn("Page Not Found", res.get_data(as_text=True))

    def test_production_requires_non_placeholder_secret_key(self):
        repo_dir = Path(__file__).resolve().parent
        invalid_keys = [
            "",
            "too-short-secret",
            "change-this-to-a-secure-random-32-byte-hex-string",
            "replace_with_a_secure_production_secret_key_32_bytes",
            "replace-with-a-random-64-char-hex-key",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for idx, key in enumerate(invalid_keys):
                with self.subTest(key=key):
                    env = os.environ.copy()
                    env["APP_ENV"] = "production"
                    env["DATABASE_PATH"] = str(Path(tmp) / f"prod_{idx}.db")
                    if key:
                        env["SECRET_KEY"] = key
                    else:
                        env.pop("SECRET_KEY", None)
                    proc = subprocess.run(
                        [sys.executable, "-c", "import app"],
                        cwd=str(repo_dir),
                        env=env,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertIn("SECRET_KEY", proc.stderr)

            valid_env = os.environ.copy()
            valid_env["APP_ENV"] = "production"
            valid_env["DATABASE_PATH"] = str(Path(tmp) / "prod_valid.db")
            valid_env["SECRET_KEY"] = "a" * 32 + "b" * 32
            ok_proc = subprocess.run(
                [sys.executable, "-c", "import app"],
                cwd=str(repo_dir),
                env=valid_env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(ok_proc.returncode, 0, ok_proc.stderr)

    def test_dev_mode_logs_single_warning_for_missing_secret(self):
        repo_dir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["APP_ENV"] = "development"
            env["DATABASE_PATH"] = str(Path(tmp) / "dev.db")
            env.pop("SECRET_KEY", None)
            proc = subprocess.run(
                [sys.executable, "-c", "import app"],
                cwd=str(repo_dir),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stderr.count("SECRET_KEY is missing"), 1)

    def test_env_example_and_relative_database_path_resolution(self):
        repo_dir = Path(__file__).resolve().parent
        env_example = (repo_dir / ".env.example").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?m)^DATABASE_PATH=", env_example))
        self.assertRegex(env_example, r"(?m)^#\s*DATABASE_PATH=")

        with tempfile.TemporaryDirectory() as tmp:
            app_root = Path(tmp) / "app_root"
            other_cwd = Path(tmp) / "other_cwd"
            app_root.mkdir()
            other_cwd.mkdir()

            resolved_rel = Path(self.module.resolve_database_path("data/custom.db", str(app_root)))
            self.assertEqual(resolved_rel, (app_root / "data" / "custom.db").resolve())

            abs_target = (other_cwd / "abs.db").resolve()
            resolved_abs = Path(self.module.resolve_database_path(str(abs_target), str(app_root)))
            self.assertEqual(resolved_abs, abs_target)

            shutil.copy2(repo_dir / "app.py", app_root / "app.py")
            shutil.copytree(repo_dir / "templates", app_root / "templates")
            shutil.copytree(
                repo_dir / "static",
                app_root / "static",
                ignore=shutil.ignore_patterns("uploads"),
            )
            (app_root / "static" / "uploads").mkdir(parents=True, exist_ok=True)

            env = os.environ.copy()
            env["APP_ENV"] = "development"
            env["DATABASE_PATH"] = "data/relative.db"
            env["UPLOAD_FOLDER"] = "custom_media/uploads"
            env["PYTHONPATH"] = str(app_root)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import app; print(app.database_path); print(app.UPLOAD_FOLDER)",
                ],
                cwd=str(other_cwd),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            lines = proc.stdout.strip().splitlines()
            self.assertEqual(
                Path(lines[0]).resolve(), (app_root / "data" / "relative.db").resolve()
            )
            self.assertEqual(
                Path(lines[1]).resolve(), (app_root / "custom_media" / "uploads").resolve()
            )
            self.assertTrue((app_root / "data" / "relative.db").exists())
            self.assertTrue((app_root / "custom_media" / "uploads").is_dir())
            self.assertFalse((other_cwd / "data").exists())
            self.assertFalse((other_cwd / "custom_media").exists())

    def test_wsgi_entrypoint_requires_secret_key_when_app_env_unset(self):
        repo_dir = Path(__file__).resolve().parent
        procfile_text = (repo_dir / "Procfile").read_text(encoding="utf-8").strip()
        self.assertEqual(procfile_text, "web: APP_ENV=production gunicorn wsgi:app")

        dockerfile_text = (repo_dir / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("APP_ENV=production", dockerfile_text)

        wsgi_text = (repo_dir / "wsgi.py").read_text(encoding="utf-8")
        self.assertNotIn("===", wsgi_text)
        self.assertNotIn("waitress", wsgi_text.lower())
        self.assertFalse(hasattr(self.module, "is_wsgi_runtime"))

        with tempfile.TemporaryDirectory() as tmp:
            base_env = os.environ.copy()
            base_env.pop("APP_ENV", None)
            base_env.pop("SECRET_KEY", None)

            wsgi_env = base_env.copy()
            wsgi_env["DATABASE_PATH"] = str(Path(tmp) / "wsgi_fail.db")
            proc_wsgi = subprocess.run(
                [sys.executable, "-c", "import wsgi"],
                cwd=str(repo_dir),
                env=wsgi_env,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc_wsgi.returncode, 0)
            self.assertIn("SECRET_KEY", proc_wsgi.stderr)

            ok_env = base_env.copy()
            ok_env["SECRET_KEY"] = "c" * 32 + "d" * 32
            ok_env["DATABASE_PATH"] = str(Path(tmp) / "wsgi_ok.db")
            proc_ok = subprocess.run(
                [sys.executable, "-c", "import wsgi"],
                cwd=str(repo_dir),
                env=ok_env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc_ok.returncode, 0, proc_ok.stderr)

    def test_app_password_protects_all_non_static_routes(self):
        self.upload(filename="existing.png", category="Existing")
        existing = self.module.db.execute("SELECT * FROM images")[0]

        token_any_user = base64.b64encode(b"ignored-user:secret-pass-42").decode("ascii")
        token_empty_user = base64.b64encode(b":secret-pass-42").decode("ascii")
        wrong_token = base64.b64encode(b"user:wrong-pass").decode("ascii")
        valid_headers = {"Authorization": f"Basic {token_any_user}"}
        empty_user_headers = {"Authorization": f"Basic {token_empty_user}"}
        bad_headers = {"Authorization": f"Basic {wrong_token}"}

        with patch.dict(self.module.app.config, {"APP_PASSWORD": "secret-pass-42"}):
            self.assertEqual(self.client.get("/robots.txt").status_code, 200)
            with self.client.get("/static/styles.css") as css_res:
                self.assertEqual(css_res.status_code, 200)

            media_url = "/media/" + existing["image_path"]
            with self.client.get(media_url) as media_unauth:
                self.assertEqual(media_unauth.status_code, 401)
                self.assertIn("Basic", media_unauth.headers.get("WWW-Authenticate", ""))
            with self.client.get(media_url, headers=bad_headers) as media_bad:
                self.assertEqual(media_bad.status_code, 401)
            with self.client.get(media_url, headers=valid_headers) as media_ok:
                self.assertEqual(media_ok.status_code, 200)

            protected_gets = [
                "/",
                "/about",
                "/add",
                f"/edit/{existing['id']}",
                "/sitemap.xml",
                "/download/" + existing["image_path"],
            ]
            for path in protected_gets:
                with self.subTest(method="GET", path=path):
                    unauth = self.client.get(path)
                    self.assertEqual(unauth.status_code, 401)
                    self.assertIn("Basic", unauth.headers.get("WWW-Authenticate", ""))
                    self.assertEqual(self.client.get(path, headers=bad_headers).status_code, 401)

            self.assertEqual(self.client.get("/", headers=empty_user_headers).status_code, 200)
            self.assertEqual(self.client.get("/about", headers=valid_headers).status_code, 200)

            add_page = self.client.get("/add", headers=valid_headers).get_data(as_text=True)
            token = re.search(r'name="csrf_token" value="([^"]+)"', add_page).group(1)

            for path in [
                "/add",
                f"/edit/{existing['id']}",
                f"/favorite/{existing['id']}",
                f"/delete/{existing['id']}",
            ]:
                unauth = self.client.post(path, data={"csrf_token": token})
                self.assertEqual(unauth.status_code, 401)
                self.assertIn("Basic", unauth.headers.get("WWW-Authenticate", ""))

                wrong = self.client.post(
                    path,
                    data={"csrf_token": token},
                    headers=bad_headers,
                )
                self.assertEqual(wrong.status_code, 401)

            stream = io.BytesIO()
            Image.new("RGB", (4, 4), "white").save(stream, format="PNG")
            add_res = self.client.post(
                "/add",
                data={
                    "csrf_token": token,
                    "image_file": (io.BytesIO(stream.getvalue()), "protected.png"),
                    "prompt_text": "Protected prompt",
                    "category": "Protected",
                },
                content_type="multipart/form-data",
                headers=valid_headers,
            )
            self.assertEqual(add_res.status_code, 302)
            row_id = self.module.db.execute("SELECT id FROM images ORDER BY id DESC LIMIT 1")[0][
                "id"
            ]

            fav_res = self.client.post(
                f"/favorite/{row_id}",
                data={"csrf_token": token},
                headers=empty_user_headers,
            )
            self.assertEqual(fav_res.status_code, 302)

            edit_res = self.client.post(
                f"/edit/{row_id}",
                data={
                    "csrf_token": token,
                    "prompt_text": "Updated protected",
                    "category": "Protected",
                },
                headers=valid_headers,
            )
            self.assertEqual(edit_res.status_code, 302)

            del_res = self.client.post(
                f"/delete/{row_id}",
                data={"csrf_token": token},
                headers=valid_headers,
            )
            self.assertEqual(del_res.status_code, 302)

    def test_app_password_blocks_upload_path_bypass_variants(self):
        self.upload(filename="secret.png", category="Private")
        existing = self.module.db.execute("SELECT * FROM images")[0]
        rel = existing["image_path"]

        token = base64.b64encode(b":secret-pass-42").decode("ascii")
        valid_headers = {"Authorization": f"Basic {token}"}

        raw_static_variants = [
            f"/static/uploads/{rel}",
            f"/static/./uploads/{rel}",
            f"/static/x/../uploads/{rel}",
            f"/static//uploads/{rel}",
            f"/static/Uploads/{rel}",
            f"/static/%2e/uploads/{rel}",
            f"/static/x/%2e%2e/uploads/{rel}",
            f"/static/uploads%2f{rel}",
        ]
        raw_media_variants = [
            f"/media/{rel}",
            f"/media/./{rel}",
            f"/media/x/../{rel}",
            f"/media//{rel}",
            f"/media/%2e/{rel}",
            f"/media/x/%2e%2e/{rel}",
            f"/media/{rel.replace('/', '%2f')}",
        ]

        with patch.dict(self.module.app.config, {"APP_PASSWORD": "secret-pass-42"}):
            self.assertEqual(self.client.get("/robots.txt").status_code, 200)
            with self.client.get("/static/styles.css") as css_res:
                self.assertEqual(css_res.status_code, 200)

            # Uploads no longer reside in static/, so no static path variant can serve them.
            for raw_path in raw_static_variants:
                with self.subTest(static_path=raw_path):
                    with self.client.get(raw_path) as res:
                        if res.status_code == 308:
                            with self.client.get(res.headers["Location"]) as followed:
                                self.assertIn(followed.status_code, (401, 404))
                        else:
                            self.assertIn(res.status_code, (401, 404))

            # Every /media/ path variant requires Basic auth (401, or 308 -> 401).
            for raw_path in raw_media_variants:
                with self.subTest(media_path=raw_path):
                    with self.client.get(raw_path) as res:
                        if res.status_code == 308:
                            with self.client.get(res.headers["Location"]) as followed:
                                self.assertEqual(followed.status_code, 401)
                        else:
                            self.assertEqual(res.status_code, 401)

            with self.module.app.test_request_context():
                media_url = self.module.image_url(existing)
            self.assertEqual(media_url, f"/media/{rel}")
            with self.client.get(media_url, headers=valid_headers) as auth_media:
                self.assertEqual(auth_media.status_code, 200)
            # Dot-segment variants under /media/ are rejected even with valid credentials.
            for dot_path in [f"/media/./{rel}", f"/media/x/../{rel}", f"/media/%2e/{rel}"]:
                with self.client.get(dot_path, headers=valid_headers) as dot_res:
                    self.assertEqual(dot_res.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
