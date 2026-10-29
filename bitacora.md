# Bitácora · Sesión 04: MCP para datos del BCRP

**Fecha:** 28 de octubre de 2026
**Proyecto:** servidor MCP con las series oficiales del Banco Central de Reserva del Perú (BCRP)

## 1. Qué construimos

Un servidor MCP (`server.py`) que permite a Claude consultar las 17 mil series del BCRP durante una conversación. Ofrece:

| Pieza | Qué hace |
|---|---|
| `buscar_series` | Encuentra el código oficial de una serie a partir de palabras |
| `serie` | Devuelve los valores de una serie entre dos fechas, con su fuente |
| `resumen` | Calcula primer y último valor, cambio, promedio, máximo y mínimo |
| `correlacion` (herramienta propia) | Mide si dos series se mueven juntas (correlación de Pearson, de -1 a 1) |
| Recurso `bcrp://serie/{codigo}` | Ficha de una serie: nombre, frecuencia, inicio y última actualización |
| Prompt `informe` | Plantilla que pide a Claude citar código y periodo de cada cifra |

Las 8 pruebas automáticas pasan. `test_server.py` no se modificó.

## 2. Comparación de los tres medios

Preguntamos las mismas 10 cifras oficiales por tres caminos. Las preguntas eran de 2025 y 2026; el modelo es Haiku.

| Medio | Acierta | Se equivoca | No sabe | Tiempo promedio |
|---|---|---|---|---|
| Sin herramientas (memoria) | 0 | 0 | 10 | 4.5 s |
| Búsqueda web | 7 | 0 | 3 | 19.6 s |
| Servidor BCRP (MCP) | 10 | 0 | 0 | 9.0 s |

Lo que se ve en cada uno:

- **Sin herramientas:** Claude respondió honestamente que no tenía acceso a datos del BCRP y que su conocimiento llegaba hasta junio de 2026. No inventó cifras, pero tampoco sirve para un informe.
- **Búsqueda web:** encontró casi todo y no se equivocó en ninguna pregunta. Pero en tres casos no encontró el dato, y en varios usó notas de prensa o cifras del INEI citadas por medios, no la serie del BCRP.
- **Servidor BCRP:** acertó las 10 y todas salieron de la serie oficial, con su código y periodo. Fue el más rápido de los dos que sí respondieron.

## 3. Cómo corregimos el error del crédito

**El problema:** en la primera corrida con el servidor, el crédito de mayo de 2026 salió mal (337 251.68 millones de soles en vez de 295 907.25). Lo repetimos y pasó lo mismo.

**Diagnóstico, paso a paso:**
1. Revisamos la fuente que citó Claude. Usó *crédito directo del sistema financiero*, no *crédito del sistema bancario*, y lo aclaró en la fuente.
2. Buscamos la causa en `buscar_series`. La pregunta decía "moneda nacional", pero el catálogo del BCRP escribe **"MN"**. La búsqueda exige que aparezcan **todas** las palabras, así que con "moneda nacional" no devolvía nada, y Claude amplió la búsqueda hasta otra serie.

**Corrección:** agregamos equivalencias (`moneda nacional` → `mn`, `moneda extranjera` → `me`). Las siglas cortas se buscan como palabra completa, para que `me` no aparezca dentro de palabras como "mensual".

**Verificación:** las 8 pruebas siguen en verde y el crédito ahora sale con la serie correcta (`PN00522MM`).

**Lo que todavía no resolvimos:** la búsqueda no filtra por frecuencia. Al buscar crédito apareció primero una serie anual (`PD09936MA`), que no tiene datos de mayo de 2026. No la usó Claude en esta corrida, pero podría hacerlo en otra.

**Honestidad sobre la evidencia:** el acierto del crédito viene de una corrida después del cambio. Antes del cambio fallaron dos corridas. Conviene repetirla antes de afirmar que el problema está resuelto del todo.

## 4. Ventajas de cada medio

| Medio | Ventajas | Límites |
|---|---|---|
| Sin herramientas | Rápido; no depende de internet; no inventa cifras (si el modelo está bien configurado) | No tiene datos recientes; no sirve para cifras de 2026 |
| Búsqueda web | Cubre temas que no están en una base; no hay que construir nada | Puede no encontrar el dato; a veces usa fuentes secundarias; más lenta |
| Servidor MCP | Fuente oficial; código y periodo en cada cifra; cálculos hechos por Python; repetible; más rápido | Hay que construirlo y mantenerlo; solo cubre lo que tiene su fuente (aquí, macroeconomía peruana); una pregunta ambigua puede llevar a una serie parecida |

## 5. Combinación que recomendamos

**MCP como fuente principal, y búsqueda web para contrastar.**

- El MCP da la cifra oficial, con código y fecha, en segundos.
- La búsqueda web sirve para confirmar esa cifra en otra fuente, o para cubrir lo que el servidor no tiene.
- Antes de usar una cifra en una decisión, conviene revisar la serie y el periodo, porque una serie parecida puede dar un valor distinto.

Esto importa especialmente para decisiones financieras. Un dato equivocado con apariencia correcta es más peligroso que un "no sé".

## 6. Producto: reporte para lectores no economistas

Como producto de prueba, creamos un reporte en Word, `informe_inflacion_bcrp.docx`, dirigido a personas sin formación en economía. Explica la inflación con una canasta de compras, cómo se calcula el IPC, qué significan "puntos porcentuales" y las expectativas, y cierra con un glosario.

**Qué verificamos del reporte:** comparamos la tabla mensual con la API del BCRP:
- La inflación observada de los 12 meses coincide con la serie `PN01273PM` en los 12 meses.
- Las expectativas de inflación (`PD12912AM`) coinciden en 10 de 12 meses. En diciembre de 2025 y enero de 2026 el valor oficial es exactamente 2.125 y 2.025; el reporte los redondeó hacia arriba (2.13 y 2.03). Es una convención de redondeo, no un error de datos.
- El promedio (3.08 %), el cambio (3.20 puntos porcentuales), el máximo y el mínimo coinciden.

**Lo que hay que corregir:** el reporte dice que los promedios y extremos fueron "calculados por el propio servicio del BCRP", y que "el MCP del BCRP" los calculó. No es correcto: el BCRP publica las series, pero el promedio y el cambio los calculó nuestro servidor, con Python. Hay que cambiar esa frase antes de presentar el documento como trabajo verificado.

**Por qué es valioso como producto:** convierte cifras técnicas en una explicación que una persona sin formación económica puede seguir, sin perder la trazabilidad, porque cada cifra lleva su código de serie.

## 7. Pendientes

- Repetir la corrida de crédito para confirmar el acierto.
- Filtrar la búsqueda por frecuencia, para no devolver series anuales en preguntas mensuales.
- Corregir la frase de atribución en el reporte Word.
- ~~Comprobar dos cifras en la web del BCRP~~ **Hecho (28 oct 2026):** IPC de setiembre de 2026 (4.55 %) y crédito MN de mayo de 2026 (295 907 millones de soles) coinciden con la web. Los enlaces están en `informe.md`, sección 6.

## 8. Archivos de la entrega

`server.py`, `test_server.py` (sin cambios), `.mcp.json`, `preguntas.csv`, `resultados.csv`, `informe.md`, `grafico.png`, `grafico.py`, `evaluar.py`, `bitacora.md` e `informe_inflacion_bcrp.docx`. La carpeta `datos/` no se sube y el repositorio no contiene claves.
