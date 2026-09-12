"""Varredura do diretório e catálogo em memória.

Uma varredura só, feita ao escolher a pasta, que não abre nenhum PDF:
lista os arquivos, lê os índices XML e liga um ao outro pelo nome do arquivo. O resultado vive na memória enquanto a janela estiver aberta e é descartado ao fechar.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from . import nomes, xml_parser
from .texto import contem

EXTENSOES_PDF = {".pdf", ".pdfa"}
EXTENSOES_XML = {".xml"}

ORIGEM_XML = "índice"
ORIGEM_NOME = "nome"


@dataclass
class Documento:
    """Um documento do acervo, com seus campos de índice preservados."""

    campos: dict[str, str] = field(default_factory=dict)
    nome_arquivo: str = ""
    caminho: Path | None = None
    origem: str = ORIGEM_NOME
    tipo: str = ""
    xml_origem: str = ""
    paginas: int | None = None
    tamanho: int = 0

    @property
    def localizado(self) -> bool:
        return self.caminho is not None

    def valor(self, campo: str) -> str:
        return self.campos.get(campo, "")

    def texto_indexado(self) -> str:
        """Todos os valores de índice juntos, para a busca por texto livre."""
        return " ".join(self.campos.values())


@dataclass
class Progresso:
    fase: str
    atual: int
    total: int
    mensagem: str = ""


@dataclass
class Catalogo:
    """O acervo de um diretório, carregado em memória."""

    raiz: Path
    incluir_subpastas: bool = True
    documentos: list[Documento] = field(default_factory=list)
    vocabulario: list[str] = field(default_factory=list)
    xmls_lidos: int = 0
    xmls_tolerantes: int = 0
    pdfs_encontrados: int = 0

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

    @property
    def sem_indice(self) -> int:
        return sum(1 for d in self.documentos if d.origem == ORIGEM_NOME)


def _percorrer(raiz: Path, incluir_subpastas: bool) -> Iterator[Path]:
    if not incluir_subpastas:
        try:
            with os.scandir(raiz) as entradas:
                for entrada in entradas:
                    if entrada.is_file():
                        yield Path(entrada.path)
        except OSError:
            pass
        return
    for pasta, _subpastas, arquivos in os.walk(raiz):
        for nome_arquivo in arquivos:
            yield Path(pasta) / nome_arquivo


def varrer(
    raiz: Path | str,
    incluir_subpastas: bool = True,
    progresso: Callable[[Progresso], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
) -> Catalogo:
    raiz = Path(raiz)
    if not raiz.exists():
        raise FileNotFoundError(f"Diretório não encontrado: {raiz}")

    catalogo = Catalogo(raiz=raiz, incluir_subpastas=incluir_subpastas)

    def parou() -> bool:
        return cancelado is not None and cancelado()

    # --- passo 1: listar, sem abrir nada
    if progresso:
        progresso(Progresso("listando", 0, 0, "Listando arquivos..."))

    pdfs: dict[str, Path] = {}
    xmls: list[Path] = []
    for i, caminho in enumerate(_percorrer(raiz, incluir_subpastas)):
        if parou():
            return catalogo
        sufixo = caminho.suffix.lower()
        if sufixo in EXTENSOES_PDF:
            pdfs.setdefault(caminho.name.lower(), caminho)
        elif sufixo in EXTENSOES_XML or (sufixo == "" and xml_parser.parece_indice(caminho)):
            xmls.append(caminho)
        if progresso and i % 250 == 0:
            progresso(Progresso("listando", i, 0, f"{len(pdfs)} PDFs, {len(xmls)} índices"))

    catalogo.pdfs_encontrados = len(pdfs)

    # --- passo 2: ler os índices e vincular
    if progresso:
        progresso(Progresso("lendo", 0, len(xmls), f"Lendo {len(xmls)} índice(s)..."))

    vocabulario: list[str] = []
    vinculados: set[str] = set()

    for i, xml_path in enumerate(xmls):
        if parou():
            return catalogo
        if progresso:
            progresso(Progresso("lendo", i, len(xmls), xml_path.name))
        try:
            registros, tolerante = xml_parser.ler_indice(xml_path)
        except Exception:
            continue
        catalogo.xmls_lidos += 1
        if tolerante:
            catalogo.xmls_tolerantes += 1

        for registro in registros:
            nome_arquivo = registro.nome_arquivo
            caminho_pdf = pdfs.get(nome_arquivo.lower()) if nome_arquivo else None
            if caminho_pdf:
                vinculados.add(nome_arquivo.lower())

            campos = dict(registro.campos)
            for nome_campo in campos:
                if nome_campo not in vocabulario:
                    vocabulario.append(nome_campo)

            tipo, do_nome = nomes.do_nome(nome_arquivo)
            do_caminho = nomes.do_caminho(registro.local_lote or str(caminho_pdf or ""))
            _completar(campos, do_nome, vocabulario)
            _completar(campos, do_caminho, vocabulario)

            catalogo.documentos.append(
                Documento(
                    campos=campos,
                    nome_arquivo=nome_arquivo or (caminho_pdf.name if caminho_pdf else ""),
                    caminho=caminho_pdf,
                    origem=ORIGEM_XML,
                    tipo=tipo,
                    xml_origem=str(xml_path),
                    paginas=registro.paginas,
                    tamanho=caminho_pdf.stat().st_size if caminho_pdf else 0,
                )
            )

    # --- passo 3: PDFs que nenhum índice menciona
    for chave, caminho_pdf in pdfs.items():
        if chave in vinculados:
            continue
        tipo, do_nome = nomes.do_nome(caminho_pdf.name)
        campos: dict[str, str] = {}
        _completar(campos, do_nome, vocabulario)
        _completar(campos, nomes.do_caminho(str(caminho_pdf.parent)), vocabulario)
        catalogo.documentos.append(
            Documento(
                campos=campos,
                nome_arquivo=caminho_pdf.name,
                caminho=caminho_pdf,
                origem=ORIGEM_NOME,
                tipo=tipo,
                paginas=None,
                tamanho=caminho_pdf.stat().st_size,
            )
        )

    catalogo.vocabulario = vocabulario
    if progresso:
        progresso(Progresso("concluido", 1, 1, "Concluído"))
    return catalogo


def _completar(campos: dict[str, str], extras: dict[str, str], vocabulario: list[str]) -> None:
    """Preenche apenas o que o índice deixou vazio, sem sobrescrever o XML."""
    for nome_campo, valor in extras.items():
        if campos.get(nome_campo, "").strip():
            continue
        campos[nome_campo] = valor
        if nome_campo not in vocabulario:
            vocabulario.append(nome_campo)


def contar_paginas_faltantes(
    catalogo: Catalogo,
    cache,
    progresso: Callable[[Progresso], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
) -> int:
    """Conta as páginas dos PDFs sem índice, abrindo só a estrutura do arquivo.

    É a única exceção à regra de não abrir PDF na varredura, e roda em
    segundo plano: se for interrompida, o que já foi contado permanece e o
    total indica quantos documentos ficaram de fora.
    """
    pendentes = [d for d in catalogo.documentos if d.paginas is None and d.localizado]
    contados = 0
    for i, documento in enumerate(pendentes):
        if cancelado is not None and cancelado():
            break
        if progresso:
            progresso(Progresso("paginas", i, len(pendentes), documento.nome_arquivo))
        paginas = cache.paginas(documento.caminho)
        if paginas is not None:
            documento.paginas = paginas
            contados += 1
    return contados
