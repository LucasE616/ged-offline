"""Testes rápidos, sem framework: python main.py --selftest"""
from __future__ import annotations

from pathlib import Path

from ged import datas, nomes, xml_parser
from ged.texto import contem, normalizar

# O acervo grava a mesma informação em formatos diferentes, e o usuário
# digita num terceiro. Todos estes precisam se encontrar.
CASOS_DATA = [
    ("29/11/2019", "2019-11-29", True),
    ("2019-11-29", "2019-11-29", True),
    ("29-11-2019", "2019-11-29", True),
    ("29/11/2019", "29-11-2019", True),
    ("11/2019", "2019-11-29", True),
    ("2019", "2019-11-29", True),
    ("2019", "01-11-2019", True),
    ("12/2019", "2019-11-29", False),
    ("29/11/2019", "2019-11-28", False),
    ("2020", "2019-11-29", False),
]

CASOS_PERIODO = [
    ("2019", "2019", "2019-06-15", True),
    ("01/11/2019", "30/11/2019", "2019-11-29", True),
    ("01/11/2019", "30/11/2019", "2019-12-01", False),
    ("11/2019", "11/2019", "2019-11-30", True),
    ("", "2019", "2018-05-04", True),
    ("2020", "", "2019-11-29", False),
]

# O que NÃO pode ser confundido com data, para não estragar a busca por texto
NAO_SAO_DATAS = ["101.0", "1100.07", "1.0", "CEMIG", "12030", "11"]

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

    print("\n== Datas em formatos diferentes ==")
    for consulta, valor, esperado in CASOS_DATA:
        obtido = datas.casa_como_data(consulta, valor)
        certo = obtido is esperado
        tudo_certo &= certo
        print(f"{_ok(certo)}: buscar '{consulta}' em '{valor}' -> {obtido}")

    print("\n== Período ==")
    for de, ate, valor, esperado in CASOS_PERIODO:
        alvo = datas.interpretar(valor)
        limite_de = datas.limite_periodo(de, inicio=True)
        limite_ate = datas.limite_periodo(ate, inicio=False)
        dentro = (limite_de is None or alvo >= limite_de) and (
            limite_ate is None or alvo <= limite_ate
        )
        certo = dentro is esperado
        tudo_certo &= certo
        print(f"{_ok(certo)}: {valor} entre '{de or '—'}' e '{ate or '—'}' -> {dentro}")

    print("\n== Não podem virar data ==")
    for valor in NAO_SAO_DATAS:
        certo = datas.interpretar_consulta(valor) is None or datas.interpretar(valor) is None
        tudo_certo &= certo
        print(f"{_ok(certo)}: '{valor}' não é tratado como data")

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
