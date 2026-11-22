import importlib.util
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

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
        workspace_uploads = workspace_static / "uploads"
        workspace_uploads.mkdir(parents=True, exist_ok=True)
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

    def test_missing_csrf_is_rejected(self):
        self.assertEqual(self.client.post("/add", data={}).status_code, 400)
        self.assertEqual(self.client.post("/delete/1").status_code, 400)
        self.assertEqual(self.client.post("/favorite/1").status_code, 400)
        self.assertEqual(self.client.post("/edit/1").status_code, 400)

    def test_valid_image_upload_and_download(self):
        self.assertEqual(self.upload().status_code, 302)
        row = self.module.db.execute("SELECT * FROM images")[0]
        with self.client.get(row["image_path"]) as static_res:
            self.assertEqual(static_res.status_code, 200)
        download_path = row["image_path"].replace("/static/uploads/", "")
        with self.client.get("/download/" + download_path) as response:
            self.assertEqual(response.status_code, 200)

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
            (app_root / "static" / "uploads").mkdir(parents=True, exist_ok=True)

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
                    (app_root / "static" / "uploads").resolve(),
                )
                self.assertFalse((other_cwd / "prompts.db").exists())
                self.assertFalse((other_cwd / "static").exists())

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
                with client.get(row["image_path"]) as img_res:
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
        self.upload(category="../outside")
        self.assertEqual(self.module.db.execute("SELECT * FROM images"), [])
        self.assertFalse(self.module.valid_category("Example\n"))

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
        image_path = Path(row["image_path"].lstrip("/"))
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
        moved_path = Path(updated_row["image_path"].lstrip("/"))
        self.assertTrue(moved_path.exists())
        self.client.post(f"/delete/{row['id']}", data={"csrf_token": self.csrf_token()})
        self.assertEqual(self.module.db.execute("SELECT * FROM images"), [])
        self.assertFalse(moved_path.exists())
        self.assertFalse(image_path.exists())

    def test_edit_category_moves_image_file(self):
        self.assertEqual(self.upload(category="Examples").status_code, 302)
        row = self.module.db.execute("SELECT * FROM images")[0]
        old_path = Path(row["image_path"].lstrip("/"))
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
        new_path = Path(updated["image_path"].lstrip("/"))
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
        finally:
            self.module.app.config["MAX_CONTENT_LENGTH"] = original_limit

    def test_download_traversal_rejected(self):
        self.assertEqual(self.client.get("/download/../prompts.db").status_code, 404)

    def test_search_filtering(self):
        self.upload(filename="scifi1.png", category="SciFi")
        self.upload(filename="art1.png", category="Art")

        # Search by matching category
        res = self.client.get("/?q=SciFi")
        self.assertEqual(res.status_code, 200)
        self.assertIn("SciFi", res.get_data(as_text=True))

        # Search by non-existent query
        res_empty = self.client.get("/?q=NonExistentQuery123")
        self.assertEqual(res_empty.status_code, 200)
        self.assertIn("No results matching query", res_empty.get_data(as_text=True))

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
        self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertIn("Permissions-Policy", res.headers)

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
        robots_res = self.client.get("/robots.txt")
        self.assertEqual(robots_res.status_code, 200)
        self.assertEqual(robots_res.mimetype, "text/plain")
        self.assertIn("Disallow: /delete/", robots_res.get_data(as_text=True))
        self.assertIn("Sitemap:", robots_res.get_data(as_text=True))

        sitemap_res = self.client.get("/sitemap.xml")
        self.assertEqual(sitemap_res.status_code, 200)
        self.assertEqual(sitemap_res.mimetype, "application/xml")
        self.assertIn("<urlset", sitemap_res.get_data(as_text=True))
        self.assertIn("<loc>", sitemap_res.get_data(as_text=True))

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
