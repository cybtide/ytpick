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

    def test_embed_cover_and_metadata(self):
        o = self.opts(embed=True)
        keys = [p["key"] for p in o["postprocessors"]]
        self.assertTrue(o["writethumbnail"])
        self.assertEqual(keys[0], "FFmpegThumbnailsConvertor")
        self.assertEqual(keys[-1], "EmbedThumbnail")
        self.assertIn("FFmpegMetadata", keys)

    def test_embed_skipped_for_plain_audio(self):
        self.assertNotIn("writethumbnail", self.opts(mode="audio", embed=True))

    def test_cut_section(self):
        o = self.opts(cut_start=80, cut_end=225)
        self.assertIn("download_ranges", o)
        self.assertTrue(o["force_keyframes_at_cuts"])
        self.assertIn(" clip", o["outtmpl"])
        self.assertNotIn("download_ranges", self.opts())

    def test_mp4_merge(self):
        self.assertEqual(self.opts(mode="mp4")["merge_output_format"], "mp4")


class HelperTests(unittest.TestCase):
    def test_parse_time(self):
        self.assertEqual(ytpick.parse_time("1:20"), 80)
        self.assertEqual(ytpick.parse_time("1:02:03"), 3723)
        self.assertEqual(ytpick.parse_time("45.5"), 45.5)
        self.assertIsNone(ytpick.parse_time("  "))
        with self.assertRaises(ValueError):
            ytpick.parse_time("a:b")
        with self.assertRaises(ValueError):
            ytpick.parse_time("1:2:3:4")

    def test_parse_clock(self):
        self.assertEqual(ytpick.parse_clock("01:30"), 90)
        with self.assertRaises(ValueError):
            ytpick.parse_clock("25:00")

    def test_in_window_overnight(self):
        start, end = 22 * 60, 6 * 60
        self.assertTrue(ytpick.in_window(23 * 60, start, end))
        self.assertTrue(ytpick.in_window(5 * 60, start, end))
        self.assertFalse(ytpick.in_window(12 * 60, start, end))

    def test_in_window_same_day(self):
        self.assertTrue(ytpick.in_window(120, 60, 360))
        self.assertFalse(ytpick.in_window(400, 60, 360))
        self.assertTrue(ytpick.in_window(400, 100, 100))

    def test_detect_browsers(self):
        from unittest import mock
        home = Path(tempfile.mkdtemp())
        (home / ".mozilla" / "firefox").mkdir(parents=True)
        with mock.patch.object(Path, "home", return_value=home), \
                mock.patch.dict(os.environ, {"LOCALAPPDATA": str(home / "x"), "APPDATA": str(home / "y")}):
            self.assertEqual(ytpick.detect_browsers(), ["firefox"])

    def test_playlist_query(self):
        spec = ytpick.parse_query("https://www.youtube.com/playlist?list=PLabc123")
        self.assertEqual(spec["kind"], "playlist")
        self.assertEqual(spec["url"], "https://www.youtube.com/playlist?list=PLabc123")


