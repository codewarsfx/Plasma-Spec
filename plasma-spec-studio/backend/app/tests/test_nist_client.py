from __future__ import annotations

import pandas as pd

from app.databases.atomic import nist_client, store


NIST_HBETA_SAMPLE = """obs_wl_air(nm)\tunc_obs_wl\tritz_wl_air(nm)\tunc_ritz_wl\twn(cm-1)\tintens\tAki(s^-1)\tAcc\tEi(cm-1)\tEk(cm-1)\tconf_i\tterm_i\tJ_i\tconf_k\tterm_k\tJ_k\tg_i\tg_k\tType\ttp_ref\tline_ref\t
""\t""\t"486.1278624"\t"0.0000024"\t"20564.97514"\t""\t"1.7188e+07"\tAAA\t"82258.9191133"\t"102823.894250"\t"2p"\t"2P*"\t"1/2"\t"4d"\t"2D"\t"3/2"\t2\t4\t\t"T7771"\t""\t
"486.135"\t"0.005"\t"486.1333"\t"0.0003"\t"20564.67"\t"180000"\t"8.4193e+06"\tAAA\t"82259.158"\t"102823.904"\t"2"\t""\t""\t"4"\t""\t""\t8\t32\t\t"T8637"\t"L7439c30"\t
"""


def test_parse_nist_tsv_prefers_observed_then_ritz_wavelength():
    frame = nist_client.parse_nist_lines_tsv(NIST_HBETA_SAMPLE, species="H I")

    assert len(frame) == 2
    assert list(frame["species"]) == ["H I", "H I"]
    assert frame.iloc[0]["wavelength_air_nm"] == 486.1278624
    assert frame.iloc[0]["nist_wavelength_source"] == "ritz_wl_air(nm)"
    assert frame.iloc[1]["wavelength_air_nm"] == 486.135
    assert frame.iloc[1]["nist_wavelength_source"] == "obs_wl_air(nm)"
    assert frame.iloc[1]["A_ki_s_1"] == 8.4193e06
    assert frame.iloc[1]["g_k"] == 32
    assert frame.iloc[1]["source"] == "NIST ASD live refresh"


def test_parse_nist_tsv_leaves_missing_level_transition_blank():
    sample = """obs_wl_air(nm)\twn(cm-1)\tintens\tline_ref\t
"337.347"\t"29634.6"\t"7"\t"L3512"\t
"""

    frame = nist_client.parse_nist_lines_tsv(sample, species="Ar I")

    assert len(frame) == 1
    assert frame.iloc[0]["transition"] is None
    assert frame.iloc[0]["lower_term"] is None
    assert frame.iloc[0]["upper_term"] is None
    assert frame.iloc[0]["line_ref"] == "L3512"


def test_build_nist_query_uses_official_tab_delimited_form_shape():
    url = nist_client.build_nist_query_url(
        species="Ar I",
        wavelength_min_nm=690,
        wavelength_max_nm=850,
        require_transition_probabilities=True,
        page_size=500,
    )

    assert url.startswith(nist_client.NIST_LINES_ENDPOINT)
    assert "spectra=Ar+I" in url
    assert "format=3" in url
    assert "line_out=1" in url
    assert "show_obs_wl=1" in url
    assert "show_calc_wl=1" in url


def test_write_nist_live_lines_merges_into_catalog(tmp_path, monkeypatch):
    fake_live = tmp_path / "nist_live_lines.csv"
    lines = pd.DataFrame(
        [
            {
                "species": "Hg I",
                "wavelength_air_nm": 253.652,
                "A_ki_s_1": 7.7e08,
                "E_k_cm1": 39412.3,
                "g_k": 3,
                "transition": "Hg resonance",
                "source": "NIST ASD live refresh",
            }
        ]
    )
    monkeypatch.setattr(store, "NIST_LIVE_CSV", fake_live)
    store.reset_cache()

    saved = store.write_nist_live_lines(lines, mode="replace")
    catalog = store.load_catalog()
    summary = store.catalog_summary()

    assert saved["line_count"] == 1
    assert "Hg I" in set(catalog["species"].astype(str))
    assert summary["has_nist_live_cache"] is True
    assert summary["source_counts"]["nist_live"] == 1
    store.reset_cache()
