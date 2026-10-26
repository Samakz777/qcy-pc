"""Janela do QCY PC. Thread de fundo (asyncio + bleak) conversa com a UI por filas.

python -m qcypc.gui          # fone real
python -m qcypc.gui --demo   # fone simulado, para ver a interface sem Bluetooth
"""
from __future__ import annotations

import asyncio
import ctypes
import os
import queue
import sys
import tempfile
import threading

import customtkinter as ctk
import pystray

from . import protocol as p
from .device import Earbuds, discover
from .icon import make_icon

SCENES = ["interno", "trajeto", "ruidoso", "vento"]
PRESET_LABEL = {"padrao": "Padrão", "popular": "Popular", "bass": "Bass pesado", "rock": "Rock",
                "suave": "Suave", "classico": "Clássico"}
ACTION_LABEL = {"nada": "Nenhuma", "play-pause": "Play/Pausa", "anterior": "Faixa anterior",
                "proxima": "Próxima faixa", "assistente": "Assistente de voz", "volume+": "Volume +",
                "volume-": "Volume −", "jogo": "Modo jogo", "anc": "Alternar ANC"}
GESTURE_LABEL = {"esq-1": "Esquerdo · 1 toque", "dir-1": "Direito · 1 toque", "esq-2": "Esquerdo · 2 toques",
                 "dir-2": "Direito · 2 toques", "esq-3": "Esquerdo · 3 toques", "dir-3": "Direito · 3 toques"}


# --- fone simulado (só para --demo) --------------------------------------------------------------

class FakeEarbuds:
    connected = True

    def __init__(self):
        self.s = {"modelo": "QCY Melobuds ANC (HT05) · simulado", "endereco": "00:00:00:00:00:00",
                  "bateria": {"esquerdo": p.Level(65, False), "direito": p.Level(68, False), "estojo": p.Level(None, False)},
                  "firmware": {"esquerdo": "2.0.9", "direito": "2.0.9"}, "ruido": (0x63, p.noise_label(0x63)),
                  "jogo": False, "sono": False, "balanco": 50, "nome": "QCY Melobuds ANC",
                  "eq": (1, [0] * 10, "padrao"), "botoes": {1: 0, 2: 0, 3: 1, 4: 1, 5: 4, 6: 4}, "mtu": 247}

    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None
    async def status(self): return dict(self.s)
    async def set_noise(self, v): self.s["ruido"] = (v, p.noise_label(v))
    async def set_toggle(self, cmd, on): self.s["jogo" if cmd == p.Cmd.GAME_MODE else "sono"] = on
    async def set_balance(self, v): self.s["balanco"] = v
    async def set_name(self, n): self.s["nome"] = n
    async def set_eq(self, i, g): self.s["eq"] = (i, list(g), p.preset_name(i, list(g)))
    async def set_buttons(self, ch): self.s["botoes"] = {**self.s["botoes"], **ch}
    async def send(self, frame): pass


# --- ponte UI <-> Bluetooth ------------------------------------------------------------------------

class Bridge:
    def __init__(self, demo: bool):
        self.demo = demo
        self.out: queue.Queue = queue.Queue()  # fundo -> UI
        self.jobs: asyncio.Queue | None = None
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.jobs = asyncio.Queue()
        self.loop.run_until_complete(self._session())

    def do(self, fn) -> None:
        """Agenda `async fn(earbuds)` na sessão conectada."""
        self.loop.call_soon_threadsafe(self.jobs.put_nowait, fn)

    async def _session(self) -> None:
        while True:
            self.out.put(("estado", "Procurando fone..."))
            try:
                if self.demo:
                    dev_cm = FakeEarbuds()
                else:
                    found = await discover(4)
                    if not found:
                        await asyncio.sleep(1)
                        continue
                    dev_cm = Earbuds(found[0])
                async with dev_cm as e:
                    self.out.put(("estado", "Conectado"))
                    self.out.put(("status", await e.status()))
                    while e.connected:
                        try:
                            job = await asyncio.wait_for(self.jobs.get(), 8)
                        except asyncio.TimeoutError:
                            job = None
                        if job:
                            await job(e)
                            await asyncio.sleep(0.8)
                        self.out.put(("status", await e.status()))
            except Exception as ex:  # reconecta sempre: fone volta ao estojo, sai de alcance...
                self.out.put(("estado", f"Reconectando ({type(ex).__name__})"))
            await asyncio.sleep(2)


# --- interface ---------------------------------------------------------------------------------

