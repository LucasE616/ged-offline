"""Exportação do resultado da busca em CSV e TXT.

O CSV vai para a planilha; o TXT vai anexado ao processo. Ambos saem do mesmo resultado em tela, e ambos registram no cabeçalho o que foi buscado — sem isso, uma lista de doze documentos não diz, meses depois, se são todos os do período ou apenas os que alguém escolheu.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from .busca import Criterios, Resultado
from .catalogo import Catalogo
from .texto import formatar_inteiro

COLUNAS_FIXAS = ["Arquivo", "Páginas", "Origem", "PDF localizado", "Caminho"]


def _agora() -> str:
    return dt.datetime.now().strftime("%d/%m/%Y %H:%M")


def _linhas_cabecalho(catalogo: Catalogo, criterios: Criterios) -> list[tuple[str, str]]:
    escopo_pasta = "incluindo subpastas" if catalogo.incluir_subpastas else "somente esta pasta"
    linhas = [
        ("Diretório", f"{catalogo.raiz}  ({escopo_pasta})"),
        ("Emitido em", _agora()),
    ]
    if catalogo.tipo_ativo:
        linhas.append(("Tipo", catalogo.tipo_ativo))
    if catalogo.indices_escolhidos:
        linhas.append(("Índices", ", ".join(catalogo.indices_escolhidos)))
    linhas.append(("Escopo", criterios.escopos_descritos()))
    return linhas


def exportar_csv(
    destino: Path | str,
    catalogo: Catalogo,
    resultado: Resultado,
    criterios: Criterios,
) -> Path:
    """Uma coluna por índice descoberto no diretório, mais os campos do arquivo.

    Separador ponto e vírgula e UTF-8 com BOM: é o que faz o Excel em
    português abrir o arquivo com acentos corretos e colunas separadas, sem
    passar pelo assistente de importação.
    """
    destino = Path(destino)
    colunas = list(catalogo.vocabulario) + COLUNAS_FIXAS

    with destino.open("w", newline="", encoding="utf-8-sig") as fh:
        escritor = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        escritor.writerow(colunas)
        for documento in resultado.documentos:
            escritor.writerow(
                [documento.valor(campo) for campo in catalogo.vocabulario]
                + [
                    documento.nome_arquivo,
                    documento.paginas if documento.paginas is not None else "",
                    documento.origem,
                    "sim" if documento.localizado else "não",
                    str(documento.caminho) if documento.caminho else "",
                ]
            )
    return destino


def exportar_txt(
    destino: Path | str,
    catalogo: Catalogo,
    resultado: Resultado,
    criterios: Criterios,
) -> Path:
    destino = Path(destino)
    largura = 74
    regua = "-" * largura

    partes: list[str] = ["RELATÓRIO DE BUSCA — GED Offline", ""]
    for rotulo, valor in _linhas_cabecalho(catalogo, criterios):
        partes.append(f"{rotulo.ljust(14, '.')} {valor}")

    criterios_descritos = criterios.descrever()
    partes.append(f"{'Critérios'.ljust(14, '.')} {criterios_descritos[0]}")
    for linha in criterios_descritos[1:]:
        partes.append(f"{' ' * 15}{linha}")

    partes.extend(["", regua, ""])

    if not resultado.documentos:
        partes.append("Nenhum documento encontrado para estes critérios.")
    else:
        rotulos = [c for c in catalogo.vocabulario]
        preenchimento = max((len(r) for r in rotulos), default=10) + 2
        for i, documento in enumerate(resultado.documentos, start=1):
            partes.append(f"{str(i).rjust(4)}. {documento.nome_arquivo}")
            for campo in rotulos:
                valor = documento.valor(campo).strip()
                if valor:
                    partes.append(f"      {campo.ljust(preenchimento, '.')} {valor}")
            paginas = documento.paginas
            partes.append(
                f"      {'Páginas'.ljust(preenchimento, '.')} "
                f"{paginas if paginas is not None else 'não contadas'}"
            )
            if not documento.localizado:
                partes.append(f"      {'Situação'.ljust(preenchimento, '.')} PDF não localizado")
            partes.append("")

    partes.extend([regua, ""])
    partes.append(
        f"TOTAL  {formatar_inteiro(resultado.total_documentos)} documento(s)"
        f"   {formatar_inteiro(resultado.total_paginas)} página(s)"
    )
    for observacao in _observacoes(catalogo, resultado):
        partes.append(f"       {observacao}")

    # BOM pelo mesmo motivo do CSV: acentuação correta mesmo em editores
    # antigos do Windows. newline="" impede que o modo texto traduza de
    # novo o \r\n já explícito, o que produziria \r\r\n e deixaria o
    # arquivo espaçado em dobro no Bloco de Notas.
    destino.write_text("\r\n".join(partes), encoding="utf-8-sig", newline="")
    return destino


def _observacoes(catalogo: Catalogo, resultado: Resultado) -> list[str]:
    """Avisos que evitam que um total pareça mais completo do que é."""
    observacoes: list[str] = []
    if resultado.paginas_desconhecidas:
        observacoes.append(
            f"{resultado.paginas_desconhecidas} documento(s) sem contagem de páginas — fora do total acima"
        )
    if resultado.sem_pdf:
        observacoes.append(f"{resultado.sem_pdf} documento(s) do índice sem PDF localizado")
    if resultado.conteudo_usado and resultado.sem_texto:
        observacoes.append(
            f"{resultado.sem_texto} PDF(s) sem camada de texto — não havia o que procurar dentro"
        )
    if resultado.conteudo_usado and resultado.nao_verificados:
        observacoes.append(
            f"{resultado.nao_verificados} documento(s) do índice não puderam ser verificados "
            "por conteúdo: o PDF não está no diretório"
        )
    if resultado.cancelado:
        observacoes.append("busca por conteúdo interrompida antes do fim — resultado parcial")
    if catalogo.xmls_tolerantes:
        observacoes.append(
            f"{catalogo.xmls_tolerantes} índice(s) XML lido(s) em modo tolerante (arquivo malformado)"
        )
    return observacoes
