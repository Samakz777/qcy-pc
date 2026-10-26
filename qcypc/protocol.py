"""Protocolo QCY sobre BLE GATT (serviço 0xA001). Puro: sem Bluetooth, sem I/O.

Fontes: bytecode do APK QCY 4.0.7 (QCYHeadsetClient, DataAnalyse, *DataBean), painel oficial do
HT05 (api.watch.qcy.com/product/findControlPanels, modelId 19777/19778) e vetores reais de captura HCI.
"""
from __future__ import annotations

from dataclasses import dataclass

SOF = 0xFF


def _u(short: str) -> str:
    return f"0000{short}-0000-1000-8000-00805f9b34fb"


SERVICE = _u("a001")
CH_CMD = _u("1001")      # write sem resposta: FF len {id n dados}...
CH_STATE = _u("1002")    # read/notify: mesmo enquadramento
CH_BATTERY = _u("0008")  # read/notify: [esq, dir, estojo]; bit7 = carregando
CH_VERSION = _u("0007")  # read: [maj,min,patch] x2
CH_BUTTONS = _u("000d")  # read/write: pares [gesto, ação]
CH_EQ = _u("000b")       # read/write: [índice, 10 x int8]
COMPANY_IDS = (0x521C, 0x522C)


class Cmd:
    RESET_DEFAULT = 0x01
    CLEAR_PAIR = 0x02
    FACTORY_RESET = 0x03
    GAME_MODE = 0x09
    NOISE_MODE = 0x0C
    SLEEP = 0x10
    BALANCE = 0x16
    ANC_SETTING = 0x17
    PAIR_NAME = 0x18
    REQUEST = 0xFE


# --- enquadramento -------------------------------------------------------------------------------

def tlv(cmd: int, data: bytes = b"") -> bytes:
    return bytes([cmd, len(data)]) + data


def encode_frame(*items: bytes) -> bytes:
    body = b"".join(items)
    if len(body) > 253:
        raise ValueError("frame grande demais para uma escrita ATT")
    return bytes([SOF, len(body)]) + body


def decode_frame(raw: bytes) -> list[tuple[int, bytes]]:
    """[(cmd, dados)]. Frame inválido (sem FF, tamanho errado) devolve lista vazia."""
    if len(raw) < 4 or raw[0] != SOF or raw[1] + 2 != len(raw):
        return []
    out, i = [], 2
    while i + 2 <= len(raw):
        cmd, n = raw[i], raw[i + 1]
        if i + 2 + n > len(raw):
            break
        out.append((cmd, bytes(raw[i + 2 : i + 2 + n])))
        i += 2 + n
    return out


def request(cmd: int) -> bytes:
    return encode_frame(tlv(Cmd.REQUEST, bytes([cmd])))


def toggle(cmd: int, on: bool) -> bytes:
    return encode_frame(tlv(cmd, bytes([1 if on else 2])))  # 1 = ligado, 2 = desligado


def reset_default() -> bytes:
    return encode_frame(tlv(Cmd.RESET_DEFAULT))


def factory_reset() -> bytes:
    return encode_frame(tlv(Cmd.FACTORY_RESET))


def balance(value: int) -> bytes:
    if not 0 <= value <= 100:
        raise ValueError("balanço vai de 0 a 100 (50 = centro)")
    return encode_frame(tlv(Cmd.BALANCE, bytes([value])))


def pair_name(name: str) -> bytes:
    raw = name.encode("utf-8")
    if not raw or len(raw) > 32:
        raise ValueError("nome: 1 a 32 bytes em UTF-8")
    return encode_frame(tlv(Cmd.PAIR_NAME, raw))


# --- controle de ruído (HT05 usa o comando legado 0x0C, 1 byte) ------------------------------------

NOISE_OFF = 0x02
ANC_SCENES = {"interno": 0x4, "trajeto": 0x5, "ruidoso": 0x6, "vento": 0x7}


def anc(scene: str, level: int = 3) -> int:
    base = ANC_SCENES[scene]
    top = 1 if scene == "vento" else 3
    if not 1 <= level <= top:
        raise ValueError(f"nível de ANC '{scene}': 1 a {top}")
    return (base << 4) | level


def transparency(level: int = 4) -> int:
    if not 0 <= level <= 6:
        raise ValueError("transparência: 0 a 6")
    return 0xA0 + level


def noise_label(v: int) -> str:
    if v == NOISE_OFF:
        return "Normal (ANC desligado)"
    if 0xA0 <= v <= 0xA6:
        return f"Transparência (nível {v - 0xA0})"
    for name, base in ANC_SCENES.items():
        if v >> 4 == base and 1 <= (v & 0xF) <= 3:
            return f"ANC {name} (nível {v & 0xF})"
    return f"desconhecido (0x{v:02X})"


