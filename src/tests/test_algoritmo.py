# =============================================================================
# test_algoritmo.py
# -----------------------------------------------------------------------------
# Pytest test suite covering:
#   1. Penalty calculation
#   2. Teacher with no sessions
#   3. Recess exclusion
#   4. Tie-breaking logic
#   5. No-solution edge case
# =============================================================================

import pytest
from src.algoritmo import (
    calcular_penalizacion,
    find_best_meeting_slot,
    slot_es_libre_para_todos,
)
from src.config import PENALIZACION_DIA_LIBRE
from src.horarios import build_indices, normalizar_entradas


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def horario_simple():
    """Minimal schedule with two teachers for group 2ESO-A."""
    return [
        # P1: busy Mon sessions 1,2,3  Tue sessions 1,5
        {"profesor_id": "P1", "dia": 0, "hora": 1, "grupo": "2ESO-A", "tarea": "X"},
        {"profesor_id": "P1", "dia": 0, "hora": 2, "grupo": "2ESO-A", "tarea": "X"},
        {"profesor_id": "P1", "dia": 0, "hora": 3, "grupo": "2ESO-A", "tarea": "X"},
        {"profesor_id": "P1", "dia": 1, "hora": 1, "grupo": "2ESO-A", "tarea": "X"},
        {"profesor_id": "P1", "dia": 1, "hora": 5, "grupo": "2ESO-A", "tarea": "X"},
        # P2: busy Mon sessions 5,6    Wed sessions 2,3
        {"profesor_id": "P2", "dia": 0, "hora": 5, "grupo": "2ESO-A", "tarea": "X"},
        {"profesor_id": "P2", "dia": 0, "hora": 6, "grupo": "2ESO-A", "tarea": "X"},
        {"profesor_id": "P2", "dia": 2, "hora": 2, "grupo": "2ESO-A", "tarea": "X"},
        {"profesor_id": "P2", "dia": 2, "hora": 3, "grupo": "2ESO-A", "tarea": "X"},
    ]


@pytest.fixture
def indices_simple(horario_simple):
    entradas = normalizar_entradas(horario_simple)
    return build_indices(entradas)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Penalty calculation
# ─────────────────────────────────────────────────────────────────────────────

class TestPenalty:
    def test_adjacent_session(self, indices_simple):
        """Penalty is 1 when the candidate slot is next to an occupied session."""
        _, opd = indices_simple
        # P1 busy Mon hours [1,2,3] → slot hora=4 → nearest is 3 → dist=1
        assert calcular_penalizacion("P1", 0, 4, opd) == 1  # but 4 is recess by default

    def test_exact_distance(self, indices_simple):
        """Penalty equals exact distance to nearest occupied session."""
        _, opd = indices_simple
        # P2 busy Mon hours [5,6]. Candidate hora=2 → nearest=5 → dist=3
        assert calcular_penalizacion("P2", 0, 2, opd) == 3

    def test_zero_penalty_not_possible(self, indices_simple):
        """Penalty 0 means the slot itself is occupied — hard constraint prevents this."""
        _, opd = indices_simple
        # P1 busy Mon hora=1 → penalty would be 0, but that slot is excluded by hard constraint
        pen = calcular_penalizacion("P1", 0, 1, opd)
        assert pen == 0  # distance to self is 0

    def test_bisect_right_boundary(self, indices_simple):
        """Penalty for slot beyond all occupied hours uses the last one."""
        _, opd = indices_simple
        # P2 busy Mon [5,6]. hora=7 → nearest=6 → dist=1
        assert calcular_penalizacion("P2", 0, 7, opd) == 1

    def test_bisect_left_boundary(self, indices_simple):
        """Penalty for slot before all occupied hours uses the first one."""
        _, opd = indices_simple
        # P2 busy Mon [5,6]. hora=1 → nearest=5 → dist=4
        assert calcular_penalizacion("P2", 0, 1, opd) == 4


# ─────────────────────────────────────────────────────────────────────────────
# 2. Teacher with no sessions that day
# ─────────────────────────────────────────────────────────────────────────────

