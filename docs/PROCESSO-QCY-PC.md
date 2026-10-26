# QCY PC — engenharia reversa do app QCY 4.0.7 e port para Windows (HT05)

Data: 26/10/2026 · Alvo: QCY HT05 (Melobuds ANC, `vendorID 19777 = 0x4D41`, chip WuQi) · APK: `qcy-4-0-7.apk`
(SHA-256 `13fa3f29…b127cd`, 74 MB, 5.995 arquivos, 6 DEX).

## 1. Como foi analisado
- **REA** (`open_binary`, `inspect_artifact`): inventário do APK (5.995 entradas, sem contradição de integridade).
  `inspect_android_package`/`decode_android_resources` exigem JADX 0.7.1 e apktool, não instalados; a extração do REA
  deu timeout. Fallback: extração do ZIP + **androguard 4.1.4** (venv isolado) para desmontar os DEX (bytecode Dalvik).
- Extração parcial no Windows: colisão `-a.png`/`-A.png` em `res/` (só imagens). Código e assets íntegros.
- Painel oficial do HT05 obtido do catálogo publicado por terceiros (Orphion, `research/panel_json/models/19777.json`);
  nenhuma chamada autenticada à API da QCY foi feita.

## 2. Estrutura do APK (o que importa)
| Parte | O que é |
|---|---|
| `com/qcymall/qcylibrary/QCYHeadsetClient` | **Núcleo dos fones**: serviço `0000A001`, leitura/escrita GATT, ~80 métodos (`setNoiseMode`, `setEQ`, `setButtonFunction`, `getBattery`, `diyanshi`=modo jogo…) |
| `qcylibrary/dataBean/*` | Um bean por comando (Noise, ANCSetting, Battery, EQ, KeyFunc, Balance, Sleep, Peidai…) |
| `qcylibrary/dataBean/DataAnalyse` | Enquadramento `FF len TLV…` (`SOF = 0xFF`), **sem checksum** |
| `com/qcymall/earphonesetup/manager/BleScanManager` | Varredura; company IDs **21020 (0x521C)** e **21036 (0x522C)** |
| `earphonesetup/manager/JLDeviceImpl`, `ota/jldevice` | Dialeto **JieLi RCSP** (serviço `0000A002`) |
| `org/wuqi`, `earphonesetup/ota/wq` | OTA do chip **WuQi** (o HT05) — fora do escopo |
| `com/qcteam/protocol` | Protocolo dos **relógios** do app (fitness/GPS) — irrelevante p/ fones |
| SDKs de chip | Realtek (`realsil`, `libRtkAesJni`), Airoha, Actions, Qualcomm, JieLi (`libjl_*`), `libnative-peq` (cálculo de EQ) |
| API | `https://api.watch.qcy.com/product/{findProductList,findQcyDeviceList,findControlPanels}` |

## 3. Evidências (confirmado no bytecode × só em fonte externa)
| Fato | No APK | Fonte externa |
|---|---|---|
| GATT `A001`; chars `1001` (cmd), `1002` (estado), `0008` bateria, `0007` versão, `000B` EQ, `000D` botões | ✔ constantes de `QCYHeadsetClient` | oqcy, Orphion |
| Frame `FF len {id n dados}…`, sem checksum; leitura = `FF 03 FE 01 id` | ✔ `DataAnalyse.getSendData`, `DataBean.getRequestDataCMD` | oqcy, Orphion |
| Modo de ruído legado `0C 01 v`; ANC novo `17 03 modo cena nível` | ✔ `NoiseDataBean.getNoiseModeCMD`, `ANCSettingDataBean.getANCSettingCMD`; `setNoiseMode`: valor >255 → 0x17, senão 0x0C | oqcy (HT05 usa 0x0C) |
| Bateria 3 bytes `[L,R,estojo]`, bit7 = carregando | ✔ `BatteryDataBean` (`&128`, `&127`) | oqcy |
| Botões: ids 1–6 (ímpar esq, par dir); funções 0–7, 11 | ✔ `KEYID_*`, `FUNID_*` + painel HT05 (11 = "ANC mode") | Orphion |
| Company IDs 0x521C / 0x522C | ✔ `BleScanManager` (21020/21036) | oqcy, Orphion |
| Sem autenticação / sem pareamento BLE | — | Orphion §1 |
| Valores de ANC do HT05 (0x02, 0x41–0x9F, 0xA0–0xA6) | ✔ painel oficial `modelId 19777` | oqcy |
| EQ: 10 bandas 31 Hz–16 kHz, ±8 dB, 6 presets | ✔ painel oficial (`sys_eq`, `freq`, `maxdb`) | oqcy (bytes capturados) |

