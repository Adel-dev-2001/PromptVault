import importlib.util
import io
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

from PIL import Image


class PromptVaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_directory = Path.cwd()
        cls.workspace = tempfile.TemporaryDirectory()
        os.chdir(cls.workspace.name)
        spec = importlib.util.spec_from_file_location('portfolio_test_app', Path(__file__).with_name('app.py'))
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)
        cls.module.app.config.update(TESTING=True, SECRET_KEY='test-only-not-a-deployment-secret')

    @classmethod
    def tearDownClass(cls):
        cls.module.db._disconnect()
        cls.module.db._engine.dispose()
        os.chdir(cls.previous_directory)
        cls.workspace.cleanup()

    def setUp(self):
        self.client = self.module.app.test_client()
        self.module.db.execute('DELETE FROM images')

    def csrf_token(self):
        page = self.client.get('/add').get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)

    def upload(self, filename='example.png', contents=None, category='Examples'):
        if contents is None:
            stream = io.BytesIO()
            Image.new('RGB', (4, 4), 'white').save(stream, format='PNG')
            contents = stream.getvalue()
        return self.client.post('/add', data={
            'csrf_token': self.csrf_token(),
            'image_file': (io.BytesIO(contents), filename),
            'prompt_text': 'A test image',
            'category': category,
        }, content_type='multipart/form-data')

    def test_gallery_and_headers(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')

    def test_missing_csrf_is_rejected(self):
        self.assertEqual(self.client.post('/add', data={}).status_code, 400)
        self.assertEqual(self.client.post('/delete/1').status_code, 400)
        self.assertEqual(self.client.post('/favorite/1').status_code, 400)
        self.assertEqual(self.client.post('/edit/1').status_code, 400)

    def test_valid_image_upload_and_download(self):
        self.assertEqual(self.upload().status_code, 302)
        row = self.module.db.execute('SELECT * FROM images')[0]
        download_path = row['image_path'].replace('/static/uploads/', '')
        with self.client.get('/download/' + download_path) as response:
            self.assertEqual(response.status_code, 200)

    def test_fake_image_rejected(self):
        self.assertEqual(self.upload('fake.png', b'not an image').status_code, 400)
        self.assertEqual(self.module.db.execute('SELECT * FROM images'), [])

    def test_mismatched_extension_rejected(self):
        self.assertEqual(self.upload('wrong.jpg').status_code, 400)
        self.assertEqual(self.module.db.execute('SELECT * FROM images'), [])

    def test_invalid_category_rejected(self):
        self.upload(category='../outside')
        self.assertEqual(self.module.db.execute('SELECT * FROM images'), [])
        self.assertFalse(self.module.valid_category('Example\n'))

    def test_favorite_filter_survives_sort(self):
        self.upload()
        identifier = self.module.db.execute('SELECT id FROM images')[0]['id']
        self.client.post(f'/favorite/{identifier}', data={'csrf_token': self.csrf_token()})
        html = self.client.get('/?favorites=1').get_data(as_text=True)
        self.assertIn('sort=oldest', html)
        self.assertIn('favorites=1', html)
        self.assertEqual(self.module.db.execute('SELECT is_favorite FROM images')[0]['is_favorite'], 1)

    def test_edit_and_delete(self):
        self.upload()
        row = self.module.db.execute('SELECT * FROM images')[0]
        image_path = Path(row['image_path'].lstrip('/'))
        self.assertTrue(image_path.exists())
        response = self.client.post(f"/edit/{row['id']}", data={
            'csrf_token': self.csrf_token(), 'prompt_text': 'Updated', 'category': 'Revised',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.module.db.execute('SELECT prompt_text FROM images')[0]['prompt_text'], 'Updated')
        updated_row = self.module.db.execute('SELECT image_path FROM images WHERE id = ?', row['id'])[0]
        moved_path = Path(updated_row['image_path'].lstrip('/'))
        self.assertTrue(moved_path.exists())
        self.client.post(f"/delete/{row['id']}", data={'csrf_token': self.csrf_token()})
        self.assertEqual(self.module.db.execute('SELECT * FROM images'), [])
        self.assertFalse(moved_path.exists())
        self.assertFalse(image_path.exists())

    def test_edit_category_moves_image_file(self):
        self.assertEqual(self.upload(category='Examples').status_code, 302)
        row = self.module.db.execute('SELECT * FROM images')[0]
        old_path = Path(row['image_path'].lstrip('/'))
        self.assertTrue(old_path.exists())

        response = self.client.post(f"/edit/{row['id']}", data={
            'csrf_token': self.csrf_token(),
            'prompt_text': 'A test image',
            'category': 'Revised',
        })
        self.assertEqual(response.status_code, 302)

        updated = self.module.db.execute('SELECT * FROM images WHERE id = ?', row['id'])[0]
        new_path = Path(updated['image_path'].lstrip('/'))
        self.assertEqual(updated['category'], 'Revised')
        self.assertNotEqual(updated['image_path'], row['image_path'])
        self.assertTrue(new_path.exists())
        self.assertFalse(old_path.exists())

    def test_request_size_limit(self):
        original_limit = self.module.app.config['MAX_CONTENT_LENGTH']
        token = self.csrf_token()
        self.module.app.config['MAX_CONTENT_LENGTH'] = 512
        try:
            response = self.client.post('/add', data={
                'csrf_token': token, 'prompt_text': 'x' * 2048,
            })
            self.assertEqual(response.status_code, 413)
        finally:
            self.module.app.config['MAX_CONTENT_LENGTH'] = original_limit

    def test_download_traversal_rejected(self):
        self.assertEqual(self.client.get('/download/../prompts.db').status_code, 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)