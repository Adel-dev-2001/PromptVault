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
        invalid_categories = [
            "Fish #1",
            "a/b",
            "../outside",
            "..",
            "foo.",
            "Example\n",
            "foo\x00bar",
            "\u200f",
            "Arab\u200fic",
            "   ",
        ]
        for category in invalid_categories:
            with self.subTest(category=category):
                self.assertFalse(self.module.valid_category(category))
                res = self.upload(category=category)
                self.assertEqual(res.status_code, 400)
                self.assertEqual(self.module.db.execute("SELECT * FROM images"), [])

    def test_valid_unicode_and_spaced_categories_served(self):
        for category in ["تصميم", "فن رقمي", "Sci-Fi_Art 1"]:
            with self.subTest(category=category):
                self.assertTrue(self.module.valid_category(category))
                res = self.upload(filename=f"{category[:3]}.png", category=category)
                self.assertEqual(res.status_code, 302)
                row = self.module.db.execute(
                    "SELECT * FROM images WHERE category = ? ORDER BY id DESC LIMIT 1",
                    category.title(),
                )[0]
                self.assertNotIn("#", row["image_path"])
                with self.client.get(row["image_path"]) as img_res:
                    self.assertEqual(img_res.status_code, 200)
                download_path = row["image_path"].removeprefix("/static/uploads/")
                with self.client.get("/download/" + download_path) as dl_res:
                    self.assertEqual(dl_res.status_code, 200)

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
        traversal_paths = [
            "/download/../prompts.db",
            "/download/%2e%2e%2fprompts.db",
            "/download/%252e%252e%252fprompts.db",
            "/download/..%5cprompts.db",
            "/download/Examples%5c..%5cprompts.db",
            "/download/Examples/%2e%2e%2fprompts.db",
        ]
        for path in traversal_paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
        raw_res = self.client.get(
            "/download/raw",
            environ_base={"PATH_INFO": "/download/%2e%2e%2fprompts.db"},
        )
        self.assertEqual(raw_res.status_code, 404)

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
        file_path = Path(self.module.upload_path_from_url(row["image_path"]))
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
