"""Servidor MCP del BCRP. Empiecen aquí: buscar_series ya funciona; completen los TODO hasta que pasen las pruebas.

    uv run pytest                                           # el contrato: las 8 pruebas deben pasar
    uv run server.py                                        # el servidor, por stdio
    claude mcp add --scope project bcrp -- uv run server.py # conectarlo a Claude Code

Las cuentas las hace Python, no el modelo: así cada cifra sale de una llamada que se puede repetir.
"""
import json
import re
import unicodedata
from functools import cache
from pathlib import Path

import httpx
import pandas as pd
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

AQUI = Path(__file__).parent
CATALOGO = AQUI / "datos" / "catalogo_bcrp.csv"
URL_CATALOGO = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": True}
# Equivalencias entre lo que se dice y lo que escribe el BCRP en sus nombres de serie (en minúsculas y sin tildes)
EQUIVALENCIAS = {"moneda nacional": "mn", "moneda extranjera": "me"}

mcp = FastMCP("bcrp", instructions=(
    "Series oficiales del Banco Central de Reserva del Perú (BCRP). Primero busca el código con buscar_series; "
    "luego usa resumen para variaciones, promedios y extremos, y serie para los datos. No calcules a mano: "
    "cita siempre el código de la serie y el periodo."))


def _sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


@cache
def catalogo():
    """El catálogo oficial: 17 mil series en unos 7 MB. Se baja una vez y queda en datos/."""
    if not CATALOGO.exists():
        CATALOGO.parent.mkdir(exist_ok=True)
        r = httpx.get(URL_CATALOGO, timeout=120)
        r.raise_for_status()
        CATALOGO.write_text(r.content.decode("latin-1"), encoding="utf-8")
    df = pd.read_csv(CATALOGO, sep=";", dtype=str).fillna("")
    df = df.rename(columns={"Código de serie": "codigo", "Categoría de serie": "categoria", "Grupo de serie": "grupo",
                            "Nombre de serie": "nombre", "Frecuencia": "frecuencia",
                            "Fecha de actualización": "actualizada", "Fecha de inicio": "inicio"})
    df["texto"] = (df.categoria + " " + df.grupo + " " + df.nombre).map(_sin_tildes)
    return df


def _ficha(codigo):
    fila = catalogo().query("codigo == @codigo")
    if fila.empty:
        raise ToolError(f"No existe el código de serie {codigo!r}. Búsquenlo con buscar_series.")
    f = fila.iloc[0]
    return {"codigo": f.codigo, "nombre": f"{f.grupo} - {f.nombre}", "categoria": f.categoria,
            "frecuencia": f.frecuencia, "inicio": f.inicio, "actualizada": f.actualizada}


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_series(texto: str, frecuencia: str | None = None, limite: int = 10) -> list[dict]:
    """Busca series del BCRP por palabras: todas deben aparecer en la categoría, el grupo o el nombre.

    Ejemplos: "ipc 12 meses", "tipo de cambio interbancario venta", "reservas internacionales netas",
    "tasa de referencia", "cobre precio". frecuencia: "Diaria", "Mensual", "Trimestral" o "Anual".
    Devuelve el código, el nombre completo, la frecuencia y desde cuándo hay datos. Si no hay resultados,
    prueben con menos palabras. "moneda nacional" y "moneda extranjera" se buscan como MN y ME, como las escribe el BCRP.
    """
    df = catalogo()
    m = pd.Series(True, index=df.index)
    texto_limpio = _sin_tildes(texto)
    for frase, sigla in EQUIVALENCIAS.items():         # Antes: "moneda nacional" | Después: "mn"
        texto_limpio = texto_limpio.replace(frase, sigla)
    for palabra in texto_limpio.split():
        # Las siglas cortas (mn, me) deben aparecer como palabra completa: "me" sola aparecería dentro de "mensual"
        patron = rf"\b{re.escape(palabra)}\b" if len(palabra) <= 2 else re.escape(palabra)
        m &= df.texto.str.contains(patron)
    if frecuencia:
        m &= df.frecuencia.str.lower() == frecuencia.lower()
    # primero las series vigentes y, entre ellas, las de nombre más corto (las más generales)
    sel = df[m]
    orden = sel.assign(vieja=sel.actualizada < "2025", largo=(sel.grupo + sel.nombre).str.len())
    return [_ficha(c) for c in orden.sort_values(["vieja", "largo"]).head(limite).codigo]


# ============================================================
# PROCESO 1 (TODO 1): serie(codigo, desde, hasta)
# Insumo:    código de serie (p. ej. PN01271PM) y un rango de fechas
# Resultado: lista de periodos con su valor, más la dirección de la fuente
# ============================================================

# Abreviaturas de los meses tal como las escribe la API (Setiembre aparece como "Set")
MESES = {"Ene": "01", "Feb": "02", "Mar": "03", "Abr": "04", "May": "05", "Jun": "06",
         "Jul": "07", "Ago": "08", "Set": "09", "Sep": "09", "Oct": "10", "Nov": "11", "Dic": "12"}


