from steam_updater import languages


def test_known_codes_map_to_descriptive_names():
    assert languages.language_name("brazilian") == "Brazilian Portuguese"
    assert languages.language_name("schinese") == "Simplified Chinese"
    assert languages.language_name("koreana") == "Korean"


def test_is_supported_is_case_insensitive():
    assert languages.is_supported("French")
    assert languages.is_supported("FRENCH")
    assert not languages.is_supported("klingon")


def test_unknown_code_falls_back_to_title_case():
    assert languages.language_name("some_new_lang") == "Some New Lang"


def test_normalize():
    assert languages.normalize("  French ") == "french"
