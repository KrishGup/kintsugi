"""kin — the Kintsugi command line.

    kin compile part.scad -o part.stl [-D name=value ...]
    kin checks part.stl --spec spec.yaml [-o checks.json]
    kin blueprint part.stl --spec spec.yaml -o sheets/ [--iteration N]
    kin new --spec spec.yaml --name bottle_handle [--sessions DIR]      -> creates a session directory
    kin iterate SESSION_DIR [--label "..."]                               -> compile + checks + blueprint for part.scad
    kin design SESSION_DIR [--model opus] [--budget 8] [--critic-rounds 2] [--message "..."]
    kin critique SESSION_DIR [--iteration N]
    kin params part.scad                                                  -> customizer parameters as JSON
    kin sheet -o calibration_sheet.pdf                                    -> printable ArUco calibration sheet
    kin serve [--host 0.0.0.0 --port 8000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kin", description="Kintsugi: photograph what broke, print what fits.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compile", help="compile a .scad file")
    p.add_argument("scad")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("-D", action="append", default=[], help="name=value overrides")
    p.add_argument("--timeout", type=float, default=300)

    p = sub.add_parser("checks", help="run spec checks on a mesh")
    p.add_argument("mesh")
    p.add_argument("--spec", required=True)
    p.add_argument("-o", "--out")
    p.add_argument("--iteration", type=int, default=0)

    p = sub.add_parser("blueprint", help="render blueprint sheets for a mesh")
    p.add_argument("mesh")
    p.add_argument("--spec", required=True)
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--iteration", type=int, default=0)
    p.add_argument("--no-checks", action="store_true")

    p = sub.add_parser("new", help="create a session")
    p.add_argument("--spec", required=True)
    p.add_argument("--name")
    p.add_argument("--sessions")
    p.add_argument("--scad", help="optional starting part.scad")

    p = sub.add_parser("iterate", help="compile + checks + blueprint for a session's part.scad")
    p.add_argument("session")
    p.add_argument("--label", default="")
    p.add_argument("--budget", type=int, default=8)

    p = sub.add_parser("design", help="run the designer agent (and critic) on a session")
    p.add_argument("session")
    p.add_argument("--model")
    p.add_argument("--critic-model")
    p.add_argument("--budget", type=int, default=8)
    p.add_argument("--critic-rounds", type=int, default=2)
    p.add_argument("--message", help="user notes for the designer")
    p.add_argument("--strategy", help="strategy hint (e.g. 'use the template', 'primitives only')")
    p.add_argument("--resume", help="message to resume a waiting session with (the user's answer)")
    p.add_argument("--no-critic", action="store_true")
    p.add_argument("--max-turns", type=int, default=150)

    p = sub.add_parser("critique", help="run the critic on a session's iteration")
    p.add_argument("session")
    p.add_argument("--iteration", type=int)
    p.add_argument("--model")

    p = sub.add_parser("params", help="print customizer parameters")
    p.add_argument("scad")

    p = sub.add_parser("sheet", help="generate the printable calibration sheet")
    p.add_argument("-o", "--out", default="calibration_sheet.pdf")
    p.add_argument("--paper", default="letter", choices=["letter", "a4"])

    p = sub.add_parser("serve", help="run the web server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")

    p = sub.add_parser("export", help="export bundle for a session")
    p.add_argument("session")

    args = ap.parse_args(argv)
    return _dispatch(args)


def _dispatch(args) -> int:
    if args.cmd == "compile":
        from kintsugi.scad.compile import compile_scad
        defines = {}
        for d in args.D:
            k, _, v = d.partition("=")
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                pass
            defines[k] = v
        r = compile_scad(args.scad, args.out, defines, timeout_s=args.timeout)
        print(r.summary())
        return 0 if r.ok else 1

    if args.cmd == "checks":
        from kintsugi.checks import run_checks
        from kintsugi.spec import PartSpec
        rep = run_checks(args.mesh, PartSpec.load(args.spec), iteration=args.iteration)
        print(rep.summary_for_model())
        if args.out:
            rep.save(args.out)
        return 0 if rep.all_hard_pass else 1

    if args.cmd == "blueprint":
        from kintsugi.checks import run_checks
        from kintsugi.render import make_blueprint
        from kintsugi.spec import PartSpec
        spec = PartSpec.load(args.spec)
        rep = None if args.no_checks else run_checks(args.mesh, spec, iteration=args.iteration)
        res = make_blueprint(args.mesh, spec, rep, args.out, args.iteration)
        print(json.dumps(res.to_dict(), indent=2))
        return 0

    if args.cmd == "new":
        from kintsugi.session.workspace import Session
        from kintsugi.spec import PartSpec
        spec = PartSpec.load(args.spec)
        s = Session.create(args.name or spec.part.name, spec, sessions_dir=Path(args.sessions) if args.sessions else None)
        if args.scad:
            s.scad_path.write_text(Path(args.scad).read_text())
            s.commit("initial part.scad")
        print(s.dir)
        return 0

    if args.cmd == "iterate":
        from kintsugi.agent.pipeline import run_iteration
        from kintsugi.session.workspace import Session
        s = Session.open(args.session)
        res = run_iteration(s, label=args.label, budget=args.budget)
        print(res.summary_for_model())
        return 0 if res.ok else 1

    if args.cmd == "design":
        from kintsugi.agent.designer import run_designer
        from kintsugi.session.workspace import Session
        s = Session.open(args.session)
        out = asyncio.run(run_designer(s, model=args.model, budget=args.budget, critic_rounds=args.critic_rounds, user_message=args.message,
                                       strategy=args.strategy, resume_message=args.resume, run_critic=not args.no_critic,
                                       critic_model=args.critic_model, max_turns=args.max_turns))
        print(json.dumps(out.to_dict(), indent=2))
        return 0 if out.status == "done" else 1

    if args.cmd == "critique":
        from kintsugi.agent.critic import critique
        from kintsugi.session.workspace import Session
        s = Session.open(args.session)
        n = args.iteration or int(s.meta.get("iteration", 0))
        it = s.iteration_dir(n)
        rep = None
        cj = it / "checks.json"
        if cj.exists():
            from kintsugi.checks import run_checks
            rep = run_checks(it / "part.stl", s.spec(), iteration=n)
        sheets = [p for p in (it / "sheets" / f"iter_{n:02d}_sheet.png", it / "sheets" / f"iter_{n:02d}_sections.png") if p.exists()]
        v = asyncio.run(critique(s.spec(), rep, sheets, model=args.model, cwd=s.dir))
        print(v.summary_for_model())
        return 0

    if args.cmd == "params":
        from kintsugi.scad.customizer import parse_customizer
        print(json.dumps([p.to_dict() for p in parse_customizer(Path(args.scad).read_text())], indent=2))
        return 0

    if args.cmd == "sheet":
        from kintsugi.measure.sheet import make_calibration_sheet
        p = make_calibration_sheet(args.out, paper=args.paper)
        print(p)
        return 0

    if args.cmd == "serve":
        import uvicorn
        uvicorn.run("kintsugi.server.app:app", host=args.host, port=args.port, reload=args.reload)
        return 0

    if args.cmd == "export":
        from kintsugi.agent.export import export_bundle
        from kintsugi.session.workspace import Session
        s = Session.open(args.session)
        print(json.dumps(export_bundle(s), indent=2, default=str))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
