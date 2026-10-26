# QCY PC

Controle dos fones **QCY** pelo Bluetooth LE no **Windows**, sem o app do celular. Feito e testado no **QCY HT05 (Melobuds ANC)**.

> Projeto independente, sem vínculo com a QCY. O protocolo foi levantado por engenharia reversa do app oficial e de capturas
> do próprio fone, para interoperabilidade. Este repositório **não contém** código, imagens ou dados do app oficial.

## O que faz

| Aba | Controles |
|---|---|
| **Geral** | Bateria (esquerdo, direito, estojo) · ruído: Normal, ANC (interno, trajeto, ruidoso, vento, 3 níveis), Transparência (7 níveis) · modo jogo · modo sono |
| **Equalizador** | 6 predefinições (Padrão, Popular, Bass, Rock, Suave, Clássico) · 10 bandas de 31 Hz a 16 kHz, ±8 dB |
| **Botões** | Ação de 1, 2 e 3 toques em cada fone: play/pausa, faixa anterior/próxima, assistente, volume, modo jogo, alternar ANC |
| **Ajustes** | Balanço entre os lados · renomear · restaurar configurações padrão |

Também tem **ícone na bandeja** (menu rápido Normal / ANC / Transparência; fechar a janela esconde na bandeja) e linha de comando.
Reconecta sozinho quando o fone volta do estojo.

## Instalar

### Opção 1: programa pronto (recomendado)
1. Abra a página de [Releases](https://github.com/Samakz777/qcy-pc/releases/latest) e baixe `QCY-PC-windows.zip`.
2. Extraia a pasta em qualquer lugar (por exemplo `C:\Programas\QCY PC`) e abra `QCY PC.exe`.
3. Se o Windows mostrar o aviso do SmartScreen ("Windows protegeu o computador"): **Mais informações → Executar assim mesmo**.
   O programa não é assinado digitalmente.
4. Para ter um atalho: botão direito em `QCY PC.exe` → **Enviar para → Área de trabalho**.

### Opção 2: a partir do código
Requisitos: Windows 10/11 com Bluetooth LE e Python 3.12 (a versão em que foi testado).

```powershell
git clone https://github.com/Samakz777/qcy-pc.git
cd qcy-pc
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run_gui.py          # abre a janela
```

Para gerar o `.exe` você mesmo: `.venv\Scripts\python build.py` (saída em `dist\QCY PC\`).

## Usar

1. **Pareie o áudio normalmente** em *Configurações → Bluetooth e dispositivos*. Este programa só cuida das configurações;
   o som continua pelo Bluetooth do Windows.
2. Tire o fone do estojo e **feche o app QCY do celular**. Só um aplicativo por vez controla o canal de configuração do fone.
3. Abra o QCY PC. Em alguns segundos aparece "Conectado" e o estado do fone.

Linha de comando (fone real; feche a janela antes, pelo mesmo motivo):

```powershell
.venv\Scripts\python -m qcypc scan                     # procura fones QCY
.venv\Scripts\python -m qcypc status                   # bateria, ruído, EQ, botões
.venv\Scripts\python -m qcypc anc transparencia:4      # off | on | interno|trajeto|ruidoso|vento[:1-3] | transparencia[:0-6]
.venv\Scripts\python -m qcypc eq rock                  # padrao|popular|bass|rock|suave|classico  ou  10 ganhos: 0,2,-1,...
.venv\Scripts\python -m qcypc button dir-2 proxima     # gesto: esq-1|dir-1|esq-2|dir-2|esq-3|dir-3
.venv\Scripts\python -m qcypc game on                  # modo jogo
.venv\Scripts\python -m qcypc probe                    # somente leitura: comandos que o fone responde
```

`python run_gui.py --demo` abre a janela com um fone simulado, para ver a interface sem Bluetooth.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| "Procurando fone..." não sai disso | Feche o app QCY do celular e qualquer outra cópia deste programa (ícone na bandeja → Sair). Tire o fone do estojo. |
| O fone some depois de voltar ao estojo | É normal; ao tirar de novo o programa reconecta sozinho. |
| O Windows não acha o fone para parear o áudio | Desligue o Bluetooth do celular, que costuma segurá-lo. Se precisar, reset do fone (veja o manual da QCY). Isso não é feito por este programa. |
| EQ própria não muda o som | O fone aceita a curva, mas ainda não confirmamos que aplica os ganhos. Use as predefinições e abra uma *issue*. |
| Fone diferente do HT05 | Pode funcionar parcialmente se usar o mesmo protocolo (serviço `0xA001`); valores de ANC e EQ variam por modelo. |

## Segurança

- Reset de fábrica e **atualização de firmware ficam de fora de propósito** (risco de inutilizar o fone).
- O fone não exige pareamento nem senha no canal de configuração: qualquer aparelho por perto pode se conectar quando ele
  está livre. Por isso o programa só envia os comandos conhecidos e documentados.
- Uso por sua conta e risco.

## Para quem quer entender ou contribuir

- Análise do APK, protocolo do HT05, evidências e pendências: [docs/PROCESSO-QCY-PC.md](docs/PROCESSO-QCY-PC.md).
- Testes: `.venv\Scripts\python -m pytest -q tests` (usam bytes reais capturados do app oficial).
- Estrutura: `qcypc/protocol.py` (puro, sem Bluetooth) · `device.py` (bleak/WinRT) · `cli.py` · `gui.py` · `icon.py`.

Outros modelos: veja os projetos [Orphion](https://github.com/hm-aktaruzzaman-mukdho/Orphion) (193 modelos),
[oqcy](https://github.com/jean-vr/oqcy) e [QCYx](https://github.com/allansomensi/qcyx), que serviram de referência.

## Licença

MIT, veja [LICENSE](LICENSE). "QCY" e nomes de produtos são marcas de seus donos, citadas só para indicar compatibilidade.
