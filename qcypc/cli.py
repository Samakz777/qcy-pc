"""CLI: python -m qcypc <comando>. Reconhece o fone pelo anúncio BLE; use --address para escolher outro."""
from __future__ import annotations

import argparse
import asyncio
import sys

from . import protocol as p
from .device import Earbuds, discover


def _lvl(l: p.Level) -> str:
    return "?" if l.percent is None else f"{l.percent}%{' (carregando)' if l.charging else ''}"


def _print_status(s: dict) -> None:
    b = s["bateria"]
    print(f"{s['modelo']}  [{s['endereco']}]  nome: {s['nome']}")
    print(f"  bateria  esq {_lvl(b['esquerdo'])}  dir {_lvl(b['direito'])}  estojo {_lvl(b['estojo'])}")
    print(f"  firmware esq {s['firmware'].get('esquerdo')}  dir {s['firmware'].get('direito')}")
    print(f"  ruido    {s['ruido'][1] if s['ruido'] else '?'}  (0x{s['ruido'][0]:02X})" if s["ruido"] else "  ruido    ?")
    print(f"  jogo {s['jogo']}  sono {s['sono']}  balanco {s['balanco']}")
    if s["eq"]:
        print(f"  EQ       indice {s['eq'][0]} preset {s['eq'][2] or 'personalizado'} ganhos {s['eq'][1]}")
    acts = {v: k for k, v in p.ACTIONS.items()}
    gest = {v: k for k, v in p.GESTURES.items()}
    print("  botoes   " + ", ".join(f"{gest.get(g, g)}={acts.get(a, a)}" for g, a in sorted(s["botoes"].items())))


def _noise_value(arg: str) -> int:
    a = arg.lower()
    if a in ("off", "normal"):
        return p.NOISE_OFF
    if a.startswith("transp"):
        return p.transparency(int(a.split(":")[1]) if ":" in a else 4)
    scene, _, lvl = a.partition(":")
    if scene == "on":
        scene = "ruidoso"
    return p.anc(scene, int(lvl) if lvl else (1 if scene == "vento" else 3))


async def _run(args) -> int:
    if args.cmd == "scan":
        found = await discover(args.seconds)
        if not found:
            print("Nenhum fone QCY anunciando. Tire do estojo/abra a tampa e feche o app QCY no celular.")
            return 1
        for f in found:
            a = f.advert
            print(f"{f.address}  {a.model}  chip {p.chip_family(a.model_id)}  esq {_lvl(a.left)} dir {_lvl(a.right)}  rssi {f.rssi}")
        return 0

    found = await discover(args.seconds)
    if args.address:
        found = [f for f in found if f.address.upper() == args.address.upper()]
    if not found:
        print("Fone não encontrado (tire do estojo; só um app controla o canal BLE por vez).")
        return 1
    async with Earbuds(found[0]) as e:
        if args.cmd == "status":
            _print_status(await e.status())
        elif args.cmd == "probe":
            res = await e.probe(range(4, 0x60))  # pula 1-3 (resets), mesmo sendo só leitura
            for cmd, val in sorted(res.items()):
                print(f"  0x{cmd:02X} ({cmd:3d})  {val.hex(' ')}")
            print(f"{len(res)} comandos responderam")
        elif args.cmd == "anc":
            await e.set_noise(_noise_value(args.value))
        elif args.cmd == "eq":
            if args.value in p.EQ_PRESETS:
                await e.set_eq(*p.EQ_PRESETS[args.value])
            else:
                await e.set_eq(args.index, [int(x) for x in args.value.split(",")])
        elif args.cmd == "button":
            await e.set_buttons({p.GESTURES[args.gesture]: p.ACTIONS[args.action]})
        elif args.cmd in ("game", "sleep"):
            await e.set_toggle(p.Cmd.GAME_MODE if args.cmd == "game" else p.Cmd.SLEEP, args.value == "on")
        elif args.cmd == "balance":
            await e.set_balance(args.value)
        elif args.cmd == "name":
            await e.set_name(args.value)
        elif args.cmd == "reset":
            await e.send(p.reset_default())
        elif args.cmd == "factory-reset":
            if not args.yes_i_am_sure:
                print("Restaura de fábrica e apaga pareamentos. Repita com --yes-i-am-sure.")
                return 2
            await e.send(p.factory_reset())
        if args.cmd not in ("status", "probe"):
            await asyncio.sleep(1.0)
            _print_status(await e.status())
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="qcypc", description=__doc__)
    ap.add_argument("--address")
    ap.add_argument("--seconds", type=float, default=6.0, help="tempo de varredura")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    sub.add_parser("status")
    sub.add_parser("probe", help="somente leitura: lista os comandos que o fone responde")
    sub.add_parser("reset", help="restaura configurações padrão (mantém pareamento)")
    sub.add_parser("factory-reset").add_argument("--yes-i-am-sure", action="store_true")
    s = sub.add_parser("anc")
    s.add_argument("value", help="off | on | interno|trajeto|ruidoso|vento[:nivel] | transparencia[:0-6]")
    s = sub.add_parser("eq")
    s.add_argument("value", help=f"{'|'.join(p.EQ_PRESETS)} ou 10 ganhos separados por vírgula")
    s.add_argument("--index", type=int, default=0, help="índice para curva personalizada")
    s = sub.add_parser("button")
    s.add_argument("gesture", choices=p.GESTURES)
    s.add_argument("action", choices=p.ACTIONS)
    for n in ("game", "sleep"):
        sub.add_parser(n).add_argument("value", choices=("on", "off"))
    sub.add_parser("balance").add_argument("value", type=int)
    sub.add_parser("name").add_argument("value")
    return asyncio.run(_run(ap.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
