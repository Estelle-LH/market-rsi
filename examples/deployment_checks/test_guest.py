"""Fixture-only tests: no local OS inspection, containers, or networking."""

import copy
import errno
import io
import json
import unittest
from contextlib import ExitStack, contextmanager, redirect_stdout
from unittest.mock import Mock, patch

import guest


def secure_report():
    return {
        "uid": 10001,
        "gid": 10001,
        "status": {"cap_eff": 0, "no_new_privs": 1, "seccomp": 2},
        "interfaces": ["lo"],
        "root_write": {"outcome": "denied", "errno": errno.EROFS, "cleanup_ok": True},
        "tmp_write": {"outcome": "writable", "errno": None, "cleanup_ok": True},
        "tmp_mounts": [{"options": ["rw", "noexec", "nosuid", "nodev"],
                        "super_options": ["rw"]}],
        "docker_sockets": {"/var/run/docker.sock": False, "/run/docker.sock": False},
        "environment": {
            "names": ["PATH", "HOME", "LANG", "PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED"],
            "values": {"HOME": "/nonexistent", "LANG": "C.UTF-8",
                       "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"},
        },
        "collection_errors": [],
    }


STATUS = ("Name:\tDO_NOT_REPORT_HOST_NAME\n"
          "CapEff:\t0000000000000000\nNoNewPrivs:\t1\nSeccomp:\t2\n")
MOUNTINFO = ("1 0 0:1 / / ro - overlay PRIVATE_SOURCE ro\n"
             "2 1 0:2 / /tmp rw,nosuid,nodev,noexec - tmpfs PRIVATE_SOURCE rw,size=65536k\n")
ENVIRONMENT = {"PATH": "/PRIVATE_HOST_PATH", "HOME": "/nonexistent", "LANG": "C.UTF-8",
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}


@contextmanager
def mocked_collection(status=STATUS, mountinfo=MOUNTINFO, environment=None,
                      socket_effect=None, root_error=None):
    files = {"/proc/self/status": status, "/proc/self/mountinfo": mountinfo}

    def open_fixture(path, *args, **kwargs):
        if path not in files:
            raise AssertionError("unexpected file read")
        value = files[path]
        if isinstance(value, Exception):
            raise value
        return io.StringIO(value)

    def create_fixture(*args, **kwargs):
        if kwargs.get("dir") == "/":
            raise root_error or OSError(errno.EROFS, "fixture read-only root")
        if kwargs.get("dir") == "/tmp":
            return 91, "/tmp/.guest-probe-fixture"
        raise AssertionError("unexpected write directory")

    with ExitStack() as stack:
        opened = stack.enter_context(patch("builtins.open", side_effect=open_fixture))
        stack.enter_context(patch("guest.os.getuid", return_value=10001))
        stack.enter_context(patch("guest.os.getgid", return_value=10001))
        stack.enter_context(patch("guest.socket.if_nameindex", return_value=[(1, "lo")]))
        stack.enter_context(patch("guest.os.environ", dict(
            ENVIRONMENT if environment is None else environment)))
        created = stack.enter_context(patch("guest.tempfile.mkstemp", side_effect=create_fixture))
        stack.enter_context(patch("guest.os.write", return_value=len(b"guest write probe\n")))
        stack.enter_context(patch("guest.os.close"))
        removed = stack.enter_context(patch("guest.os.unlink"))
        checked = stack.enter_context(patch(
            "guest.os.lstat", side_effect=socket_effect or FileNotFoundError(errno.ENOENT, "absent")))
        yield {"opened": opened, "created": created, "removed": removed, "checked": checked}


