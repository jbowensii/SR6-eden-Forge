import sys; sys.path.insert(0, ".")
from domain_lib import write_domain, DATA
from extractor.ingest import load_registry
from extractor.qualities import read_qualities
if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    reg = load_registry(DATA)
    recs = read_qualities(reg["corebook"]["pdf"], range(71, 79))
    write_domain("qualities", recs, "corebook", ("cost", "gameEffect", "description"))
