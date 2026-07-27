import sys; sys.path.insert(0, ".")
from domain_lib import write_domain, DATA
from extractor.ingest import load_registry
from extractor.actors import read_actors
reg = load_registry(DATA)
recs = read_actors(reg["corebook"]["pdf"], range(82, 92), category="NPC")
write_domain("npcs", recs, "corebook",
             ("metatype", "activeSkills", "qualities", "gear", "weapons", "description"))