## 4. Especificação do HT05 (painel oficial `19777`; `19778 = TWS HT05` é idêntico)
- **Anúncio**: company `0x521C`; bytes 0–1 model id BE; 5/6/7 = bateria E/D/estojo (bit7 carregando); 11–16 MAC clássico
  na ordem `12 11 13 16 15 14`. Famílias: `id&0xF0` = `0x40` WuQi, `0xC0` Realtek, `0x70` JieLi, `0x90` ZR.
- **Ruído** (`FF 03 0C 01 v`): `0x02` Normal · ANC `0x41–0x43` Interno, `0x51–0x53` Trajeto, `0x61–0x63` Ruidoso
  (padrão `0x63`), `0x71` Vento · Transparência `0xA0–0xA6` (padrão `0xA4`). Semântica nibble = cena, nível = 1–3 é **inferida** da faixa.
- **EQ** (`000B`: `[índice, 10×int8]`): Padrão 1, Popular 2, Bass 3, Rock 4, Suave 5, Clássico 6 (bytes idênticos aos capturados pelo oqcy).
- **Botões** (`000D`, pares `[gesto, ação]`): 1 toque (1/2, padrão nada), 2 toques (3/4, play/pausa), 3 toques (5/6, assistente).
  Ações: 0 nada, 1 play/pausa, 2 anterior, 3 próxima, 4 assistente, 5 vol+, 6 vol−, 7 modo jogo, 11 alternar ANC.
- **Itens**: modo jogo `FF 03 09 01 01|02`, sono `FF 03 10 01 01|02`, balanço `0x16` (0–100), nome `0x18`,
  reset padrão `FF 02 01 00`, reset de fábrica `FF 02 03 00`. Fora de escopo: atualização de firmware, "encontrar fone" (só celular).

