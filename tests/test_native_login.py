import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self):
        for handler in list(self.handlers):
            handler()


class Events:
    def __init__(self):
        self.closed = Event()
        self.loaded = Event()


class Window:
    def __init__(self):
        self.events = Events()
        self.clear_count = 0
        self.loaded_urls = []
        self.destroyed = False

    def clear_cookies(self):
        self.clear_count += 1

    def load_url(self, url):
        self.loaded_urls.append(url)

    def get_current_url(self):
        return self.loaded_urls[-1] if self.loaded_urls else 'https://www.baidu.com/'

    def get_cookies(self):
        return []

    def show(self):
        pass

    def restore(self):
        pass

    def destroy(self):
        self.destroyed = True


class NativeLoginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.window = None
        fake_webview = types.ModuleType('webview')

        def create_window(*args, **kwargs):
            cls.window = Window()
            return cls.window

        fake_webview.create_window = create_window
        with patch.dict(sys.modules, {'webview': fake_webview}):
            sys.modules.pop('studio.native_login', None)
            cls.native_login = importlib.import_module('studio.native_login')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='baijia-native-login-', dir=Path.cwd())
        self.data_patch = patch.object(self.native_login, 'DATA', Path(self.temp.name))
        self.cookie_patch = patch.object(self.native_login, 'set_cookie')
        self.data_patch.start()
        self.set_cookie = self.cookie_patch.start()
        self.client = self.native_login.NativeBaidu()

    def tearDown(self):
        self.cookie_patch.stop()
        self.data_patch.stop()
        self.temp.cleanup()

    def test_relogin_clears_persistent_cookies_after_window_loads(self):
        result = self.client.start('owner', replace=True)
        marker = Path(self.temp.name) / 'login-reset-owner.pending'
        self.assertTrue(marker.exists())
        self.assertEqual(result['status'], 'waiting')
        self.assertIn('清理旧登录态', result['message'])
        self.set_cookie.assert_called_once_with('owner', '')

        self.window.events.loaded.fire()

        self.assertEqual(self.window.clear_count, 1)
        self.assertFalse(marker.exists())
        self.assertEqual(self.window.loaded_urls[-1], 'https://www.baidu.com/')
        self.assertIsNone(self.client.reset_owner)

    def test_disconnect_without_an_open_window_leaves_a_durable_reset(self):
        self.client.disconnect('owner')
        self.assertTrue((Path(self.temp.name) / 'login-reset-owner.pending').exists())
        self.set_cookie.assert_called_once_with('owner', '')


if __name__ == '__main__':
    unittest.main()
