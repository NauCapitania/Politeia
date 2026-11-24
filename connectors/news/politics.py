"""Shared editorial filter for the public news radar."""

import re
from collections.abc import Iterable
from urllib.parse import unquote, urlsplit

from connectors.base.protocol import normalize_name

POLITICS_TOPIC = "politica"
DOSSIER_TOPICS = {
    "impeachment_stf": ("impeachment", "impedimento de ministro", "crime de responsabilidade"),
    "stf": ("stf", "supremo", "moraes", "toffoli", "mendonca", "nunes marques", "fachin", "gilmar", "zanin",
            "dino", "fux", "carmen lucia", "cármen lúcia"),
    "caso_master": ("banco master", "vorcaro", "caso master", "compliance zero", "brb"),
    "presidencia_senado": ("presidencia do senado", "presidente do senado", "alcolumbre", "rogerio marinho",
                           "tereza cristina"),
    "pgr": ("pgr", "procuradoria-geral", "gonet"),
    "senado": ("senado", "senador", "senadora"),
}
POLITICAL_TOPICS = frozenset(DOSSIER_TOPICS) | {POLITICS_TOPIC}
POLITICAL_FEEDS = frozenset({
    "agencia_senado", "g1_politica", "folha_poder", "estadao_politica", "gazeta_republica",
    "agencia_brasil_politica", "cartacapital_politica",
})
POLITICAL_SECTIONS = frozenset({
    "politica", "politica-brasil", "poder", "republica", "eleicoes", "congresso", "legislativo",
    "poder-congresso", "poder-governo", "poder-eleicoes",
})
OTHER_SECTIONS = frozenset({
    "celebridades", "entretenimento", "esporte", "esportes", "fabia-oliveira", "famosos", "futebol", "games", "ge",
    "poder-sports-mkt", "realities", "reality-show", "televisao", "tv-e-famosos",
})
POLITICAL_TEXT = re.compile(
    r"\b(?:politica brasileira|politica nacional|reforma politica|crise politica|partidos? politicos?|"
    r"eleicao|eleicoes|eleitoral|eleitorais|urnas|urna eletronica|"
    r"senad[oa](?:r(?:a|es|as)?)?|deputad[oa]s?|parlamentar(?:es)?|legislativ[oa]s?|"
    r"camara dos deputados|congresso nacional|projeto de lei|emendas parlamentares|"
    r"stf|pgr|tse|cpi|cpmi|impeachment|supremo tribunal federal|procuradoria-geral da republica|"
    r"governo federal|congresso aprova|camara aprova|"
    r"presidente da republica|ministr[oa] d[aoe] [a-z]+|governador(?:a|es|as)?|"
    r"lula|bolsonaro|alcolumbre|caso master|operacao compliance zero)\b"
)


def _sections(url: str) -> set[str]:
    parsed = urlsplit(url)
    path = unquote(parsed.path)
    if parsed.hostname == "redir.folha.com.br" and "/*https://" in path:
        path = urlsplit(path.split("/*", 1)[1]).path
    segments = path.strip("/").split("/")
    return {normalize_name(section) for section in (segments[:-1] or segments)}


def topics_for(text: str) -> list[str]:
    key = normalize_name(text)
    return [t for t, words in DOSSIER_TOPICS.items() if any(re.search(rf"\b{re.escape(normalize_name(w))}\b", key)
                                                             for w in words)]


def is_political_news(url: str, title: str, excerpt: str | None, feed: str, *,
                      topics: Iterable[str] = (), categories: Iterable[str] = ()) -> bool:
    try:
        sections = _sections(url)
    except ValueError:
        return False
    sections.update(normalize_name(category).replace(" ", "-") for category in categories)
    if sections & OTHER_SECTIONS:
        return False
    return (
        bool(sections & POLITICAL_SECTIONS)
        or feed in POLITICAL_FEEDS
        or not POLITICAL_TOPICS.isdisjoint(topics)
        or POLITICAL_TEXT.search(normalize_name(f"{title} {excerpt or ''}")) is not None
    )
