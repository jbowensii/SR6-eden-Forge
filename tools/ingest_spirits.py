import sys; sys.path.insert(0, ".")
from domain_lib import write_domain, DATA
from extractor.ingest import load_registry
from extractor.spirits import read_spirits
if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    reg = load_registry(DATA)
    recs = read_spirits(reg["corebook"]["pdf"], range(147, 153))
    write_domain("spirits", recs, "corebook", ("powers", "optionalPowers", "attacks", "description"))