class App(ctk.CTk):
    def __init__(self, demo: bool):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("QCY PC" + (" (demo)" if demo else ""))
        self.geometry("560x640")
        self.minsize(520, 600)
        self.bridge = Bridge(demo)
        self._building = False
        self.calls: queue.Queue = queue.Queue()  # callbacks da bandeja -> thread da UI
        self.protocol("WM_DELETE_WINDOW", self.withdraw)  # X esconde na bandeja; "Sair" fecha de verdade
        self.tray = self._make_tray()
        self.tray.run_detached()

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 4))
        self.lbl_model = ctk.CTkLabel(top, text="QCY PC", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_model.pack(anchor="w")
        self.lbl_state = ctk.CTkLabel(top, text="Procurando fone...", text_color="gray70")
        self.lbl_state.pack(anchor="w")

        self.tabs = tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=12, pady=8)
        self._tab_geral(tabs.add("Geral"))
        self._tab_eq(tabs.add("Equalizador"))
        self._tab_botoes(tabs.add("Botões"))
        self._tab_avancado(tabs.add("Ajustes"))
        self.after(150, self._poll)

    # Geral
    def _tab_geral(self, t) -> None:
        self.bars = {}
        box = ctk.CTkFrame(t)
        box.pack(fill="x", pady=(4, 10))
        for i, n in enumerate(("esquerdo", "direito", "estojo")):
            ctk.CTkLabel(box, text=n.capitalize(), width=80, anchor="w").grid(row=i, column=0, padx=10, pady=5)
            bar = ctk.CTkProgressBar(box, width=300)
            bar.grid(row=i, column=1, padx=6)
            lbl = ctk.CTkLabel(box, text="–", width=110, anchor="w")
            lbl.grid(row=i, column=2, padx=6)
            self.bars[n] = (bar, lbl)

        ctk.CTkLabel(t, text="Controle de ruído", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(6, 2))
        self.seg_noise = ctk.CTkSegmentedButton(t, values=["Normal", "ANC", "Transparência"], command=self._noise_changed)
        self.seg_noise.pack(fill="x")
        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(fill="x", pady=6)
        self.opt_scene = ctk.CTkOptionMenu(row, values=[s.capitalize() for s in SCENES], command=lambda _v: self._noise_changed(None))
        self.opt_scene.set("Ruidoso")
        self.opt_scene.pack(side="left")
        self.sld_level = ctk.CTkSlider(row, from_=1, to=3, number_of_steps=2, command=lambda _v: None)
        self.sld_level.set(3)
        self.sld_level.pack(side="left", fill="x", expand=True, padx=10)
        self.sld_level.bind("<ButtonRelease-1>", lambda _e: self._noise_changed(None))
        self.lbl_noise = ctk.CTkLabel(t, text="", text_color="gray70")
        self.lbl_noise.pack(anchor="w")

        self.sw_game = ctk.CTkSwitch(t, text="Modo jogo (baixa latência)", command=lambda: self._toggle(p.Cmd.GAME_MODE, self.sw_game))
        self.sw_game.pack(anchor="w", pady=(14, 4))
        self.sw_sleep = ctk.CTkSwitch(t, text="Modo sono (desliga o toque até voltar ao estojo)", command=lambda: self._toggle(p.Cmd.SLEEP, self.sw_sleep))
        self.sw_sleep.pack(anchor="w", pady=4)
        self.lbl_fw = ctk.CTkLabel(t, text="", text_color="gray60")
        self.lbl_fw.pack(anchor="w", pady=(14, 0))

    def _noise_changed(self, _v) -> None:
        if self._building:
            return
        mode = self.seg_noise.get()
        level = int(round(self.sld_level.get()))
        if mode == "Normal":
            v = p.NOISE_OFF
        elif mode == "ANC":
            scene = self.opt_scene.get().lower()
            v = p.anc(scene, 1 if scene == "vento" else level)
        else:
            v = p.transparency(level + 1)
        self.bridge.do(lambda e: e.set_noise(v))

    def _toggle(self, cmd: int, sw) -> None:
        on = bool(sw.get())
        self.bridge.do(lambda e: e.set_toggle(cmd, on))

    # Equalizador
    def _tab_eq(self, t) -> None:
        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(fill="x", pady=(4, 8))
        ctk.CTkLabel(row, text="Predefinição").pack(side="left")
        self.opt_preset = ctk.CTkOptionMenu(row, values=list(PRESET_LABEL.values()), command=self._preset_chosen)
        self.opt_preset.pack(side="left", padx=10)
        self.lbl_eq = ctk.CTkLabel(row, text="", text_color="gray70")
        self.lbl_eq.pack(side="left")
        grid = ctk.CTkFrame(t)
        grid.pack(fill="both", expand=True)
        self.eq_sliders = []
        for i, hz in enumerate(p.EQ_FREQS_HZ):
            col = ctk.CTkFrame(grid, fg_color="transparent")
            col.pack(side="left", expand=True, fill="y", padx=2, pady=6)
            val = ctk.CTkLabel(col, text="0", width=28)
            val.pack()
            s = ctk.CTkSlider(col, from_=-p.EQ_MAX_DB, to=p.EQ_MAX_DB, number_of_steps=2 * p.EQ_MAX_DB, orientation="vertical",
                              command=lambda v, lab=val: lab.configure(text=f"{int(round(v)):+d}"))
            s.set(0)
            s.pack(fill="y", expand=True, pady=4)
            ctk.CTkLabel(col, text=f"{hz // 1000}k" if hz >= 1000 else str(hz), text_color="gray70").pack()
            self.eq_sliders.append((s, val))
        ctk.CTkButton(t, text="Aplicar curva personalizada", command=self._apply_eq).pack(pady=8)

    def _set_eq_sliders(self, gains) -> None:
        for (s, lab), g in zip(self.eq_sliders, gains):
            s.set(g)
            lab.configure(text=f"{g:+d}")

    def _preset_chosen(self, label: str) -> None:
        name = next(k for k, v in PRESET_LABEL.items() if v == label)
        idx, gains = p.EQ_PRESETS[name]
        self._set_eq_sliders(gains)
        self.bridge.do(lambda e: e.set_eq(idx, gains))

    def _apply_eq(self) -> None:
        gains = [int(round(s.get())) for s, _ in self.eq_sliders]
        # o HT05 aceita qualquer índice com os 10 ganhos (validado 26/10); 0 = "curva própria"
        self.bridge.do(lambda e: e.set_eq(0, gains))

    # Botões
    def _tab_botoes(self, t) -> None:
        self.btn_opts = {}
        labels = list(ACTION_LABEL.values())
        for key, text in GESTURE_LABEL.items():
            row = ctk.CTkFrame(t, fg_color="transparent")
            row.pack(fill="x", pady=5)
            ctk.CTkLabel(row, text=text, width=170, anchor="w").pack(side="left")
            o = ctk.CTkOptionMenu(row, values=labels, width=220, command=lambda v, k=key: self._button_chosen(k, v))
            o.pack(side="left")
            self.btn_opts[p.GESTURES[key]] = o

    def _button_chosen(self, key: str, label: str) -> None:
        if self._building:
            return
        act = next(k for k, v in ACTION_LABEL.items() if v == label)
        self.bridge.do(lambda e: e.set_buttons({p.GESTURES[key]: p.ACTIONS[act]}))

    # Ajustes
    def _tab_avancado(self, t) -> None:
        ctk.CTkLabel(t, text="Balanço entre os lados", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(4, 2))
        self.sld_bal = ctk.CTkSlider(t, from_=0, to=100, number_of_steps=100)
        self.sld_bal.set(50)
        self.sld_bal.pack(fill="x")
        self.sld_bal.bind("<ButtonRelease-1>", lambda _e: self.bridge.do(lambda e, v=int(self.sld_bal.get()): e.set_balance(v)))
        ctk.CTkLabel(t, text="Nome do fone", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(18, 2))
        row = ctk.CTkFrame(t, fg_color="transparent")
        row.pack(fill="x")
        self.ent_name = ctk.CTkEntry(row)
        self.ent_name.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Renomear", width=90, command=self._rename).pack(side="left", padx=8)
        ctk.CTkLabel(t, text="Manutenção", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(24, 2))
        ctk.CTkButton(t, text="Restaurar configurações padrão", fg_color="gray30", command=self._reset).pack(anchor="w")
        ctk.CTkLabel(t, text="Reset de fábrica e atualização de firmware ficam de fora de propósito (risco de inutilizar o fone).",
                     text_color="gray60", wraplength=470, justify="left").pack(anchor="w", pady=8)

    def _rename(self) -> None:
        name = self.ent_name.get().strip()
        if name:
            self.bridge.do(lambda e: e.set_name(name))

    def _reset(self) -> None:
        self.bridge.do(lambda e: e.send(p.reset_default()))

    # bandeja
    def _make_tray(self) -> pystray.Icon:
        ui = lambda fn: (lambda *_: self.calls.put(fn))
        noise = lambda v: (lambda *_: self.bridge.do(lambda e: e.set_noise(v)))
        menu = pystray.Menu(
            pystray.MenuItem("Abrir QCY PC", ui(self.show), default=True),
            pystray.MenuItem("Normal", noise(p.NOISE_OFF)),
            pystray.MenuItem("ANC", noise(p.anc("ruidoso", 3))),
            pystray.MenuItem("Transparência", noise(p.transparency(4))),
            pystray.MenuItem("Sair", ui(self.quit)),
        )
        return pystray.Icon("qcypc", make_icon(64), "QCY PC", menu)

    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def quit(self) -> None:
        self.tray.stop()
        self.destroy()

    # atualização vinda do fundo
    def _poll(self) -> None:
        try:
            while True:
                self.calls.get_nowait()()
        except queue.Empty:
            pass
        try:
            while True:
                kind, payload = self.bridge.out.get_nowait()
                if kind == "estado":
                    self.lbl_state.configure(text=payload)
                else:
                    self._render(payload)
        except queue.Empty:
            pass
        self.after(150, self._poll)

    def _render(self, s: dict) -> None:
        self._building = True
        try:
            self.lbl_model.configure(text=s["modelo"])
            pct = lambda n: "?" if s["bateria"][n].percent is None else f"{s['bateria'][n].percent}%"
            self.tray.title = f"{s['modelo']}  E {pct('esquerdo')}  D {pct('direito')}"
            for n, (bar, lbl) in self.bars.items():
                lv = s["bateria"].get(n)
                bar.set((lv.percent or 0) / 100 if lv else 0)
                lbl.configure(text="–" if not lv or lv.percent is None else f"{lv.percent}%{' ⚡' if lv.charging else ''}")
            if s["ruido"]:
                v, label = s["ruido"]
                self.lbl_noise.configure(text=f"{label}  (0x{v:02X})")
                if v == p.NOISE_OFF:
                    self.seg_noise.set("Normal")
                elif 0xA0 <= v <= 0xA6:
                    self.seg_noise.set("Transparência")
                else:
                    self.seg_noise.set("ANC")
                    for name, base in p.ANC_SCENES.items():
                        if v >> 4 == base:
                            self.opt_scene.set(name.capitalize())
                            self.sld_level.set(max(1, v & 0xF))
            for sw, key in ((self.sw_game, "jogo"), (self.sw_sleep, "sono")):
                (sw.select if s[key] else sw.deselect)()
            if s["balanco"] is not None:
                self.sld_bal.set(s["balanco"])
            if s["nome"] and self.focus_get() is not self.ent_name._entry:
                self.ent_name.delete(0, "end")
                self.ent_name.insert(0, s["nome"])
            if s["eq"]:
                idx, gains, name = s["eq"]
                self._set_eq_sliders(gains)
                self.lbl_eq.configure(text="" if name else "personalizado")
                if name:
                    self.opt_preset.set(PRESET_LABEL[name])
            acts = {v: k for k, v in p.ACTIONS.items()}
            for g, o in self.btn_opts.items():
                if g in s["botoes"]:
                    o.set(ACTION_LABEL.get(acts.get(s["botoes"][g], "nada"), "Nenhuma"))
            fw = s["firmware"]
            self.lbl_fw.configure(text=f"Firmware  E {fw.get('esquerdo', '?')}  ·  D {fw.get('direito', '?')}   ·   {s['endereco']}")
        finally:
            self._building = False


_mutex = None


def _already_running() -> bool:
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\QCYPC-single-instance")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def main() -> None:
    if "--selftest" not in sys.argv and _already_running():
        return  # duas cópias brigariam pelo único canal BLE do fone
    app = App(demo="--demo" in sys.argv)
    if "--tray" in sys.argv:
        app.withdraw()
    if "--selftest" in sys.argv:  # usado para validar o .exe empacotado
        def dump() -> None:
            b = {k: v[1].cget("text") for k, v in app.bars.items()}
            out = f"modelo={app.lbl_model.cget('text')} estado={app.lbl_state.cget('text')} bateria={b} ruido={app.lbl_noise.cget('text')} tray={app.tray.visible}"
            open(os.path.join(tempfile.gettempdir(), "qcypc-selftest.txt"), "w", encoding="utf-8").write(out)
            app.quit()
        app.after(22000, dump)
    app.mainloop()


if __name__ == "__main__":
    main()
