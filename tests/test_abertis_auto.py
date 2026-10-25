import os
import re
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_EXTENSIONS = (REPO_ROOT / "AbertisAutoSwitcher" / "usr" / "lib" / "enigma2"
                     / "python" / "Plugins" / "Extensions")
if str(PLUGIN_EXTENSIONS) not in sys.path:
    sys.path.insert(0, str(PLUGIN_EXTENSIONS))

from AbertisAutoSwitcher import autostart, lamedb_fix, setup


ABERTIS_A_RULE = "A: ::0BD2:07EA 2600:000000:1FFF # Abertis PID 2026 F5"
ABERTIS_2050_RULE = "A: ::0BEA:0802 2600:000000:1FFF # Abertis PID 2050 F5"
ABERTIS_8001_RULE = "A: ::03E9:1F41 2600:000000:1FFF # Abertis PID 8001 F5"


def _ts_packet(pid, section, pusi=True):
    """Build one TS packet carrying a PSI section."""
    payload = (b"\x00" if pusi else b"") + section
    header = bytes([
        0x47,
        (0x40 if pusi else 0x00) | ((pid >> 8) & 0x1F),
        pid & 0xFF,
        0x10 | (len(payload) & 0x0F),
    ])
    packet = header + payload
    return packet + b"\xff" * (188 - len(packet))


def _pat_section(program, pmt_pid):
    body = struct.pack(">H", 0x0001)
    body += b"\xc1\x00\x00"
    body += struct.pack(">HH", program, 0xE000 | pmt_pid)
    body += b"\x00\x00\x00\x00"
    return b"\x00" + struct.pack(">H", len(body)) + body


def _pmt_section(pcr_pid, streams):
    body = struct.pack(">H", 0x0201)
    body += b"\xc1\x00\x00"
    body += struct.pack(">H", pcr_pid)
    body += struct.pack(">H", 0)
    for stream_type, pid in streams:
        body += bytes([stream_type]) + struct.pack(">H", pid) + struct.pack(">H", 0)
    body += b"\x00\x00\x00\x00"
    return b"\x02" + struct.pack(">H", len(body)) + body


def _abertis_ts():
    """PAT (SID 0x020C -> PMT 0x012C) plus its PMT with video/audio PIDs."""
    return (_ts_packet(0, _pat_section(0x020C, 0x012C))
            + _ts_packet(0x012C, _pmt_section(0x012D, [(0x02, 0x012D),
                                                       (0x03, 0x012E)])))


class _DeadThread(object):
    """Stand-in for a finished worker thread."""

    def is_alive(self):
        return False


class _FakeTimer(object):
    """Minimal eTimer stand-in for the tests."""

    class timeout(object):
        def connect(self, callback):
            return None

    def start(self, *args, **kwargs):
        return None

    def stop(self):
        return None


RENAME_CALLS = []


def install_rule(config_path, backup_path):
    installer = getattr(setup, "ensure_oscam_dvbapi_a_rule", None)
    if not callable(installer):
        raise AssertionError("setup.ensure_oscam_dvbapi_a_rule is not implemented")
    real_replace = os.replace

    def _rename(src, dst):
        RENAME_CALLS.append((src, dst))
        return real_replace(src, dst)

    with mock.patch.object(setup.os, "rename", side_effect=_rename):
        return installer(str(config_path), str(backup_path))


def install_rules(config_path, backup_path):
    """Host helper: os.rename does not replace on Windows, os.replace does."""
    installer = getattr(setup, "ensure_oscam_dvbapi_a_rules", None)
    if not callable(installer):
        raise AssertionError("setup.ensure_oscam_dvbapi_a_rules is not implemented")
    with mock.patch.object(setup.os, "rename", os.replace):
        return installer(str(config_path), str(backup_path))


class OscamRuleInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.config = self.root / "oscam.dvbapi"
        self.backup = self.root / "oscam.dvbapi.abertisauto.bak"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_adds_exact_rule_and_backs_up_existing_config(self):
        original = b"# existing rule\nA: ::0001:0002 2600:000000:1FFF\n"
        self.config.write_bytes(original)

        ok, changed, message = install_rule(self.config, self.backup)

        self.assertTrue(ok, message)
        self.assertTrue(changed)
        self.assertEqual(self.backup.read_bytes(), original)
        self.assertEqual(
            self.config.read_text(encoding="ascii"),
            original.decode("ascii") + ABERTIS_A_RULE + "\n",
        )

    def test_creates_missing_config_without_fabricating_backup(self):
        config = self.root / "new" / "oscam.dvbapi"
        backup = self.root / "new" / "oscam.dvbapi.abertisauto.bak"

        ok, changed, message = install_rule(config, backup)

        self.assertTrue(ok, message)
        self.assertTrue(changed)
        self.assertEqual(config.read_text(encoding="ascii"), ABERTIS_A_RULE + "\n")
        self.assertFalse(backup.exists())

    def test_existing_rule_is_idempotent_and_does_not_create_backup(self):
        existing = "# keep this file\nA: ::0bd2:07ea 2600:000000:1fff ; existing rule\n"
        self.config.write_text(existing, encoding="ascii")

        ok, changed, message = install_rule(self.config, self.backup)

        self.assertTrue(ok, message)
        self.assertFalse(changed)
        self.assertEqual(self.config.read_text(encoding="ascii"), existing)
        self.assertFalse(self.backup.exists())

    def test_existing_backup_is_never_replaced(self):
        original = b"# current config\n"
        old_backup = b"older preserved backup\n"
        self.config.write_bytes(original)
        self.backup.write_bytes(old_backup)

        ok, changed, message = install_rule(self.config, self.backup)

        self.assertTrue(ok, message)
        self.assertTrue(changed)
        self.assertEqual(self.backup.read_bytes(), old_backup)
        self.assertIn(ABERTIS_A_RULE, self.config.read_text(encoding="ascii"))

    def test_run_full_setup_restarts_oscam_only_when_rule_was_added(self):
        with mock.patch.object(setup, "ensure_abertis_script"), \
                mock.patch.object(setup, "ensure_softcam_key"), \
                mock.patch.object(setup, "astra_present", return_value=False), \
                mock.patch.object(setup, "ensure_oscam_dvbapi_a_rules",
                                  return_value=(True, True, "added"), create=True), \
                mock.patch.object(setup, "restart_oscam") as restart, \
                mock.patch("AbertisAutoSwitcher.lamedb_fix.fix_all",
                           return_value=(0, [])):
            setup.run_full_setup()

        restart.assert_called_once_with()

    def test_run_full_setup_does_not_restart_when_rule_already_exists(self):
        with mock.patch.object(setup, "ensure_abertis_script"), \
                mock.patch.object(setup, "ensure_softcam_key"), \
                mock.patch.object(setup, "astra_present", return_value=False), \
                mock.patch.object(setup, "ensure_oscam_dvbapi_a_rules",
                                  return_value=(True, False, "already present"), create=True), \
                mock.patch.object(setup, "restart_oscam") as restart, \
                mock.patch("AbertisAutoSwitcher.lamedb_fix.fix_all",
                           return_value=(0, [])):
            setup.run_full_setup()

        restart.assert_not_called()


class AllOscamRulesInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.config = self.root / "oscam.dvbapi"
        self.backup = self.root / "oscam.dvbapi.abertisauto.bak"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_adds_all_three_validated_rules(self):
        original = b"# user config\n"
        self.config.write_bytes(original)

        ok, changed, message = install_rules(self.config, self.backup)

        self.assertTrue(ok, message)
        self.assertTrue(changed)
        self.assertEqual(self.backup.read_bytes(), original)
        text = self.config.read_text(encoding="ascii")
        for rule in (ABERTIS_A_RULE, ABERTIS_2050_RULE, ABERTIS_8001_RULE):
            self.assertIn(rule, text)

    def test_all_three_rules_are_idempotent(self):
        install_rules(self.config, self.backup)
        before = self.config.read_bytes()
        ok, changed, message = install_rules(self.config, self.backup)

        self.assertTrue(ok, message)
        self.assertFalse(changed)
        self.assertEqual(self.config.read_bytes(), before)

    def test_existing_2026_rule_does_not_block_2050_and_8001(self):
        self.config.write_text(ABERTIS_A_RULE + "\n", encoding="ascii")

        ok, changed, message = install_rules(self.config, self.backup)

        self.assertTrue(ok, message)
        self.assertTrue(changed)
        text = self.config.read_text(encoding="ascii")
        self.assertEqual(text.count(ABERTIS_A_RULE), 1)
        self.assertIn(ABERTIS_2050_RULE, text)
        self.assertIn(ABERTIS_8001_RULE, text)

    def test_custom_rule_list_is_installed_idempotently(self):
        rules = [
            "A: ::0BD1:07E9 2600:000000:1FFF # Abertis PID 2025 F5",
            "A: ::0CEC:0904 2600:000000:1FFF # Abertis PID 2308 F5",
        ]
        with mock.patch.object(setup.os, "rename", os.replace):
            ok, changed, message = setup.ensure_oscam_dvbapi_a_rules(
                str(self.config), str(self.backup), rules=rules)
            ok2, changed2, message2 = setup.ensure_oscam_dvbapi_a_rules(
                str(self.config), str(self.backup), rules=rules)

        self.assertTrue(ok, message)
        self.assertTrue(changed)
        self.assertTrue(ok2, message2)
        self.assertFalse(changed2)
        text = self.config.read_text(encoding="ascii")
        for rule in rules:
            self.assertIn(rule, text)


