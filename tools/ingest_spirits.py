import sys; sys.path.insert(0, ".")
from domain_lib import write_domain, DATA
from extractor.ingest import load_registry
from extractor.spirits import read_spirits
reg = load_registry(DATA)
recs = read_spirits(reg["corebook"]["pdf"], range(147, 153))
write_domain("spirits", recs, "corebook", ("powers", "optionalPowers", "attacks", "description"))
