from eurodata.sources.eurostat import dataset_id


def test_dataset_id_passthrough_without_suffix():
    assert dataset_id("isoc_ci_ac_i") == "isoc_ci_ac_i"
    assert dataset_id("prc_hicp_manr") == "prc_hicp_manr"


def test_dataset_id_strips_suffix():
    assert dataset_id("isoc_ci_ac_i#Y16_24") == "isoc_ci_ac_i"
