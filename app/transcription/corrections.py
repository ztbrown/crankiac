"""
Vocabulary corrections dictionary for Whisper transcription post-processing.

This module provides corrections for common political terms, names, and
show-specific vocabulary that Whisper frequently mishears in the context
of Chapo Trap House podcast transcriptions.
"""

from typing import Dict, Set

# Corrections dictionary mapping common mishearings to correct spellings
# Format: {incorrect: correct}
# Case-insensitive matching is applied during correction

VOCABULARY_CORRECTIONS: Dict[str, str] = {
    # ===================
    # HOST NAMES
    # ===================
    # Matt Christman
    "christmas": "Christman",
    "christmans": "Christman's",
    "matthias": "Matt",
    "mathchristman": "Matt Christman",

    # Will Menaker
    "meneker": "Menaker",
    "moniker": "Menaker",
    "minaker": "Menaker",
    "will maker": "Will Menaker",

    # Felix Biederman
    "beederman": "Biederman",
    "bierderman": "Biederman",
    "beiderman": "Biederman",
    "biderman": "Biederman",
    "beaderman": "Biederman",

    # Amber A'Lee Frost
    "amber lee frost": "Amber A'Lee Frost",
    "amber ali frost": "Amber A'Lee Frost",
    "amberly frost": "Amber A'Lee Frost",

    # ===================
    # SHOW-SPECIFIC TERMS
    # ===================
    "chappeau": "Chapo",
    "choppa": "Chapo",
    "choppo": "Chapo",
    "cheapo": "Chapo",
    "chopo": "Chapo",
    "trap house": "Trap House",
    "traphouse": "Trap House",

    # Common show vocabulary
    "dirt bag left": "dirtbag left",
    "hell world": "hellworld",
    "fail son": "failson",
    "fail sons": "failsons",
    "hell yeah dude": "hell yeah dude",
    "posting": "posting",
    "poster": "poster",
    "extremely online": "extremely online",

    # ===================
    # POLITICAL FIGURES - US
    # ===================
    # Pete Buttigieg - commonly misheared
    "buddha judge": "Buttigieg",
    "booty judge": "Buttigieg",
    "boot edge edge": "Buttigieg",
    "bootyjudge": "Buttigieg",
    "buddhajudge": "Buttigieg",
    "pete buddha judge": "Pete Buttigieg",
    "pete booty judge": "Pete Buttigieg",
    "butt a gig": "Buttigieg",
    "butajig": "Buttigieg",
    "buttageg": "Buttigieg",
    "buttigig": "Buttigieg",

    # Bernie Sanders
    "bernie": "Bernie",
    "sanders": "Sanders",

    # Alexandria Ocasio-Cortez
    "aoc": "AOC",
    "a.o.c.": "AOC",
    "ocasio cortez": "Ocasio-Cortez",
    "ocasio-cortez": "Ocasio-Cortez",
    "alexandria ocasio cortez": "Alexandria Ocasio-Cortez",

    # Joe Biden
    "biden": "Biden",
    "joe biden": "Joe Biden",
    "bidens": "Biden's",

    # Donald Trump
    "trump": "Trump",
    "donald trump": "Donald Trump",
    "trumps": "Trump's",
    "trumpism": "Trumpism",

    # Kamala Harris
    "kamala": "Kamala",
    "comma la": "Kamala",
    "kamal a": "Kamala",
    "camel a": "Kamala",
    "kamala harris": "Kamala Harris",

    # Mitch McConnell
    "mcconnell": "McConnell",
    "mc connell": "McConnell",
    "mitchmcconnell": "Mitch McConnell",

    # Chuck Schumer
    "schumer": "Schumer",
    "shoomer": "Schumer",
    "shumer": "Schumer",

    # Nancy Pelosi
    "pelosi": "Pelosi",
    "pelossi": "Pelosi",

    # Ted Cruz
    "ted cruz": "Ted Cruz",
    "cruz": "Cruz",

    # Ron DeSantis
    "desantis": "DeSantis",
    "de santis": "DeSantis",
    "dessantis": "DeSantis",
    "ron desantis": "Ron DeSantis",

    # Joe Manchin
    "manchin": "Manchin",
    "mansion": "Manchin",
    "joe manchin": "Joe Manchin",

    # Kyrsten Sinema
    "sinema": "Sinema",
    "cinema": "Sinema",
    "kyrsten sinema": "Kyrsten Sinema",
    "kirsten sinema": "Kyrsten Sinema",

    # Other politicians
    "gavin newsom": "Gavin Newsom",
    "newsome": "Newsom",
    "deblasio": "de Blasio",
    "de blasio": "de Blasio",
    "rahm emanuel": "Rahm Emanuel",
    "emanuel": "Emanuel",
    "cory booker": "Cory Booker",
    "booker": "Booker",
    "elizabeth warren": "Elizabeth Warren",
    "warrens": "Warren's",
    "obamas": "Obama's",
    "clintons": "Clinton's",
    "hillary": "Hillary",
    "hilary": "Hillary",

    # ===================
    # POLITICAL FIGURES - INTERNATIONAL
    # ===================
    "bolsonaro": "Bolsonaro",
    "balsonaro": "Bolsonaro",
    "netanyahu": "Netanyahu",
    "net and yahoo": "Netanyahu",
    "putin": "Putin",
    "xi jinping": "Xi Jinping",
    "jinping": "Jinping",
    "erdogan": "Erdoğan",
    "orban": "Orbán",
    "viktor orban": "Viktor Orbán",
    "modi": "Modi",
    "boris johnson": "Boris Johnson",

    # ===================
    # POLITICAL TERMINOLOGY
    # ===================
    # Economic/Political theory
    "bourgeoisie": "bourgeoisie",
    "bourgeois": "bourgeois",
    "boorjwazee": "bourgeoisie",
    "bourgeoisy": "bourgeoisie",
    "proletariat": "proletariat",
    "prolotariat": "proletariat",
    "proletariot": "proletariat",
    "neoliberal": "neoliberal",
    "neo liberal": "neoliberal",
    "neo-liberal": "neoliberal",
    "neoliberalism": "neoliberalism",
    "means of production": "means of production",
    "capitalism": "capitalism",
    "capitalist": "capitalist",
    "marxism": "Marxism",
    "marxist": "Marxist",
    "marxists": "Marxists",
    "leninism": "Leninism",
    "leninist": "Leninist",
    "socialism": "socialism",
    "socialist": "socialist",
    "socialists": "socialists",
    "communism": "communism",
    "communist": "communist",
    "anarchism": "anarchism",
    "anarchist": "anarchist",
    "libertarian": "libertarian",

    # Organizations
    "dsa": "DSA",
    "d.s.a.": "DSA",
    "democratic socialists": "Democratic Socialists",
    "democratic socialists of america": "Democratic Socialists of America",
    "dnc": "DNC",
    "d.n.c.": "DNC",
    "rnc": "RNC",
    "r.n.c.": "RNC",
    "gop": "GOP",
    "g.o.p.": "GOP",
    "antifa": "antifa",
    "anti-fa": "antifa",
    "anti fa": "antifa",
    "black lives matter": "Black Lives Matter",
    "blm": "BLM",
    "b.l.m.": "BLM",
    "proud boys": "Proud Boys",
    "qanon": "QAnon",
    "q anon": "QAnon",
    "cue anon": "QAnon",

    # Policy terms
    "medicare for all": "Medicare for All",
    "m4a": "M4A",
    "green new deal": "Green New Deal",
    "maga": "MAGA",
    "m.a.g.a.": "MAGA",
    "make america great again": "Make America Great Again",
    "build the wall": "Build the Wall",
    "defund the police": "Defund the Police",
    "critical race theory": "critical race theory",
    "crt": "CRT",
    "c.r.t.": "CRT",
    "roe v wade": "Roe v. Wade",
    "roe vs wade": "Roe v. Wade",
    "citizens united": "Citizens United",
    "super pac": "super PAC",
    "super pacs": "super PACs",

    # ===================
    # MEDIA & PUBLICATIONS
    # ===================
    "new york times": "New York Times",
    "nyt": "NYT",
    "n.y.t.": "NYT",
    "washington post": "Washington Post",
    "wapo": "WaPo",
    "wall street journal": "Wall Street Journal",
    "wsj": "WSJ",
    "cnn": "CNN",
    "c.n.n.": "CNN",
    "msnbc": "MSNBC",
    "m.s.n.b.c.": "MSNBC",
    "fox news": "Fox News",
    "breitbart": "Breitbart",
    "jacobin": "Jacobin",
    "the intercept": "The Intercept",
    "current affairs": "Current Affairs",
    "vox": "Vox",
    "politico": "Politico",

    # ===================
    # COMMON POLITICAL PHRASES
    # ===================
    "both sides": "both sides",
    "bipartisan": "bipartisan",
    "bi-partisan": "bipartisan",
    "filibuster": "filibuster",
    "filabuster": "filibuster",
    "gerrymandering": "gerrymandering",
    "jerry mandering": "gerrymandering",
    "electoral college": "Electoral College",
    "swing state": "swing state",
    "swing states": "swing states",
    "blue wave": "blue wave",
    "red wave": "red wave",
    "midterms": "midterms",
    "mid terms": "midterms",
    "primary": "primary",
    "caucus": "caucus",
    "iowa caucus": "Iowa caucus",
    "new hampshire primary": "New Hampshire primary",
    "super tuesday": "Super Tuesday",
}