class ValidationTests(unittest.TestCase):
    def assert_failure(self, report, label):
        failures = guest.validate(report)
        self.assertTrue(failures)
        self.assertTrue(any(label in item for item in failures), failures)
        self.assertTrue(all(isinstance(item, str) and item for item in failures))

    def test_secure_fixture_passes_without_mutation(self):
        report = secure_report()
        original = copy.deepcopy(report)
        self.assertEqual(guest.validate(report), [])
        self.assertEqual(report, original)

    def test_optional_lc_ctype_and_denial_errnos(self):
        for code in (errno.EACCES, errno.EPERM, errno.EROFS):
            with self.subTest(code=code):
                report = secure_report()
                report["environment"]["names"].append("LC_CTYPE")
                report["root_write"]["errno"] = code
                self.assertEqual(guest.validate(report), [])

    def test_uid_and_gid_must_be_nonroot_integers(self):
        for key in ("uid", "gid"):
            for value in (0, -1, None, "10001", True, 1.5, [], {}):
                with self.subTest(key=key, value=value):
                    report = secure_report()
                    report[key] = value
                    self.assert_failure(report, key)

    def test_capabilities_nonewprivs_and_seccomp(self):
        for key, value in (("cap_eff", 1), ("cap_eff", 1 << 40),
                           ("no_new_privs", 0), ("seccomp", 0), ("seccomp", 1)):
            with self.subTest(key=key, value=value):
                report = secure_report()
                report["status"][key] = value
                self.assert_failure(report, "status." + key)
        for key in ("cap_eff", "no_new_privs", "seccomp"):
            for value in (None, True, "0", [], {}):
                with self.subTest(key=key, value=value):
                    report = secure_report()
                    report["status"][key] = value
                    self.assert_failure(report, "status." + key)

    def test_interfaces_must_be_only_lo(self):
        for value in ([], ["lo", "eth0"], ["eth0"], ["lo", "lo"], "lo", [None], [["lo"]]):
            with self.subTest(value=value):
                report = secure_report()
                report["interfaces"] = value
                self.assert_failure(report, "interfaces")

    def test_write_outcomes_and_cleanup(self):
        cases = (("root_write", "outcome", "writable"),
                 ("root_write", "outcome", "error"),
                 ("root_write", "errno", errno.ENOENT),
                 ("root_write", "errno", None),
                 ("root_write", "errno", True),
                 ("tmp_write", "outcome", "denied"),
                 ("tmp_write", "outcome", "error"),
                 ("tmp_write", "errno", errno.EIO))
        for key, field, value in cases:
            with self.subTest(key=key, field=field, value=value):
                report = secure_report()
                report[key][field] = value
                self.assert_failure(report, key + "." + field)
        for key in ("root_write", "tmp_write"):
            report = secure_report()
            report[key]["cleanup_ok"] = False
            self.assert_failure(report, key + ".cleanup_ok")
            for field in ("outcome", "errno", "cleanup_ok"):
                report = secure_report()
                del report[key][field]
                self.assert_failure(report, key + "." + field)

    def test_mount_must_be_dedicated_and_unambiguous(self):
        for value in ([], None, {}, [None], [{}, {}]):
            with self.subTest(value=value):
                report = secure_report()
                report["tmp_mounts"] = value
                self.assert_failure(report, "tmp_mounts")

    def test_each_mount_flag_is_required(self):
        for flag in ("rw", "noexec", "nosuid", "nodev"):
            report = secure_report()
            report["tmp_mounts"][0]["options"].remove(flag)
            self.assert_failure(report, "missing " + flag)
        report = secure_report()
        report["tmp_mounts"][0]["super_options"] = ["ro"]
        self.assert_failure(report, "super_options")

    def test_contradictory_and_malformed_mount_flags(self):
        for field in ("options", "super_options"):
            for flag in ("ro", "exec", "suid", "dev"):
                report = secure_report()
                report["tmp_mounts"][0][field].append(flag)
                self.assert_failure(report, "forbidden " + flag)
            for value in (None, "rw,noexec,nosuid,nodev", [None], [["rw"]], [], ["rw", "rw"]):
                with self.subTest(field=field, value=value):
                    report = secure_report()
                    report["tmp_mounts"][0][field] = value
                    self.assert_failure(report, "tmp_mounts[0]." + field)

    def test_docker_sockets_must_be_observed_absent(self):
        for path in guest.DOCKER_PATHS:
            for value in (True, None, 0, "false", []):
                with self.subTest(path=path, value=value):
                    report = secure_report()
                    report["docker_sockets"][path] = value
                    self.assert_failure(report, path)
            report = secure_report()
            del report["docker_sockets"][path]
            self.assert_failure(report, path)

    def test_environment_rejects_extra_and_missing_names(self):
        report = secure_report()
        report["environment"]["names"].append("AWS_SECRET_ACCESS_KEY")
        self.assert_failure(report, "unexpected variable")
        for name in guest.REQUIRED_ENV:
            report = secure_report()
            report["environment"]["names"].remove(name)
            self.assert_failure(report, "missing " + name)
        for value in (None, "PATH", [None], [["PATH"]], ["PATH", "PATH"]):
            report = secure_report()
            report["environment"]["names"] = value
            self.assert_failure(report, "environment.names")

    def test_environment_exact_required_values(self):
        for name in guest.ENV_VALUES:
            for value in (None, "wrong", 0, True, [], {}):
                with self.subTest(name=name, value=value):
                    report = secure_report()
                    report["environment"]["values"][name] = value
                    self.assert_failure(report, "environment.values." + name)
            report = secure_report()
            del report["environment"]["values"][name]
            self.assert_failure(report, "environment.values." + name)

    def test_every_top_level_observation_is_required(self):
        for key in secure_report():
            with self.subTest(key=key):
                report = secure_report()
                del report[key]
                self.assert_failure(report, key)
                report = secure_report()
                report[key] = None
                self.assert_failure(report, key)

    def test_nested_missing_observations(self):
        for parent, keys in (("status", ("cap_eff", "no_new_privs", "seccomp")),
                             ("environment", ("names", "values"))):
            for key in keys:
                report = secure_report()
                del report[parent][key]
                self.assert_failure(report, parent + "." + key)
        for key in ("options", "super_options"):
            report = secure_report()
            del report["tmp_mounts"][0][key]
            self.assert_failure(report, key)

    def test_invalid_reports_and_collection_errors(self):
        for value in (None, [], "report", 0, True):
            self.assertEqual(guest.validate(value), ["report: expected an object"])
        for value in (None, "error", [None], [""], ["status: ValueError"]):
            report = secure_report()
            report["collection_errors"] = value
            self.assert_failure(report, "collection")


