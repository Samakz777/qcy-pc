"""Sessão BLE com um fone QCY (bleak/WinRT). Reconhece pelo anúncio (company 0x521C/0x522C); não exige pareamento."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from . import protocol as p

_STATE_IDS = (p.Cmd.NOISE_MODE, p.Cmd.GAME_MODE, p.Cmd.SLEEP, p.Cmd.BALANCE, p.Cmd.PAIR_NAME)


@dataclass
class Found:
    device: BLEDevice
    advert: p.Advert
    rssi: int

    @property
    def address(self) -> str:
        return self.device.address


async def discover(seconds: float = 6.0) -> list[Found]:
    seen: dict[str, Found] = {}

    def cb(dev, adv):
        ad = p.parse_advert(adv.manufacturer_data)
        if ad:
            seen[dev.address] = Found(dev, ad, adv.rssi)

    async with BleakScanner(cb):
        await asyncio.sleep(seconds)
    return sorted(seen.values(), key=lambda f: -f.rssi)


class Earbuds:
    def __init__(self, found: Found, on_change: Callable[[], None] | None = None):
        self.found = found
        self.raw: dict[int, bytes] = {}  # último valor TLV por comando
        self.battery_raw = b""
        self._client = BleakClient(found.device, disconnected_callback=lambda _c: self._lost())
        self._on_change = on_change
        self.connected = False

    def _lost(self) -> None:
        self.connected = False
        if self._on_change:
            self._on_change()

    def _on_state(self, _ch, data: bytearray) -> None:
        for cmd, val in p.decode_frame(bytes(data)):
            self.raw[cmd] = val
        if self._on_change:
            self._on_change()

    def _on_battery(self, _ch, data: bytearray) -> None:
        self.battery_raw = bytes(data)
        if self._on_change:
            self._on_change()

    async def __aenter__(self) -> "Earbuds":
        await self._client.connect()
        self.connected = True
        # o serviço OTA da WuQi reaproveita 0x1001/0x1002: resolver sempre dentro do serviço A001
        self._svc = self._client.services.get_service(p.SERVICE)
        if self._svc is None:
            raise RuntimeError("serviço 0xA001 não encontrado: não é um fone QCY com este protocolo")
        await self._client.start_notify(self._ch(p.CH_STATE), self._on_state)
        await self._client.start_notify(self._ch(p.CH_BATTERY), self._on_battery)
        return self

    def _ch(self, uuid: str):
        ch = self._svc.get_characteristic(uuid)
        if ch is None:
            raise KeyError(f"característica {uuid} ausente neste fone")
        return ch

    async def __aexit__(self, *exc) -> None:
        if self._client.is_connected:
            await self._client.disconnect()
        self.connected = False

    async def refresh(self) -> None:
        c = self._client
        self._on_state(None, await c.read_gatt_char(self._ch(p.CH_STATE)))
        self.battery_raw = bytes(await c.read_gatt_char(self._ch(p.CH_BATTERY)))
        for cmd in _STATE_IDS:
            await self.send(p.request(cmd))
        await asyncio.sleep(0.7)

    async def read_char(self, uuid: str) -> bytes:
        return bytes(await self._client.read_gatt_char(self._ch(uuid)))

    async def send(self, frame: bytes) -> None:
        await self._client.write_gatt_char(self._ch(p.CH_CMD), frame, response=False)

    async def write_raw(self, uuid: str, data: bytes) -> None:
        await self._client.write_gatt_char(self._ch(uuid), data, response=False)

    async def probe(self, ids: range | list[int]) -> dict[int, bytes]:
        """Somente leitura: pede cada comando e devolve o que o fone respondeu."""
        before = dict(self.raw)
        for cmd in ids:
            self.raw.pop(cmd, None)
            await self.send(p.request(cmd))
            await asyncio.sleep(0.12)
        out = {k: v for k, v in self.raw.items() if k in set(ids)}
        for k, v in before.items():
            self.raw.setdefault(k, v)
        return out

    async def status(self) -> dict:
        await self.refresh()
        c = self._client
        version = p.decode_version(await self.read_char(p.CH_VERSION))
        try:
            eq = p.decode_eq(await self.read_char(p.CH_EQ))
        except Exception:  # característica ausente em alguns modelos
            eq = None
        try:
            buttons = p.decode_buttons(await self.read_char(p.CH_BUTTONS))
        except Exception:
            buttons = {}
        r = self.raw
        flag = lambda cmd: None if cmd not in r else r[cmd][:1] == b"\x01"
        noise = r[p.Cmd.NOISE_MODE][0] if r.get(p.Cmd.NOISE_MODE) else None
        return {
            "modelo": self.found.advert.model,
            "endereco": self.found.address,
            "bateria": p.decode_battery(self.battery_raw),
            "firmware": version,
            "ruido": None if noise is None else (noise, p.noise_label(noise)),
            "jogo": flag(p.Cmd.GAME_MODE),
            "sono": flag(p.Cmd.SLEEP),
            "balanco": r[p.Cmd.BALANCE][0] if r.get(p.Cmd.BALANCE) else None,
            "nome": r[p.Cmd.PAIR_NAME].split(b"\0")[0].decode("utf-8", "replace") if r.get(p.Cmd.PAIR_NAME) else None,
            "eq": None if eq is None else (eq[0], eq[1], p.preset_name(*eq)),
            "botoes": buttons,
            "mtu": getattr(c, "mtu_size", None),
        }

    # --- ajustes ---
    async def set_noise(self, value: int) -> None:
        await self.send(p.noise_mode(value))

    async def set_toggle(self, cmd: int, on: bool) -> None:
        await self.send(p.toggle(cmd, on))

    async def set_balance(self, value: int) -> None:
        await self.send(p.balance(value))

    async def set_name(self, name: str) -> None:
        await self.send(p.pair_name(name))

    async def set_eq(self, index: int, gains) -> None:
        await self.write_raw(p.CH_EQ, p.eq_bytes(index, gains))

    async def set_buttons(self, changes: dict[int, int]) -> None:
        await self.write_raw(p.CH_BUTTONS, p.buttons_bytes(changes))