class StatsTests(unittest.TestCase):
    def test_compute_stats(self):
        from datetime import datetime
        today = datetime(2026, 10, 8, 12, 0, 0)
        downloads = {
            "a": {"mode": "mkv", "channel": "X", "at": "2026-10-08 09:00:00", "size": 1000, "duration": 60},
            "b": {"mode": "mp3", "channel": "X", "at": "2026-10-05 09:00:00", "size": 500, "duration": 120},
            "c": {"mode": "mp4", "channel": "Y", "at": "2026-09-20 09:00:00", "size": 200, "duration": 30},
            "d": {"mode": "audio", "channel": "Z", "at": "2025-01-01 09:00:00"},
        }
        st = ytpick.compute_stats(downloads, {"a", "b", "c", "d", "old"}, today)
        self.assertEqual(st["total"], 4)
        self.assertEqual(st["videos"], 2)
        self.assertEqual(st["music"], 2)
        self.assertEqual(st["without_record"], 1)
        self.assertEqual((st["today"], st["week"], st["month"]), (1, 2, 3))
        self.assertEqual(st["size"], 1700)
        self.assertEqual(st["duration"], 210)
        self.assertEqual(st["channels"][0], ("X", 2))
        self.assertEqual(len(st["months"]), 12)
        self.assertEqual(st["months"][-1], ("2026-10", 2))
        self.assertEqual(dict(st["months"])["2026-09"], 1)

    def test_formatting(self):
        self.assertEqual(ytpick.fmt_size(512), "512 B")
        self.assertEqual(ytpick.fmt_size(1536), "1.5 KB")
        self.assertEqual(ytpick.fmt_hours(3660), "1:01 h")

    def test_empty(self):
        st = ytpick.compute_stats({}, set())
        self.assertEqual((st["total"], st["size"]), (0, 0))


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

    def test_filters(self):
        items = self.items()
        items[1]["duration"] = 30
        items[2]["duration"] = 7200
        self.show(items)
        total = len(self.app.tree.get_children())
        self.app.f_min.set("1")
        self.app.update()
        self.assertEqual(len(self.app.tree.get_children()), total - 2)
        self.app.reset_filters()
        self.app.f_verified.set(True)
        self.app.update()
        self.assertTrue(all(self.app.by_id[i].get("verified") for i in self.app.tree.get_children()))
        self.app.reset_filters()
        self.app.update()
        self.assertEqual(len(self.app.tree.get_children()), total)

    def test_date_filter(self):
        items = self.items(3)
        items[0]["date"] = "20200101"
        self.show(items)
        label = ytpick._(ytpick.DATE_RANGES[1][0])
        self.app.f_range.set(label)
        self.app.update()
        self.assertNotIn("vid00000000", self.app.tree.get_children())
        self.app.reset_filters()

    def test_playlist_limit_shows_all_items(self):
        items = self.items(60)
        self.app.token += 1
        self.app._show(items, self.app.token, "playlist", ytpick.CHANNEL_POOL)
        self.app.update()
        self.assertEqual(len(self.app.tree.get_children()), 60)
        self.show(items)
        self.assertEqual(len(self.app.tree.get_children()), ytpick.RESULTS)

    def test_duplicate_download_prompt(self):
        from unittest import mock
        self.show(self.items())
        item = self.app.items[0]
        self.app.history.add(item["id"])
        self.app.paused = True
        before = len(self.app.jobs)
        with mock.patch.object(ytpick.messagebox, "askyesnocancel", return_value=False):
            self.app.enqueue([item], dict(ytpick.DEFAULT_FMT), "mkv")
        self.assertEqual(len(self.app.jobs), before)
        with mock.patch.object(ytpick.messagebox, "askyesnocancel", return_value=True):
            self.app.enqueue([item], dict(ytpick.DEFAULT_FMT), "mp3")
        self.assertEqual(len(self.app.jobs), before + 1)
        with mock.patch.object(ytpick.messagebox, "askyesnocancel", return_value=None):
            self.app.cancel_jobs(all_jobs=True)
            self.app.enqueue([item], dict(ytpick.DEFAULT_FMT), "mkv")
        self.assertEqual(len(self.app.jobs), before + 2 - 1)
        self.app.history.discard(item["id"])
        self.app.paused = False
        self.app.q_win.destroy()

    def test_rate_limit_applied(self):
        self.show(self.items())
        self.app.paused = True
        self.app.rate_mb = 2
        self.app.enqueue([self.app.items[3]], dict(ytpick.DEFAULT_FMT), "mkv")
        self.assertEqual(self.app.jobs[-1]["base"]["ratelimit"], 2 * 1048576)
        self.app.rate_mb = 0
        self.app.cancel_jobs(all_jobs=True)
        self.app.paused = False
        self.app.q_win.destroy()

    def test_stats_window(self):
        self.app.downloads["vid00000002"] = {"title": "T", "channel": "C", "mode": "mp3", "height": 0,
                                             "at": ytpick.now(), "file": "", "size": 2048, "duration": 90}
        self.app.open_stats()
        self.app.update()
        values = [self.app.s_trees["sum"].item(i, "values") for i in self.app.s_trees["sum"].get_children()]
        self.assertTrue(any(str(v[1]) == "1" for v in values if v[0] == ytpick._("Downloads gesamt")))
        self.assertEqual(len(self.app.s_trees["month"].get_children()), 12)
        self.app.s_win.destroy()
        self.app.downloads.pop("vid00000002")

    def test_history_window(self):
        self.app.downloads["vid00000001"] = {"title": "T", "channel": "C", "mode": "mp3", "height": 0,
                                             "at": "2026-01-01 10:00:00", "file": "/nonexistent/x.mp3"}
        self.app.open_history()
        self.app.update()
        self.assertIn("vid00000001", self.app.h_tree.get_children())
        self.app.h_tree.selection_set("vid00000001")
        self.app.remove_history()
        self.assertNotIn("vid00000001", self.app.downloads)
        self.app.h_win.destroy()

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