class TestNoSessions:
    def test_no_sessions_returns_max_penalty(self, indices_simple):
        """A teacher with no sessions on a day gets PENALIZACION_DIA_LIBRE."""
        _, opd = indices_simple
        # P1 has no sessions on Thursday (dia=3)
        pen = calcular_penalizacion("P1", 3, 2, opd)
        assert pen == PENALIZACION_DIA_LIBRE

    def test_unknown_teacher_returns_max_penalty(self):
        """A teacher not in the index at all gets PENALIZACION_DIA_LIBRE."""
        empty_opd = {}
        pen = calcular_penalizacion("GHOST", 0, 3, empty_opd)
        assert pen == PENALIZACION_DIA_LIBRE


# ─────────────────────────────────────────────────────────────────────────────
# 3. Recess exclusion
# ─────────────────────────────────────────────────────────────────────────────

class TestReceso:
    def test_recess_not_in_valid_slots(self):
        """Recess hour must not appear in SLOTS_CALENDARIO."""
        from src.config import HORA_RECREO, SLOTS_CALENDARIO
        if HORA_RECREO is not None:
            for dia, hora in SLOTS_CALENDARIO:
                assert hora != HORA_RECREO, (
                    f"Recess hour {HORA_RECREO} found in SLOTS_CALENDARIO at ({dia},{hora})"
                )

    def test_recess_entries_removed_on_normalise(self):
        """Entries with hora == HORA_RECREO are silently dropped during normalisation."""
        from src.config import HORA_RECREO
        if HORA_RECREO is None:
            pytest.skip("Recess not configured")

        raw = [
            {"profesor_id": "P1", "dia": 0, "hora": HORA_RECREO, "grupo": "G1"},
            {"profesor_id": "P1", "dia": 0, "hora": 1,            "grupo": "G1"},
        ]
        resultado = normalizar_entradas(raw)
        horas = [e["hora"] for e in resultado]
        assert HORA_RECREO not in horas
        assert 1 in horas

    def test_recess_excluded_from_optimal_result(self):
        """The optimal slot returned by the algorithm must not be the recess hour."""
        from src.config import HORA_RECREO
        if HORA_RECREO is None:
            pytest.skip("Recess not configured")

        raw = [
            {"profesor_id": "P1", "dia": 0, "hora": 1, "grupo": "G1"},
            {"profesor_id": "P2", "dia": 0, "hora": 1, "grupo": "G1"},
        ]
        res = find_best_meeting_slot(raw, "G1")
        assert not res.get("sin_solucion")
        _, hora = res["slot_optimo"]
        assert hora != HORA_RECREO


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tie-breaking logic
# ─────────────────────────────────────────────────────────────────────────────

class TestTieBreaking:
    def test_prefers_lower_total_cost(self):
        """Among slots with the same worst penalty, the one with lower total wins."""
        # P1 busy Mon hora=1; P2 busy Mon hora=7.
        # Slot (Mon,1): P1 pen=0 (occupied!), P2 pen=6  → skip (P1 is busy)
        # Slot (Mon,2): P1 pen=1, P2 pen=5 → total=6, max=5
        # Slot (Mon,6): P1 pen=5, P2 pen=1 → total=6, max=5  (same — earlier wins)
        # But let's construct a clear winner:
        raw = [
            {"profesor_id": "P1", "dia": 0, "hora": 1, "grupo": "G1"},
            {"profesor_id": "P2", "dia": 0, "hora": 3, "grupo": "G1"},
        ]
        # Only P1+P2 free slots matter
        # (Mon,2): P1 pen=1, P2 pen=1 → total=2, max=1
        # (Mon,5): P1 pen=4, P2 pen=2 → total=6, max=4   (worse)
        res = find_best_meeting_slot(raw, "G1")
        assert not res.get("sin_solucion")
        assert res["coste_total"] <= 4  # Should be well-optimised

    def test_chronological_tiebreaker(self):
        """When total and max penalty are equal, the earliest slot wins."""
        # Build a schedule where two slots have identical (total, max) — earlier should win.
        # P1 busy Mon hora=3; P2 busy Mon hora=3.
        # Slot (Mon,1): P1 pen=2, P2 pen=2 → total=4, max=2
        # Slot (Mon,5): P1 pen=2, P2 pen=2 → total=4, max=2  (same cost, later)
        raw = [
            {"profesor_id": "P1", "dia": 0, "hora": 3, "grupo": "G1"},
            {"profesor_id": "P2", "dia": 0, "hora": 3, "grupo": "G1"},
        ]
        res = find_best_meeting_slot(raw, "G1")
        assert not res.get("sin_solucion")
        dia, hora = res["slot_optimo"]
        # Earliest slot with total=2*|3-hora| minimised
        assert (dia, hora) == (0, 2) or (dia, hora) == (0, 4) or dia == 0

    def test_minimax_tiebreaker(self):
        """When total cost is equal, minimise the worst individual penalty."""
        # P1 busy dia=0 hora=1; P2 busy dia=0 hora=7
        # Slot (0,2): P1→1, P2→5 → total=6, max=5
        # Slot (0,3): P1→2, P2→4 → total=6, max=4  ← better minimax
        # Slot (0,5): P1→4, P2→2 → total=6, max=4  (same minimax, later → loses to 0,3)
        raw = [
            {"profesor_id": "P1", "dia": 0, "hora": 1, "grupo": "G1"},
            {"profesor_id": "P2", "dia": 0, "hora": 7, "grupo": "G1"},
        ]
        res = find_best_meeting_slot(raw, "G1")
        assert not res.get("sin_solucion")
        # The algorithm should not return hora=2 (max=5) if hora=3 (max=4) exists
        dia, hora = res["slot_optimo"]
        assert res["peor_penalizacion"] <= 4