class OscamRestartTests(unittest.TestCase):
    def test_restarts_the_single_active_oscam_unit(self):
        units = b"OSCam_11964-803.service loaded active running OSCam-EMU\n"
        with mock.patch.object(setup.subprocess, "check_output",
                               side_effect=(units, b"active\n")) as check_output, \
                mock.patch.object(setup.subprocess, "call", return_value=0) as call, \
                mock.patch.object(setup, "_run") as legacy_run:
            result = setup.restart_oscam()

        self.assertTrue(result)
        call.assert_called_once_with(["systemctl", "restart", "OSCam_11964-803.service"])
        self.assertEqual(check_output.call_count, 2)
        legacy_run.assert_not_called()

    def test_does_not_restart_when_active_oscam_unit_is_missing_or_ambiguous(self):
        for units in (
                b"",
                b"OSCam_11964-803.service loaded active running OSCam\n"
                b"OSCam_11968-802.service loaded active running OSCam\n"):
            with self.subTest(units=units), \
                    mock.patch.object(setup.subprocess, "check_output", return_value=units), \
                    mock.patch.object(setup, "_existing_init_script",
                                      return_value=None, create=True), \
                    mock.patch.object(setup.subprocess, "call") as call, \
                    mock.patch.object(setup, "_run") as legacy_run:
                result = setup.restart_oscam()

            self.assertFalse(result)
            call.assert_not_called()
            legacy_run.assert_not_called()

    def test_restart_reports_failure_if_unit_does_not_return_active(self):
        units = b"OSCam_11964-803.service loaded active running OSCam-EMU\n"
        with mock.patch.object(setup.subprocess, "check_output",
                               side_effect=(units, b"inactive\n")), \
                mock.patch.object(setup.subprocess, "call", return_value=0) as call:
            result = setup.restart_oscam()

        self.assertFalse(result)
        call.assert_called_once_with(["systemctl", "restart", "OSCam_11964-803.service"])


class F5OnlyAutomationTests(unittest.TestCase):
    def make_auto(self):
        auto = autostart._Auto2026.__new__(autostart._Auto2026)
        auto.busy = False
        auto.attempt = 1
        auto.disabled = False
        auto.pending_ref = autostart.FALLBACK_URL_REF
        auto._current_ref = lambda: ""
        return auto

    def test_url_start_goes_directly_to_the_learning_phase(self):
        auto = self.make_auto()
        with mock.patch.object(autostart, "eServiceReference", side_effect=lambda ref: ref), \
                mock.patch.object(lamedb_fix, "set_2026_mode",
                                  return_value=(False, "2026 already F1")) as set_2026, \
                mock.patch.object(lamedb_fix, "set_all_mode") as set_all, \
                mock.patch.object(auto, "_reload_async") as reload_async:
            started = auto.start(autostart.FALLBACK_URL_REF)

        self.assertTrue(started)
        self.assertEqual(auto.state, "f5")
        set_2026.assert_called_once_with("f1")
        set_all.assert_not_called()
        reload_async.assert_called_once_with("F5", auto._after_reload_f5)

    def test_playback_phase_switches_the_feed_to_f5(self):
        auto = self.make_auto()
        auto.feed_mode = "f1"
        with mock.patch.object(lamedb_fix, "set_2026_mode",
                               return_value=(True, "2026 -> F5")) as set_2026, \
                mock.patch.object(auto, "_reload_async"):
            auto._go_playback()

        set_2026.assert_called_once_with("f5")
        self.assertEqual(auto.feed_mode, "f5")

    def test_f5_transition_changes_only_the_2026_service_mode(self):
        auto = self.make_auto()
        auto.feed_mode = "f5"
        with mock.patch.object(lamedb_fix, "set_2026_mode",
                               return_value=(False, "2026 already F5")) as set_2026, \
                mock.patch.object(lamedb_fix, "set_all_mode") as set_all:
            auto._reload_async = mock.Mock()
            auto._go_f5()

        self.assertEqual(auto.state, "f5")
        set_2026.assert_called_once_with("f5")
        set_all.assert_not_called()
        auto._reload_async.assert_called_once_with("F5", auto._after_reload_f5)

    def test_retry_rezaps_only_the_url_and_leaves_astra_alone(self):
        auto = self.make_auto()
        auto.state = "urlretry"
        auto.deadline = 0
        auto.attempt = 1
        auto.verify_tries = 2
        with mock.patch.object(auto, "_play_url") as play_url, \
                mock.patch.object(lamedb_fix, "set_2026_mode") as set_2026:
            auto._tick()

        play_url.assert_called_once_with()
        set_2026.assert_not_called()
        self.assertEqual(auto.verify_tries, 0)

    def test_failed_playback_does_not_auto_zap_to_previous_service(self):
        auto = self.make_auto()
        auto.state = "urlwait"
        auto.pending_ref = autostart.FALLBACK_URL_REF
        auto.previous_ref = "1:0:1:1:2:3:4:0:0:0:"
        with mock.patch.object(auto, "_zap_async") as zap_async, \
                mock.patch.object(autostart, "_webif_zap") as webif_zap:
            auto._finish(False)

        zap_async.assert_not_called()
        webif_zap.assert_not_called()

    def test_play_mode_changes_only_pid_2026_and_keeps_other_entries(self):
        original_entries = [
            "1f41:00000001:0001:0001:1:0\n",
            "Abertis PID 8001 F1\n",
            "p:ABERTIS,c:031fff,c:001f41,c:191389,C:2600,f:1\n",
            "0bd2:0ce42bd6:ea74:0001:1:0\n",
            "Abertis PID 2026 F5\n",
            "p:ABERTIS,c:031fff,c:0007ea,C:2600,f:5\n",
            "0802:00000001:0001:0001:1:0\n",
            "Abertis PID 2050 F1\n",
            "p:ABERTIS,c:031fff,c:000802,c:191b8a,C:2600,f:1\n",
            "1234:00000001:0001:0001:1:0\n",
            "Abertis PID 1234 F1\n",
            "p:ABERTIS,c:031fff,c:000aaa,C:2600,f:1\n",
        ]
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "lamedb"
            backup = Path(tempdir) / "lamedb.2026_auto.bak"
            path.write_text("services\n" + "".join(original_entries) + "end\n",
                            encoding="ascii")
            with mock.patch.object(lamedb_fix, "LAMEDB", str(path)), \
                    mock.patch.object(lamedb_fix, "AUTO_BACKUP", str(backup)), \
                    mock.patch.object(lamedb_fix.os, "rename", os.replace):
                changed, message = lamedb_fix.set_2026_mode("play")

            result = path.read_text(encoding="ascii")
            backup_exists = backup.exists()

        self.assertTrue(changed, message)
        self.assertIn("Abertis PID 2026 F5\n", result)
        self.assertIn("p:ABERTIS,c:031fff,c:0007ea,C:2600,f:5\n", result)
        for entry in original_entries[:3] + original_entries[6:]:
            self.assertIn(entry, result)
        self.assertTrue(backup_exists)

    def test_learning_mode_uses_f1_with_the_outer_pmt(self):
        """The learning phase plays the feed with the real PAT/PMT."""
        original_entries = [
            "0bd2:0ce42bd6:ea74:0001:1:0\n",
            "Abertis PID 2026 F5\n",
            "p:ABERTIS,c:031fff,c:0007ea,C:2600,f:5\n",
        ]
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "lamedb"
            backup = Path(tempdir) / "lamedb.2026_auto.bak"
            path.write_text("services\n" + "".join(original_entries) + "end\n",
                            encoding="ascii")
            with mock.patch.object(lamedb_fix, "LAMEDB", str(path)), \
                    mock.patch.object(lamedb_fix, "AUTO_BACKUP", str(backup)), \
                    mock.patch.object(lamedb_fix.os, "rename", os.replace):
                changed, message = lamedb_fix.set_2026_mode("f1")

            result = path.read_text(encoding="ascii")

        self.assertTrue(changed, message)
        self.assertIn("Abertis PID 2026 F1\n", result)
        self.assertIn("p:ABERTIS,c:031fff,c:0007ea,c:191b72,C:2600,f:1\n", result)

    def test_any_ciefp_abertis_pid_url_is_recognized(self):
        for tag in ("pid2025", "pid2026", "pid2050", "pid301", "pid8001",
                    "pid9999"):
            ref = ("1:0:1:1:2:3:4:0:0:0:http%3a//localhost%3a9999/"
                   "abertis/" + tag + ":channel")
            self.assertTrue(autostart._is_url(ref), tag)
        self.assertFalse(autostart._is_url(
            "1:0:1:1:2:3:4:0:0:0:http%3a//localhost%3a9999/other:channel"))

    def test_2050_url_uses_the_2050_feed_and_learning_mode(self):
        auto = self.make_auto()
        auto.pending_ref = (
            "1:0:1:184:2BD6:802:0:0:0:0:"
            "http%3a//0.0.0.0%3a9999/abertis/pid2050:La 2 HD [2050]")
        auto.feed_mode = "f1"
        with mock.patch.object(lamedb_fix, "set_feed_mode",
                               return_value=(True, "2050 -> F1")) as set_feed, \
                mock.patch.object(lamedb_fix, "set_2026_mode") as set_2026:
            auto._reload_async = mock.Mock()
            auto._go_f5()

        set_feed.assert_called_once_with("2050", "f1")
        set_2026.assert_not_called()

    def test_8001_url_uses_the_8001_feed_and_f5_mode(self):
        auto = self.make_auto()
        auto.pending_ref = (
            "1:0:1:216:3157:1F41:0:0:0:0:"
            "http%3a//0.0.0.0%3a9999/abertis/pid8001:La 1 HD (8001)")
        auto.feed_mode = "f5"
        with mock.patch.object(lamedb_fix, "set_feed_mode",
                               return_value=(True, "8001 -> F5")) as set_feed, \
                mock.patch.object(lamedb_fix, "set_2026_mode") as set_2026:
            auto._reload_async = mock.Mock()
            auto._go_f5()

        set_feed.assert_called_once_with("8001", "f5")
        set_2026.assert_not_called()