class CollectionTests(unittest.TestCase):
    def test_secure_collection_reads_only_fixture_surfaces_and_redacts(self):
        with mocked_collection() as calls:
            report = guest.collect()
        self.assertEqual(guest.validate(report), [])
        self.assertEqual([call.args[0] for call in calls["opened"].call_args_list],
                         ["/proc/self/status", "/proc/self/mountinfo"])
        self.assertEqual([call.kwargs["dir"] for call in calls["created"].call_args_list],
                         ["/", "/tmp"])
        self.assertEqual([call.args[0] for call in calls["checked"].call_args_list],
                         list(guest.DOCKER_PATHS))
        calls["removed"].assert_called_once_with("/tmp/.guest-probe-fixture")
        encoded = json.dumps(report)
        for private in ("DO_NOT_REPORT_HOST_NAME", "PRIVATE_SOURCE", "PRIVATE_HOST_PATH", "65536k"):
            self.assertNotIn(private, encoded)

    def test_status_missing_duplicate_and_malformed_do_not_pass(self):
        cases = ("", STATUS.replace("Seccomp:\t2\n", ""),
                 STATUS + "CapEff:\t0\n", STATUS.replace("0000000000000000", "garbage"),
                 STATUS.replace("NoNewPrivs:\t1", "NoNewPrivs:\t-1"),
                 STATUS.replace("Seccomp:\t2", "Seccomp:\ttwo"),
                 PermissionError(errno.EACCES, "PRIVATE_ERROR"))
        for value in cases:
            with self.subTest(value=type(value).__name__):
                with mocked_collection(status=value):
                    report = guest.collect()
                self.assertTrue(guest.validate(report))
                self.assertTrue(any(error.startswith("status:") for error in report["collection_errors"]))
                self.assertNotIn("PRIVATE_ERROR", json.dumps(report))

    def test_nonzero_status_is_collected_and_fails(self):
        for old, new, key in (("0000000000000000", "0000000000000001", "cap_eff"),
                               ("NoNewPrivs:\t1", "NoNewPrivs:\t0", "no_new_privs"),
                               ("Seccomp:\t2", "Seccomp:\t1", "seccomp")):
            with mocked_collection(status=STATUS.replace(old, new)):
                report = guest.collect()
            self.assertTrue(any(key in failure for failure in guest.validate(report)))

    def test_missing_unsafe_duplicate_and_malformed_mountinfo(self):
        cases = ("", MOUNTINFO.splitlines()[0] + "\n", MOUNTINFO + MOUNTINFO,
                 MOUNTINFO.replace(",noexec", ""), "malformed\n",
                 PermissionError(errno.EACCES, "PRIVATE_ERROR"))
        for value in cases:
            with mocked_collection(mountinfo=value):
                report = guest.collect()
            self.assertTrue(any("tmp_mounts" in failure for failure in guest.validate(report)))

    def test_socket_permission_error_is_not_absence(self):
        with mocked_collection(socket_effect=PermissionError(errno.EACCES, "PRIVATE_ERROR")):
            report = guest.collect()
        self.assertTrue(all(value is None for value in report["docker_sockets"].values()))
        self.assertTrue(guest.validate(report))
        self.assertNotIn("PRIVATE_ERROR", json.dumps(report))

    def test_socket_presence_is_recorded(self):
        with mocked_collection(socket_effect=Mock(return_value=object())):
            report = guest.collect()
        self.assertTrue(all(value is True for value in report["docker_sockets"].values()))
        self.assertTrue(guest.validate(report))

    def test_unexpected_environment_values_are_never_reported(self):
        environment = dict(ENVIRONMENT, SECRET_TOKEN="PRIVATE_SECRET")
        with mocked_collection(environment=environment):
            report = guest.collect()
        self.assertNotIn("PRIVATE_SECRET", json.dumps(report))
        self.assertIn("SECRET_TOKEN", report["environment"]["names"])
        self.assertTrue(guest.validate(report))

    def test_unrelated_root_errors_do_not_count_as_denial(self):
        with mocked_collection(root_error=OSError(errno.EIO, "fixture IO failure")):
            report = guest.collect()
        self.assertEqual(report["root_write"]["outcome"], "error")
        self.assertTrue(guest.validate(report))


