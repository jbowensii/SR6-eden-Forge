"""Ingest toxins and drugs (corebook Toxins and Drugs section)."""
import sys; sys.path.insert(0, ".")
from domain_lib import write_domain, DATA
from extractor.ingest import load_registry
from extractor.toxins_drugs import read_toxins_drugs

reg = load_registry(DATA)
recs = read_toxins_drugs(reg["corebook"]["pdf"], range(123, 128))
BASE = ("vector", "speed", "duration", "effect", "description")
write_domain("toxins", [r for r in recs if r["system"]["category"] == "TOXIN"], "corebook", BASE + ("power",))
write_domain("drugs", [r for r in recs if r["system"]["category"] == "DRUG"], "corebook", BASE + ("addictionRating", "addictionType"))
