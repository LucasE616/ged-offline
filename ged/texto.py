"""Normalização de texto para comparação.

Todo o acervo tem acentuação inconsistente: os XML vêm em Windows-1252, o texto dos PDFs veio de reconhecimento óptico e os usuários digitam sem acento. Buscar "municipio" precisa achar "MUNICÍPIO".
"""
from __future__ import annotations

import unicodedata


def normalizar(texto: str) -> str:
    """Remove acentos e diferenças de caixa, para comparação de busca."""
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return sem_acento.casefold()


def contem(agulha: str, palheiro: str) -> bool:
    """Busca por substring, ignorando acento e caixa."""
    if not agulha:
        return True
    return normalizar(agulha) in normalizar(palheiro)


def formatar_inteiro(valor: int) -> str:
    """12345 -> '12.345' (separador de milhar brasileiro)."""
    return f"{valor:,}".replace(",", ".")
