"""Metadados extraídos do nome do arquivo e do caminho da pasta.

São a segunda e a terceira fontes de metadados: valem para PDFs que não aparecem em nenhum índice XML, e para completar registros cujo índice veio com campos vazios.

Os padrões são dados, não código. O nome de cada grupo capturado vira o nome do campo de índice, o que permite acrescentar um tipo de documento sem tocar em lógica — e, mais adiante, carregar os padrões de um perfil JSON em vez desta lista.
"""
from __future__ import annotations

import re
from pathlib import Path

# Grupos cujo nome começa com "_" são descartados: servem só para ancorar a
# expressão (data e hora da digitalização, por exemplo).
PADROES_NOME = [
    {
        "tipo": "despesa",
        "regex": r"^despesa[_-](?:(?P<Ano>\d{4})[_-])?(?P<Numero>\d+)-(?P<_data>\d{6})-(?P<_hora>\d{6})",
    },
    {
        "tipo": "licitacao",
        "regex": r"^licita[cç][aã]o[_-](?P<Numero>[\d./-]*?)-(?P<_data>\d{8})-(?P<_hora>\d{4})",
    },
    {
        "tipo": "legislacao",
        "regex": r"^(?P<Tipo>lei|lei[_-]complementar|decreto|portaria|resolu[cç][aã]o)[_-](?P<Numero>[\d.]+)[_-](?P<Ano>\d{4})",
    },
]

PADROES_CAMINHO = [
    # .../licitacao/2017/licitacao_098_76  -> Numero 098
    {"regex": r"licita[cç][aã]o[_-](?P<Numero>\d+)[_-]"},
    # .../DESPESAS_2019_121_NOV  ou  .../2019/...  -> Ano 2019
    {"regex": r"(?:^|[_\-/\\])(?P<Ano>19\d{2}|20\d{2})(?:[_\-/\\]|$)"},
]

_COMPILADOS_NOME = [
    (p["tipo"], re.compile(p["regex"], re.IGNORECASE)) for p in PADROES_NOME
]
_COMPILADOS_CAMINHO = [re.compile(p["regex"], re.IGNORECASE) for p in PADROES_CAMINHO]


def _limpar(grupos: dict[str, str | None]) -> dict[str, str]:
    return {
        nome: valor
        for nome, valor in grupos.items()
        if valor and not nome.startswith("_")
    }


def do_nome(nome_arquivo: str) -> tuple[str, dict[str, str]]:
    """Extrai tipo e campos do nome do PDF.

    Devolve ("", {}) quando nenhum padrão reconhece o nome — o documento
    entra no catálogo mesmo assim, apenas sem esses campos.
    """
    base = Path(nome_arquivo).name
    for tipo, regex in _COMPILADOS_NOME:
        m = regex.match(base)
        if m:
            return tipo, _limpar(m.groupdict())
    return "", {}


def do_caminho(caminho: str) -> dict[str, str]:
    """Extrai campos do caminho da pasta.

    Serve tanto para a pasta real onde o PDF está quanto para o
    "Batch Location" gravado no XML, que aponta para a máquina de
    digitalização e frequentemente carrega o ano e o número que faltaram
    nos outros lugares.
    """
    campos: dict[str, str] = {}
    for regex in _COMPILADOS_CAMINHO:
        for m in regex.finditer(caminho):
            for nome, valor in _limpar(m.groupdict()).items():
                campos.setdefault(nome, valor)
    return campos
