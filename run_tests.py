#!/usr/bin/env python3
"""Standalone test runner — no pytest needed."""
import sys, traceback
sys.path.insert(0, '.')

from src.config import (HORA_RECREO, SESIONES_VALIDAS, DIAS_VALIDOS,
                        SLOTS_CALENDARIO, PENALIZACION_DIA_LIBRE)
from src.algoritmo import calcular_penalizacion, find_best_meeting_slot
from src.horarios import build_indices, normalizar_entradas
from src.parser_csv import parsear_ejemplo

passed = failed = 0

def run(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✅  {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌  {name}: {e}")
        failed += 1

def ok(cond, msg="assertion failed"):
    if not cond: raise AssertionError(msg)

# ── shared fixture ────────────────────────────────────────────────────────────
def make_opd():
    raw = [
        {"profesor_id":"P1","dia":0,"hora":1,"grupo":"G","tarea":""},
        {"profesor_id":"P1","dia":0,"hora":2,"grupo":"G","tarea":""},
        {"profesor_id":"P1","dia":0,"hora":3,"grupo":"G","tarea":""},
        {"profesor_id":"P1","dia":1,"hora":1,"grupo":"G","tarea":""},
        {"profesor_id":"P1","dia":1,"hora":5,"grupo":"G","tarea":""},
        {"profesor_id":"P2","dia":0,"hora":5,"grupo":"G","tarea":""},
        {"profesor_id":"P2","dia":0,"hora":6,"grupo":"G","tarea":""},
        {"profesor_id":"P2","dia":2,"hora":2,"grupo":"G","tarea":""},
        {"profesor_id":"P2","dia":2,"hora":3,"grupo":"G","tarea":""},
    ]
    _, opd = build_indices(normalizar_entradas(raw))
    return opd

opd = make_opd()

print()
print("═"*60)
print("  TEST SUITE — PROYECTO-HORARIOS-V2")
print("═"*60)

# ── 1. Penalty calculation ────────────────────────────────────────────────────
print("\n1. PENALTY CALCULATION")
run("Right boundary  P2 Mon hora=7 → dist=1", lambda: ok(calcular_penalizacion("P2",0,7,opd)==1))
run("Left boundary   P2 Mon hora=1 → dist=4", lambda: ok(calcular_penalizacion("P2",0,1,opd)==4))
run("Exact distance  P2 Mon hora=2 → dist=3", lambda: ok(calcular_penalizacion("P2",0,2,opd)==3))
run("Self (occupied) P1 Mon hora=1 → dist=0", lambda: ok(calcular_penalizacion("P1",0,1,opd)==0))

# ── 2. No sessions ────────────────────────────────────────────────────────────
print("\n2. TEACHER WITH NO SESSIONS")
run("No sessions that day → DIA_LIBRE",  lambda: ok(calcular_penalizacion("P1",3,2,opd)==PENALIZACION_DIA_LIBRE))
run("Unknown teacher → DIA_LIBRE",       lambda: ok(calcular_penalizacion("GHOST",0,3,{})==PENALIZACION_DIA_LIBRE))

# ── 3. Recess exclusion ───────────────────────────────────────────────────────
print("\n3. RECESS EXCLUSION")
if HORA_RECREO is not None:
    run("Recess not in SLOTS_CALENDARIO",
        lambda: ok(all(h != HORA_RECREO for _,h in SLOTS_CALENDARIO)))

    def _rec_normalise():
        raw=[{"profesor_id":"P1","dia":0,"hora":HORA_RECREO,"grupo":"G1"},
             {"profesor_id":"P1","dia":0,"hora":1,            "grupo":"G1"}]
        r=normalizar_entradas(raw); horas=[e["hora"] for e in r]
        ok(HORA_RECREO not in horas); ok(1 in horas)
    run("Recess entries removed by normalizar", _rec_normalise)

    def _rec_result():
        raw=[{"profesor_id":"P1","dia":0,"hora":1,"grupo":"G1"},
             {"profesor_id":"P2","dia":0,"hora":1,"grupo":"G1"}]
        res=find_best_meeting_slot(raw,"G1")
        ok(res["slot_optimo"][1] != HORA_RECREO)
    run("Recess hour not in algorithm result", _rec_result)
else:
    print("  ⏭  Skipped (HORA_RECREO is None)")

# ── 4. Tie-breaking ───────────────────────────────────────────────────────────
print("\n4. TIE-BREAKING")
def _minimax():
    raw=[{"profesor_id":"P1","dia":0,"hora":1,"grupo":"G"},
         {"profesor_id":"P2","dia":0,"hora":7,"grupo":"G"}]
    res=find_best_meeting_slot(raw,"G")
    ok(not res.get("sin_solucion"))
    ok(res["peor_penalizacion"] <= 4, f"peor_pen={res['peor_penalizacion']} expected <=4")
run("Minimax: peor_penalizacion <= 4", _minimax)

def _chron():
    raw=[{"profesor_id":"P1","dia":0,"hora":5,"grupo":"G"},
         {"profesor_id":"P2","dia":0,"hora":5,"grupo":"G"}]
    res=find_best_meeting_slot(raw,"G")
    ok(not res.get("sin_solucion"))
    dia,hora=res["slot_optimo"]
    ok(dia==0, f"Expected Monday, got día={dia}")
run("Chronological: Monday preferred", _chron)

def _determ():
    raw=parsear_ejemplo()
    ok(find_best_meeting_slot(raw,"1BACH-B") == find_best_meeting_slot(raw,"1BACH-B"))
run("Result is deterministic", _determ)

# ── 5. No-solution ────────────────────────────────────────────────────────────
print("\n5. NO-SOLUTION CASES")
def _all_blocked():
    raw=[]
    for d in DIAS_VALIDOS:
        for h in SESIONES_VALIDAS:
            raw.append({"profesor_id":"P1","dia":d,"hora":h,"grupo":"G"})
    raw.append({"profesor_id":"P2","dia":0,"hora":1,"grupo":"G"})
    ok(find_best_meeting_slot(raw,"G").get("sin_solucion") is True)
run("All slots blocked → sin_solucion", _all_blocked)

run("Unknown group → sin_solucion",
    lambda: ok(find_best_meeting_slot(
        [{"profesor_id":"P1","dia":0,"hora":1,"grupo":"2ESO-A"}],"MISSING"
    ).get("sin_solucion") is True))

# ── 6. Integration ────────────────────────────────────────────────────────────
print("\n6. INTEGRATION")
def _struct():
    res=find_best_meeting_slot(parsear_ejemplo(),"2ESO-A")
    ok(not res.get("sin_solucion"))
    for key in ("slot_optimo","coste_total","peor_penalizacion","detalle_por_profesor"):
        ok(key in res, f"missing key {key}")
    d,h=res["slot_optimo"]; ok(d in DIAS_VALIDOS); ok(h in SESIONES_VALIDAS)
run("2ESO-A result has correct structure", _struct)

def _sanity():
    res=find_best_meeting_slot(parsear_ejemplo(),"2ESO-A")
    total=sum(d["penalizacion"] for d in res["detalle_por_profesor"])
    mx=max(d["penalizacion"] for d in res["detalle_por_profesor"])
    ok(total==res["coste_total"], f"total mismatch {total}!={res['coste_total']}")
    ok(mx==res["peor_penalizacion"], f"max mismatch {mx}!={res['peor_penalizacion']}")
run("Cost sanity: totals match detail", _sanity)

def _show():
    res=find_best_meeting_slot(parsear_ejemplo(),"2ESO-A")
    dias=["Lun","Mar","Mié","Jue","Vie"]
    d,h=res["slot_optimo"]
    print(f"\n  → Slot óptimo 2ESO-A: {dias[d]} sesión {h} | "
          f"coste={res['coste_total']} peor_pen={res['peor_penalizacion']}")
    for det in res["detalle_por_profesor"]:
        print(f"     {det['profesor_id']:4s} pen={det['penalizacion']} "
              f"cercana={det['sesion_ocupada_mas_cercana']} "
              f"tiene_sesiones={det['tiene_sesiones_ese_dia']}")
run("Print algorithm output", _show)

print()
print("═"*60)
print(f"  {passed} passed   {failed} failed")
print("═"*60)
sys.exit(1 if failed else 0)
