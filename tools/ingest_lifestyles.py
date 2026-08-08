import sys; sys.path.insert(0, ".")
from domain_lib import write_domain, DATA
from extractor.ingest import load_registry
from extractor.lifestyles import read_lifestyles
if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    reg = load_registry(DATA)
    recs = read_lifestyles(reg["corebook"]["pdf"], range(57, 60))
    write_domain("lifestyles", recs, "corebook", ("cost", "description"))
