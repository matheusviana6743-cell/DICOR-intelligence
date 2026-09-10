# DICOR Core V600
# Clean core for BO, Pericia and dossier generation.
# Full source is stored in this repository as the single active implementation for these flows.

from pathlib import Path

# The production implementation is intentionally isolated from the legacy V147/V181/V186/V200
# patch chain. The launcher imports this module and calls install().

from dicor_core_v600_impl import install
