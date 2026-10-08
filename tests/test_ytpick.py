import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ytpick

VID = "abcdefghijk"


class VerifyDownloadTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.file = self.dir / f"Title [{VID}].mkv"
        self.file.write_bytes(b"data")

    def info(self, vid=VID, path=None):
        return {"id": vid, "requested_downloads": [{"filepath": str(path or self.file)}]}

    def test_accepts_matching_file(self):
        ok, reason, path = ytpick.verify_download(self.info(), VID, self.dir)
        self.assertTrue(ok, reason)
        self.assertEqual(path, str(self.file))

    def test_rejects_wrong_id(self):
        ok, _, _ = ytpick.verify_download(self.info(vid="zzzzzzzzzzz"), VID, self.dir)
        self.assertFalse(ok)

    def test_rejects_empty_file(self):
        self.file.write_bytes(b"")
        ok, _, _ = ytpick.verify_download(self.info(), VID, self.dir)
        self.assertFalse(ok)

    def test_rejects_file_without_id_in_name(self):
        other = self.dir / "Title.mkv"
        other.write_bytes(b"data")
        ok, _, _ = ytpick.verify_download(self.info(path=other), VID, self.dir)
        self.assertFalse(ok)

    def test_rejects_file_outside_target_folder(self):
        elsewhere = Path(tempfile.mkdtemp()) / f"Title [{VID}].mkv"
        elsewhere.write_bytes(b"data")
        ok, _, _ = ytpick.verify_download(self.info(path=elsewhere), VID, self.dir)
        self.assertFalse(ok)

    def test_accepts_channel_subfolder(self):
        sub = self.dir / "Channel"
        sub.mkdir()
        f = sub / f"Title [{VID}].mkv"
        f.write_bytes(b"data")
        ok, _, _ = ytpick.verify_download(self.info(path=f), VID, self.dir)
        self.assertTrue(ok)

    def test_rejects_missing_info(self):
        ok, _, _ = ytpick.verify_download(None, VID, self.dir)
        self.assertFalse(ok)


class ParseQueryTests(unittest.TestCase):
    def test_plain_search(self):
        spec = ytpick.parse_query("lofi beats")
        self.assertEqual(spec["kind"], "search")
        self.assertTrue(spec["url"].startswith("ytsearch"))

    def test_handle_with_filter(self):
        spec = ytpick.parse_query("@someone training")
        self.assertEqual(spec["kind"], "channel")
        self.assertEqual(spec["term"], "training")
        self.assertTrue(spec["url"].endswith("/@someone/videos"))


class DownloadOptionsTests(unittest.TestCase):
    def opts(self, mode="mkv", **fmt):
        merged = {**ytpick.DEFAULT_FMT, **fmt}
        return ytpick.download_opts({}, Path("/out"), mode, merged, lambda d: None)

    def test_best_quality_default(self):
        self.assertEqual(self.opts()["format"], "bv*+ba/b")

    def test_height_limit(self):
        self.assertIn("height<=720", self.opts(height=720)["format"])

    def test_channel_folder_template(self):
        self.assertIn("%(channel)s", self.opts(channel_folder=True)["outtmpl"])
        self.assertNotIn("%(channel)s", self.opts()["outtmpl"])

    def test_subtitles_and_chapters(self):
        o = self.opts(subs=True, sub_langs="de, en", chapters=True)
        self.assertEqual(o["subtitleslangs"], ["de", "en"])
        keys = [p["key"] for p in o["postprocessors"]]
        self.assertIn("FFmpegEmbedSubtitle", keys)
        self.assertIn("FFmpegMetadata", keys)

    def test_audio_mode_ignores_video_options(self):
        o = self.opts(mode="audio", subs=True)
        self.assertEqual(o["format"], "bestaudio/best")
        self.assertNotIn("writesubtitles", o)

    def test_mp3_mode(self):
        o = self.opts(mode="mp3", subs=True, chapters=True)
        self.assertEqual(o["format"], "bestaudio/best")
        self.assertNotIn("writesubtitles", o)
        extract = [p for p in o["postprocessors"] if p["key"] == "FFmpegExtractAudio"][0]
        self.assertEqual(extract["preferredcodec"], "mp3")

    def test_mp4_merge(self):
        self.assertEqual(self.opts(mode="mp4")["merge_output_format"], "mp4")