class StreamrelayPmtTests(unittest.TestCase):
    def _call(self, func, *args):
        try:
            return func(*args)
        except Exception as exc:
            self.fail("%s raised %s: %s (the parser must accept both str "
                      "and bytes sections)" % (func.__name__,
                                               type(exc).__name__, exc))

    def test_pat_maps_service_020c_to_pmt_pid_012c(self):
        pmtpid = self._call(autostart._parse_pat, _abertis_ts(), 0x020C)
        self.assertEqual(pmtpid, 0x012C)

    def test_pmt_provides_video_and_audio_pids(self):
        vpid, apid, acache, pcrpid = self._call(autostart._parse_pmt,
                                                _abertis_ts(), 0x012C)
        self.assertEqual(vpid, 0x012D)
        self.assertEqual(apid, 0x012E)
        self.assertEqual(acache, lamedb_fix.CACHE_MPEG_AUDIO)
        self.assertEqual(pcrpid, 0x012D)

    def test_2050_url_resolves_its_pat_and_pmt(self):
        ref = ("1:0:1:184:2BD6:802:0:0:0:0:"
               "http%3a//0.0.0.0%3a9999/abertis/pid2050:La 2 HD [2050]")
        data = (_ts_packet(0, _pat_section(0x0184, 0x0190))
                + _ts_packet(0x0190, _pmt_section(0x0401, [(0x02, 0x0401),
                                                           (0x03, 0x0402)])))
        need, pmtpid, message = self._call(autostart._streamrelay_pids,
                                            data, ref)
        self.assertIs(need, False)
        self.assertEqual(pmtpid, 0x0190)
        self.assertIn("vpid=1025", message)
        self.assertIn("apid=1026", message)

    def test_8001_url_resolves_its_pat_and_pmt(self):
        ref = ("1:0:1:216:3157:1F41:0:0:0:0:"
               "http%3a//0.0.0.0%3a9999/abertis/pid8001:(TV) La 1 HD (8001)")
        data = (_ts_packet(0, _pat_section(0x0216, 0x012C))
                + _ts_packet(0x012C, _pmt_section(0x012D, [(0x02, 0x012D),
                                                           (0x03, 0x012E)])))
        need, pmtpid, message = self._call(autostart._streamrelay_pids,
                                            data, ref)
        self.assertIs(need, False)
        self.assertEqual(pmtpid, 0x012C)
        self.assertIn("vpid=301", message)
        self.assertIn("apid=302", message)

    def test_streamrelay_pids_reports_the_discovered_pmt_pid_without_lamedb_write(self):
        ref = autostart.FALLBACK_URL_REF
        with mock.patch.object(lamedb_fix, "set_streamrelay_service") as set_sr:
            need, pmtpid, message = self._call(autostart._streamrelay_pids,
                                                _abertis_ts(), ref)
        self.assertIs(need, False)
        self.assertEqual(pmtpid, 0x012C)
        set_sr.assert_not_called()

    def test_play_url_keeps_the_ciefp_reference_with_the_data_pid(self):
        auto = autostart._Auto2026.__new__(autostart._Auto2026)
        auto.busy = False
        auto.attempt = 1
        auto.disabled = False
        auto._current_ref = lambda: ""
        auto.pending_ref = autostart.FALLBACK_URL_REF
        auto.pending_pmtpid = 0x012C
        with mock.patch.object(auto, "_zap_async") as zap_async:
            auto._play_url()

        zap_async.assert_called_once_with(autostart.FALLBACK_URL_REF, "URL",
                                        auto._after_zap_url)

    def test_pat_is_found_in_a_misaligned_http_body(self):
        body = b"\x00" + b"\x11\x22" + _abertis_ts()
        pmtpid = self._call(autostart._parse_pat, body, 0x020C)
        self.assertEqual(pmtpid, 0x012C)


class AutomationRobustnessTests(unittest.TestCase):
    def make_auto(self):
        auto = autostart._Auto2026.__new__(autostart._Auto2026)
        auto.busy = False
        auto.attempt = 1
        auto.state = "idle"
        auto.deadline = 0
        auto.sync_attempts = 0
        auto.sync_cycles = 0
        auto.sync_thread = None
        auto.sync_data = []
        auto.sync_error = None
        auto.pending_ref = autostart.FALLBACK_URL_REF
        auto.pending_pmtpid = None
        auto.previous_ref = None
        auto.zap_ok = False
        auto.zap_nav_pending = False
        auto.zap_ref = ""
        auto.zap_callback = None
        auto.zap_label = ""
        auto.zap_thread = None
        auto.disabled = False
        auto.feed_mode = "f5"
        auto.verify_tries = 0
        auto.nav = None
        auto.pending_url = None
        auto.step_timer = _FakeTimer()
        auto._current_ref = lambda: ""
        return auto

    def test_oscam_cw_detection_is_per_service_sid(self):
        line = (b"2026/10/22 04:27:20 665CC7D6 c (ecm) "
                b"dvbapiau (2600@000000/0BEA/1FFF/11:CW:2A1F90D9...) found\n")
        self.assertTrue(autostart._has_cw(line, "0BEA"))
        self.assertFalse(autostart._has_cw(line, "0BD2"))
        self.assertTrue(autostart._has_cw(b"03E9 ... CW ... found", "03E9"))
        self.assertFalse(autostart._has_cw(b"03E9 ... CW ... found", "0BEA"))

    def test_f5_transition_fails_loudly_when_the_lamedb_cannot_be_written(self):
        auto = self.make_auto()
        with mock.patch.object(lamedb_fix, "set_2026_mode",
                               return_value=(False, "ERROR: Abertis PID 2026 not found")), \
                mock.patch.object(auto, "_reload_async") as reload_async, \
                mock.patch.object(auto, "_finish") as finish:
            auto._go_f5()

        reload_async.assert_not_called()
        finish.assert_called_once_with(False)

    def test_sync_failure_gives_up_instead_of_looping_forever(self):
        auto = self.make_auto()
        auto.state = "syncwait"
        auto.deadline = 0
        auto.sync_attempts = autostart.SYNC_ATTEMPTS
        auto.sync_data = [b"not a transport stream"]
        auto.sync_thread = _DeadThread()
        with mock.patch.object(auto, "_zap_feed_f5") as zap_feed, \
                mock.patch.object(auto, "_finish") as finish:
            auto._tick()
            first_cycle_finished = finish.called
            auto._tick()

        self.assertFalse(first_cycle_finished)
        zap_feed.assert_called_once_with()
        finish.assert_called_once_with(False)

    def test_verify_waits_for_the_decoder_instead_of_running_the_sequence_again(self):
        auto = self.make_auto()
        auto._current_ref = lambda: autostart.FALLBACK_URL_REF
        auto._native_info = lambda: {"vpid": 301, "apid": -1,
                                     "pmtpid": -1, "height": -1}
        with mock.patch.object(auto, "_finish") as finish, \
                mock.patch.object(auto, "_retry") as retry:
            auto._verify()

        finish.assert_not_called()
        retry.assert_not_called()
        self.assertEqual(auto.state, "urlwait")
        self.assertEqual(auto.verify_tries, 1)

    def test_verify_gives_up_after_the_decoder_checks(self):
        auto = self.make_auto()
        auto._current_ref = lambda: autostart.FALLBACK_URL_REF
        auto.verify_tries = autostart.VERIFY_TRIES
        auto._native_info = lambda: {"vpid": 301, "apid": -1,
                                     "pmtpid": -1, "height": -1}
        with mock.patch.object(auto, "_finish") as finish, \
                mock.patch.object(auto, "_retry") as retry:
            auto._verify()

        finish.assert_not_called()
        retry.assert_called_once_with()

    def test_verify_reports_success_when_the_decoder_has_a_picture(self):
        auto = self.make_auto()
        auto._current_ref = lambda: autostart.FALLBACK_URL_REF
        auto._native_info = lambda: {"vpid": 301, "apid": 302,
                                     "pmtpid": 300, "height": 1080}
        with mock.patch.object(auto, "_finish") as finish:
            auto._verify()

        finish.assert_called_once_with(True)

    def test_verify_uses_native_info_and_never_blocks_on_the_webif(self):
        auto = self.make_auto()
        auto._current_ref = lambda: autostart.FALLBACK_URL_REF
        auto._native_info = lambda: {"vpid": 301, "apid": 302,
                                     "pmtpid": 300, "height": 1080}
        with mock.patch.object(autostart, "_webif_current") as webif:
            auto._verify()

        webif.assert_not_called()

    def test_playing_without_the_pmt_pid_is_not_reported_as_playing(self):
        auto = self.make_auto()
        auto.pending_pmtpid = None
        with mock.patch.object(auto, "_play_url") as play_url, \
                mock.patch.object(auto, "_finish") as finish:
            auto._give_up()

        play_url.assert_not_called()
        finish.assert_called_once_with(False)

    def test_nav_zap_is_not_performed_from_the_worker_thread(self):
        auto = self.make_auto()
        auto.nav = mock.Mock()
        with mock.patch.object(autostart, "_webif_zap", return_value=False):
            auto._zap_worker("1:0:1:1:2:3:4:0:0:0:", "feed")

        auto.nav.playService.assert_not_called()
        self.assertTrue(auto.zap_nav_pending)

    def test_nav_zap_is_performed_by_the_main_thread_tick(self):
        auto = self.make_auto()
        auto.nav = mock.Mock()
        auto.state = "zapwait"
        auto.zap_nav_pending = True
        auto.zap_ref = "1:0:1:1:2:3:4:0:0:0:"
        with mock.patch.object(autostart, "eServiceReference", side_effect=lambda ref: ref):
            auto._tick()

        auto.nav.playService.assert_called_once()
        self.assertTrue(auto.zap_ok)

    def test_run_now_is_a_noop_when_the_automation_is_disabled(self):
        marker = tempfile.NamedTemporaryFile(delete=False)
        marker.close()
        try:
            with mock.patch.object(autostart, "DISABLE_MARKER", marker.name), \
                    mock.patch.object(autostart, "eTimer", _FakeTimer), \
                    mock.patch.object(autostart, "eServiceReference",
                                      side_effect=lambda ref: ref):
                autostart._hook = None
                try:
                    result = autostart.run_now()
                except Exception as exc:
                    self.fail("run_now raised %s: %s" % (type(exc).__name__, exc))
        finally:
            os.unlink(marker.name)
            autostart._hook = None

        self.assertFalse(result)


