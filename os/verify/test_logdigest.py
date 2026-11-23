"""Deterministic log digest + the log.digest / log.lines tools of the tool plane."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import aiws_logdigest as D
import aiws_toolplane as plane


def numbered(texts, start=1):
    return list(enumerate(texts, start))


class Digest(unittest.TestCase):
    def test_numbers_are_ignored_when_merging_and_the_first_line_is_kept(self):
        r = D.digest(numbered(["2025-01-01 00:00:01 INFO worker 17 done in 40 ms", "2025-01-01 00:00:02 ERROR disk full",
                               "2025-01-01 00:00:03 INFO worker 9 done in 12 ms", "2025-01-01 00:00:04 INFO worker 88 done in 7 ms"]))
        self.assertEqual([(e["line"], e["count"]) for e in r["entries"]], [(1, 3), (2, 1)])
        self.assertEqual(r["entries"][0]["text"], "INFO worker 17 done in 40 ms")            # verbatim, first occurrence, timestamp removed
        self.assertEqual((r["totalLines"], r["distinct"]), (4, 2))

    def test_levels_are_counted_from_the_raw_lines(self):
        r = D.digest(numbered(["INFO a", "ERROR b", "ERROR c", "WARN d", "no level here", "DEBUG e"]))
        self.assertEqual(r["levels"], {"INFO": 1, "ERROR": 2, "WARN": 1, "DEBUG": 1})

    def test_timestamp_styles_are_stripped(self):
        for line in ("2025-03-14T02:05:52.123Z hello", "[2025-03-14 02:05:52,123] hello", "02:05:52 hello", "Mar 14 02:05:52 hello", "1710381952 hello"):
            self.assertEqual(D.strip_timestamp(line), "hello", line)
        self.assertEqual(D.strip_timestamp("no timestamp"), "no timestamp")

    def test_blank_lines_are_skipped_but_counted_in_numbering(self):
        r = D.digest(numbered(["a", "", "   ", "b"]))
        self.assertEqual([(e["line"], e["text"]) for e in r["entries"]], [(1, "a"), (4, "b")])
        self.assertEqual(r["totalLines"], 4)

    def test_over_budget_keeps_rare_messages_and_restores_line_order(self):
        lines = ["INFO common message %d" % i for i in range(300)]
        lines += ["FATAL unique problem %s here" % chr(97 + k) * 1 for k in range(30)]
        rows = []
        for n, t in enumerate(lines, 1):
            rows.append((n, t if t.startswith("FATAL") else t))
        # the 30 FATAL lines differ only by a letter, so they are 30 distinct templates; the common line is ONE template x300
        r = D.digest(rows, budget_chars=600)
        self.assertGreater(r["omittedFrequent"], 0)
        numbers = [e["line"] for e in r["entries"]]
        self.assertEqual(numbers, sorted(numbers))
        self.assertTrue(all(e["count"] == 1 for e in r["entries"]))                          # the x300 message was the one dropped
        self.assertLessEqual(sum(len(e["text"]) + 8 for e in r["entries"]), 900)

    def test_a_single_early_rare_message_survives_a_flood(self):
        rows = [(1, "WARN free space is 0 bytes")] + [(n, "INFO tick %d" % n) for n in range(2, 5000)]
        r = D.digest(rows, budget_chars=300)
        self.assertIn(1, [e["line"] for e in r["entries"]])

    def test_long_lines_are_cut_and_template_cap_is_counted(self):
        r = D.digest(numbered(["x" * 2000]))
        self.assertEqual(len(r["entries"][0]["text"]), D.MAX_LINE_CHARS)
        with patch.object(D, "MAX_GROUPS", 3):
            r = D.digest(numbered(["a one", "b two", "c three", "d four", "e five"]))
            self.assertEqual((r["distinct"], r["otherUncounted"]), (3, 2))

    def test_render_is_compact_and_verbatim(self):
        text = D.render_digest(D.digest(numbered(["INFO a 1", "INFO a 2", "ERROR boom"])))
        self.assertIn("L1 x2 INFO a 1", text)
        self.assertIn("L3 ERROR boom", text)
        self.assertIn("ERROR=1", text)


class Files(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.p = Path(self.t.name)

    def tearDown(self):
        self.t.cleanup()

    def test_line_range_basics_clipping_and_cut(self):
        f = self.p / "a.log"
        f.write_text("\n".join("line %d %s" % (i, "y" * 500 if i == 3 else "") for i in range(1, 501)))
        r = D.line_range(f, 2, 4)
        self.assertEqual([x["line"] for x in r["lines"]], [2, 3, 4])
        self.assertEqual(len(r["lines"][1]["text"]), D.MAX_LINE_CHARS)
        r = D.line_range(f, 10, 1000)
        self.assertEqual((len(r["lines"]), r["end"]), (D.MAX_RANGE, 10 + D.MAX_RANGE - 1))
        self.assertEqual(D.line_range(f, 9999, 10005)["lines"], [])
        self.assertIn("fewer lines", D.line_range(f, 9999, 10005)["note"])
        for bad in ((0, 5), (5, 4), ("a", 3), (None, 3), (True, 3), ("no digits here", 9)):
            with self.assertRaises(D.LogError):
                D.line_range(f, *bad)
        # what a real 9B passed: a whole digest entry, or L-prefixed numbers
        for start, end in (("L2", "L4"), ("line 2", "line 4"), ("L2 WARN free space on /data is 0 bytes", "}}} 4"), ("2", 4)):
            self.assertEqual([x["line"] for x in D.line_range(f, start, end)["lines"]], [2, 3, 4], (start, end))

    def test_binary_and_oversized_files_are_refused(self):
        b = self.p / "b.bin"
        b.write_bytes(b"abc\x00def")
        with self.assertRaises(D.LogError):
            D.digest_file(b)
        big = self.p / "big.log"
        big.write_text("x\n" * 10)
        with patch.object(D, "MAX_FILE", 5), self.assertRaises(D.LogError):
            D.digest_file(big)
        with self.assertRaises(D.LogError):
            D.digest_file(self.p)                                                            # a directory

    def test_invalid_utf8_does_not_crash(self):
        f = self.p / "c.log"
        f.write_bytes(b"ok line\n\xff\xfe broken \xc3\x28 line\nlast\n")
        r = D.digest_file(f)
        self.assertEqual(r["totalLines"], 3)


class ToolPlane(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.root = Path(self.t.name) / "project"
        self.root.mkdir()
        self.old = os.environ.get("AIWS_WORKSPACE")
        os.environ["AIWS_WORKSPACE"] = str(self.root)
        self.guard = patch("aiws_toolplane.protect_guest_workspace", return_value=True)
        self.guard.start()

    def tearDown(self):
        self.guard.stop()
        os.environ.pop("AIWS_WORKSPACE", None) if self.old is None else os.environ.__setitem__("AIWS_WORKSPACE", self.old)
        self.t.cleanup()

    def test_the_tools_are_registered_as_read_only_with_required_fields(self):
        cat = {t["name"]: t for t in plane.catalog()}
        self.assertEqual(cat["log.digest"]["inputSchema"]["required"], ["path"])
        self.assertEqual(cat["log.lines"]["inputSchema"]["required"], ["path", "start", "end"])
        self.assertTrue({"log.digest", "log.lines"} <= plane.READ_TOOLS)
        self.assertFalse({"log.digest", "log.lines"} & plane.FILE_WRITE_TOOLS)

    def test_digest_and_lines_work_through_invoke_and_a_log_larger_than_file_read_allows(self):
        log = self.root / "build.log"
        log.write_text("".join("2025-01-01 00:00:%02d INFO step %d ok\n" % (i % 60, i) for i in range(1, 20001)) + "ERROR link failed: undefined symbol foo\n")
        self.assertGreater(log.stat().st_size, plane.MAX_TEXT)
        with self.assertRaises(ValueError):
            plane.invoke("file.read", {"path": "build.log"})                                  # the old tool cannot read it
        d = plane.invoke("log.digest", {"path": "build.log"})
        self.assertEqual(d["totalLines"], 20001)
        self.assertEqual([e["line"] for e in d["entries"]], [1, 20001])
        self.assertEqual(d["entries"][1]["text"], "ERROR link failed: undefined symbol foo")
        r = plane.invoke("log.lines", {"path": "build.log", "start": "19999", "end": "20001"})
        self.assertEqual([x["line"] for x in r["lines"]], [19999, 20000, 20001])

    def test_confinement_is_the_same_as_every_other_tool(self):
        (self.root / "ok.log").write_text("a\n")
        for bad in ("../x.log", "/etc/passwd", ".git/config", "a\\b"):
            with self.assertRaises(ValueError, msg=bad):
                plane.invoke("log.digest", {"path": bad})
        (self.root / "link.log").symlink_to(self.root / "ok.log")
        with self.assertRaises(ValueError):
            plane.invoke("log.digest", {"path": "link.log"})
        with self.assertRaises(ValueError):
            plane.invoke("log.lines", {"path": "ok.log", "start": "0", "end": "3"})           # a LogError becomes a plain ValueError
        with self.assertRaises(ValueError):
            plane.invoke("log.lines", {"path": "ok.log", "start": "1"})                       # missing field


if __name__ == "__main__":
    unittest.main()