def noise_mode(value: int) -> bytes:
    if not 0 <= value <= 0xFF:
        raise ValueError("valor de modo de ruído: 1 byte")
    return encode_frame(tlv(Cmd.NOISE_MODE, bytes([value])))


# --- equalizador (característica 0x000B: [índice, 10 x int8]) ----------------------------------------

EQ_FREQS_HZ = (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
EQ_MAX_DB = 8
EQ_PRESETS: dict[str, tuple[int, tuple[int, ...]]] = {
    "padrao": (1, (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)),
    "popular": (2, (-6, 5, -3, -2, 5, 4, -4, -3, 6, 4)),
    "bass": (3, (6, 5, 4, 3, 0, 0, 0, 0, 0, 0)),
    "rock": (4, (5, 4, 2, 1, -3, -4, 2, 1, 4, 5)),
    "suave": (5, (5, -5, -4, -4, 3, 2, 4, 4, 0, 0)),
    "classico": (6, (5, 5, 1, 2, -1, 1, -4, -6, -7, -8)),
}


def eq_bytes(index: int, gains: tuple[int, ...] | list[int]) -> bytes:
    if len(gains) != 10 or any(not -EQ_MAX_DB <= g <= EQ_MAX_DB for g in gains):
        raise ValueError(f"EQ: 10 ganhos entre -{EQ_MAX_DB} e +{EQ_MAX_DB} dB")
    return bytes([index]) + bytes(g & 0xFF for g in gains)


def decode_eq(raw: bytes) -> tuple[int, list[int]] | None:
    if len(raw) < 11:
        return None
    return raw[0], [b - 256 if b > 127 else b for b in raw[1:11]]


def preset_name(index: int, gains: list[int]) -> str | None:
    for name, (i, g) in EQ_PRESETS.items():
        if i == index and list(g) == gains:
            return name
    return None


# --- botões (característica 0x000D) ----------------------------------------------------------------

GESTURES = {  # ímpar = esquerdo, par = direito
    "esq-1": 1, "dir-1": 2, "esq-2": 3, "dir-2": 4, "esq-3": 5, "dir-3": 6,
}
ACTIONS = {
    "nada": 0, "play-pause": 1, "anterior": 2, "proxima": 3, "assistente": 4,
    "volume+": 5, "volume-": 6, "jogo": 7, "anc": 11,
}


def buttons_bytes(changes: dict[int, int]) -> bytes:
    """Só os pares alterados: o fone aceita escrita parcial."""
    return b"".join(bytes([g, a]) for g, a in changes.items())


def decode_buttons(raw: bytes) -> dict[int, int]:
    out = {}
    for i in range(0, len(raw) - 1, 2):
        if raw[i]:
            out[raw[i]] = raw[i + 1]
    return out


# --- leituras --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Level:
    percent: int | None  # None = desconhecido (0)
    charging: bool


def decode_battery(raw: bytes) -> dict[str, Level]:
    if len(raw) < 3:
        return {}
    names = ("esquerdo", "direito", "estojo")
    return {n: Level((b & 0x7F) or None, bool(b & 0x80)) for n, b in zip(names, raw[:3])}


def decode_version(raw: bytes) -> dict[str, str]:
    if len(raw) < 6:
        return {}
    return {"esquerdo": ".".join(map(str, raw[0:3])), "direito": ".".join(map(str, raw[3:6]))}


# --- anúncio BLE -----------------------------------------------------------------------------------

MODELS = {0x4D41: "QCY Melobuds ANC (HT05)", 0x4D42: "QCY TWS HT05"}


def chip_family(model_id: int) -> str:
    return {0x40: "WuQi", 0xC0: "Realtek", 0x70: "JieLi", 0x90: "ZR"}.get(model_id & 0xF0, "genérico")


@dataclass(frozen=True)
class Advert:
    model_id: int
    color: int
    left: Level
    right: Level
    case: Level
    classic_mac: str

    @property
    def model(self) -> str:
        return MODELS.get(self.model_id, f"QCY modelo 0x{self.model_id:04X}")


def _mac(d: bytes, order: tuple[int, ...]) -> str:
    return ":".join(f"{d[i]:02X}" for i in order)


def parse_advert(manufacturer_data: dict[int, bytes]) -> Advert | None:
    """manufacturer_data como o bleak entrega (dados após o company id)."""
    for cid in COMPANY_IDS:
        d = manufacturer_data.get(cid)
        if d is not None and len(d) >= 20:
            lv = lambda b: Level((b & 0x7F) or None, bool(b & 0x80))
            return Advert((d[0] << 8) | d[1], (d[3] >> 1) & 7, lv(d[5]), lv(d[6]), lv(d[7]),
                          _mac(d, (12, 11, 13, 16, 15, 14)))
    return None