class UpgradeTests(unittest.TestCase):
    def test_reports_pip_failure(self):
        from unittest import mock
        fake = mock.Mock(returncode=1, stderr="line one\nerror: externally-managed-environment", stdout="")
        with mock.patch("subprocess.run", return_value=fake):
            with self.assertRaises(RuntimeError) as ctx:
                ytpick.upgrade_ytdlp()
        self.assertIn("externally-managed", str(ctx.exception))

    def test_returns_installed_version(self):
        from unittest import mock
        fake = mock.Mock(returncode=0, stderr="", stdout="ok")
        with mock.patch("subprocess.run", return_value=fake), \
                mock.patch.object(ytpick, "installed_ytdlp_version", return_value="9.9.9"):
            self.assertEqual(ytpick.upgrade_ytdlp(), "9.9.9")


class NormalizeTests(unittest.TestCase):
    def test_verified_flag_is_optional(self):
        self.assertIsNone(ytpick.normalize({"id": VID}, None)["verified"])
        self.assertTrue(ytpick.normalize({"id": VID, "channel_is_verified": True}, None)["verified"])


class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            raise unittest.SkipTest("no display")
        home = Path(tempfile.mkdtemp())
        ytpick.STATE_FILE = home / "state.json"
        ytpick.CACHE_FILE = home / "cache.json"
        ytpick.LOG_FILE = home / "log.txt"
        ytpick.THUMB_DIR = home / "thumbs"
        try:
            cls.app = ytpick.App()
        except Exception as err:
            raise unittest.SkipTest(f"tk unavailable: {err}")
        cls.app.show_readme.set(False)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "app"):
            cls.app.destroy()

    def items(self, n=5):
        return [{"id": f"vid{i:08d}", "title": f"Video {i}", "channel": f"Ch {i % 2}",
                 "channel_id": f"UC{i % 2}", "duration": 60 * i, "views": 100 * i,
                 "date": "20260101", "verified": i % 2 == 0} for i in range(n)]

    def show(self, items):
        self.app.token += 1
        self.app._show(items, self.app.token, "test")
        self.app.update()

    def test_render_and_pin(self):
        self.show(self.items())
        self.assertEqual(len(self.app.tree.get_children()), 5)
        target = "vid00000003"
        self.app.tree.selection_set([target])
        self.app.toggle_pin()
        self.assertEqual(self.app.tree.get_children()[0], target)
        self.app.toggle_pin()
        self.assertNotIn(target, self.app.pinned)

    def test_pinned_survive_new_search(self):
        self.show(self.items())
        self.app.set_pin(["vid00000001"])
        self.show(self.items()[2:])
        self.assertIn("vid00000001", self.app.tree.get_children())
        self.app.set_pin(["vid00000001"])

    def test_column_settings(self):
        self.app.open_settings()
        self.app.set_order.reverse()
        self.app.set_vis.discard("dauer")
        self.app.apply_settings()
        shown = list(self.app.tree.cget("displaycolumns"))
        self.assertNotIn("dauer", shown)
        self.assertIn("titel", shown)
        self.assertEqual(shown, [k for k in self.app.col_order if k in self.app.col_visible])

    def test_format_dialog_opens(self):
        self.show(self.items())
        self.app.open_format_dialog([self.app.items[0]])
        self.app.update()
        self.assertTrue(self.app.fmt_win.winfo_exists())
        self.app.fmt_win.destroy()

    def test_enqueue_deduplicates(self):
        self.show(self.items())
        self.app.paused = True
        before = len(self.app.jobs)
        self.app.enqueue([self.app.items[0]], dict(ytpick.DEFAULT_FMT), "mkv")
        self.app.enqueue([self.app.items[0]], dict(ytpick.DEFAULT_FMT), "mkv")
        self.assertEqual(len(self.app.jobs), before + 1)
        self.app.cancel_jobs(all_jobs=True)
        self.app.paused = False
        self.app.q_win.destroy()


if __name__ == "__main__":
    unittest.main()
