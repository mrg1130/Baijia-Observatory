import json
import unittest
from unittest.mock import Mock

from studio.desktop_js import read_snapshot


class NativeWebviewSnapshotTest(unittest.TestCase):
    def test_cocoa_and_webview2_return_the_same_chinese_snapshot(self):
        expected = {'title': '百家观测', 'text': '数据概览', 'manual': True}
        plain = json.dumps(expected, ensure_ascii=False)
        for engine_result in [plain, json.dumps(plain)]:
            with self.subTest(result=engine_result):
                window = Mock()
                window.run_js.return_value = engine_result
                self.assertEqual(read_snapshot(window, '({})'), expected)

    def test_unloaded_document_has_no_snapshot(self):
        window = Mock()
        window.run_js.return_value = None
        self.assertEqual(read_snapshot(window, '({})'), {})
