import sys; sys.path.insert(0, ".")
from domain_lib import write_domain, DATA
from extractor.ingest import load_registry
from extractor.qualities import read_qualities
reg = load_registry(DATA)
recs = read_qualities(reg["corebook"]["pdf"], range(71, 79))
write_domain("qualities", recs, "corebook", ("cost", "gameEffect", "description"))
