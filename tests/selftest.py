"""Testes rápidos, sem framework: python main.py --selftest"""
from __future__ import annotations

from pathlib import Path

from ged import nomes, xml_parser
from ged.texto import contem, normalizar

XMLS_EXEMPLO = [
    Path(r"C:\Users\Lucas Emanuel\Downloads\xml despesa"),
    Path(r"C:\Users\Lucas Emanuel\Downloads\xml licitacao"),
]

CASOS_NOME = [
    ("Despesa_2019_06953-261224-095339.pdf", "despesa", {"Ano": "2019", "Numero": "06953"}),
    ("Despesa_06953-261224-095339.pdf", "despesa", {"Numero": "06953"}),
    ("licitacao_058-2015-06112025-1726.pdfa", "licitacao", {"Numero": "058-2015"}),
    ("lei_1234_2015-010101-000000.pdf", "legislacao", {"Tipo": "lei", "Numero": "1234", "Ano": "2015"}),
]

CASOS_CAMINHO = [
    (r"C:\PaperCapture\exportados\licitacao\2017\licitacao_098_76", {"Numero": "098", "Ano": "2017"}),
    (r"D:\Processar-Kodak\2019\DESPESAS\DESPESAS_2019_121_NOV", {"Ano": "2019"}),
]


def _ok(condicao: bool) -> str:
    return "OK  " if condicao else "FALHA"


def rodar() -> None:
    tudo_certo = True

    print("== Normalização de texto ==")
    for entrada, alvo in [("municipio", "MUNICÍPIO"), ("SAO", "São"), ("agua", "Água")]:
        certo = contem(entrada, alvo)
        tudo_certo &= certo
        print(f"{_ok(certo)}: '{entrada}' encontra '{alvo}'")

    print("\n== Nome do arquivo ==")
    for arquivo, tipo_esperado, campos_esperados in CASOS_NOME:
        tipo, campos = nomes.do_nome(arquivo)
        certo = tipo == tipo_esperado and all(
            campos.get(k) == v for k, v in campos_esperados.items()
        )
        tudo_certo &= certo
        print(f"{_ok(certo)}: {arquivo} -> {tipo} {campos}")

    print("\n== Caminho da pasta ==")
    for caminho, campos_esperados in CASOS_CAMINHO:
        campos = nomes.do_caminho(caminho)
        certo = all(campos.get(k) == v for k, v in campos_esperados.items())
        tudo_certo &= certo
        print(f"{_ok(certo)}: ...{caminho[-42:]} -> {campos}")

    print("\n== Índices XML de exemplo ==")
    for caminho in XMLS_EXEMPLO:
        if not caminho.exists():
            print(f"(pulado: {caminho} não encontrado)")
            continue
        try:
            registros, tolerante = xml_parser.ler_indice(caminho)
        except Exception as exc:
            tudo_certo = False
            print(f"FALHA: {caminho.name}: {exc}")
            continue
        certo = len(registros) > 0
        tudo_certo &= certo
        modo = " (modo tolerante)" if tolerante else ""
        print(f"{_ok(certo)}: {caminho.name} -> {len(registros)} documento(s){modo}")
        if registros:
            primeiro = registros[0]
            print(f"       campos de índice: {list(primeiro.campos)}")
            print(f"       arquivo: {primeiro.nome_arquivo!r}  páginas: {primeiro.paginas}")

    print("\nResultado final:", "TUDO OK" if tudo_certo else "HÁ FALHAS")


if __name__ == "__main__":
    rodar()
