# 📅 PROYECTO-HORARIOS-V2
### Optimal Evaluation Meeting Slot Finder — Python / Flask

---

## 📌 What It Does

This application analyses a school timetable and finds the **optimal time slot** for an evaluation meeting, where **all teachers of a student group are simultaneously free**.

The optimum is defined lexicographically:

1. **Minimum total penalty** (sum of distances to nearest occupied session)
2. **Minimum worst individual penalty** (minimax fairness)
3. **Earliest slot** (chronological tie-breaker)

---

## 🗂 Project Structure

```
PROYECTO-HORARIOS-V2/
├── src/
│   ├── config.py          # Constants: sessions, recess, level rules
│   ├── horarios.py        # Index building & team extraction
│   ├── algoritmo.py       # Backtracking + Branch & Bound core
│   └── parser_csv.py      # CSV / JSON file parser & validator
├── web/
│   ├── static/style.css
│   └── templates/
│       ├── base.html
│       ├── index.html
│       ├── subir_pdf.html
│       ├── generar_horario.html
│       └── resultado.html
├── app.py
├── requirements.txt
└── README.md
```

---

## ⚙️ Installation

```bash
# 1. Clone / unzip the project
cd PROYECTO-HORARIOS-V2

# 2. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

---

## 🚀 Running the Application

```bash
python app.py
```

Then open your browser at: **http://localhost:5000**

---

## 📋 Input Data Format

Upload a **CSV** or **JSON** file.

### JSON format
```json
[
  { "profesor_id": "P1", "dia": 0, "hora": 2, "grupo": "2ESO-A", "tarea": "Clase" },
  { "profesor_id": "P1", "dia": 1, "hora": 5, "grupo": "2ESO-A", "tarea": "Clase" },
  { "profesor_id": "P2", "dia": 0, "hora": 3, "grupo": "2ESO-A", "tarea": "Clase" }
]
```

### CSV format
```
profesor_id,dia,hora,grupo,tarea
P1,0,2,2ESO-A,Clase
P1,1,5,2ESO-A,Clase
P2,0,3,2ESO-A,Clase
```

### Field Reference

| Field        | Type   | Description                              |
|--------------|--------|------------------------------------------|
| profesor_id  | string | Unique teacher identifier                |
| dia          | int    | 0 = Monday … 4 = Friday                  |
| hora         | int    | Session number (1–7)                     |
| grupo        | string | Student group e.g. `2ESO-A`             |
| tarea        | string | Activity label (e.g. `Clase`)            |
| aula         | string | Optional — classroom                     |

> **Rule:** if a teacher does NOT appear in a given slot → they are free that slot.

---

## 🧠 Algorithm Explained

### Penalty Model

For teacher **p** at candidate slot **(dia, hora)**:

- If p has occupied sessions on **dia**: `penalty = min(|occupied_hour − hora|)` for all occupied hours that day.
- If p has **no** sessions on **dia**: `penalty = 7`.

Binary search (`bisect`) is used to find the nearest occupied hour in **O(log n)**.

### Backtracking + Branch & Bound

```
for each candidate slot (dia, hora):
    for each teacher in team:
        compute penalty(teacher, dia, hora)
        running_sum  += penalty
        running_max   = max(running_max, penalty)

        PRUNE if:
            running_sum > best_total
            OR (running_sum == best_total AND running_max >= best_max)

    if slot survives pruning:
        compare lexicographically with current best
        update best if better
```

### Calendar

- Days: Monday–Friday (0–4)
- Sessions per day: 7
- Recess: configurable (`HORA_RECREO = 4` by default → skipped)
- Valid sessions: `[1, 2, 3, 5, 6, 7]`

---

## ⚙️ Configuration (`src/config.py`)

| Constant                   | Default | Description                                  |
|----------------------------|---------|----------------------------------------------|
| `HORA_RECREO`              | 4       | Session number excluded as recess            |
| `PERMITIR_SESION_7`        | True    | Whether session 7 is a valid meeting slot    |
| `PERMITIR_RECREO`          | False   | Whether recess can host a meeting            |
| `PERMITIR_HORAS_SIN_CLASE` | True    | Allow slots where teachers have no sessions  |
| `DIAS_EVALUACION`          | dict    | Max evaluation days per level (ESO/BACH/FP)  |

---

## 🧪 Running Tests

```bash
pytest src/tests/ -v
```

Tests cover:
- Penalty calculation
- Teacher with no sessions
- Recess exclusion
- Tie-breaking logic
- No-solution edge case

---

## 📤 Output Structure

```python
{
    "slot_optimo": (dia, hora),       # e.g. (0, 3) = Monday session 3
    "coste_total": 5,
    "peor_penalizacion": 3,
    "detalle_por_profesor": [
        {
            "profesor_id": "P1",
            "penalizacion": 2,
            "sesion_ocupada_mas_cercana": 5,
            "tiene_sesiones_ese_dia": True
        }
    ]
}
```

If no valid slot exists:
```python
{ "sin_solucion": True }
```

---

## 📦 Example Dataset

A built-in example dataset is available at the `/ejemplo` route, or you can find `ejemplo_horario.json` in the project root after first run.

---

## 👩‍💻 Tech Stack

- **Python 3.11+**
- **Flask 3.0** — web framework
- **bisect** — binary search for O(log n) penalty lookup
- **pytest** — test suite
