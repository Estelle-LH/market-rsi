"""Minimal, stdlib-only probe for an isolated disposable Linux container."""

import errno
import json
import os
import re
import socket
import tempfile


DOCKER_PATHS = ("/var/run/docker.sock", "/run/docker.sock")
ENV_VALUES = {
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
}
REQUIRED_ENV = frozenset(ENV_VALUES) | {"PATH"}
ALLOWED_ENV = REQUIRED_ENV | {"LC_CTYPE"}
DENIAL_ERRNOS = frozenset((errno.EACCES, errno.EPERM, errno.EROFS))
MOUNT_FLAGS = frozenset(("rw", "ro", "noexec", "exec", "nosuid", "suid", "nodev", "dev"))


def _write_probe(directory):
    result = {"outcome": "error", "errno": None, "cleanup_ok": True}
    try:
        fd, name = tempfile.mkstemp(prefix=".guest-probe-", dir=directory)
    except OSError as exc:
        result["errno"] = exc.errno
        if exc.errno in DENIAL_ERRNOS:
            result["outcome"] = "denied"
        return result
    try:
        payload = b"guest write probe\n"
        if os.write(fd, payload) != len(payload):
            raise OSError(errno.EIO, "short probe write")
        result["outcome"] = "writable"
    except OSError as exc:
        result["errno"] = exc.errno
    finally:
        # Only remove the unique file created by this probe, even on failure.
        try:
            os.close(fd)
        except OSError:
            result["cleanup_ok"] = False
        try:
            os.unlink(name)
        except OSError:
            result["cleanup_ok"] = False
    return result


def collect():
    report = {
        "uid": None, "gid": None, "status": {}, "interfaces": None,
        "root_write": None, "tmp_write": None, "tmp_mounts": None,
        "docker_sockets": {}, "environment": None, "collection_errors": [],
    }

    def observe(label, action):
        try:
            return action()
        except Exception as exc:
            # Exception messages and raw proc data can contain host identifiers.
            report["collection_errors"].append(label + ": " + type(exc).__name__)
            return None

    report["uid"] = observe("uid", os.getuid)
    report["gid"] = observe("gid", os.getgid)

    def read_status():
        with open("/proc/self/status", encoding="ascii") as stream:
            lines = stream.read().splitlines()
        result = {}
        for source, target, base in (("CapEff", "cap_eff", 16),
                                     ("NoNewPrivs", "no_new_privs", 10),
                                     ("Seccomp", "seccomp", 10)):
            values = [line.partition(":")[2].strip() for line in lines
                      if line.partition(":")[0] == source]
            pattern = r"[0-9a-fA-F]+" if base == 16 else r"[0-9]+"
            if len(values) != 1 or re.fullmatch(pattern, values[0]) is None:
                raise ValueError("missing or malformed status field")
            result[target] = int(values[0], base)
        return result

    report["status"] = observe("status", read_status)
    report["interfaces"] = observe(
        "interfaces", lambda: [name for _, name in socket.if_nameindex()])
    report["root_write"] = observe("root_write", lambda: _write_probe("/"))
    report["tmp_write"] = observe("tmp_write", lambda: _write_probe("/tmp"))

    def read_mounts():
        mounts = []
        with open("/proc/self/mountinfo", encoding="ascii") as stream:
            for line in stream:
                before, separator, after = line.strip().partition(" - ")
                fields, tail = before.split(), after.split()
                if not separator or len(fields) < 6 or len(tail) != 3:
                    raise ValueError("malformed mountinfo")
                if fields[4] == "/tmp":
                    # Omit mount IDs, sources, filesystem roots, and size options.
                    mounts.append({
                        "options": sorted(set(fields[5].split(",")) & MOUNT_FLAGS),
                        "super_options": sorted(set(tail[2].split(",")) & MOUNT_FLAGS),
                    })
        return mounts

    report["tmp_mounts"] = observe("tmp_mounts", read_mounts)
    for path in DOCKER_PATHS:
        def exists(path=path):
            try:
                os.lstat(path)
            except FileNotFoundError:
                return False
            return True
        report["docker_sockets"][path] = observe("docker socket " + path, exists)

    def read_environment():
        environment = dict(os.environ)
        # Only approved assertion values are recorded; never dump arbitrary values.
        return {"names": sorted(environment),
                "values": {key: environment[key] for key in ENV_VALUES
                           if key in environment}}

    report["environment"] = observe("environment", read_environment)
    return report


