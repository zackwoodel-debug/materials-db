"""Dataset labels changed by a dataset release, and what each old label resolves to now.

v0.21.0 and v0.22.0 (docs/release-0.21.0-expected-diff.md, docs/release-0.22.0-expected-diff.md) moved "amorphous" out of
the polymorph slot: structure is written in the process-condition grammar (structure:amorphous) only on datasets whose own
evidence states it, and dropped where it is not stated.
Old labels keep working everywhere a label is looked up (the ModalFit exporter, the XRR stack syntax, the access layer) through
resolve(); every caller still requires the resolved label to exist, so a wrong or removed label still raises, never picks a row.
Keyed by formula: an alias applies only to the exact old label of that formula.
"""
from materials_db.pipeline.process_condition import format_process_condition

AMORPHOUS = format_process_condition(structure="amorphous")  # "structure:amorphous"

# (formula, old optical dataset_label) -> current label
OPTICAL = {
    ("SiO2", "amorphous | Malitson1965"): f"{AMORPHOUS} | Malitson1965",  # COMMENTS: "Fused silica, 20 C"
    ("Ta2O5", "amorphous | Bright2013"): f"{AMORPHOUS} | Bright2013",  # COMMENTS: "Amporphous thin film"
    ("GeO2", "Fleming1984"): f"{AMORPHOUS} | Fleming1984",  # catalog page: "Fleming 1984: Fused germania"
    ("Nb2O5", "amorphous | Franta2024"): "Franta2024",  # structure not stated (data/oxide_gaps.csv)
    ("SiO", "amorphous | Hass1954"): "Hass1954",  # structure not stated (data/oxide_gaps.csv)
    ("B", "amorphous | FernandezPerea2007"): "FernandezPerea2007",  # structure not stated ("Film deposited at room temperature")
    ("As2S3", "amorphous | Rodney1958"): f"{AMORPHOUS} | Rodney1958",  # v0.22.0; COMMENTS: "Arsenic trisulfide glass. 25 C"
}
# (formula, old polymorph prefix): the polymorph these materials had, which no label carries now (resolves to "no polymorph")
OLD_PREFIXES = {("Nb2O5", "amorphous"), ("SiO", "amorphous"), ("SiO2", "amorphous"), ("Ta2O5", "amorphous"), ("B", "amorphous"),
                ("As2S3", "amorphous")}


def resolve(formula, label):
    """The current label for an old one: a full old optical label -> its new label; an old polymorph prefix -> None (no
    polymorph); anything else is returned unchanged."""
    if label is None:
        return None
    if (formula, label) in OPTICAL:
        return OPTICAL[(formula, label)]
    if (formula, label) in OLD_PREFIXES:
        return None
    return label
