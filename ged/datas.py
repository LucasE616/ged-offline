"""Interpretação de datas escritas de qualquer jeito.

O acervo não tem um formato de data só. O mesmo arquivo de índice traz
`2019-11-29` na maioria dos registros e `01-11-2019` em outros, e o
usuário digita `29/11/2019`, que não é nenhum dos dois. Como os campos de
índice são descobertos em tempo de execução, não dá para declarar de
antemão qual é o campo de data nem em que formato ele vem — então aqui a
data é reconhecida pelo formato do valor, não pelo nome do campo.

A consulta pode ser parcial: `2019` acha o ano inteiro, `11/2019` acha o
mês, `29/11/2019` acha o dia exato. Quando o texto não se parece com uma
data, quem chama volta para a comparação por trecho de texto, e o campo
continua funcionando como texto comum.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

# Formatos completos aceitos num valor de índice, na ordem em que são
# tentados. O dia antes do mês vem primeiro por ser o uso brasileiro.
FORMATOS_VALOR = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%d.%m.%Y",
    "%Y%m%d",
    "%d%m%Y",
)

_SEPARADOR = re.compile(r"[/\-.]")
_SO_DIGITOS = re.compile(r"^\d+$")


def interpretar(valor: str) -> date | None:
    """Converte um valor de índice em data, ou devolve None se não for uma."""
    valor = (valor or "").strip()
    if not valor:
        return None
    # Descarta cedo o que claramente não é data: "101.0", "1100.07", "1.0"
    if re.fullmatch(r"\d+[.,]\d+", valor):
        return None
    for formato in FORMATOS_VALOR:
        try:
            return datetime.strptime(valor, formato).date()
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class DataParcial:
    """Uma data que o usuário digitou, possivelmente incompleta."""

    ano: int | None = None
    mes: int | None = None
    dia: int | None = None

    def casa(self, alvo: date) -> bool:
        if self.ano is not None and alvo.year != self.ano:
            return False
        if self.mes is not None and alvo.month != self.mes:
            return False
        if self.dia is not None and alvo.day != self.dia:
            return False
        return True

    def como_data(self, inicio: bool) -> date | None:
        """Vira uma data concreta, para servir de limite de período.

        `inicio=True` puxa para o começo do intervalo que a parcial
        descreve ("11/2019" → 01/11/2019); `inicio=False` puxa para o fim
        ("11/2019" → 30/11/2019). É o que faz "de 2019 até 2019" pegar o
        ano inteiro em vez de um dia só.
        """
        if self.ano is None:
            return None
        if self.mes is None:
            return date(self.ano, 1, 1) if inicio else date(self.ano, 12, 31)
        if self.dia is None:
            if inicio:
                return date(self.ano, self.mes, 1)
            return date(self.ano, self.mes, _ultimo_dia(self.ano, self.mes))
        try:
            return date(self.ano, self.mes, self.dia)
        except ValueError:
            return None


def _ultimo_dia(ano: int, mes: int) -> int:
    if mes == 12:
        return 31
    return (date(ano, mes + 1, 1) - date.resolution).day


def interpretar_consulta(texto: str) -> DataParcial | None:
    """Lê o que o usuário digitou como data, aceitando formas incompletas.

    Só trata como data o que tem separador ou é um ano de quatro dígitos —
    assim digitar "11" num campo continua sendo busca por texto, e não
    vira "novembro" sem que ninguém tenha pedido.
    """
    texto = (texto or "").strip()
    if not texto:
        return None

    if _SO_DIGITOS.match(texto):
        if len(texto) == 4 and 1900 <= int(texto) <= 2199:
            return DataParcial(ano=int(texto))
        if len(texto) == 8:
            completa = interpretar(texto)
            if completa:
                return DataParcial(completa.year, completa.month, completa.day)
        return None

    partes = [p for p in _SEPARADOR.split(texto) if p]
    if not partes or not all(_SO_DIGITOS.match(p) for p in partes):
        return None

    numeros = [int(p) for p in partes]

    if len(partes) == 3:
        completa = interpretar(texto)
        if completa:
            return DataParcial(completa.year, completa.month, completa.day)
        return None

    if len(partes) == 2:
        primeiro, segundo = numeros
        # "2019-11" → ano e mês
        if len(partes[0]) == 4:
            return DataParcial(ano=primeiro, mes=segundo) if 1 <= segundo <= 12 else None
        # "11/2019" → mês e ano
        if len(partes[1]) == 4:
            return DataParcial(ano=segundo, mes=primeiro) if 1 <= primeiro <= 12 else None
        # "29/11" → dia e mês, sem ano
        if 1 <= primeiro <= 31 and 1 <= segundo <= 12:
            return DataParcial(mes=segundo, dia=primeiro)
        return None

    return None


def casa_como_data(consulta: str, valor: str) -> bool | None:
    """Compara consulta e valor como datas.

    Devolve None quando a comparação não se aplica — porque a consulta não
    parece data, ou porque o valor não é uma. Nesse caso quem chamou deve
    cair para a busca por trecho de texto.
    """
    parcial = interpretar_consulta(consulta)
    if parcial is None:
        return None
    alvo = interpretar(valor)
    if alvo is None:
        return None
    return parcial.casa(alvo)


def limite_periodo(texto: str, inicio: bool) -> date | None:
    """Interpreta o que foi digitado num campo 'de'/'até' de período."""
    parcial = interpretar_consulta(texto)
    if parcial is None:
        return None
    return parcial.como_data(inicio)


def parece_campo_de_data(valores: list[str], minimo: int = 3) -> bool:
    """Decide se um campo de índice é de data, olhando o que ele contém.

    Exige que os valores preenchidos sejam datas na sua maioria — assim um
    campo de texto que por acaso tenha uma data solta no meio não vira um
    filtro de período.
    """
    preenchidos = [v for v in valores if v and v.strip()]
    if len(preenchidos) < min(minimo, 1):
        return False
    datas = sum(1 for v in preenchidos if interpretar(v) is not None)
    return datas >= max(1, int(len(preenchidos) * 0.6))


def formatar(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else ""
