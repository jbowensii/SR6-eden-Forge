import sys; sys.path.insert(0, ".")
from domain_lib import write_domain, DATA
from extractor.ingest import load_registry
from extractor.critters import read_critters
reg = load_registry(DATA)
recs = read_critters(reg["corebook"]["pdf"], range(216, 222))
write_domain("critters", recs, "corebook", ("skills", "powers", "movement", "description"))