class WriteProbeTests(unittest.TestCase):
    def test_unexpected_writable_root_is_removed_and_fails(self):
        with patch("guest.tempfile.mkstemp", return_value=(91, "/.guest-probe-fixture")) as create, \
                patch("guest.os.write", return_value=len(b"guest write probe\n")), \
                patch("guest.os.close") as close, patch("guest.os.unlink") as remove:
            result = guest._write_probe("/")
        self.assertEqual(result, {"outcome": "writable", "errno": None, "cleanup_ok": True})
        create.assert_called_once_with(prefix=".guest-probe-", dir="/")
        close.assert_called_once_with(91)
        remove.assert_called_once_with("/.guest-probe-fixture")
        report = secure_report()
        report["root_write"] = result
        self.assertTrue(guest.validate(report))

    def test_tmp_denial_short_write_and_cleanup_failures(self):
        with patch("guest.tempfile.mkstemp", side_effect=PermissionError(errno.EACCES, "denied")):
            result = guest._write_probe("/tmp")
        self.assertEqual(result["outcome"], "denied")
        report = secure_report()
        report["tmp_write"] = result
        self.assertTrue(guest.validate(report))
        for write_result, close_error, unlink_error in (
                (0, None, None), (len(b"guest write probe\n"), OSError(errno.EIO, "close"), None),
                (len(b"guest write probe\n"), None, PermissionError(errno.EPERM, "unlink"))):
            with patch("guest.tempfile.mkstemp", return_value=(91, "/tmp/.guest-probe-fixture")), \
                    patch("guest.os.write", return_value=write_result), \
                    patch("guest.os.close", side_effect=close_error), \
                    patch("guest.os.unlink", side_effect=unlink_error) as remove:
                result = guest._write_probe("/tmp")
            remove.assert_called_once_with("/tmp/.guest-probe-fixture")
            report = secure_report()
            report["tmp_write"] = result
            self.assertTrue(guest.validate(report))

    def test_write_exception_still_removes_only_created_file(self):
        with patch("guest.tempfile.mkstemp", return_value=(91, "/tmp/.guest-probe-fixture")), \
                patch("guest.os.write", side_effect=OSError(errno.EIO, "write")), \
                patch("guest.os.close") as close, patch("guest.os.unlink") as remove:
            result = guest._write_probe("/tmp")
        self.assertEqual(result["outcome"], "error")
        self.assertEqual(result["errno"], errno.EIO)
        close.assert_called_once_with(91)
        remove.assert_called_once_with("/tmp/.guest-probe-fixture")


class MainTests(unittest.TestCase):
    def run_main(self, report=None, error=None):
        output = io.StringIO()
        with patch("guest.collect", return_value=report, side_effect=error), redirect_stdout(output):
            code = guest.main()
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        return code, json.loads(lines[0])

    def test_secure_main_intentionally_returns_37(self):
        code, report = self.run_main(secure_report())
        self.assertEqual(code, 37)
        self.assertIs(report["passed"], True)
        self.assertEqual(report["failures"], [])

    def test_unsafe_main_returns_1_with_precise_failures(self):
        fixture = secure_report()
        fixture["uid"] = 0
        code, report = self.run_main(fixture)
        self.assertEqual(code, 1)
        self.assertIs(report["passed"], False)
        self.assertTrue(any("uid" in failure for failure in report["failures"]))

    def test_missing_or_exceptional_observations_return_1(self):
        for fixture in (None, {}, []):
            code, report = self.run_main(fixture)
            self.assertEqual(code, 1)
            self.assertIs(report["passed"], False)
            self.assertTrue(report["failures"])
        code, report = self.run_main(error=RuntimeError("PRIVATE_EXCEPTION"))
        self.assertEqual(code, 1)
        self.assertEqual(report["failures"], ["probe exception: RuntimeError"])
        self.assertNotIn("PRIVATE_EXCEPTION", json.dumps(report))

    def test_validation_and_json_exceptions_return_1(self):
        with patch("guest.validate", side_effect=RuntimeError("PRIVATE_EXCEPTION")):
            code, report = self.run_main(secure_report())
        self.assertEqual(code, 1)
        self.assertIs(report["passed"], False)
        fixture = secure_report()
        fixture["unserializable"] = object()
        code, report = self.run_main(fixture)
        self.assertEqual(code, 1)
        self.assertIs(report["passed"], False)
        self.assertIn("JSON report exception", report["failures"][0])


if __name__ == "__main__":
    unittest.main()
