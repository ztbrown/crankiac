import pytest

from app.transcription.corrections import (
    VOCABULARY_CORRECTIONS,
    PRESERVE_TERMS,
    get_corrections,
    get_preserve_terms,
    build_enhanced_prompt,
)


@pytest.mark.unit
def test_vocabulary_corrections_is_dict():
    """Test that VOCABULARY_CORRECTIONS is a dictionary."""
    assert isinstance(VOCABULARY_CORRECTIONS, dict)
    assert len(VOCABULARY_CORRECTIONS) > 0


@pytest.mark.unit
def test_vocabulary_corrections_contains_host_names():
    """Test that corrections include common host name mishearings."""
    # Matt Christman mishearings
    assert "christmas" in VOCABULARY_CORRECTIONS
    assert VOCABULARY_CORRECTIONS["christmas"] == "Christman"

    # Will Menaker mishearings
    assert "meneker" in VOCABULARY_CORRECTIONS
    assert VOCABULARY_CORRECTIONS["meneker"] == "Menaker"

    # Felix Biederman mishearings
    assert "beederman" in VOCABULARY_CORRECTIONS
    assert VOCABULARY_CORRECTIONS["beederman"] == "Biederman"


@pytest.mark.unit
def test_vocabulary_corrections_contains_show_terms():
    """Test that corrections include show-specific vocabulary."""
    # Chapo mishearings
    assert "chappeau" in VOCABULARY_CORRECTIONS
    assert VOCABULARY_CORRECTIONS["chappeau"] == "Chapo"

    assert "choppa" in VOCABULARY_CORRECTIONS
    assert VOCABULARY_CORRECTIONS["choppa"] == "Chapo"


@pytest.mark.unit
def test_vocabulary_corrections_contains_politician_names():
    """Test that corrections include commonly misheared politician names."""
    # Pete Buttigieg - famously misheared
    assert "buddha judge" in VOCABULARY_CORRECTIONS
    assert VOCABULARY_CORRECTIONS["buddha judge"] == "Buttigieg"

    assert "booty judge" in VOCABULARY_CORRECTIONS
    assert VOCABULARY_CORRECTIONS["booty judge"] == "Buttigieg"

    # Kamala Harris
    assert "comma la" in VOCABULARY_CORRECTIONS
    assert VOCABULARY_CORRECTIONS["comma la"] == "Kamala"


@pytest.mark.unit
def test_vocabulary_corrections_contains_political_terms():
    """Test that corrections include political terminology."""
    assert "neoliberal" in VOCABULARY_CORRECTIONS
    assert "bourgeoisie" in VOCABULARY_CORRECTIONS
    assert "proletariat" in VOCABULARY_CORRECTIONS


@pytest.mark.unit
def test_vocabulary_corrections_contains_organizations():
    """Test that corrections include organization abbreviations."""
    assert "dsa" in VOCABULARY_CORRECTIONS
    assert VOCABULARY_CORRECTIONS["dsa"] == "DSA"

    assert "qanon" in VOCABULARY_CORRECTIONS
    assert VOCABULARY_CORRECTIONS["qanon"] == "QAnon"

    assert "antifa" in VOCABULARY_CORRECTIONS
    assert VOCABULARY_CORRECTIONS["antifa"] == "antifa"


@pytest.mark.unit
def test_preserve_terms_is_set():
    """Test that PRESERVE_TERMS is a set."""
    assert isinstance(PRESERVE_TERMS, set)
    assert len(PRESERVE_TERMS) > 0


@pytest.mark.unit
def test_preserve_terms_contains_key_vocabulary():
    """Test that preserve terms include important vocabulary."""
    assert "Chapo" in PRESERVE_TERMS
    assert "DSA" in PRESERVE_TERMS
    assert "MAGA" in PRESERVE_TERMS
    assert "hellworld" in PRESERVE_TERMS


@pytest.mark.unit
def test_get_corrections_returns_copy():
    """Test that get_corrections returns a copy of the dictionary."""
    corrections1 = get_corrections()
    corrections2 = get_corrections()

    # Should be equal
    assert corrections1 == corrections2

    # But modifying one shouldn't affect the other
    corrections1["test_key"] = "test_value"
    assert "test_key" not in corrections2
    assert "test_key" not in VOCABULARY_CORRECTIONS


@pytest.mark.unit
def test_get_preserve_terms_returns_copy():
    """Test that get_preserve_terms returns a copy of the set."""
    terms1 = get_preserve_terms()
    terms2 = get_preserve_terms()

    # Should be equal
    assert terms1 == terms2

    # But modifying one shouldn't affect the other
    terms1.add("test_term")
    assert "test_term" not in terms2
    assert "test_term" not in PRESERVE_TERMS


@pytest.mark.unit
def test_build_enhanced_prompt_with_base():
    """Test building enhanced prompt with a base prompt."""
    base = "Test podcast"
    result = build_enhanced_prompt(base)

    assert result.startswith("Test podcast")
    assert "Key terms:" in result
    assert "Chapo Trap House" in result
    assert "Pete Buttigieg" in result
    assert "DSA" in result


@pytest.mark.unit
def test_build_enhanced_prompt_without_base():
    """Test building enhanced prompt without a base prompt."""
    result = build_enhanced_prompt()

    assert "Political podcast discussion" in result
    assert "Key terms:" in result
    assert "Matt Christman" in result
    assert "Will Menaker" in result


@pytest.mark.unit
def test_build_enhanced_prompt_empty_string():
    """Test building enhanced prompt with empty string base."""
    result = build_enhanced_prompt("")

    # Empty string is falsy, so should use default
    assert "Political podcast discussion" in result


@pytest.mark.unit
def test_corrections_keys_are_lowercase():
    """Test that all correction keys are lowercase for consistent matching."""
    for key in VOCABULARY_CORRECTIONS.keys():
        assert key == key.lower(), f"Key '{key}' should be lowercase"


@pytest.mark.unit
def test_corrections_values_are_strings():
    """Test that all correction values are strings."""
    for key, value in VOCABULARY_CORRECTIONS.items():
        assert isinstance(value, str), f"Value for '{key}' should be a string"


@pytest.mark.unit
def test_corrections_no_empty_values():
    """Test that no corrections have empty values."""
    for key, value in VOCABULARY_CORRECTIONS.items():
        assert value.strip() != "", f"Value for '{key}' should not be empty"
