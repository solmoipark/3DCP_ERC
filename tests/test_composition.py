"""Unit tests for the composition normaliser on synthetic component rows."""
from __future__ import annotations

import pandas as pd
import pytest

from pmpredict.composition import normalize_mix


def rows(*items):
    cols = ["material_uid", "role", "material_class", "dosage_reported", "unit_reported", "basis_reported",
            "dosage_raw", "solid_content", "density_solution"]
    data = []
    for i, it in enumerate(items):
        d = dict(material_uid=f"m{i}", dosage_raw=None, solid_content=None, density_solution=None)
        d.update(it)
        data.append(d)
    return pd.DataFrame(data, columns=cols)


def mix(**kw):
    base = dict(mix_uid="t::M1", paper_uid="t", system_type="mortar", w_b_reported=None, sand_binder_ratio=None,
                sand_binder_basis=None, fresh_density_kg_m3=None, binder_total_kg_m3=None, curing_regime=None,
                curing_temp_C=None, curing_rh_pct=None)
    base.update(kw)
    return pd.Series(base)


def test_abs_kg_m3():
    r = rows(dict(role="binder", material_class="portland_cement", dosage_reported=400, unit_reported="kg/m3", basis_reported="kg_m3"),
             dict(role="scm", material_class="fly_ash_class_F", dosage_reported=100, unit_reported="kg/m3", basis_reported="kg_m3"),
             dict(role="water", material_class="water", dosage_reported=200, unit_reported="kg/m3", basis_reported="kg_m3"),
             dict(role="fine_aggregate", material_class="natural_sand", dosage_reported=1000, unit_reported="kg/m3", basis_reported="kg_m3"),
             dict(role="admixture", material_class="superplasticiser_pce", dosage_reported=5, unit_reported="kg/m3", basis_reported="kg_m3"))
    c = normalize_mix(r, mix())
    assert c.mode == "abs"
    assert c.powder == pytest.approx({"opc": 0.8, "fly_ash_f": 0.2})
    assert c.water_b == pytest.approx(0.4) and c.water_b_source == "computed"
    assert c.sand_b == pytest.approx(2.0)
    assert c.admix_pct["sp_pce"] == pytest.approx(1.0)
    assert c.admix_solid_pct["sp_pce"] == pytest.approx(0.3)      # 30 % solids default
    assert c.cement_share == pytest.approx(0.8)


def test_rel_pct_binder_with_reported_wb_fallback():
    r = rows(dict(role="binder", material_class="portland_cement", dosage_reported=70, unit_reported="%", basis_reported="pct_binder_mass"),
             dict(role="scm", material_class="ggbfs", dosage_reported=30, unit_reported="%", basis_reported="pct_binder_mass"))
    c = normalize_mix(r, mix(w_b_reported=0.45))
    assert c.mode == "rel"
    assert c.powder == pytest.approx({"opc": 0.7, "ggbfs": 0.3})
    assert c.water_b == pytest.approx(0.45) and c.water_b_source == "reported"


def test_parts_with_ratio_reinterpretation():
    r = rows(dict(role="binder", material_class="portland_cement", dosage_reported=100, unit_reported="pct", basis_reported="mass_parts"),
             dict(role="fine_aggregate", material_class="natural_sand", dosage_reported=3.0, unit_reported="ratio", basis_reported="mass_parts"),
             dict(role="water", material_class="water", dosage_reported=0.5, unit_reported="ratio", basis_reported="mass_parts"))
    c = normalize_mix(r, mix())
    assert c.mode == "parts"
    assert c.water_b == pytest.approx(0.5)
    assert c.sand_b == pytest.approx(3.0)
    assert "parts_ratio_reinterpreted" in c.flags


def test_relc_primary_all_relative_to_cement():
    r = rows(dict(role="binder", material_class="white_cement", dosage_reported=100, unit_reported="wt%", basis_reported="pct_cement_mass"),
             dict(role="admixture", material_class="vma_cellulose", dosage_reported=0.25, unit_reported="wt%", basis_reported="pct_cement_mass"),
             dict(role="water", material_class="water", dosage_reported=35, unit_reported="wt%", basis_reported="pct_cement_mass"))
    c = normalize_mix(r, mix(system_type="paste"))
    assert c.ok and "relc_primary" in c.flags
    assert c.powder == pytest.approx({"opc": 1.0})
    assert c.water_b == pytest.approx(0.35)
    assert c.admix_pct["vma"] == pytest.approx(0.25)


def test_molarity_row_not_summed_and_duplicates():
    r = rows(dict(material_uid="fa", role="binder", material_class="fly_ash_class_F", dosage_reported=1000, unit_reported="kg/m3", basis_reported="kg_m3"),
             dict(material_uid="naoh", role="activator", material_class="sodium_hydroxide", dosage_reported=100, unit_reported="kg/m3", basis_reported="kg_m3"),
             dict(material_uid="naoh", role="activator", material_class="sodium_hydroxide", dosage_reported=10, unit_reported="mol/L", basis_reported="molarity"),
             dict(material_uid="w", role="water", material_class="water", dosage_reported=250, unit_reported="kg/m3", basis_reported="kg_m3"),
             dict(material_uid="w", role="water", material_class="water", dosage_reported=50, unit_reported="kg/m3", basis_reported="kg_m3"))
    c = normalize_mix(r, mix(system_type="paste"))
    assert c.activator_b["naoh"] == pytest.approx(0.1)
    assert c.activator_molarity["naoh"] == 10
    assert c.water_b == pytest.approx(0.3) and "dup_material_summed" in c.flags
    assert "cement_share_proxy" in c.flags


def test_null_basis_inferred_and_unparsed_water_falls_back():
    r = rows(dict(role="binder", material_class="portland_cement", dosage_reported=450, unit_reported="kg/m3", basis_reported=None),
             dict(role="water", material_class="water", dosage_reported=None, unit_reported=None, basis_reported=None),
             dict(role="fine_aggregate", material_class="standard_sand", dosage_reported=1350, unit_reported="kg/m3", basis_reported=None))
    c = normalize_mix(r, mix(w_b_reported=0.5))
    assert c.ok and c.mode == "abs" and "basis_inferred" in c.flags
    assert c.water_b == pytest.approx(0.5) and c.water_b_source == "reported"
    assert c.sand_b == pytest.approx(3.0)


def test_fibre_volume_and_mass_cross_conversion():
    r = rows(dict(role="binder", material_class="portland_cement", dosage_reported=800, unit_reported="kg/m3", basis_reported="kg_m3"),
             dict(role="water", material_class="water", dosage_reported=200, unit_reported="kg/m3", basis_reported="kg_m3"),
             dict(role="fibre", material_class="steel_fibre", dosage_reported=2.0, unit_reported="vol%", basis_reported="pct_binder_volume"))
    c = normalize_mix(r, mix(system_type="paste", binder_total_kg_m3=800))
    assert c.fibre_vol_pct["steel"] == 2.0
    # 2 vol% steel = 0.02*7850 = 157 kg/m3 -> /800 kg binder
    assert c.fibre_mass_b["steel"] == pytest.approx(157 / 800, rel=1e-3)


def test_failures():
    assert not normalize_mix(rows(dict(role="water", material_class="water", dosage_reported=1, unit_reported="ratio", basis_reported="ratio_to_binder")), mix()).ok
    r = rows(dict(role="binder", material_class="portland_cement", dosage_reported=None, unit_reported="kg/m3", basis_reported="kg_m3"))
    c = normalize_mix(r, mix())
    assert not c.ok and "failed:unparsed_major_dose" in c.flags
