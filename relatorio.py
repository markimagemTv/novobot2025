import json
import pandas as pd
from datetime import datetime
import os

def gerar_relatorio_mensal(caminho_arquivo="data/orders.json", saida_csv="data/relatorio_mensal.csv"):
    if not os.path.exists(caminho_arquivo):
        print("Arquivo de pedidos não encontrado.")
        return

    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        pedidos = json.load(f)

    dados = []
    for pedido in pedidos.values():
        if pedido.get("status") != "pago":
            continue
        data = datetime.strptime(pedido["created_at"], "%Y-%m-%d %H:%M:%S")
        mes = data.strftime("%Y-%m")
        total = sum(item["price"] for item in pedido["items"])
        quantidade = len(pedido["items"])
        dados.append({"mes": mes, "total": total, "quantidade": quantidade})

    if not dados:
        print("Nenhum pedido pago encontrado.")
        return

    df = pd.DataFrame(dados)
    resumo = df.groupby("mes").agg(
        pedidos=("mes", "count"),
        itens=("quantidade", "sum"),
        arrecadado=("total", "sum")
    ).reset_index()

    resumo.to_csv(saida_csv, index=False)
    print(f"Relatório salvo em: {saida_csv}")
