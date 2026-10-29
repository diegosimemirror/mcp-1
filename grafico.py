"""Genera grafico.png: cuántas cifras acertó Claude en cada modo.

    uv run grafico.py

Lee resultados.csv (lo escribe evaluar.py) y dibuja una barra por modo.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

AQUI = Path(__file__).parent
ETIQUETAS = {"memoria": "Sin herramientas\n(solo memoria)", "web": "Búsqueda web\n(modo web)",
             "mcp": "Con el servidor BCRP\n(modo mcp)"}
COLORES = {"memoria": "#9e9e9e", "web": "#7fb0f5", "mcp": "#1f6feb"}

resultados = pd.read_csv(AQUI / "resultados.csv")
ORDEN = ["memoria", "web", "mcp"]                                    # de menos a más herramientas
total = resultados.groupby("modo").id.nunique().reindex(ORDEN)      # preguntas por modo
aciertos = resultados[resultados.resultado == "acierta"].groupby("modo").id.count().reindex(ORDEN, fill_value=0)

fig, ax = plt.subplots(figsize=(7, 4.5))
colores = [COLORES[m] for m in ORDEN]
barras = ax.bar([ETIQUETAS[m] for m in ORDEN], aciertos.values, color=colores, width=0.5)
for barra, n, t in zip(barras, aciertos.values, total.values):
    ax.text(barra.get_x() + barra.get_width() / 2, n + 0.2, f"{n} de {t}", ha="center", fontsize=12, fontweight="bold")

ax.set_ylim(0, total.max() + 1.5)
ax.set_ylabel("Cifras correctas")
ax.set_title("Cifras correctas por modo (10 preguntas)", fontsize=12, loc="left")
ax.spines[["top", "right"]].set_visible(False)
fig.text(0.01, 0.01, "Fuente: BCRP, 10 preguntas con cifra oficial y tolerancia de redondeo.", fontsize=8, color="#555")
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(AQUI / "grafico.png", dpi=150)
print("grafico.png escrito")