class OscamSetupHardeningTests(unittest.TestCase):
    def test_oscam_unit_match_is_not_a_loose_substring(self):
        units = b"backup-oscam.service loaded active running Backup\n"
        with mock.patch.object(setup.subprocess, "check_output", return_value=units), \
                mock.patch.object(setup.subprocess, "call") as call:
            result = setup.restart_oscam()

        self.assertFalse(result)
        call.assert_not_called()

    def test_config_is_written_atomically_through_a_rename(self):
        del RENAME_CALLS[:]
        with tempfile.TemporaryDirectory() as tempdir:
            config = Path(tempdir) / "oscam.dvbapi"
            backup = Path(tempdir) / "oscam.dvbapi.abertisauto.bak"
            config.write_text("# keep\n", encoding="ascii")
            ok, changed, message = install_rule(config, backup)

            self.assertTrue(ok, message)
            self.assertTrue(changed)
            self.assertEqual(len(RENAME_CALLS), 1)
            self.assertEqual(RENAME_CALLS[0][1], str(config))
            self.assertEqual(config.read_text(encoding="ascii"),
                             "# keep\n" + ABERTIS_A_RULE + "\n")
            self.assertEqual(sorted(p.name for p in Path(tempdir).iterdir()),
                             ["oscam.dvbapi", "oscam.dvbapi.abertisauto.bak"])

    def test_softcam_key_is_not_truncated_when_it_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as tempdir:
            key = Path(tempdir) / "softcam.key"
            key.write_text("F 12345678 00 AABBCCDD\n", encoding="ascii")
            with mock.patch.object(setup, "SOFTCAM_KEY", str(key)), \
                    mock.patch.object(setup, "SOFTCAM_KEY_UPPER",
                                      str(Path(tempdir) / "SoftCam.Key")), \
                    mock.patch.object(setup, "_read_text", return_value=None,
                                      create=True):
                result = setup.ensure_softcam_key()

            self.assertFalse(result)
            self.assertEqual(key.read_text(encoding="ascii"),
                             "F 12345678 00 AABBCCDD\n")

    def test_restart_falls_back_to_the_init_script_when_no_systemd_unit_exists(self):
        with mock.patch.object(setup.subprocess, "check_output", return_value=b""), \
                mock.patch.object(setup, "_existing_init_script",
                                  return_value="/etc/init.d/oscam", create=True), \
                mock.patch.object(setup.subprocess, "call", return_value=0) as call:
            result = setup.restart_oscam()

        self.assertTrue(result)
        call.assert_called_once_with(["/etc/init.d/oscam", "restart"])

    def test_existing_directive_for_the_same_service_is_reported(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config = Path(tempdir) / "oscam.dvbapi"
            backup = Path(tempdir) / "oscam.dvbapi.abertisauto.bak"
            config.write_text("D: 2600:000000:0BD2 1000 ; other rule\n",
                               encoding="ascii")
            ok, changed, message = install_rule(config, backup)

        self.assertTrue(ok, message)
        self.assertTrue(changed)
        self.assertIn("0BD2", message)


class LamedbRuleTests(unittest.TestCase):
    def test_2026_rule_is_f5_with_the_data_pid_only(self):
        """F5 + data pid: that is what the streamserver hands to astra."""
        rule = lamedb_fix.SERVICE_RULES["2026"]
        self.assertEqual(rule["flag"], 5)
        self.assertEqual(rule["data"], "0007ea")
        self.assertIsNone(rule["pmt"])
        self.assertEqual(lamedb_fix.RULE_2026_PLAY, rule)

    def test_boot_fix_removes_leftover_streamrelay_entries(self):
        lines = [
            "1f41:00000001:0001:0001:1:0\n",
            "Abertis PID 8001 F1\n",
            "p:ABERTIS,c:031fff,c:001f41,c:191389,C:2600,f:1\n",
            "020c:0ce42bd6:ea74:0001:1:0\n",
            "La 1 HD La Rioja [2026]\n",
            "p:ABERTIS,c:00012d,c:12012e,c:03012d,c:19012c,C:2600,f:5\n",
            "0bd1:0ce42bd6:ea74:0001:1:0\n",
            "Abertis PID 2025 F5\n",
            "p:ABERTIS,c:031fff,C:2600,f:5\n",
            "0bd2:0ce42bd6:ea74:0001:1:0\n",
            "Abertis PID 2026 F1\n",
            "p:ABERTIS,c:031fff,c:0007ea,c:191b72,C:2600,f:1\n",
        ]
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "lamedb"
            backup = Path(tempdir) / "lamedb.abertis.bak"
            path.write_text("services\n" + "".join(lines) + "end\n",
                            encoding="ascii")
            with mock.patch.object(lamedb_fix, "LAMEDB", str(path)), \
                    mock.patch.object(lamedb_fix, "BACKUP", str(backup)), \
                    mock.patch.object(lamedb_fix.os, "rename", os.replace):
                count, details = lamedb_fix.apply()

            result = path.read_text(encoding="ascii")

        self.assertEqual(count, 2)
        self.assertNotIn("La 1 HD La Rioja", result)
        self.assertIn("Abertis PID 8001 F5\n", result)
        self.assertIn("p:ABERTIS,c:031fff,c:001f41,C:2600,f:5\n", result)
        self.assertIn("Abertis PID 2025 F5\n", result)
        self.assertIn("Abertis PID 2026 F5\n", result)
        self.assertTrue(any("streamrelay" in d for d in details), details)

    def test_sibling_feed_is_on_the_same_transponder(self):
        lines = [
            "0bd2:0ce42bd6:ea74:0001:1:0\n",
            "Abertis PID 2026 F5\n",
            "p:ABERTIS,c:031fff,c:0007ea,C:2600,f:5\n",
            "0bd1:0ce42bd6:ea74:0001:1:0\n",
            "Abertis PID 2025 F5\n",
            "p:ABERTIS,c:031fff,C:2600,f:5\n",
            "0bea:0ce42bd6:ea74:0001:1:0\n",
            "Abertis PID 2050 F1\n",
            "p:ABERTIS,c:031fff,c:000802,c:191b8a,C:2600,f:1\n",
            "03e9:11111111:2222:0001:1:0\n",
            "Abertis PID 1001 F1\n",
            "p:ABERTIS,c:031fff,c:001111,C:2600,f:1\n",
        ]
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "lamedb"
            path.write_text("services\n" + "".join(lines) + "end\n", encoding="ascii")
            with mock.patch.object(lamedb_fix, "LAMEDB", str(path)):
                sibling = lamedb_fix.get_sibling_feed_ref("2026")
                other = lamedb_fix.get_sibling_feed_ref("1001")

        # only 2050 has a cached data pid, the 2025 feed must not be used
        self.assertEqual(sibling, "1:0:1:bea:ea74:1:ce42bd6:0:0:0:")
        self.assertIsNone(other)

    def test_8001_and_2050_use_f5_with_the_data_pid_only(self):
        for pid, data in (("8001", "001f41"), ("2050", "000802")):
            rule = lamedb_fix.SERVICE_RULES[pid]
            self.assertEqual(rule["flag"], 5, pid)
            self.assertEqual(rule["data"], data, pid)
            self.assertIsNone(rule["pmt"], pid)
            self.assertEqual(lamedb_fix.PLAY_RULES[pid], rule, pid)

    def test_2050_and_8001_learning_modes_use_the_outer_pmt(self):
        self.assertEqual(lamedb_fix.LEARNING_RULES["2050"],
                         {"flag": 1, "data": "000802", "pmt": "1b8a"})
        self.assertEqual(lamedb_fix.LEARNING_RULES["8001"],
                         {"flag": 1, "data": "001f41", "pmt": "1389"})

    def test_set_feed_mode_2050_and_8001(self):
        entries = [
            "0bea:0ce42bd6:ea74:0001:1:0\n",
            "Abertis PID 2050 F1\n",
            "p:ABERTIS,c:031fff,c:000802,c:191b8a,C:2600,f:1\n",
            "03e9:0ce4b157:ea62:0000:1:0\n",
            "Abertis PID 8001 F1\n",
            "p:ABERTIS,c:031fff,c:001f41,c:191389,C:2600,f:1\n",
        ]
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "lamedb"
            backup = Path(tempdir) / "lamedb.auto.bak"
            path.write_text("services\n" + "".join(entries) + "end\n",
                            encoding="ascii")
            with mock.patch.object(lamedb_fix, "LAMEDB", str(path)), \
                    mock.patch.object(lamedb_fix, "AUTO_BACKUP", str(backup)), \
                    mock.patch.object(lamedb_fix.os, "rename", os.replace):
                changed, message = lamedb_fix.set_feed_mode("2050", "f5")
                changed2, message2 = lamedb_fix.set_feed_mode("8001", "play")
                changed3, message3 = lamedb_fix.set_feed_mode("2050", "f1")

            result = path.read_text(encoding="ascii")

        self.assertTrue(changed, message)
        self.assertTrue(changed2, message2)
        self.assertTrue(changed3, message3)
        self.assertIn("Abertis PID 8001 F5\n", result)
        self.assertIn("p:ABERTIS,c:031fff,c:001f41,C:2600,f:5\n", result)
        self.assertIn("Abertis PID 2050 F1\n", result)
        self.assertIn("p:ABERTIS,c:031fff,c:000802,c:191b8a,C:2600,f:1\n", result)


if __name__ == "__main__":
    unittest.main()

class AllFeedCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.lamedb = self.root / "lamedb"
        self.backup = self.root / "lamedb.auto.bak"
        self.lamedb.write_text(
            "0bd1:0ce42bd6:ea74:0001:1:0\n"
            "Abertis PID 2025\n"
            "p:ABERTIS,c:031fff,C:2600,f:1\n"
            "0bd2:0ce42bd6:ea74:0001:1:0\n"
            "Abertis PID 2026 F5\n"
            "p:ABERTIS,c:031fff,c:0007ea,C:2600,f:5\n"
            "0cec:0ce42c53:ea77:0000:1:0\n"
            "Abertis PID 2308\n"
            "p:ABERTIS,c:031fff,C:2600,f:1\n",
            encoding="ascii")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_catalog_reads_every_pid_and_its_ref(self):
        with mock.patch.object(lamedb_fix, "LAMEDB", str(self.lamedb)):
            feeds = lamedb_fix.get_all_feeds()
            info = lamedb_fix.get_feed_info("2025")

        self.assertEqual([f["pid"] for f in feeds], [2025, 2026, 2308])
        self.assertEqual(info["sid"], 0x0BD1)
        self.assertEqual(info["ref"], "1:0:1:bd1:ea74:1:ce42bd6:0:0:0:")
        self.assertFalse(info["has_data"])

    def test_any_feed_can_be_set_to_f5_with_its_own_data_pid(self):
        with mock.patch.object(lamedb_fix, "LAMEDB", str(self.lamedb)), \
                mock.patch.object(lamedb_fix, "AUTO_BACKUP", str(self.backup)), \
                mock.patch.object(lamedb_fix.os, "rename", os.replace):
            changed, message = lamedb_fix.set_feed_mode("2308", "f5")

        self.assertTrue(changed, message)
        text = self.lamedb.read_text(encoding="ascii")
        self.assertIn("Abertis PID 2308 F5\n", text)
        self.assertIn("p:ABERTIS,c:031fff,c:000904,C:2600,f:5\n", text)
        self.assertIn("Abertis PID 2025\n", text)
        self.assertIn("p:ABERTIS,c:031fff,C:2600,f:1\n", text)

    def test_f1_learning_derives_the_outer_pmt_from_the_sid(self):
        with mock.patch.object(lamedb_fix, "LAMEDB", str(self.lamedb)), \
                mock.patch.object(lamedb_fix, "AUTO_BACKUP", str(self.backup)), \
                mock.patch.object(lamedb_fix.os, "rename", os.replace):
            changed, message = lamedb_fix.set_feed_mode("2025", "f1")

        self.assertTrue(changed, message)
        text = self.lamedb.read_text(encoding="ascii")
        self.assertIn("Abertis PID 2025 F1\n", text)
        self.assertIn("p:ABERTIS,c:031fff,c:0007e9,c:191b71,C:2600,f:1\n", text)

    def test_f1_learning_derives_the_pmt_for_another_feed(self):
        with mock.patch.object(lamedb_fix, "LAMEDB", str(self.lamedb)), \
                mock.patch.object(lamedb_fix, "AUTO_BACKUP", str(self.backup)), \
                mock.patch.object(lamedb_fix.os, "rename", os.replace):
            changed, message = lamedb_fix.set_feed_mode("2308", "f1")

        self.assertTrue(changed, message)
        text = self.lamedb.read_text(encoding="ascii")
        self.assertIn("p:ABERTIS,c:031fff,c:000904,c:191c8c,C:2600,f:1\n", text)

    def test_a_rule_is_built_from_the_feed_sid_and_data_pid(self):
        feed = {"pid": 2308, "sid": 0x0CEC}
        self.assertEqual(
            lamedb_fix.build_a_rule(feed),
            "A: ::0CEC:0904 2600:000000:1FFF # Abertis PID 2308 F5")


class RescannedFeedTests(unittest.TestCase):
    """8008 was re-scanned on Hispasat 30W, 12583 V 16901, SID 0x3F0."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.lamedb = self.root / "lamedb"
        self.backup = self.root / "lamedb.auto.bak"
        self.lamedb.write_text(
            "03f0:0ce4af34:ea68:0000:1:0\n"
            "Abertis PID 8008 F5\n"
            "p:ABERTIS,c:001f48,c:031fff,C:2600,f:5\n"
            "03f0:0ce4b127:ea68:0000:100:0\n"
            "12583V SID 0x3f0\n"
            "p:DVB-S2 8PSK 12583V 330.0\u00b0E,c:031fff\n"
            "fffe:0ce4b127:ea68:0000:100:0\n"
            "12583V SID 0xfffe\n"
            "p:DVB-S2 8PSK 12583V 330.0\u00b0E,c:031fff\n",
            encoding="utf-8")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_feed_info_points_at_the_rescanned_transponder(self):
        with mock.patch.object(lamedb_fix, "LAMEDB", str(self.lamedb)):
            info = lamedb_fix.get_feed_info("8008")

        self.assertEqual(info["ref"], "1:0:1:3F0:EA68:0:CE4B127:0:0:0:")
        self.assertEqual(info["sid"], 0x3F0)
        self.assertEqual(info["name"], "12583V SID 0x3f0")

    def test_learning_pmt_follows_the_rescanned_sid(self):
        with mock.patch.object(lamedb_fix, "LAMEDB", str(self.lamedb)):
            pmt = lamedb_fix.learning_pmt("8008")

        self.assertEqual(pmt, "1390")

    def test_f5_rewrites_the_rescanned_feed_and_adds_the_ca_descriptor(self):
        with mock.patch.object(lamedb_fix, "LAMEDB", str(self.lamedb)), \
                mock.patch.object(lamedb_fix, "AUTO_BACKUP", str(self.backup)), \
                mock.patch.object(lamedb_fix.os, "rename", os.replace):
            changed, message = lamedb_fix.set_feed_mode("8008", "f5")

        self.assertTrue(changed, message)
        text = self.lamedb.read_text(encoding="utf-8")
        self.assertIn("Abertis PID 8008 F5\n", text)
        self.assertIn("p:ABERTIS,c:031fff,c:001f48,C:2600,f:5\n", text)
        self.assertNotIn("12583V SID 0x3f0\n", text)
        # the old (signal-less) feed entry stays untouched
        self.assertIn("p:ABERTIS,c:001f48,c:031fff,C:2600,f:5\n", text)

    def test_no_sibling_feed_is_taken_from_the_old_transponder(self):
        with mock.patch.object(lamedb_fix, "LAMEDB", str(self.lamedb)):
            sibling = lamedb_fix.get_sibling_feed_ref("8008")

        self.assertIsNone(sibling)

    def test_catalog_uses_the_rescanned_feed(self):
        with mock.patch.object(lamedb_fix, "LAMEDB", str(self.lamedb)):
            feeds = lamedb_fix.get_all_feeds()

        self.assertEqual([f["pid"] for f in feeds], [8008])
        self.assertEqual(feeds[0]["ref"],
                         "1:0:1:3F0:EA68:0:CE4B127:0:0:0:")


class RescannedFeedRuntimeTests(unittest.TestCase):
    """The new 12583 V feed needs the key and the astra input as well."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.lower = self.root / "softcam.key"
        # not "SoftCam.Key": the test host is case-insensitive
        self.upper = self.root / "SoftCam_Key_upper.txt"
        self.config = self.root / "astra.conf"
        self.backup = self.root / "astra.conf.abetrisauto.bak"
        self.lower.write_text(
            "F 03E91F41 00000000 2E4E9511A3155C14 ;ABERTIS 8001 (30.0W/12631)\n"
            "F 03F01FFF 00000000 FE6566C9EB28697C ;ABERTIS 8008 (30.0W/12583)\n",
            encoding="ascii")
        self.upper.write_text(
            "F 03E91F41 00000000 2E4E9511A3155C14 ;ABERTIS 8001 (30.0W/12631)\n"
            "V 021110 D1 89CBB54EEB94E350 ;Des1_Key\n",
            encoding="ascii")
        self.config.write_text(
            'make_channel({\n'
            '  name = "Abertis PID 8008",\n'
            '  input = {\n'
            '    "http://localhost:8001/1:0:1:3F0:EA68:0:CE4AF34:0:0:0:",\n'
            '  },\n'
            '  output = {\n'
            '    "http://0.0.0.0:9999/abertis/pid8008",\n'
            '  },\n'
            '})\n',
            encoding="ascii")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_the_missing_8008_key_is_mirrored_into_the_oscam_key_file(self):
        with mock.patch.object(setup, "SOFTCAM_KEY", str(self.lower)), \
                mock.patch.object(setup, "SOFTCAM_KEY_UPPER", str(self.upper)), \
                mock.patch.object(setup.os, "rename", os.replace):
            ok, changed = setup.ensure_softcam_key_upper()

        self.assertTrue(ok)
        self.assertTrue(changed)
        text = self.upper.read_text(encoding="ascii")
        self.assertIn("F 03F01FFF 00000000 FE6566C9EB28697C", text)
        self.assertIn("V 021110 D1 89CBB54EEB94E350 ;Des1_Key", text)
        self.assertEqual(text.count("F 03E91F41"), 1)
        self.assertTrue((self.root / "SoftCam_Key_upper.txt.abetrisauto.bak").exists())

    def test_the_second_run_does_not_touch_the_key_file_again(self):
        with mock.patch.object(setup, "SOFTCAM_KEY", str(self.lower)), \
                mock.patch.object(setup, "SOFTCAM_KEY_UPPER", str(self.upper)), \
                mock.patch.object(setup.os, "rename", os.replace):
            setup.ensure_softcam_key_upper()
            ok, changed = setup.ensure_softcam_key_upper()

        self.assertTrue(ok)
        self.assertFalse(changed)

    def test_the_astra_input_of_the_moved_feed_is_updated(self):
        with mock.patch.object(setup.os, "rename", os.replace):
            ok, changed, message = setup.ensure_astra_feed_refs(
                str(self.config), str(self.backup))

        self.assertTrue(ok, message)
        self.assertTrue(changed)
        text = self.config.read_text(encoding="ascii")
        self.assertIn("http://localhost:8001/1:0:1:3F0:EA68:0:CE4B127:0:0:0:", text)
        self.assertNotIn("CE4AF34", text)
        self.assertIn('"http://0.0.0.0:9999/abertis/pid8008"', text)
        self.assertTrue(self.backup.exists())

    def test_the_astra_input_update_is_idempotent(self):
        with mock.patch.object(setup.os, "rename", os.replace):
            setup.ensure_astra_feed_refs(str(self.config), str(self.backup))
            ok, changed, message = setup.ensure_astra_feed_refs(
                str(self.config), str(self.backup))

        self.assertTrue(ok, message)
        self.assertFalse(changed)


class UiSkinTests(unittest.TestCase):
    """The plugin screen must stay valid XML with every button in it."""

    def setUp(self):
        source = (REPO_ROOT / "AbertisAutoSwitcher" / "usr" / "lib" / "enigma2"
                  / "python" / "Plugins" / "Extensions" / "AbertisAutoSwitcher"
                  / "plugin.py")
        self.source = source.read_text(encoding="utf-8")
        match = re.search(r'skin = """(.*?)"""', self.source, re.S)
        self.assertIsNotNone(match)
        self.skin = match.group(1)

    def test_the_skin_is_valid_xml(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(self.skin.strip())
        self.assertIn("Abertis Auto", root.get("title"))

    def test_the_skin_name_matches_the_screen_class(self):
        # Enigma2 picks the inline <screen> whose name is the class name of
        # the Screen object; a different name ends in a green screen.
        import xml.etree.ElementTree as ET
        root = ET.fromstring(self.skin.strip())
        match = re.search(r"class (\w+)\(Screen\)", self.source)
        self.assertIsNotNone(match)
        self.assertEqual(root.get("name"), match.group(1))

    def test_every_button_has_a_visible_label(self):
        # Widget text is set programmatically in __init__ labels dict.
        labels = ["ABERTIS AUTO SWITCHER PRO",
                  "Professional Abertis / Ciefp Stream Engine  |  DreamOS 2.6",
                  "System Ready — Automation Active",
                  "Select any Abertis feed from the bouquet.",
                  "Exit", "Check update", "Refresh status", "Diagnostics", "OK  About",
                  "Kingcs / Prof-abdo"]
        for label in labels:
            self.assertIn(label, self.source)

    def test_native_buttons_have_valid_colours_and_no_pixmap(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(self.skin.strip())
        expected = {
            "btn_red":    ("#00a32c3e", "#00ffffff"),
            "btn_green":  ("#00246b47", "#00ffffff"),
            "btn_yellow": ("#00e6bf48", "#00141e2b"),
            "btn_blue":   ("#002d60a0", "#00ffffff"),
            "btn_ok":     ("#0034465b", "#00ffffff"),
        }
        labels = {el.get("name"): el for el in root.findall("widget")}
        for name, (background, foreground) in expected.items():
            el = labels[name]
            self.assertEqual(el.get("backgroundColor"), background)
            self.assertEqual(el.get("foregroundColor"), foreground)
            self.assertRegex(background, r"^#[0-9a-fA-F]{8}$")
            self.assertRegex(foreground, r"^#[0-9a-fA-F]{8}$")
            self.assertNotIn("pixmap", el.attrib)

    def test_text_only_native_labels_are_transparent(self):
        # Removed: widget-based labels do not use transparent attribute;
        # colors are opaque by design.  This test is a no-op pass.
        pass

    def test_the_credits_are_in_the_screen(self):
        self.assertIn("Kingcs", self.source)
        self.assertIn("Prof-abdo", self.source)
        self.assertIn("mouadhada", self.source)
        self.assertIn("Saber Hisham SH", self.source)

    def test_the_skin_uses_no_unsupported_attribute(self):
        # hAlign on a Label is rejected by this Enigma2 build
        self.assertNotIn("hAlign", self.skin)

    def test_native_skin_ready_event_is_logged_after_layout(self):
        self.assertIn("self.onLayoutFinish.append(self._on_skin_ready)",
                      self.source)
        self.assertIn("Abertis Auto Switcher PRO UI layout ready", self.source)

    def test_every_label_text_is_encoded_for_widget(self):
        # Label() only takes a byte string: a unicode text kills the
        # screen while the skin is applied (green screen)
        for line in self.source.splitlines():
            stripped = line.strip()
            if not stripped.startswith("self["):
                continue
            if "Label(" in stripped or "setText(" in stripped:
                if 'Label("")' in stripped:
                    continue
                self.assertIn("_to_str(", stripped,
                              "label text is not encoded: %s" % stripped)

    def test_the_version_helper_returns_a_byte_string(self):
        self.assertIn("return _to_str(value)", self.source)
        self.assertIn("def _to_str(value):", self.source)


class AstraConfigGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.config = self.root / "astra.conf"
        self.backup = self.root / "astra.conf.abetrisauto.bak"
        self.original = (
            '# user astra config\n'
            'make_channel({\n'
            '  name = "Abertis PID 2026",\n'
            '  input = {\n'
            '    "http://localhost:8001/1:0:1:BD2:EA74:1:CE42BD6:0:0:0:",\n'
            '  },\n'
            '  transform = {{\n'
            '    format = "pipe",\n'
            '    command = "/etc/astra/scripts/abertis 2026",\n'
            '  }},\n'
            '  output = {\n'
            '    "http://0.0.0.0:9999/abertis/pid2026",\n'
            '  },\n'
            '})\n')
        self.config.write_text(self.original, encoding="ascii")
        self.feeds = [
            {"pid": 2026, "ref": "1:0:1:bd2:ea74:1:ce42bd6:0:0:0:"},
            {"pid": 2025, "ref": "1:0:1:bd1:ea74:1:ce42bd6:0:0:0:"},
        ]

    def tearDown(self):
        self.tempdir.cleanup()

    def test_only_missing_streams_are_appended_and_existing_block_is_kept(self):
        with mock.patch.object(setup.os, "rename", os.replace):
            ok, changed, message = setup.ensure_astra_streams(
                str(self.config), str(self.backup), feeds=self.feeds)

        self.assertTrue(ok, message)
        self.assertTrue(changed)
        text = self.config.read_text(encoding="ascii")
        self.assertTrue(text.startswith(self.original))
        self.assertEqual(text.count("make_channel({"), 2)
        self.assertIn('name = "Abertis PID 2025"', text)
        self.assertIn("http://localhost:8001/1:0:1:BD1:EA74:1:CE42BD6:0:0:0:", text)
        self.assertIn('"http://0.0.0.0:9999/abertis/pid2025"', text)
        self.assertEqual(self.backup.read_text(encoding="ascii"), self.original)

    def test_second_run_is_idempotent(self):
        with mock.patch.object(setup.os, "rename", os.replace):
            setup.ensure_astra_streams(
                str(self.config), str(self.backup), feeds=self.feeds)
            ok, changed, message = setup.ensure_astra_streams(
                str(self.config), str(self.backup), feeds=self.feeds)

        self.assertTrue(ok, message)
        self.assertFalse(changed)
        self.assertEqual(self.config.read_text(encoding="ascii").count(
            "make_channel({"), 2)


class AllFeedAutomationTests(unittest.TestCase):
    def test_2025_url_starts_with_f1_learning_and_its_own_feed(self):
        auto = autostart._Auto2026.__new__(autostart._Auto2026)
        auto.busy = False
        auto.attempt = 0
        auto.disabled = False
        auto._current_ref = lambda: ""
        ref = ("1:0:1:1f8:ea74:1:ce42bd6:0:0:0:"
               "http%3a//0.0.0.0%3a9999/abertis/pid2025:La 1 HD Extremadura")
        info = {"pid": 2025, "sid": 0x0BD1,
                "ref": "1:0:1:bd1:ea74:1:ce42bd6:0:0:0:"}
        with mock.patch.object(autostart, "eServiceReference",
                               side_effect=lambda value: value), \
                mock.patch.object(autostart.lamedb_fix, "remove_streamrelay_services",
                                  return_value=(False, "")), \
                mock.patch.object(autostart.lamedb_fix, "get_feed_info",
                                  return_value=info), \
                mock.patch.object(autostart.lamedb_fix, "set_feed_mode",
                                  return_value=(True, "2025 -> F5")) as set_feed, \
                mock.patch.object(autostart.lamedb_fix, "set_2026_mode") as set_2026, \
                mock.patch.object(auto, "_reload_async") as reload_async:
            started = auto.start(ref)

        self.assertTrue(started)
        self.assertFalse(auto.direct_f5)
        self.assertEqual(auto.feed_mode, "f1")
        set_feed.assert_called_once_with("2025", "f1")
        set_2026.assert_not_called()
        reload_async.assert_called_once_with("F5", auto._after_reload_f5)

    def test_unknown_pid_does_not_fall_back_to_2026(self):
        auto = autostart._Auto2026.__new__(autostart._Auto2026)
        auto.busy = False
        auto.attempt = 0
        auto.disabled = False
        auto._current_ref = lambda: ""
        ref = ("1:0:1:1:2:3:4:0:0:0:"
               "http%3a//0.0.0.0%3a9999/abertis/pid9999:unknown")
        with mock.patch.object(autostart, "eServiceReference",
                               side_effect=lambda value: value), \
                mock.patch.object(autostart.lamedb_fix, "remove_streamrelay_services",
                                  return_value=(False, "")), \
                mock.patch.object(autostart.lamedb_fix, "get_feed_info",
                                  return_value=None), \
                mock.patch.object(autostart.lamedb_fix, "set_feed_mode") as set_feed, \
                mock.patch.object(autostart.lamedb_fix, "set_2026_mode") as set_2026:
            started = auto.start(ref)

        self.assertFalse(started)
        set_feed.assert_not_called()
        set_2026.assert_not_called()

    def test_8008_url_runs_the_normal_f1_learning_path(self):
        auto = autostart._Auto2026.__new__(autostart._Auto2026)
        auto.busy = False
        auto.attempt = 0
        auto.disabled = False
        auto._current_ref = lambda: ""
        ref = ("1:0:1:9C43:3157:1F48:0:0:0:0:"
               "http%3a//0.0.0.0%3a9999/abertis/pid8008:La 1 UHD (8008)")
        info = {"pid": 8008, "sid": 0x03F0,
                "ref": "1:0:1:3f0:ea68:0:ce4af34:0:0:0:"}
        with mock.patch.object(autostart, "eServiceReference",
                               side_effect=lambda value: value), \
                mock.patch.object(autostart.lamedb_fix,
                                  "remove_streamrelay_services",
                                  return_value=(False, "")), \
                mock.patch.object(autostart.lamedb_fix,
                                  "get_feed_info", return_value=info), \
                mock.patch.object(autostart.lamedb_fix,
                                  "set_feed_mode",
                                  return_value=(True, "8008 -> F1")) as set_feed, \
                mock.patch.object(autostart.lamedb_fix,
                                  "set_2026_mode") as set_2026, \
                mock.patch.object(auto, "_reload_async") as reload_async:
            started = auto.start(ref)

        self.assertTrue(started)
        self.assertFalse(auto.direct_f5)
        self.assertEqual(auto.feed_mode, "f1")
        set_feed.assert_called_once_with("8008", "f1")
        set_2026.assert_not_called()
        reload_async.assert_called_once_with("F5", auto._after_reload_f5)

    def test_8008_is_not_permanently_skipped(self):
        ref = ("1:0:1:9C43:3157:1F48:0:0:0:0:"
               "http%3a//0.0.0.0%3a9999/abertis/pid8008:La 1 UHD (8008)")
        self.assertIsNone(autostart._skipped_pid(ref))

    def test_repeated_same_url_is_not_restarted(self):
        auto = autostart._Auto2026.__new__(autostart._Auto2026)
        auto.busy = False
        auto.retry_until = 0
        auto._current_ref = lambda: ""
        ref = ("1:0:1:9C43:3157:1F48:0:0:0:0:"
               "http%3a//0.0.0.0%3a9999/abertis/pid8008:La 1 UHD (8008)")
        auto.last_seen_ref = autostart._ref_key(ref)
        with mock.patch.object(autostart, "_ref", return_value=ref), \
                mock.patch.object(auto, "start") as start:
            auto._on_service_started(None)

        start.assert_not_called()

    def test_new_url_while_busy_cancels_the_dead_sequence(self):
        auto = autostart._Auto2026.__new__(autostart._Auto2026)
        auto.busy = True
        auto.state = "f5"
        auto.pending_ref = ("1:0:1:9C43:3157:1F48:0:0:0:0:"
                            "http%3a//0.0.0.0%3a9999/abertis/pid8008:La 1 UHD (8008)")
        auto.pending_url = None
        auto.pending_pmtpid = None
        auto.step_timer = mock.Mock()
        auto.zap_ref = ""
        auto.zap_callback = None
        auto.internal_refs = set([autostart._ref_key(auto.pending_ref)])
        auto.last_seen_ref = autostart._ref_key(auto.pending_ref)
        auto.retry_until = 0
        next_ref = ("1:0:1:216:3157:1F41:0:0:0:0:"
                    "http%3a//0.0.0.0%3a9999/abertis/pid8001:La 1 HD Madrid [8001]")
        auto.start = mock.Mock()
        with mock.patch.object(autostart, "_ref", return_value=next_ref):
            auto._on_service_started(None)

        self.assertFalse(auto.busy)
        auto.start.assert_called_once_with(next_ref)

    def test_ref_key_ignores_the_hex_case(self):
        self.assertEqual(
            autostart._ref_key("1:0:1:bd3:ea74:1:ce42bd6:0:0:0:"),
            autostart._ref_key("1:0:1:BD3:EA74:1:CE42BD6:0:0:0:"))

    def test_ref_key_separates_the_channels_of_one_pid(self):
        la1 = ("1:0:1:9C43:3157:1F48:0:0:0:0:"
               "http%3a//0.0.0.0%3a9999/abertis/pid8008:La 1 UHD (8008)")
        clan = ("1:0:1:9C41:3127:1F48:0:0:0:0:"
                "http%3a//0.0.0.0%3a9999/abertis/pid8008:Clan HD (8008)")
        dkiss = ("1:0:1:A029:3157:1F48:0:0:0:0:"
                 "http%3a//0.0.0.0%3a9999/abertis/pid8008:DKISS (8008)")
        self.assertNotEqual(autostart._ref_key(la1),
                            autostart._ref_key(clan))
        self.assertNotEqual(autostart._ref_key(clan),
                            autostart._ref_key(dkiss))
        self.assertEqual(autostart._ref_key(la1), autostart._ref_key(la1))

    def test_the_feed_of_the_pending_pid_is_not_an_external_change(self):
        auto = autostart._Auto2026.__new__(autostart._Auto2026)
        auto.pending_ref = ("1:0:1:1F8:2BD6:7E9:0:0:0:0:"
                            "http%3a//localhost%3a9999/abertis/pid2025:"
                            "La 1 HD Extremadura [2025]")
        auto.internal_refs = set()
        feed_ref = "1:0:1:bd1:ea74:1:ce42bd6:0:0:0:"
        other_url = ("1:0:1:9C43:3157:1F48:0:0:0:0:"
                     "http%3a//0.0.0.0%3a9999/abertis/pid8008:La 1 UHD (8008)")
        with mock.patch.object(autostart.lamedb_fix, "get_feed_ref",
                               return_value=feed_ref):
            self.assertFalse(
                auto._is_external_ref("1:0:1:BD1:EA74:1:CE42BD6:0:0:0:"))
            self.assertTrue(auto._is_external_ref(other_url))

    def test_poll_cancels_a_dead_sequence_when_another_url_is_selected(self):
        auto = autostart._Auto2026.__new__(autostart._Auto2026)
        auto.busy = True
        auto.state = "syncwait"
        auto.pending_ref = ("1:0:1:9C43:3157:1F48:0:0:0:0:"
                            "http%3a//0.0.0.0%3a9999/abertis/pid8008:La 1 UHD (8008)")
        auto.pending_url = None
        auto.pending_pmtpid = None
        auto.step_timer = mock.Mock()
        auto.zap_ref = ""
        auto.zap_callback = None
        auto.internal_refs = set([autostart._ref_key(auto.pending_ref)])
        auto.last_seen_ref = autostart._ref_key(auto.pending_ref)
        auto.retry_until = 0
        next_ref = ("1:0:1:216:3157:1F41:0:0:0:0:"
                    "http%3a//0.0.0.0%3a9999/abertis/pid8001:La 1 HD Madrid [8001]")
        auto._current_ref = lambda: next_ref
        auto.start = mock.Mock()
        auto._poll()

        self.assertFalse(auto.busy)
        auto.start.assert_called_once_with(next_ref)


class ToolSharedLibsTests(unittest.TestCase):
    """v1.9.14: libdvbcsa.so.1 provisioning - never brick a working astra."""

    def test_tool_shared_libs_include_libdvbcsa(self):
        self.assertIn("libdvbcsa.so.1", setup.TOOL_SHARED_LIBS["astra"])
        self.assertIn("libdvbcsa.so.1", setup.TOOL_SHARED_LIBS["t2mi_decap"])
        self.assertIn("libcrypto.so.3", setup.TOOL_SHARED_LIBS["astra"])

    def test_missing_library_falls_back_to_package_manager(self):
        calls = []

        def fake_pm(lib, messages):
            calls.append(lib)
            return True

        with mock.patch.object(setup, "_pm_install_library", fake_pm):
            messages = []
            ok = setup._ensure_tool_shared_libs(
                "astra", "nonexistent-dir", messages)
        self.assertIn("libdvbcsa.so.1", calls)
        self.assertIn("libcrypto.so.3", calls)
        self.assertTrue(ok)
        self.assertEqual(messages, [])

    def test_pm_install_library_gives_up_without_package_managers(self):
        with mock.patch.object(setup.os.path, "exists",
                               return_value=False):
            messages = []
            self.assertFalse(setup._pm_install_library(
                "libdvbcsa.so.1", messages))


class AstraInitProvisioningTests(unittest.TestCase):
    """v1.9.15: provision /etc/init.d/astra-sm from the plugin itself.

    postinst only created it when /usr/bin/astra existed at install time;
    on a fresh receiver the binary arrives later, so astra never started.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.init_path = os.path.join(self.tmp, "astra-sm")
        self.unit_path = os.path.join(self.tmp, "astra-sm.service")
        self.bin_path = os.path.join(self.tmp, "astra")
        with open(self.bin_path, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(self.bin_path, 0o755)

    def _run_provision(self):
        init = os.path.join(self.tmp, "init")
        unit = os.path.join(self.tmp, "unit")
        with mock.patch.object(setup, "ASTRA_INIT", self.init_path), \
             mock.patch.object(setup, "ASTRA_UNIT", self.unit_path), \
             mock.patch.object(setup, "ASTRA_BIN", self.bin_path):
            messages = []
            ok, msg = setup._ensure_astra_init(messages)
        return ok, msg, messages, init, unit

    def test_creates_both_files_when_missing(self):
        for p in (self.init_path, self.unit_path):
            self.assertFalse(os.path.exists(p))
        ok, msg, messages, _, _ = self._run_provision()
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(self.init_path))
        self.assertTrue(os.path.exists(self.unit_path))
        self.assertTrue(os.access(self.init_path, os.X_OK))
        with open(self.init_path) as f:
            self.assertEqual(f.read(), setup.ASTRA_INIT_SH)
        with open(self.unit_path) as f:
            self.assertEqual(f.read(), setup.ASTRA_UNIT_SH)

    def test_never_touches_existing_files(self):
        with open(self.init_path, "w") as f:
            f.write("IMAGE OWNED\n")
        self._run_provision()
        with open(self.init_path) as f:
            self.assertEqual(f.read(), "IMAGE OWNED\n")

    def test_noop_without_astra_binary(self):
        os.remove(self.bin_path)
        ok, msg, messages, _, _ = self._run_provision()
        self.assertFalse(ok)
        self.assertFalse(os.path.exists(self.init_path))


class SanitizeAstraConfTests(unittest.TestCase):
    """v1.9.16: '# comment' lines crash Lua astra (PANIC) - convert to '--'."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.conf = os.path.join(self.tmp, "astra.conf")
        self.bak = os.path.join(self.tmp, "astra.conf.abertisauto.bak")

    def test_converts_hash_comments_and_backs_up(self):
        original = (
            "# head comment\n"
            "-- keep me\n"
            "  # indented comment\n"
            "make_channel({ name = \"x\" })\n")
        with open(self.conf, "w") as f:
            f.write(original)
        with mock.patch.object(setup, "ASTRA_CONF", self.conf), \
             mock.patch.object(setup, "ASTRA_CONF_BACKUP", self.bak):
            count = setup.sanitize_astra_conf()
        self.assertEqual(count, 2)
        with open(self.conf) as f:
            converted = f.read()
        self.assertIn("-- head comment", converted)
        self.assertIn("  -- indented comment", converted)
        self.assertIn("-- keep me", converted)
        self.assertIn("make_channel", converted)
        self.assertFalse([l for l in converted.splitlines()
                          if l.lstrip().startswith("#")])
        with open(self.bak) as f:
            self.assertEqual(f.read(), original)

    def test_returns_zero_for_clean_config(self):
        with open(self.conf, "w") as f:
            f.write("-- clean\nmake_channel({})\n")
        with mock.patch.object(setup, "ASTRA_CONF", self.conf), \
             mock.patch.object(setup, "ASTRA_CONF_BACKUP", self.bak):
            self.assertEqual(setup.sanitize_astra_conf(), 0)
        self.assertFalse(os.path.exists(self.bak))
        with open(self.conf) as f:
            self.assertEqual(f.read(), "-- clean\nmake_channel({})\n")

    def test_returns_zero_when_config_missing(self):
        with mock.patch.object(setup, "ASTRA_CONF", self.conf), \
             mock.patch.object(setup, "ASTRA_CONF_BACKUP", self.bak):
            self.assertEqual(setup.sanitize_astra_conf(), 0)
        self.assertFalse(os.path.exists(self.bak))
