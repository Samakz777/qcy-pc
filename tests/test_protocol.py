import pytest

from qcypc import protocol as p

h = bytes.fromhex


def test_noise_frames_match_official_app_capture():
    assert p.noise_mode(0x63) == h("ff030c0163")  # ANC ligado
    assert p.noise_mode(0xA4) == h("ff030c01a4")  # transparência
    assert p.noise_mode(p.NOISE_OFF) == h("ff030c0102")
    assert [p.noise_mode(v) for v in (0x41, 0x51, 0x61, 0x71)] == [h(f"ff030c01{v:02x}") for v in (0x41, 0x51, 0x61, 0x71)]


def test_noise_values_follow_the_official_panel_ranges():
    assert p.anc("interno", 1) == 0x41 and p.anc("trajeto", 3) == 0x53
    assert p.anc("ruidoso") == 0x63  # padrão do painel do HT05
    assert p.anc("vento", 1) == 0x71
    assert p.transparency() == 0xA4 and p.transparency(0) == 0xA0
    with pytest.raises(ValueError):
        p.anc("vento", 2)
    with pytest.raises(ValueError):
        p.transparency(7)
    assert p.noise_label(0x63) == "ANC ruidoso (nível 3)"


def test_frames_and_requests():
    assert p.request(0x0C) == h("ff03fe010c")
    assert p.toggle(p.Cmd.GAME_MODE, True) == h("ff03090101")  # igual ao painel: FF03090101
    assert p.toggle(p.Cmd.SLEEP, False) == h("ff03100102")
    assert p.reset_default() == h("ff020100")
    assert p.balance(50) == h("ff03160132")


def test_decode_frame_multiple_tlvs_and_garbage():
    assert p.decode_frame(h("ff06fe0107fe010c")) == [(0xFE, b"\x07"), (0xFE, b"\x0c")]
    assert p.decode_frame(h("ff0c0c0102")) == []  # tamanho não confere
    assert p.decode_frame(h("000c0c0102")) == []  # sem SOF


def test_battery_and_version():
    b = p.decode_battery(h("64e300"))
    assert b["esquerdo"] == p.Level(100, False)
    assert b["direito"] == p.Level(99, True)
    assert b["estojo"] == p.Level(None, False)
    assert p.decode_version(h("020006020006")) == {"esquerdo": "2.0.6", "direito": "2.0.6"}


def test_eq_presets_match_captured_bytes():
    captured = {
        "suave": "0505fbfcfc030204040000",
        "rock": "0405040201fdfc02010405",
        "bass": "0306050403000000000000",
        "popular": "02fa05fdfe0504fcfd0604",
        "padrao": "0100000000000000000000",
    }
    for name, hexs in captured.items():
        idx, gains = p.EQ_PRESETS[name]
        assert p.eq_bytes(idx, gains) == h(hexs)
        assert p.preset_name(*p.decode_eq(h(hexs))) == name
    with pytest.raises(ValueError):
        p.eq_bytes(9, [9] + [0] * 9)


def test_buttons_roundtrip():
    raw = h("0100020003010401050406030700080000000000")
    m = p.decode_buttons(raw)
    assert m[4] == p.ACTIONS["play-pause"] and m[5] == p.ACTIONS["assistente"]
    assert p.buttons_bytes({p.GESTURES["dir-2"]: p.ACTIONS["proxima"]}) == h("0403")


def test_real_advert_from_ht05():
    # anúncio BLE real de um HT05 (company 0x521C); endereços Bluetooth trocados por valores fictícios
    d = h("4d4113006e4144004fe2efbbaaccffeedd01000000000000")
    ad = p.parse_advert({0x521C: d})
    assert ad.model_id == 0x4D41 and ad.model == "QCY Melobuds ANC (HT05)"
    assert p.chip_family(ad.model_id) == "WuQi"
    assert ad.left == p.Level(65, False) and ad.right == p.Level(68, False) and ad.case.percent is None
    assert ad.classic_mac == "AA:BB:CC:DD:EE:FF"
    assert p.parse_advert({0x004C: d}) is None
    assert p.parse_advert({0x521C: d[:5]}) is None
