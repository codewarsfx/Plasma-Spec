from __future__ import annotations

import pytest

from app.databases.atomic import store


def test_catalog_loads_bundled_lines():
    summary = store.catalog_summary()
    assert summary["line_count"] >= 40
    assert summary["species_count"] >= 6
    assert summary["wavelength_min_nm"] is not None
    assert summary["wavelength_max_nm"] is not None
    assert summary["sources"].get("primary_source", "").startswith("NIST")


def test_search_returns_hbeta_within_tolerance():
    results = store.search_lines(near_nm=486.135, tolerance_nm=0.1, max_results=5)
    species = {item["species"] for item in results}
    assert "H I" in species
    hbeta = next(item for item in results if item["species"] == "H I")
    assert hbeta["transition"] == "Balmer beta"
    assert hbeta["boltzmann_ready"] is True


def test_species_filter_returns_subset():
    ar_results = store.search_lines(species="Ar I", max_results=200)
    assert len(ar_results) >= 5
    assert all(item["species"] == "Ar I" for item in ar_results)


def test_wavelength_range_filter():
    visible = store.search_lines(wavelength_min_nm=700.0, wavelength_max_nm=820.0, max_results=200)
    for line in visible:
        assert 700.0 <= line["wavelength_air_nm"] <= 820.0


def test_require_einstein_only_returns_boltzmann_ready():
    results = store.search_lines(require_einstein=True, max_results=200)
    for item in results:
        assert item.get("A_ki_s_1") is not None


def test_list_species_aggregates_counts():
    species = store.list_species()
    species_names = [item["species"] for item in species]
    assert "H I" in species_names
    assert "Ar I" in species_names
    h_entry = next(item for item in species if item["species"] == "H I")
    assert h_entry["line_count"] >= 5


def test_search_with_no_matches_returns_empty_list():
    # Regression: previously the search returned ghost rows (all-None payloads
    # with only delta_nm populated) when the near/tolerance filter selected zero
    # rows, because .assign(delta_nm=...) re-broadcast the full delta index.
    results = store.search_lines(near_nm=697.0, tolerance_nm=0.05, max_results=20)
    assert results == [] or all(item["wavelength_air_nm"] is not None for item in results)


def test_search_near_keeps_only_matching_rows():
    results = store.search_lines(near_nm=811.5, tolerance_nm=0.2, max_results=20)
    assert len(results) >= 1
    assert all(item["wavelength_air_nm"] is not None for item in results)
    assert all(item["delta_nm"] <= 0.2 + 1e-9 for item in results)


def test_user_overrides_are_merged_into_catalog(tmp_path, monkeypatch):
    """When user_overrides.csv exists, its rows show up in the catalog."""

    # Point the overrides CSV to a temp file so we don't pollute the repo
    fake_overrides = tmp_path / "user_overrides.csv"
    fake_overrides.write_text(
        "species,wavelength_air_nm,A_ki_s_1,acc_A,E_i_cm1,E_k_cm1,g_i,g_k,lower_term,upper_term,transition,source,notes\n"
        "Hg I,253.7,7.7e+08,A,0.0,39412.3,1,3,6s 1S,6p 3P*,Hg I 253.7,test,user override\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(store, "USER_OVERRIDE_CSV", fake_overrides)
    store.reset_cache()

    catalog = store.load_catalog()
    assert "Hg I" in set(catalog["species"].astype(str))
    summary = store.catalog_summary()
    assert summary["has_user_overrides"] is True
    store.reset_cache()


@pytest.fixture(autouse=True)
def reset_atomic_cache():
    store.reset_cache()
    yield
    store.reset_cache()
