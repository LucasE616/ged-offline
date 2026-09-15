"""Varredura do diretório e catálogo em memória.

Uma varredura só, feita ao escolher a pasta, que não abre nenhum PDF:
lista os arquivos, lê os índices XML e liga um ao outro pelo nome do arquivo. O resultado vive na memória enquanto a janela estiver aberta e é descartado ao fechar.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

from . import datas, nomes, xml_parser
from .texto import contem, normalizar

EXTENSOES_PDF = {".pdf", ".pdfa"}
EXTENSOES_XML = {".xml"}

ORIGEM_XML = "índice"
ORIGEM_NOME = "nome"

SEM_TIPO = "(sem tipo identificado)"

# Quantos valores olhar por campo ao decidir se ele é de data.
AMOSTRA_DATA = 200


def _data_de_criacao(caminho: Path) -> datetime | None:
    """Data de criação do arquivo.

    No Windows `st_ctime` é de fato a criação; em outros sistemas usamos
    `st_birthtime` quando existe e caímos na modificação quando não.
    """
    try:
        info = caminho.stat()
    except OSError:
        return None
    bruto = getattr(info, "st_birthtime", None)
    if bruto is None:
        bruto = info.st_ctime if os.name == "nt" else info.st_mtime
    try:
        return datetime.fromtimestamp(bruto)
    except (OSError, OverflowError, ValueError):
        return None


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
    data_criacao: datetime | None = None

    @property
    def localizado(self) -> bool:
        return self.caminho is not None

    def valor(self, campo: str) -> str:
        return self.campos.get(campo, "")

    def texto_indexado(self) -> str:
        """Todos os valores de índice juntos, para a busca por texto livre."""
        return " ".join(self.campos.values())

    def rotulo_tipo(self) -> str:
        """Como este documento se apresenta na escolha de tipo.

        Usa o tipo deduzido do nome do arquivo; se não houver, recorre ao
        campo "Título" do próprio índice, que nos exports do acervo traz
        exatamente isso ("Despesa", "PREI").
        """
        if self.tipo:
            return self.tipo[:1].upper() + self.tipo[1:]
        for nome_campo, valor in self.campos.items():
            if normalizar(nome_campo) == "titulo" and valor.strip():
                return valor.strip()
        return SEM_TIPO


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
    # Campos do vocabulário cujos valores são datas — descobertos olhando
    # o conteúdo, já que o nome do campo varia de acervo para acervo
    # ("Data de Pagto", "Data Ass", "Data").
    campos_data: list[str] = field(default_factory=list)
    tipo_ativo: str = ""
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
                    data_criacao=_data_de_criacao(caminho_pdf) if caminho_pdf else None,
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
                data_criacao=_data_de_criacao(caminho_pdf),
            )
        )

    catalogo.vocabulario = vocabulario
    catalogo.campos_data = detectar_campos_de_data(catalogo)
    if progresso:
        progresso(Progresso("concluido", 1, 1, "Concluído"))
    return catalogo


def detectar_campos_de_data(catalogo: Catalogo) -> list[str]:
    """Quais campos do vocabulário contêm datas, julgando pelos valores."""
    encontrados: list[str] = []
    for campo in catalogo.vocabulario:
        amostra: list[str] = []
        for documento in catalogo.documentos:
            valor = documento.valor(campo)
            if valor and valor.strip():
                amostra.append(valor)
            if len(amostra) >= AMOSTRA_DATA:
                break
        if datas.parece_campo_de_data(amostra):
            encontrados.append(campo)
    return encontrados


@dataclass
class GrupoTipo:
    """Um tipo de documento encontrado no diretório."""

    rotulo: str
    documentos: list[Documento] = field(default_factory=list)
    vocabulario: list[str] = field(default_factory=list)

    @property
    def total_documentos(self) -> int:
        return len(self.documentos)

    @property
    def total_paginas(self) -> int:
        return sum(d.paginas or 0 for d in self.documentos)


def agrupar_por_tipo(catalogo: Catalogo) -> list[GrupoTipo]:
    """Separa o catálogo pelos tipos de documento presentes.

    Uma pasta costuma ter um tipo só, mas apontar para a raiz de um acervo
    mistura despesas com licitações — e os vocabulários se somam, enchendo
    a busca de campos que não valem para o que se está procurando. Este
    agrupamento é o que permite escolher um tipo e trabalhar só com os
    índices dele.
    """
    grupos: dict[str, GrupoTipo] = {}
    for documento in catalogo.documentos:
        rotulo = documento.rotulo_tipo()
        grupo = grupos.setdefault(rotulo, GrupoTipo(rotulo=rotulo))
        grupo.documentos.append(documento)

    for grupo in grupos.values():
        presentes = {c for d in grupo.documentos for c, v in d.campos.items() if v.strip()}
        # Mantém a ordem do vocabulário geral, para as colunas não dançarem
        grupo.vocabulario = [c for c in catalogo.vocabulario if c in presentes]

    return sorted(grupos.values(), key=lambda g: (-g.total_documentos, g.rotulo))


def subcatalogo(catalogo: Catalogo, grupo: GrupoTipo) -> Catalogo:
    """Uma visão do catálogo restrita a um tipo, com o vocabulário dele."""
    recorte = Catalogo(
        raiz=catalogo.raiz,
        incluir_subpastas=catalogo.incluir_subpastas,
        documentos=list(grupo.documentos),
        vocabulario=list(grupo.vocabulario),
        tipo_ativo=grupo.rotulo,
        xmls_lidos=catalogo.xmls_lidos,
        xmls_tolerantes=catalogo.xmls_tolerantes,
        pdfs_encontrados=catalogo.pdfs_encontrados,
    )
    recorte.campos_data = [c for c in catalogo.campos_data if c in recorte.vocabulario]
    return recorte


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