## 5. Repositórios de referência (reutilizados como fonte de fatos; código nosso, MIT)
| Projeto | Licença | Uso |
|---|---|---|
| [hm-aktaruzzaman-mukdho/Orphion](https://github.com/hm-aktaruzzaman-mukdho/Orphion) | Apache-2.0 | Rust, Windows+Linux, 193 modelos, `docs/PROTOCOL.md` completo, catálogo de painéis |
| [jean-vr/oqcy](https://github.com/jean-vr/oqcy) | MIT | Testado no **HT05 ANC**; vetores de teste de captura HCI; arquitetura de conexão |
| [allansomensi/qcyx](https://github.com/allansomensi/qcyx) | MIT | Rust CLI+GUI, MeloBuds Pro/Ailybuds; perfis exportáveis, pt-BR |
| [GiorgioRafael/OpenQCY-Desktop](https://github.com/GiorgioRafael/OpenQCY-Desktop) (+ fork elonuziel) | — | Controlador Windows (N70/T13) |
| [tsnery/h3-control](https://github.com/tsnery/h3-control) | — | Electron/Windows, QCY H3 |
| [Tekkiech/qcy-ht07-protocol](https://github.com/Tekkiech/qcy-ht07-protocol) | — | Notas BLE do HT07 |

Decisão: **código próprio em Python + bleak** (WinRT nativo, sem driver), porque Orphion/qcyx exigem toolchain Rust e o
objetivo é um app enxuto só para o HT05, com os fatos validados no APK. Orphion fica como plano B pronto
(`cargo run` suporta 0x4D41 em Windows) e fonte de comparação.

## 6. O que foi construído (`qcy-pc/`)
- `qcypc/protocol.py` — puro: frames, ANC/transparência, EQ, botões, bateria, versão, anúncio. **8 testes** (`pytest`),
  incluindo um **anúncio real de HT05** (endereços trocados por fictícios) e os bytes de EQ/ruído capturados do app oficial.
- `qcypc/device.py` — sessão BLE (bleak): descoberta pelo anúncio, notificações, `status()`, setters, `probe()` (só leitura).
- `qcypc/cli.py` — `python -m qcypc scan|status|probe|anc|eq|button|game|sleep|balance|name|reset|factory-reset`.
- `qcypc/gui.py` — janela (customtkinter) com 4 abas: Geral (bateria, ruído, jogo, sono), Equalizador (presets + 10 bandas),
  Botões (6 gestos), Ajustes (balanço, nome, reset). Reconecta sozinha. `--demo` simula o fone.

## 7. Estado de validação (honesto)
Testado em **um** HT05 (firmware 5.0.3) com Windows 11 e adaptador Intel:
- ✔ Anúncio BLE decodificado (modelo `0x4D41`, baterias, MAC clássico).
- ✔ Leitura: bateria, firmware, ruído, EQ, botões, jogo, balanço. O `probe` mostra que o HT05 só responde aos comandos
  `0x09`, `0x0C`, `0x10`, `0x16` e `0x18` (o nome volta vazio).
- ✔ Escrita com leitura de volta, **21/21**: ruído (Normal, ANC interno/trajeto/ruidoso/vento, transparência 0/4/6), 5 presets de EQ
  + curva própria com índices 0, 255 e 7, 3 botões (escrita parcial) e modo jogo. Estado original restaurado ao final.
- ✔ Janela e `.exe` empacotado: autoteste conecta, mostra o estado e cria o ícone de bandeja.
- ✘ Não validado: modo sono, balanço, renomear, restaurar padrão. Não implementado de propósito: reset de fábrica na interface,
  atualização de firmware (OTA).
- Armadilha encontrada: o fone tem **dois serviços com as características `0x1001/0x1002`** (o OTA da WuQi reaproveita os UUIDs);
  sempre resolver as características dentro do serviço `0xA001`.
- Só um aplicativo segura o canal BLE por vez (app do celular, esta janela ou a CLI). O áudio não precisa estar desconectado.

## 8. Pendências
1. **Curva de EQ própria**: o fone aceita qualquer índice com os 10 ganhos, mas não está provado se aplica os ganhos ao som nem qual
   índice o app oficial usa (`EQDataBean` tem `getSaveIndex`/`getCurMusicType`, ramo com 255 não rastreado). A janela usa índice 0.
2. Iniciar com o Windows; assinatura do `.exe` (hoje sem assinatura, o SmartScreen pode avisar).
3. Opcionais fora do núcleo: LED, volume do fone, detecção de uso, auto-desligar, perfis salvos.
4. Outros modelos QCY (WuQi/Realtek/JieLi/ZR): ver Orphion, que cobre 193 modelos.

## 9. Lições
- Ferramenta de decompilação ausente (JADX/apktool) não bloqueia: androguard em venv desmonta DEX e basta para constantes/fluxo.
- `ImageGrab` sem `SetProcessDpiAwareness` captura a tela errada — conferir coordenadas e descartar imagens da tela do usuário.
- Não reescrever arquivos com acento via PowerShell `Set-Content`; usar Write.
- Três fontes independentes + bytecode deram confiança no protocolo; o hardware ainda achou um erro (UUIDs duplicados).
- Testar contra o fone real exige fechar tudo que segura o BLE (inclusive a própria janela do usuário).
