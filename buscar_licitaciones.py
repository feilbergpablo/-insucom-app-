"""
INSUCOM - Búsqueda automática diaria de licitaciones
Ejecutado por GitHub Actions cada día a las 8am (Argentina)
Guarda resultados en resultados.json para que el index.html los muestre al abrir
"""

import anthropic
import json
import os
import sys
from datetime import datetime

# API key viene del secret de GitHub Actions
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    print("ERROR: ANTHROPIC_API_KEY no está configurado")
    sys.exit(1)

client = anthropic.Anthropic(api_key=api_key)

TERMINOS = [
    "librería papelería artículos oficina",
    "tóner impresora cartuchos",
    "notebook computadora equipos informáticos",
    "mobiliario oficina sillas escritorios",
    "útiles escolares oficina insumos",
]

hoy = datetime.now().strftime("%d/%m/%Y")

SYSTEM = f"""Sos un experto en licitaciones públicas argentinas. Hoy es {hoy}.

Tu tarea es buscar en comprar.gob.ar y boletinoficial.gob.ar licitaciones que AÚN ESTÁN ABIERTAS.

REGLAS ESTRICTAS:
1. Solo incluí licitaciones cuya fecha de apertura de ofertas sea POSTERIOR a {hoy}.
2. EXCLUÍ cualquier proceso con estado "apertura pasada", "en evaluación", "adjudicado", "finalizado", "sin efecto", "desierta".
3. Si no encontrás procesos con apertura futura, devolvé resultados vacíos.
4. Priorizá procesos publicados en los últimos 30 días.

Devolvé SOLO JSON válido, sin texto extra:
{{"resultados":[{{"numero":"...","nombre":"...","tipo":"...","apertura":"...","estado":"...","organismo":"...","link":"...","fuente":"..."}}],"resumen":"...","total":0}}"""


def buscar_termino(termino):
    """Busca licitaciones para un término y retorna lista de resultados"""
    messages = [{
        "role": "user",
        "content": f"Fecha de hoy: {hoy}. Buscá en comprar.gob.ar y boletinoficial.gob.ar licitaciones con apertura POSTERIOR a {hoy} relacionadas con: {termino}. Solo apertura futura. Devolvé JSON."
    }]

    def post(msgs):
        return client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=SYSTEM,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=msgs
        )

    response = post(messages)

    ciclos = 0
    while response.stop_reason == "tool_use" and ciclos < 5:
        ciclos += 1
        # Convertir bloques de contenido a dicts para la API
        content_dicts = []
        for block in response.content:
            if block.type == "text":
                content_dicts.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content_dicts.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })

        messages.append({"role": "assistant", "content": content_dicts})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Búsqueda completada. Solo incluir resultados con apertura posterior a {hoy}."
                })

        if not tool_results:
            break

        messages.append({"role": "user", "content": tool_results})
        response = post(messages)

    texto = "".join(
        block.text for block in response.content if block.type == "text"
    )

    ini = texto.find("{")
    fin = texto.rfind("}") + 1
    if ini < 0:
        print(f"  Sin JSON para: {termino}")
        return []

    try:
        data = json.loads(texto[ini:fin])
        resultados = data.get("resultados", [])
        print(f"  '{termino}': {len(resultados)} licitaciones encontradas")
        return resultados
    except json.JSONDecodeError as e:
        print(f"  Error JSON para '{termino}': {e}")
        return []


def main():
    print(f"=== INSUCOM - Búsqueda automática {hoy} ===")
    todos = []

    for termino in TERMINOS:
        print(f"Buscando: {termino}...")
        try:
            resultados = buscar_termino(termino)
            todos.extend(resultados)
        except Exception as e:
            print(f"  Error en '{termino}': {e}")

    # Deduplicar por número de licitación
    seen = set()
    unique = []
    for r in todos:
        key = (r.get("numero", "") + "|" + r.get("nombre", "")[:30]).strip("|")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)

    # Guardar resultados
    output = {
        "resultados": unique,
        "total": len(unique),
        "ultima_actualizacion": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fecha_busqueda": hoy,
        "resumen": f"Búsqueda automática del {hoy}. Se encontraron {len(unique)} licitaciones con apertura futura."
    }

    with open("resultados.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Guardadas {len(unique)} licitaciones en resultados.json")


if __name__ == "__main__":
    main()
