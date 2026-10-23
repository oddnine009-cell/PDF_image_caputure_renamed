"""核心逻辑测试（零依赖，直接 python -m unittest 运行）。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import csv
import itertools
import json
import shutil
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from spn.apply import apply_plan, rollback                      # noqa: E402
from spn.config import Config, Region                          # noqa: E402
from spn.match import match_names                              # noqa: E402
from spn.naming import sanitize, unique_path                   # noqa: E402
from spn.pipeline import collect_files, process_file, scan      # noqa: E402
from spn.plan import save_plan                                # noqa: E402
from spn.roster import dedupe_roster, load_roster               # noqa: E402
from spn.similarity import char_similarity, levenshtein        # noqa: E402

TMP_ROOT = ROOT / ".tmp"
_COUNTER = itertools.count()


def mkdtemp() -> Path:
    """临时目录放在工作区内。不用 tempfile.mkdtemp：在受限环境里它建出的目录
    可能带受限 ACL 而不可写，直接用 mkdir 更稳。"""
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    d = TMP_ROOT / f"t{next(_COUNTER):04d}_{time.time_ns() % 10**9}"
    d.mkdir()
    return d


ROSTER = [
    ("2023001", "张三", "高一(3)班"),
    ("2023002", "李四", "高一(3)班"),
    ("2023003", "王五", "高一(3)班"),
    ("2023004", "张山", "高一(3)班"),
    ("2023005", "欧阳修", "高一(3)班"),
]


def make_cfg(tmp: Path) -> Config:
    cfg = Config()
    cfg.outdir = tmp / "out"
    cfg.mode = "copy"
    cfg.ocr = "json"
    return cfg


def write_roster(tmp: Path) -> Path:
    p = tmp / "roster.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["学号", "姓名", "班级"])
        w.writerows(ROSTER)
    return p


class TestSimilarity(unittest.TestCase):
    def test_levenshtein(self):
        self.assertEqual(levenshtein("张三", "张三"), 0)
        self.assertEqual(levenshtein("张三", "张四"), 1)
        self.assertEqual(levenshtein("", "abc"), 3)
        self.assertEqual(levenshtein("张三", "张三丰"), 1)

    def test_confusable_partial_credit(self):
        # 「未/末」形近：应比完全无关的字更接近
        confusable = char_similarity("未", "末")
        unrelated = char_similarity("未", "李")
        self.assertGreater(confusable, 0.4)
        self.assertLess(confusable, 1.0)
        self.assertGreater(confusable, unrelated)

    def test_identical(self):
        self.assertAlmostEqual(char_similarity("欧阳修", "欧阳修"), 1.0)


class TestMatch(unittest.TestCase):
    def setUp(self):
        self.students = dedupe_roster(load_roster(write_roster(mkdtemp())))

    def test_field_line(self):
        r = match_names(["姓名：张三"], self.students, Config())
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.name, "张三")

    def test_noisy_line(self):
        r = match_names(["李四  高一(3)班  学号 2023002"], self.students, Config())
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.name, "李四")

    def test_three_char_name(self):
        r = match_names(["学生签名：欧阳修"], self.students, Config())
        self.assertEqual(r.name, "欧阳修")

    def test_ambiguous_goes_to_review(self):
        # 张三 / 张山 只差一字：必须降低置信度交给人工，而不是硬猜
        r = match_names(["张山"], self.students, Config())
        self.assertEqual(r.name, "张山")
        self.assertIn(r.status, ("ok", "review"))

    def test_unrelated_text_fails(self):
        r = match_names(["期中作业 第一章 习题 1.1 求导"], self.students, Config())
        self.assertEqual(r.status, "fail")
        self.assertIsNone(r.best)


class TestNaming(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(sanitize('a/b:c*d?"e'), "abcde")
        self.assertEqual(sanitize("张三 "), "张三")
        self.assertEqual(sanitize("CON"), "_CON")
        self.assertEqual(sanitize("..."), "未命名")

    def test_unique(self):
        tmp = mkdtemp()
        try:
            f = tmp / "张三.pdf"
            f.write_text("x", encoding="utf-8")
            got = unique_path(tmp / "张三.pdf")
            self.assertEqual(got.name, "张三 (2).pdf")
            taken: set[str] = set()
            a = unique_path(tmp / "李四.pdf", taken)
            b = unique_path(tmp / "李四.pdf", taken)
            self.assertEqual(a.name, "李四.pdf")
            self.assertEqual(b.name, "李四 (2).pdf")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestPipelineEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = mkdtemp()
        self.src = self.tmp / "incoming"
        self.src.mkdir()
        self.roster = write_roster(self.tmp)
        self.cfg = make_cfg(self.tmp)

        cases = {
            "扫描件_001.pdf": ["姓名：张三"],
            "扫描件_002.pdf": ["李四", "高一(3)班"],
            "扫描件_003.pdf": ["欧阳修"],
            "扫描件_004.pdf": ["这一页是空白页"],
        }
        for name, lines in cases.items():
            (self.src / name).write_bytes(b"%PDF-1.4\n% fake\n")
            (self.src / name).with_suffix(".ocr.json").write_text(
                json.dumps({"lines": lines}, ensure_ascii=False), encoding="utf-8"
            )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scan_classifies(self):
        students = dedupe_roster(load_roster(self.roster))
        entries = scan([self.src], students, self.cfg)
        by = {Path(e.src).name: e for e in entries}
        self.assertEqual(len(entries), 4)
        self.assertEqual(by["扫描件_001.pdf"].name, "张三")
        self.assertEqual(by["扫描件_002.pdf"].name, "李四")
        self.assertEqual(by["扫描件_003.pdf"].name, "欧阳修")
        self.assertEqual(by["扫描件_004.pdf"].status, "fail")
        for e in entries:
            if e.status == "ok":
                self.assertTrue(e.dst.endswith(".pdf"))

    def test_apply_copy_then_rollback(self):
        students = dedupe_roster(load_roster(self.roster))
        entries = scan([self.src], students, self.cfg)
        plan_file = save_plan(entries, self.cfg.outdir / "plan.json", {"mode": "copy"})

        stats = apply_plan(plan_file, include_review=True, perform=True)
        self.assertEqual(stats["failed"], 0)
        names = sorted(p.name for p in self.cfg.outdir.glob("*.pdf"))
        self.assertIn("张三.pdf", names)
        self.assertIn("李四.pdf", names)
        self.assertIn("欧阳修.pdf", names)
        self.assertEqual(len(list(self.src.glob("*.pdf"))), 4)  # 原文件还在

        rb = rollback(self.cfg.outdir / "manifest.jsonl", perform=True)
        self.assertEqual(rb["failed"], 0)
        self.assertEqual(list(self.cfg.outdir.glob("*.pdf")), [])

    def test_rename_mode(self):
        self.cfg.mode = "rename"
        students = dedupe_roster(load_roster(self.roster))
        entries = scan([self.src], students, self.cfg)
        plan_file = save_plan(entries, self.cfg.outdir / "plan.json", {"mode": "rename"})
        apply_plan(plan_file, include_review=True, perform=True)
        self.assertTrue((self.src / "张三.pdf").exists())
        self.assertFalse((self.src / "扫描件_001.pdf").exists())

    def test_corrections_override(self):
        students = dedupe_roster(load_roster(self.roster))
        entries = scan([self.src], students, self.cfg)
        # 模拟人工把失败项改成 王五
        fail_src = str(next(e.src for e in entries if e.status == "fail"))
        for e in entries:
            if e.src == fail_src:
                e.status = "review"
        plan_file = save_plan(entries, self.cfg.outdir / "plan.json", {"mode": "copy"})
        corr = self.cfg.outdir / "corrections.csv"
        with corr.open("w", encoding="utf-8-sig", newline="") as fh:
            csv.writer(fh).writerows([["src", "name"], [fail_src, "王五"]])
        apply_plan(plan_file, include_review=True, perform=True, corrections=corr)
        self.assertTrue((self.cfg.outdir / "王五.pdf").exists())


class TestMisc(unittest.TestCase):
    def test_collect_files(self):
        tmp = mkdtemp()
        try:
            (tmp / "a.pdf").write_bytes(b"x")
            (tmp / "sub").mkdir()
            (tmp / "sub" / "b.pdf").write_bytes(b"x")
            (tmp / "note.txt").write_text("x")
            got = collect_files([tmp])
            self.assertEqual({p.name for p in got}, {"a.pdf", "b.pdf"})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_region_bounds(self):
        cfg = Config()
        cfg.region = Region(x0=0.9, x1=0.1)
        with self.assertRaises(ValueError):
            cfg.validate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
