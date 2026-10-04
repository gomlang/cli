import json
import os
from pathlib import Path
import pty
import re
import select
import shlex
import signal
import sys
import time

root = Path(sys.argv[1]).resolve()
fish = sys.argv[2]
report = []


def read_until(fd, marker, timeout=10):
    output = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if select.select([fd], [], [], 0.05)[0]:
            try:
                output.extend(os.read(fd, 65536))
            except OSError:
                break
            match = re.search(marker, output)
            if match:
                return bytes(output), match
    raise AssertionError(f"terminal deadline: {output.decode(errors='replace')}")


def fish_quote(value):
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def run_case(shell, arguments, prefix, expected, suffix=""):
    marker = root / "injected"
    marker.unlink(missing_ok=True)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(root)
        environment = dict(os.environ, TERM="xterm-256color", LC_ALL="C.UTF-8")
        os.execvpe(shell, [shell, *arguments], environment)
    output = b""
    try:
        reader = 'import json,sys; print("GOML_ARGS:"+json.dumps(sys.argv[1:]))'
        if shell == fish:
            functions = Path(fish).parent.parent / "share/fish/functions"
            setup = ""
            if functions.is_dir():
                setup = "set -g fish_function_path " + fish_quote(str(functions)) + "; fish_default_key_bindings; "
            setup += "source " + fish_quote(str(root / "completion.fish"))
            setup += "; function app; " + fish_quote(sys.executable) + " -c " + fish_quote(reader) + " $argv; end"
            setup += "; function fish_prompt; printf 'GOML_PROMPT> '; end"
        else:
            setup = "source " + shlex.quote(str(root / ("completion." + shell)))
            setup += "; app() { " + shlex.quote(sys.executable) + " -c " + shlex.quote(reader) + ' "$@"; }; PS1="GOML_PROMPT> "'
            if shell == "zsh":
                setup = "autoload -Uz compinit; compinit -D -i; " + setup
        os.write(fd, (setup + "; printf '__GOML_READY__\\n'\n").encode())
        read_until(fd, rb"__GOML_READY__\r\n")
        os.write(fd, (prefix + suffix + "\x02" * len(suffix) + "\t\n").encode())
        output, match = read_until(fd, rb"GOML_ARGS:(\[[^\r\n]*\])\r\n")
        actual = json.loads(match.group(1))
        if actual != expected or marker.exists():
            raise AssertionError(f"{shell}: {prefix}: expected {expected!r}, got {actual!r}, injection={marker.exists()}")
        report.append({"shell": shell, "prefix": prefix, "arguments": actual, "injected": False})
    except BaseException as error:
        raise AssertionError(f"{shell}: {prefix}: {error}; terminal={output.decode(errors='replace')}") from error
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(pid, 0)
        os.close(fd)


if len(sys.argv) > 3 and sys.argv[3] == "empty":
    for shell, arguments in [("bash", ["--noprofile", "--norc", "-i"]), ("zsh", ["-f", "-i"]), (fish, ["--no-config", "--interactive"])]:
        for quote in ["", "'", '"', "''", '""']:
            # Fish 3.x needs a quote for a separate empty argument; its completion
            # reader otherwise inserts only a space for an empty candidate.
            if shell != fish or quote:
                for option in ["--mode", "--style", "-m"]:
                    run_case(shell, arguments, "app " + option + " " + quote, [option, ""])
                run_case(shell, arguments, "app run -- " + quote, ["run", "--", ""])
                suffix = (quote if len(quote) == 1 else "") + " end"
                run_case(shell, arguments, "app run --mode " + quote, ["run", "--mode", "", "end"], suffix)
            for option in ["--mode", "--style"]:
                run_case(shell, arguments, "app " + option + "=" + quote, [option + "="])
        for quote in ["", "'", '"']:
            run_case(shell, arguments, "app --mixed " + quote + "va", ["--mixed", "value"])
            run_case(shell, arguments, "app --mixed " + quote + "tw", ["--mixed", "two words"])
        run_case(shell, arguments, "app --mixed unknown", ["--mixed", "unknown"])
    (root / "pty-report.json").write_text(json.dumps(report, indent=2))
    print(f"{len(report)} interactive empty completion cases passed")
    sys.exit(0)


values = [
    ("two", "two words"),
    ("quo", "quo'te"),
    ("back", "back\\slash"),
    ("evil", "evil$(touch injected)"),
    ("tick", "tick`touch injected`"),
    ("dollar", "dollar$HOME"),
    ("semi", "semi;touch injected"),
    ("glob", "glob[abc]*?"),
    ("dirc", "dirchoice"),
    ("caf", "café"),
    ("漢", "漢字 two"),
]
(root / "dirchoice").mkdir(exist_ok=True)
for shell, arguments in [("bash", ["--noprofile", "--norc", "-i"]), ("zsh", ["-f", "-i"]), (fish, ["--no-config", "--interactive"])]:
    for prefix, value in values:
        for quote in ["", '"', "'"]:
            run_case(shell, arguments, "app --mode " + quote + prefix, ["--mode", value])
    for value_prefix, value in [("two", "two words"), ("evil", "evil$(touch injected)")]:
        for quote in ["", '"', "'"]:
            run_case(shell, arguments, "app --mode=" + quote + value_prefix, ["--mode=" + value])
            run_case(shell, arguments, "app -vm" + quote + value_prefix, ["-vm" + value])
    run_case(shell, arguments, "app --mode region:e", ["--mode", "region:east"])
    run_case(shell, arguments, "app --mode caf", ["--mode", "café", "end"], " end")
    run_case(shell, arguments, "app --mode 漢字 run --f", ["--mode", "漢字", "run", "--force", "end"], " end")
    run_case(shell, arguments, 'app "run" --f', ["run", "--force"])
    run_case(shell, arguments, "app 'run' --f", ["run", "--force"])
    run_case(shell, arguments, "app --mode \\$H", ["--mode", "$HOME"])
    if shell != fish:
        run_case(shell, arguments, "app r\\un --f", ["run", "--force"])
    if shell == "bash":
        run_case(shell, arguments, "app --mode $H", ["--mode", "$HOME"])
(root / "pty-report.json").write_text(json.dumps(report, indent=2))
print(f"{len(report)} interactive completion cases passed")
