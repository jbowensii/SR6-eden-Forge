"""Ingest adept powers from the corebook Magic chapter."""
from domain_lib import write_domain, DATA
import sys; sys.path.insert(0, ".")
from extractor.ingest import load_registry
from extractor.adept_powers import read_adept_powers

if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    reg = load_registry(DATA)
    recs = read_adept_powers(reg["corebook"]["pdf"], range(157, 161))
    write_domain("adept_powers", recs, "corebook", ("cost", "activation", "description"))