def validate(report):
    """Return explicit failures; missing or malformed evidence never passes."""
    failures = []
    if not isinstance(report, dict):
        return ["report: expected an object"]

    for key in ("uid", "gid"):
        value = report.get(key)
        if type(value) is not int or value <= 0:
            failures.append(key + ": expected a positive nonroot integer")

    status = report.get("status")
    if not isinstance(status, dict):
        failures.append("status: expected an object")
        status = {}
    for key, expected in (("cap_eff", 0), ("no_new_privs", 1), ("seccomp", 2)):
        if type(status.get(key)) is not int or status[key] != expected:
            failures.append("status." + key + ": expected integer " + str(expected))

    interfaces = report.get("interfaces")
    if (not isinstance(interfaces, list) or not interfaces
            or any(type(name) is not str for name in interfaces)
            or interfaces != ["lo"]):
        failures.append("interfaces: expected exactly the loopback interface lo")

    for key, expected in (("root_write", "denied"), ("tmp_write", "writable")):
        probe = report.get(key)
        if not isinstance(probe, dict):
            failures.append(key + ": expected a write-probe object")
            continue
        if probe.get("outcome") != expected:
            failures.append(key + ".outcome: expected " + expected)
        if probe.get("cleanup_ok") is not True:
            failures.append(key + ".cleanup_ok: expected true")
        if expected == "denied":
            if type(probe.get("errno")) is not int or probe["errno"] not in DENIAL_ERRNOS:
                failures.append(key + ".errno: expected EACCES, EPERM, or EROFS")
        elif "errno" not in probe or probe["errno"] is not None:
            failures.append(key + ".errno: expected null after successful write")

    mounts = report.get("tmp_mounts")
    if not isinstance(mounts, list) or len(mounts) != 1:
        failures.append("tmp_mounts: expected exactly one dedicated /tmp mount")
    elif not isinstance(mounts[0], dict):
        failures.append("tmp_mounts[0]: expected an object")
    else:
        for key, required in (("options", {"rw", "noexec", "nosuid", "nodev"}),
                              ("super_options", {"rw"})):
            flags = mounts[0].get(key)
            label = "tmp_mounts[0]." + key
            if (not isinstance(flags, list) or not flags
                    or any(type(flag) is not str or not flag for flag in flags)):
                failures.append(label + ": expected a nonempty list of flag strings")
                continue
            flagset = set(flags)
            if len(flags) != len(flagset):
                failures.append(label + ": duplicate flags")
            for flag in sorted(required - flagset):
                failures.append(label + ": missing " + flag)
            for flag in sorted(flagset & {"ro", "exec", "suid", "dev"}):
                failures.append(label + ": forbidden " + flag)

    sockets = report.get("docker_sockets")
    if not isinstance(sockets, dict):
        failures.append("docker_sockets: expected an object")
        sockets = {}
    for path in DOCKER_PATHS:
        if sockets.get(path) is not False:
            failures.append("docker_sockets[" + path + "]: expected false (absent)")

    environment = report.get("environment")
    if not isinstance(environment, dict):
        failures.append("environment: expected an object")
        environment = {}
    names = environment.get("names")
    if (not isinstance(names, list)
            or any(type(name) is not str or not name for name in names)):
        failures.append("environment.names: expected a list of nonempty strings")
        nameset = set()
    else:
        nameset = set(names)
        if len(names) != len(nameset):
            failures.append("environment.names: duplicate names")
        for name in sorted(nameset - ALLOWED_ENV):
            # Do not echo unexpected environment names or values.
            failures.append("environment.names: unexpected variable present")
    for name in sorted(REQUIRED_ENV - nameset):
        failures.append("environment.names: missing " + name)
    values = environment.get("values")
    if not isinstance(values, dict):
        failures.append("environment.values: expected an object")
        values = {}
    for name, expected in ENV_VALUES.items():
        if type(values.get(name)) is not str or values[name] != expected:
            failures.append("environment.values." + name + ": expected " + expected)

    errors = report.get("collection_errors")
    if not isinstance(errors, list):
        failures.append("collection_errors: expected a list")
    else:
        for index, error in enumerate(errors):
            if type(error) is not str or not error:
                failures.append("collection_errors[" + str(index) + "]: expected a nonempty string")
            else:
                failures.append("collection error: " + error)
    return failures


def main():
    try:
        report = collect()
        failures = validate(report)
        if not isinstance(report, dict):
            report = {}
    except Exception as exc:
        report = {}
        failures = ["probe exception: " + type(exc).__name__]
    report["failures"] = failures
    report["passed"] = not failures
    try:
        print(json.dumps(report, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"passed": False,
                          "failures": ["JSON report exception: " + type(exc).__name__]}))
        return 1
    return 37 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
