"""Parser dos arquivos de índice XML gerados pelo Kodak Capture / PaperCapture.

Duas particularidades do formato guiam este módulo:

1. Os arquivos declaram encoding utf-8 no cabeçalho, mas costumam estar gravados em Windows-1252. E alguns truncam valores de campo muito longos sem fechar as aspas, o que quebra qualquer parser XML estrito. Os dois casos são contornados aqui, sem descartar o arquivo.

2. Cada <field> traz um atributo `level`: "document" para os índices do acervo (Favorecido, Ementa, Modalidade...) e "system" para os metadados do processo de digitalização (nome do arquivo, número de páginas). Essa separação é o que permite descobrir o vocabulário de índices de um diretório sem conhecê-lo de antemão — por isso os nomes de campo são preservados exatamente como vieram, sem tradução.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .texto import normalizar

ENCODINGS_TENTADOS = ("utf-8", "cp1252", "latin-1")

# Campos de sistema que o resto do programa precisa localizar. A busca é
# feita por nome normalizado, porque a grafia varia entre exports.
SISTEMA_NOME_ARQUIVO = "documentfilename"
SISTEMA_PAGINAS = "pagecountindocument"
SISTEMA_LOCAL_LOTE = "batchlocation"
SISTEMA_TAMANHO = "documentsizebytes"


@dataclass
class DocumentoXML:
    """Um <document> do índice, com os nomes de campo preservados."""

    campos: dict[str, str] = field(default_factory=dict)
    sistema: dict[str, str] = field(default_factory=dict)
    xml_origem: str = ""

    def _sistema(self, chave_normalizada: str) -> str:
        for nome, valor in self.sistema.items():
            if _chave(nome) == chave_normalizada:
                return valor
        return ""

    @property
    def nome_arquivo(self) -> str:
        return self._sistema(SISTEMA_NOME_ARQUIVO).strip()

    @property
    def paginas(self) -> int | None:
        bruto = self._sistema(SISTEMA_PAGINAS).strip()
        try:
            return int(bruto)
        except ValueError:
            return None

    @property
    def local_lote(self) -> str:
        return self._sistema(SISTEMA_LOCAL_LOTE).strip()


def _chave(nome: str) -> str:
    """Reduz um nome de campo a letras e dígitos, para comparação estável."""
    return re.sub(r"[^a-z0-9]+", "", normalizar(nome))


def _remover_lixo_em_volta(texto: str) -> str:
    """Descarta o que vier antes do <?xml e depois do </root>.

    Alguns arquivos chegam embrulhados em marcadores estranhos — uma linha
    de aspas triplas antes do prólogo, um "?" solto colado no <?xml. Nada
    disso é XML, então localizamos o início e o fim reais e ignoramos o
    resto.
    """
    texto = texto.lstrip("﻿")
    inicio = re.search(r"<\?xml|<root\b", texto)
    if inicio and inicio.start() > 0:
        texto = texto[inicio.start():]
    fins = list(re.finditer(r"</root\s*>", texto))
    if fins:
        texto = texto[: fins[-1].end()]
    return texto


def _ler_texto(caminho: Path) -> str:
    bruto = caminho.read_bytes()
    for encoding in ENCODINGS_TENTADOS:
        try:
            texto = bruto.decode(encoding)
        except UnicodeDecodeError:
            continue
        texto = re.sub(r'encoding\s*=\s*"[^"]*"', 'encoding="utf-8"', texto, count=1)
        return _remover_lixo_em_volta(texto)
    return _remover_lixo_em_volta(bruto.decode("latin-1", errors="replace"))


def parece_indice(caminho: Path) -> bool:
    """Checagem barata, sem parse, de que o arquivo é um índice do acervo."""
    try:
        with caminho.open("rb") as fh:
            inicio = fh.read(4096)
    except OSError:
        return False
    return b"<root" in inicio and (b"<document" in inicio or b"field" in inicio)


_ENTIDADES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}
_ENTIDADE_RE = re.compile(r"&(#x[0-9a-fA-F]+|#\d+|[a-zA-Z]+);")


def _decodificar_entidades(texto: str) -> str:
    """Resolve &amp;, &#xA; etc. no caminho tolerante, que não passa pelo xml.etree."""

    def troca(m: re.Match[str]) -> str:
        token = m.group(1)
        try:
            if token[:2].lower() == "#x":
                return chr(int(token[2:], 16))
            if token.startswith("#"):
                return chr(int(token[1:]))
            return _ENTIDADES.get(token, m.group(0))
        except ValueError:
            return m.group(0)

    return _ENTIDADE_RE.sub(troca, texto)


def _montar(campos_brutos: list[tuple[str, str, str]], xml_origem: str) -> DocumentoXML:
    """Distribui os campos entre índice (level=document) e sistema (level=system)."""
    doc = DocumentoXML(xml_origem=xml_origem)
    for nivel, nome, valor in campos_brutos:
        nome = nome.strip()
        if not nome:
            continue
        # O export deixa espaços sobrando em quase todo valor ("1100.07 ").
        # Sem tirá-los, o Excel lê os números como texto e a busca por
        # igualdade falha por um motivo invisível.
        valor = valor.strip()
        if normalizar(nivel).strip() == "system":
            doc.sistema[nome] = valor
        else:
            doc.campos[nome] = valor
    return doc


_CAUDA_TRUNCADA = re.compile(r"(/>\s*)$")


def _parse_tolerante(texto: str, xml_origem: str) -> list[DocumentoXML]:
    """Extrai campos por expressão regular quando o XML não é bem formado.

    Acontece quando o export trunca um valor longo sem fechar as aspas. Em
    vez de perder o arquivo inteiro, aproveitamos o que dá, aceitando o
    valor truncado como está.
    """
    documentos: list[DocumentoXML] = []
    for bloco in re.split(r"<document\b[^>]*>", texto)[1:]:
        bloco = re.split(r"</document>", bloco)[0]
        brutos: list[tuple[str, str, str]] = []
        for pedaco in re.split(r"<field\b", bloco)[1:]:
            nome_m = re.search(r'name\s*=\s*"([^"]*)"', pedaco)
            if not nome_m:
                continue
            nivel_m = re.search(r'level\s*=\s*"([^"]*)"', pedaco)
            valor_m = re.search(r'value\s*=\s*"(.*?)"\s*/?>', pedaco, re.DOTALL)
            if valor_m:
                valor = valor_m.group(1)
            else:
                truncado = re.search(r'value\s*=\s*"(.*)', pedaco, re.DOTALL)
                valor = _CAUDA_TRUNCADA.sub("", truncado.group(1)).rstrip() if truncado else ""
            brutos.append(
                (nivel_m.group(1) if nivel_m else "", nome_m.group(1), _decodificar_entidades(valor))
            )
        if brutos:
            documentos.append(_montar(brutos, xml_origem))
    return documentos


def ler_indice(caminho: Path) -> tuple[list[DocumentoXML], bool]:
    """Lê um índice XML.

    Devolve os documentos e um sinalizador indicando se foi preciso recorrer
    ao modo tolerante — número que a interface reporta ao usuário.
    """
    texto = _ler_texto(caminho)

    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError:
        try:
            limpo = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", texto)
            raiz = ET.fromstring(limpo)
        except ET.ParseError:
            return _parse_tolerante(texto, str(caminho)), True

    documentos = [
        _montar(
            [
                (el.get("level", ""), el.get("name", ""), el.get("value", ""))
                for el in doc_el.findall("field")
            ],
            str(caminho),
        )
        for doc_el in raiz.findall("document")
    ]
    return documentos, False
