"""상세 페이지에 반복되는 인라인 스크립트를 공용 파일로 뺀다 (사이트 1GB 한도 대응)."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build

BODY = "(function(){ var x = 1; })();" + " " * 500


class SharedScriptsTest(unittest.TestCase):
    def test_repeated_scripts_move_to_file(self):
        with tempfile.TemporaryDirectory() as d:
            shared = build.SharedScripts(d)
            page = f"<p>a</p><script>{BODY}</script><script>short()</script>"
            outs = [shared.apply(page) for _ in range(build.SHARED_SCRIPT_MIN_PAGES)]
            self.assertIn(BODY, outs[0])                          # 처음 몇 페이지는 인라인 그대로
            last = outs[-1]
            self.assertNotIn(BODY, last)
            self.assertIn('<script src="../assets/js/', last)
            self.assertIn("<script>short()</script>", last)       # 짧은 스크립트는 유지
            rel = last.split('src="../')[1].split('"')[0]
            self.assertEqual((Path(d) / rel).read_text(encoding="utf-8"), BODY)

    def test_page_data_and_typed_scripts_stay_inline(self):
        with tempfile.TemporaryDirectory() as d:
            shared = build.SharedScripts(d)
            chart = "<script>var pts = [1];" + " " * 500 + "</script>"
            ld = '<script type="application/ld+json">' + "{}" + " " * 500 + "</script>"
            for _ in range(build.SHARED_SCRIPT_MIN_PAGES + 1):
                out = shared.apply(chart + ld)
            self.assertEqual(out, chart + ld)


if __name__ == "__main__":
    unittest.main()