# Terms that should be preserved exactly as-is (case-sensitive)
# These are commonly used terms that Whisper might try to "correct"
PRESERVE_TERMS: Set[str] = {
    "Chapo",
    "Trap House",
    "dirtbag",
    "hellworld",
    "failson",
    "posting",
    "AOC",
    "DSA",
    "QAnon",
    "MAGA",
    "antifa",
    "M4A",
}


def get_corrections() -> Dict[str, str]:
    """
    Returns the vocabulary corrections dictionary.

    Returns:
        Dict mapping incorrect terms to their corrections.
    """
    return VOCABULARY_CORRECTIONS.copy()


def get_preserve_terms() -> Set[str]:
    """
    Returns the set of terms to preserve exactly.

    Returns:
        Set of terms that should not be altered.
    """
    return PRESERVE_TERMS.copy()


def build_enhanced_prompt(base_prompt: str = "") -> str:
    """
    Build an enhanced initial prompt for Whisper that includes key vocabulary.

    This can help Whisper recognize terms correctly during transcription
    rather than requiring post-processing corrections.

    Args:
        base_prompt: Base prompt to enhance. Defaults to empty string.

    Returns:
        Enhanced prompt with vocabulary hints.
    """
    # Key terms to include in the prompt for better recognition
    vocabulary_hints = [
        # Show context
        "Chapo Trap House podcast",
        "Matt Christman", "Will Menaker", "Felix Biederman",
        "Amber A'Lee Frost", "Virgil Texas",

        # Commonly discussed politicians
        "Bernie Sanders", "Pete Buttigieg", "AOC", "Alexandria Ocasio-Cortez",
        "Joe Biden", "Donald Trump", "Kamala Harris",
        "Mitch McConnell", "Chuck Schumer", "Nancy Pelosi",
        "Joe Manchin", "Kyrsten Sinema", "Ron DeSantis",

        # Political terminology
        "DSA", "Democratic Socialists", "neoliberal", "Medicare for All",
        "bourgeoisie", "proletariat", "MAGA", "QAnon", "antifa",
        "Green New Deal", "dirtbag left", "hellworld",
    ]

    hint_string = ", ".join(vocabulary_hints)

    if base_prompt:
        return f"{base_prompt} Key terms: {hint_string}."
    else:
        return f"Political podcast discussion. Key terms: {hint_string}."
