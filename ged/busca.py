"""Busca sobre o catálogo em memória.

Duas coisas diferentes acontecem aqui, e a distinção é o que faz a busca se comportar como o usuário espera:

Os **filtros por campo** restringem — valem todos ao mesmo tempo, em E.
Preencher "Favorecido = CEMIG" tira da frente tudo que não for da CEMIG.

O **texto livre** amplia — vale em OU entre os escopos marcados. Um documento entra no resultado se o termo aparecer no nome do arquivo, ou nos índices, ou dentro do PDF. Por isso marcar "conteúdo do PDF" acrescenta resultados em vez de cortar: é uma pergunta a mais, não uma exigência a mais.

A economia vem daí naturalmente: só precisam ser abertos os PDFs dos documentos que ainda não casaram pelo nome nem pelo índice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from . import datas
from .catalogo import Catalogo, Documento
from .texto import contem


@dataclass
class Criterios:
    termo: str = ""
    escopo_nome: bool = True
    escopo_indice: bool = True
    escopo_conteudo: bool = False
    filtros: dict[str, str] = field(default_factory=dict)
    # Período sobre o campo de data do índice (Data de Pagto, Data Ass...)
    indice_de: str = ""
    indice_ate: str = ""
    # Período sobre a data de criação do arquivo no disco
    criacao_de: str = ""
    criacao_ate: str = ""

    @property
    def termo_limpo(self) -> str:
        return self.termo.strip()

    def periodo_indice(self) -> tuple[date | None, date | None]:
        return (
            datas.limite_periodo(self.indice_de, inicio=True),
            datas.limite_periodo(self.indice_ate, inicio=False),
        )

    def periodo_criacao(self) -> tuple[date | None, date | None]:
        return (
            datas.limite_periodo(self.criacao_de, inicio=True),
            datas.limite_periodo(self.criacao_ate, inicio=False),
        )

    def descrever(self) -> list[str]:
        """Critérios em texto, para o cabeçalho do relatório."""
        linhas: list[str] = []
        for campo, valor in self.filtros.items():
            if valor.strip():
                linhas.append(f'{campo} contém "{valor.strip()}"')
        for rotulo, (de, ate) in (
            ("data do índice", self.periodo_indice()),
            ("data de criação do arquivo", self.periodo_criacao()),
        ):
            if de and ate:
                linhas.append(f"{rotulo} entre {datas.formatar(de)} e {datas.formatar(ate)}")
            elif de:
                linhas.append(f"{rotulo} a partir de {datas.formatar(de)}")
            elif ate:
                linhas.append(f"{rotulo} até {datas.formatar(ate)}")
        if self.termo_limpo:
            linhas.append(f'texto contém "{self.termo_limpo}"')
        return linhas or ["nenhum — todos os documentos do diretório"]

    def escopos_descritos(self) -> str:
        ativos = []
        if self.escopo_nome:
            ativos.append("nome do arquivo")
        if self.escopo_indice:
            ativos.append("índice XML")
        if self.escopo_conteudo:
            ativos.append("conteúdo do PDF")
        return " ou ".join(ativos) or "nenhum escopo marcado"


@dataclass
class Resultado:
    documentos: list[Documento] = field(default_factory=list)
    conteudo_usado: bool = False
    lidos_para_conteudo: int = 0
    achados_por_conteudo: int = 0
    sem_texto: int = 0
    # Documentos que não casaram pelo nome nem pelo índice e cujo PDF não
    # está no diretório: não dá para afirmar nada sobre o conteúdo deles.
    nao_verificados: int = 0
    cancelado: bool = False

    @property
    def total_documentos(self) -> int:
        return len(self.documentos)

    @property
    def total_paginas(self) -> int:
        return sum(d.paginas or 0 for d in self.documentos)

    @property
    def paginas_desconhecidas(self) -> int:
        return sum(1 for d in self.documentos if d.paginas is None)

    @property
    def sem_pdf(self) -> int:
        return sum(1 for d in self.documentos if not d.localizado)


def _campo_casa(consulta: str, valor: str) -> bool:
    """Compara um campo com o que foi digitado.

    Tenta primeiro como data: assim procurar "29/11/2019" encontra o
    registro gravado como "2019-11-29", e "11/2019" encontra o mês
    inteiro. Quando a comparação por data não se aplica — porque o que foi
    digitado não parece data, ou porque o campo não contém uma — volta a
    ser busca por trecho de texto, como qualquer outro campo.
    """
    como_data = datas.casa_como_data(consulta, valor)
    if como_data is not None:
        return como_data
    return contem(consulta, valor)


def _dentro_do_periodo(alvo: date | None, de: date | None, ate: date | None) -> bool:
    if de is None and ate is None:
        return True
    if alvo is None:
        return False
    if de is not None and alvo < de:
        return False
    if ate is not None and alvo > ate:
        return False
    return True


def _passa_filtros(documento: Documento, criterios: Criterios, campos_data: list[str]) -> bool:
    """Filtros por campo e por período: todos precisam bater."""
    for campo, valor in criterios.filtros.items():
        if not valor.strip():
            continue
        if not _campo_casa(valor, documento.valor(campo)):
            return False

    de_indice, ate_indice = criterios.periodo_indice()
    if de_indice or ate_indice:
        # Basta um dos campos de data do documento cair no período.
        candidatas = [
            datas.interpretar(documento.valor(campo))
            for campo in campos_data
        ]
        candidatas = [d for d in candidatas if d is not None]
        if not any(_dentro_do_periodo(d, de_indice, ate_indice) for d in candidatas):
            return False

    de_criacao, ate_criacao = criterios.periodo_criacao()
    if de_criacao or ate_criacao:
        criada = documento.data_criacao.date() if documento.data_criacao else None
        if not _dentro_do_periodo(criada, de_criacao, ate_criacao):
            return False

    return True


def _casa_metadados(documento: Documento, criterios: Criterios) -> bool:
    """Termo livre no nome ou no índice — os escopos que não custam nada."""
    termo = criterios.termo_limpo
    if criterios.escopo_nome and contem(termo, documento.nome_arquivo):
        return True
    if criterios.escopo_indice and contem(termo, documento.texto_indexado()):
        return True
    return False


def filtrados(catalogo: Catalogo, criterios: Criterios) -> list[Documento]:
    """Só os filtros por campo e por período, sem o termo livre."""
    return [
        d
        for d in catalogo.documentos
        if _passa_filtros(d, criterios, catalogo.campos_data)
    ]


def a_ler_para_conteudo(catalogo: Catalogo, criterios: Criterios, cache=None) -> list[Documento]:
    """Quais PDFs a busca por conteúdo precisaria abrir agora.

    Serve para avisar o usuário antes de uma leitura demorada: exclui os
    que já casaram por nome ou índice, os que não têm PDF no diretório e
    os que já foram lidos nesta sessão.
    """
    if not criterios.escopo_conteudo or not criterios.termo_limpo:
        return []
    pendentes = [
        d
        for d in filtrados(catalogo, criterios)
        if d.localizado and not _casa_metadados(d, criterios)
    ]
    if cache is not None:
        pendentes = [d for d in pendentes if not cache.ja_lido(d.caminho)]
    return pendentes


def buscar(
    catalogo: Catalogo,
    criterios: Criterios,
    cache=None,
    progresso: Callable[[int, int, str], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
) -> Resultado:
    base = filtrados(catalogo, criterios)

    if not criterios.termo_limpo:
        return Resultado(documentos=base)

    marcados = [_casa_metadados(d, criterios) for d in base]

    usar_conteudo = criterios.escopo_conteudo and cache is not None
    if not usar_conteudo:
        return Resultado(documentos=[d for d, ok in zip(base, marcados) if ok])

    # Só abre os PDFs que ainda não casaram por nome nem por índice.
    pendentes = [(i, d) for i, (d, ok) in enumerate(zip(base, marcados)) if not ok]
    com_pdf = [(i, d) for i, d in pendentes if d.localizado]

    resultado = Resultado(conteudo_usado=True, nao_verificados=len(pendentes) - len(com_pdf))
    caminhos_lidos: list[str] = []

    for posicao, (indice, documento) in enumerate(com_pdf):
        if cancelado is not None and cancelado():
            resultado.cancelado = True
            break
        if progresso:
            progresso(posicao, len(com_pdf), documento.nome_arquivo)
        texto = cache.texto(documento.caminho)
        caminhos_lidos.append(str(documento.caminho))
        resultado.lidos_para_conteudo += 1
        if documento.paginas is None:
            documento.paginas = cache.paginas(documento.caminho)
        if contem(criterios.termo_limpo, texto):
            marcados[indice] = True
            resultado.achados_por_conteudo += 1

    resultado.sem_texto = cache.sem_texto(caminhos_lidos)
    resultado.documentos = [d for d, ok in zip(base, marcados) if ok]
    return resultado