def _pedir(url):
    """Descarga una URL y devuelve el contenido como JSON (un diccionario de Python).

    Antes: una dirección web | Después: los datos ya leídos como diccionario
    """
    respuesta = httpx.get(url, timeout=60)
    respuesta.raise_for_status()   # si el servidor responde con error (p. ej. 500), lo detiene aquí
    try:
        return respuesta.json()
    except ValueError:
        # Si el BCRP limita los pedidos, responde una página HTML en vez de datos
        raise ToolError("El BCRP no respondió con datos (puede que haya muchos pedidos seguidos). "
                        "Espera unos segundos y vuelve a intentar.")


def _fecha_api(fecha, frecuencia):
    """Convierte la fecha que escribe el usuario al formato que pide la API.

    Antes: "2026-01" (mensual) | Después: "2026-1"
    Antes: "2026-10-15" (diaria) | Después: "2026-10-15" (no cambia)
    """
    if frecuencia == "Diaria":
        return fecha
    if frecuencia == "Anual":
        return fecha[:4]                                  # "2026-01" -> "2026"
    anio, mes = (fecha.split("-") + ["1"])[:2]            # "2026" -> mes 1
    return f"{anio}-{int(mes)}"                           # "2026-01" -> "2026-1"


def _periodo(nombre):
    """Convierte el nombre de un periodo de la API al formato del servidor.

    Antes: "Ene.2025" | Después: "2025-01"
    Antes: "01.Oct.26" | Después: "2026-10-01"
    Antes: "T1.25" | Después: "2025-T1"
    Antes: "2025" | Después: "2025" (no cambia)
    """
    partes = nombre.split(".")
    if len(partes) == 1:                                  # "2025": anual
        return nombre
    if len(partes) == 3:                                  # "01.Oct.26": diaria
        dia, mes, anio = partes
        return f"20{anio}-{MESES[mes]}-{dia}"
    if partes[0].startswith("T"):                         # "T1.25": trimestral
        return f"20{partes[1]}-{partes[0]}"
    mes, anio = partes                                    # "Ene.2025": mensual
    return f"{anio}-{MESES[mes]}"


@mcp.tool(annotations=SOLO_LECTURA)
def serie(codigo: str, desde: str, hasta: str) -> dict:
    """Devuelve los valores de una serie del BCRP entre dos fechas.

    codigo: el código que devuelve buscar_series, p. ej. "PN01271PM".
    desde y hasta: "2025-01" para series mensuales o trimestrales, "2025-01-15" para diarias, "2025" para anuales.
    Devuelve cada periodo con su valor y la dirección de la fuente oficial.
    """
    ficha = _ficha(codigo)                                # datos de la serie; error claro si el código no existe
    frecuencia = ficha["frecuencia"]
    url = f"{API}/{codigo}/json/{_fecha_api(desde, frecuencia)}/{_fecha_api(hasta, frecuencia)}"
    respuesta = _pedir(url)

    datos = []
    for periodo in respuesta["periods"]:
        try:
            valor = float(periodo["values"][0])           # "0.81" -> 0.81
        except (ValueError, IndexError):
            continue                                      # "n.d." (no disponible) no es un número: se salta
        datos.append({"periodo": _periodo(periodo["name"]), "valor": valor})

    return {"codigo": codigo, "nombre": ficha["nombre"], "frecuencia": frecuencia, "datos": datos, "fuente": url}

# ============================================================
# PROCESO 2 (TODO 2): resumen(codigo, desde, hasta)
# Insumo:    los periodos y valores que devuelve serie()
# Resultado: primer y último valor, cambio, variación, promedio, máximo y mínimo
# ============================================================

@mcp.tool(annotations=SOLO_LECTURA)
def resumen(codigo: str, desde: str, hasta: str) -> dict:
    """Resume una serie del BCRP entre dos fechas: primer y último valor, cambio, promedio, máximo y mínimo.

    Úsala cuando la pregunta pida una variación, un promedio o un extremo ("¿cuánto subió?", "¿cuál fue el máximo?").
    Las cuentas las hace Python, así que las cifras son exactas. Cita el código y los periodos que devuelve.
    Si la serie es un porcentaje, variacion_pct viene vacío y el cambio se lee en puntos porcentuales.
    """
    respuesta = serie(codigo, desde, hasta)               # Antes: el código y las fechas | Después: la serie con su nombre y datos
    datos = respuesta["datos"]
    if not datos:
        raise ToolError(f"La serie {codigo} no tiene datos entre {desde} y {hasta}.")

    primero, ultimo = datos[0], datos[-1]                 # datos van en orden de fecha: el primero y el último
    valores = [d["valor"] for d in datos]
    maximo = max(datos, key=lambda d: d["valor"])        # el periodo cuyo valor es el más alto
    minimo = min(datos, key=lambda d: d["valor"])        # el periodo cuyo valor es el más bajo

    # Si la serie ya es un porcentaje (p. ej. inflación, tasa de interés), calcular "% de un %" no tiene sentido.
    # Detectamos el % en el nombre de la serie. En esos casos, la diferencia se lee en puntos porcentuales.
    es_porcentaje = "%" in respuesta["nombre"]

    return {
        "codigo": codigo,
        "primero": primero,
        "ultimo": ultimo,
        "cambio": ultimo["valor"] - primero["valor"],                    # diferencia simple entre ambos extremos
        "cambio_en": "puntos porcentuales" if es_porcentaje else "unidades de la serie",
        # Variación en %: solo para series que no son porcentajes. Si el primero es 0, tampoco se puede: queda None
        "variacion_pct": None if es_porcentaje or not primero["valor"]
        else (ultimo["valor"] / primero["valor"] - 1) * 100,
        "promedio": sum(valores) / len(valores),          # suma de todos los valores dividida entre cuántos son
        "maximo": maximo,
        "minimo": minimo,
    }

