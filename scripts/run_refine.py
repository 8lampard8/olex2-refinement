"""Run one isolated Olex2 1.5 IAM refinement on Windows."""
import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path


def prepare(model, output, mask):
    if model.suffix.lower() not in {".res", ".ins"}:
        raise ValueError("Supply an INS or RES model.")
    data = model.with_suffix(".hkl")
    if not data.is_file():
        raise ValueError(f"Missing paired HKL: {data}")
    ins = model.read_bytes()
    records = ins.decode("latin1").splitlines()
    hklf = [r.strip() for r in records if re.match(r"\s*HKLF\b", r, re.I)]
    if len(hklf) != 1 or not re.fullmatch(r"HKLF\s+4(?:\.0+)?", hklf[0], re.I):
        raise ValueError("This runner needs a single plain HKLF 4 instruction.")
    if any(re.match(r"\s*(?:\+|TWIN\b|BASF\b)", r, re.I) for r in records):
        raise ValueError("Open the complete project in Olex2 for includes or twin models.")
    for line in records:
        if re.search(r"<HklSrc\b", line, re.I):
            field = re.search(r'<HklSrc\s+"([^"]+)"', line, re.I)
            source = field[1].replace("\\", "/") if field else ""
            local_names = {prefix + data.name.casefold() for prefix in ("", "./", "%.//", "%./")}
            if source.casefold() not in local_names:
                raise ValueError("Set HklSrc to the matching local HKL in a working copy.")
    fab = model.with_suffix(".fab")
    abin = any(re.match(r"\s*ABIN\b", r, re.I) for r in records)
    if mask is None and (abin or fab.exists()):
        raise ValueError("Existing mask detected. Choose --mask reuse or recompute explicitly.")
    if mask == "off" and abin:
        raise ValueError("ABIN is present. Prepare a separate unmasked INS before selecting off.")
    if mask == "reuse" and not fab.is_file():
        raise ValueError("Mask replay requires the matching .fab file.")
    if not any(re.fullmatch(r"\s*ACTA(?:\s+.*)?", r, re.I) for r in records) or not any(
        re.fullmatch(r"\s*LIST\s+4\s*", r, re.I) for r in records
    ):
        raise ValueError("Set ACTA and LIST 4 in a working copy for verifiable CIF and FCF output.")
    if re.search(r"""['"<>\r\n]""", str(output / model.name)):
        raise ValueError("Choose a plain output path without quotes or Olex2 macro delimiters.")
    output.mkdir(parents=True, exist_ok=False)
    staged = output / model.with_suffix(".ins").name
    staged.write_bytes(ins)
    sidecars = [data, model.with_suffix(".cif_od")]
    if mask == "reuse":
        sidecars += [fab, model.with_suffix(".sqf"), model.with_name(model.stem + "-mask.log")]
    for file in sidecars:
        if file.is_file():
            shutil.copyfile(file, output / file.name)
    return staged


def exchange(port, command):
    with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
        client.sendall(command.encode("utf-8"))
        return client.recv(1024).decode("utf-8", errors="replace").strip()


def refine(model, olex, mask, sump_mode, cycles, peaks, timeout):
    engine_log = model.parent / "engine.log"
    commands = [
        f"reap '{model}' -no_save=true",
        "spy.SetParam user.refinement.client_mode False",
        "spy.SetParam snum.refinement.program olex2.refine",
        "spy.SetParam snum.refinement.method Gauss-Newton",
        "spy.SetParam snum.refinement.use_solvent_mask " + str(mask in {"reuse", "recompute"}),
        "spy.SetParam snum.refinement.recompute_mask_before_refinement " + str(mask == "recompute"),
    ]
    if sump_mode:
        commands.append("spy.SetParam snum.smtbx.sump " + sump_mode)
    commands.append(f"refine {cycles} {peaks}")
    (model.parent / "commands.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
    environment = dict(os.environ, PYTHONHOME=str(olex / "Python"), OLEX2_DIR=str(olex) + os.sep,
                       BOOST_ADAPTBX_FPE_DEFAULT="1", BOOST_ADAPTBX_SIGNALS_DEFAULT="1")
    environment.pop("PYTHONPATH", None)
    environment["PATH"] = os.pathsep.join(map(str, [olex, olex / "cctbx/cctbx_build/lib",
                                                    olex / "Python/DLLs", environment["PATH"]]))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    job = uuid.uuid4().hex
    deadline = time.monotonic() + timeout
    with (model.parent / "console.log").open("wb") as console:
        process = subprocess.Popen([str(olex / "olex2c.dll"), "server", str(port), job, "-tm=90"],
                                   env=environment, cwd=olex, stdout=console, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            while True:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Engine failed to start. See console.log.")
                try:
                    if exchange(port, "status\n") == "busy":
                        break
                except OSError:
                    pass
                time.sleep(0.5)
            reply = exchange(port, "\n".join([f"run:{job}", f"xlog:{engine_log}", *commands, "@close"]))
            if "running" not in reply.lower():
                raise RuntimeError(f"Engine rejected run: {reply}")
            while time.monotonic() < deadline:
                time.sleep(1)
                if exchange(port, "status\n") != "busy":
                    break
            else:
                raise RuntimeError("Refinement timed out. See engine.log.")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    log = engine_log.read_text(encoding="utf-8", errors="replace") if engine_log.exists() else ""
    if "Refinement finished" not in log:
        raise RuntimeError("No completion marker. See engine.log.")
    for suffix in (".res", ".cif", ".fcf"):
        artifact = model.with_suffix(suffix)
        if not artifact.exists() or not artifact.stat().st_size:
            raise RuntimeError(f"Missing fresh output: {artifact.name}")
    if mask == "recompute" and not model.with_suffix(".fab").is_file():
        raise RuntimeError("Recomputed mask has no FAB for replay.")
    print(model.with_suffix(".cif"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="New trial directory (must not exist)")
    parser.add_argument("--olex-dir", type=Path, default=Path(os.getenv("ProgramFiles", ".")) / "Olex2-1.5")
    parser.add_argument("--mask", choices=["off", "reuse", "recompute"])
    parser.add_argument("--sump-mode", choices=["restraint", "constraint"])
    parser.add_argument("--cycles", type=int, default=8)
    parser.add_argument("--peaks", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=600, help="Wall-clock limit in seconds")
    args = parser.parse_args()
    if os.name != "nt" or not (args.olex_dir / "olex2c.dll").is_file():
        parser.error("The Windows Olex2 1.5 installation with olex2c.dll is required.")
    if args.cycles < 1 or args.peaks < 0 or args.timeout < 1:
        parser.error("Use positive cycles and timeout, and a nonnegative peak count.")
    try:
        staged = prepare(args.model.resolve(), args.out.resolve(), args.mask)
        refine(staged, args.olex_dir.resolve(), args.mask, args.sump_mode, args.cycles,
               args.peaks, args.timeout)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