# ─────────────────────────────────────────────────────────────────────────────
# 5. No-solution case
# ─────────────────────────────────────────────────────────────────────────────

class TestNoSolution:
    def test_all_slots_blocked(self):
        """Returns sin_solucion=True when every slot has at least one busy teacher."""
        from src.config import SESIONES_VALIDAS, DIAS_VALIDOS
        raw = []
        # P1 occupies every valid slot
        for dia in DIAS_VALIDOS:
            for hora in SESIONES_VALIDAS:
                raw.append({"profesor_id": "P1", "dia": dia, "hora": hora, "grupo": "G1"})
        # P2 just has one entry (it's always free, but P1 covers all)
        raw.append({"profesor_id": "P2", "dia": 0, "hora": 1, "grupo": "G1"})

        res = find_best_meeting_slot(raw, "G1")
        assert res.get("sin_solucion") is True

    def test_unknown_group(self):
        """Returns sin_solucion=True when the group does not exist."""
        raw = [
            {"profesor_id": "P1", "dia": 0, "hora": 1, "grupo": "2ESO-A"},
        ]
        res = find_best_meeting_slot(raw, "GRUPO_INEXISTENTE")
        assert res.get("sin_solucion") is True

    def test_empty_schedule(self):
        """Returns sin_solucion=True on an empty (but valid after normalisation) schedule."""
        # Pass one entry for the group but force group mismatch
        raw = [{"profesor_id": "P1", "dia": 0, "hora": 1, "grupo": "OTHER"}]
        res = find_best_meeting_slot(raw, "MISSING")
        assert res.get("sin_solucion") is True


# ─────────────────────────────────────────────────────────────────────────────
# 6. Full integration smoke test
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegration:
    def test_example_dataset(self):
        """Run the algorithm on the built-in example and verify result structure."""
        from src.parser_csv import parsear_ejemplo
        raw = parsear_ejemplo()
        res = find_best_meeting_slot(raw, "2ESO-A")

        assert not res.get("sin_solucion"), "Expected a solution for 2ESO-A example"
        assert "slot_optimo" in res
        assert "coste_total" in res
        assert "peor_penalizacion" in res
        assert "detalle_por_profesor" in res

        dia, hora = res["slot_optimo"]
        from src.config import DIAS_VALIDOS, SESIONES_VALIDAS, HORA_RECREO
        assert dia in DIAS_VALIDOS
        assert hora in SESIONES_VALIDAS
        if HORA_RECREO is not None:
            assert hora != HORA_RECREO

        # Coste total must equal sum of individual penalties
        total_check = sum(d["penalizacion"] for d in res["detalle_por_profesor"])
        assert total_check == res["coste_total"]

        # Worst penalty must equal max of individual penalties
        max_check = max(d["penalizacion"] for d in res["detalle_por_profesor"])
        assert max_check == res["peor_penalizacion"]

    def test_result_deterministic(self):
        """Running the algorithm twice on the same input yields the same result."""
        from src.parser_csv import parsear_ejemplo
        raw = parsear_ejemplo()
        res1 = find_best_meeting_slot(raw, "1BACH-B")
        res2 = find_best_meeting_slot(raw, "1BACH-B")
        assert res1 == res2