# ============================================================
# PROCESO 3 (TODO 3): correlacion(codigo_a, codigo_b, desde, hasta)
# Insumo:    dos series del BCRP con sus periodos
# Resultado: coeficiente de correlación (de -1 a 1) y cuántos periodos se compararon
# ============================================================

@mcp.tool(annotations=SOLO_LECTURA)
def correlacion(codigo_a: str, codigo_b: str, desde: str, hasta: str) -> dict:
    """Mide qué tan juntas se mueven dos series del BCRP entre dos fechas (correlación de Pearson, de -1 a 1).

    Cerca de 1: suben y bajan juntas. Cerca de -1: una sube cuando la otra baja. Cerca de 0: no hay relación lineal.
    Solo compara los periodos en que ambas tienen datos. Correlación no es causalidad: no digas que una causa la otra.
    """
    # Antes: dos listas de periodos y valores | Después: una tabla con un periodo por fila y una columna por serie
    a = pd.Series({d["periodo"]: d["valor"] for d in serie(codigo_a, desde, hasta)["datos"]}, name=codigo_a)
    b = pd.Series({d["periodo"]: d["valor"] for d in serie(codigo_b, desde, hasta)["datos"]}, name=codigo_b)
    # join="inner": conserva solo los periodos que aparecen en ambas series
    pares = pd.concat([a, b], axis=1, join="inner").sort_index()

    if len(pares) < 3:
        raise ToolError(f"Solo hay {len(pares)} periodos en común entre {codigo_a} y {codigo_b}. "
                        "Revisa que tengan la misma frecuencia (mensual, diaria...) y el mismo rango.")

    coeficiente = pares[codigo_a].corr(pares[codigo_b])   # Pearson: qué tanto se mueven juntas
    if pd.isna(coeficiente):
        raise ToolError("No se puede calcular: una de las series no cambia (todos sus valores son iguales).")

    return {
        "codigo_a": codigo_a,
        "codigo_b": codigo_b,
        "correlacion": round(float(coeficiente), 3),
        "periodos_comparados": len(pares),
        "desde": pares.index[0],
        "hasta": pares.index[-1],
    }

# TODO 3 (opciones que dejamos para después): comparar_paises con la API del Banco Mundial, o grafico(codigo, desde, hasta)
#   que guarde un PNG en salidas/ y devuelva la ruta.

# ============================================================
# PROCESO 4 (TODO 4): recurso bcrp://serie/{codigo}
# Insumo:    el código que va en la dirección (p. ej. bcrp://serie/PN01271PM)
# Resultado: la ficha de esa serie como texto JSON
# ============================================================

# Un recurso es información de solo lectura que se pide por dirección (URI), no una acción.
# {codigo} es una variable: Claude puede pedir bcrp://serie/PN01273PM, con cualquier código.
@mcp.resource("bcrp://serie/{codigo}", mime_type="application/json")
def ficha_serie(codigo: str) -> str:
    """Ficha de una serie del BCRP: nombre, categoría, frecuencia y desde cuándo tiene datos."""
    # Antes: una fila del catálogo (tabla) | Después: un texto JSON con esos mismos campos
    return json.dumps(_ficha(codigo), ensure_ascii=False, indent=2)

# ============================================================
# PROCESO 5 (TODO 5): prompt informe(tema)
# Insumo:    el tema que escribe el usuario (p. ej. "inflación")
# Resultado: instrucciones listas para que Claude escriba un informe con cifras citadas
# ============================================================

# Un prompt es una plantilla de instrucciones. En Claude Code se invoca con / (p. ej. /mcp__bcrp__informe inflación).
@mcp.prompt
def informe(tema: str) -> str:
    """Pide un informe breve sobre un tema económico del Perú, con cada cifra citada por código y periodo."""
    # Antes: solo el tema | Después: el tema dentro de reglas claras para que las cifras sean verificables
    return (
        f"Haz un informe breve sobre: {tema}.\n"
        "Usa primero buscar_series para encontrar el código de la serie y luego resumen o serie para las cifras.\n"
        "Cada cifra debe ir con su código y su periodo, por ejemplo: 4.55 % en 2026-09 (serie PN01273PM).\n"
        "No hagas cuentas a mano: usa resumen para variaciones, promedios y extremos.\n"
        "Si una cifra no está disponible, dilo. No la estimes."
    )


if __name__ == "__main__":
    mcp.run()
