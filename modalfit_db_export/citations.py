"""
citations.py -- vendored optical-source citation table
=======================================================
The merged RESOLVED_OPTICAL_SOURCE_CITATION table that materials-db
assembles at import time from two per-batch material-list modules
(scripts/oxide_material_list.py and
scripts/fluoride_nitride_sulfide_material_list.py).

Vendored here as plain data because in materials-db those modules live
under scripts/ and are reached via a sys.path.insert -- a repo-layout
dependency that would not survive being dropped into another project.
The table is small and changes only when a new batch resolves a
previously-ambiguous optical source.

Keyed by FORMULA (not material name -- these are phase resolutions, and
a formula is what identifies the published dataset). export_layer()
merges each entry's verification_note into the optical citation it reads
from the DB's own `sources` table: the note records HOW the phase behind
a published n,k dataset was confirmed, which `sources` has no column for.

REGENERATE from a materials-db checkout (repo root) with:
    python3 -c "import sys; sys.path.insert(0, 'scripts'); \
import oxide_material_list as a, fluoride_nitride_sulfide_material_list as b; \
import pprint; pprint.pprint({**a.RESOLVED_OPTICAL_SOURCE_CITATION, \
**b.RESOLVED_OPTICAL_SOURCE_CITATION})"
"""

RESOLVED_OPTICAL_SOURCE_CITATION = {
    'As2S3': dict(
        doi=None,
        title='AMTIR-6 (As2S3) product datasheet',
        authors='Amorphous Materials, Inc.',
        journal=None,
        year=None,
        verification_note='Reuses the SiO2 quartz-vs-fused-silica '
                          "resolution verbatim. RI.info's 'Slavich' dataset "
                          '(biaxial alpha/beta/gamma) is necessarily '
                          'CRYSTALLINE (orpiment) since biaxial optics '
                          'require an ordered crystal -- switched default '
                          "to 'Rodney' (Rodney, Malitson, King 1958), whose "
                          "COMMENTS state 'Arsenic trisulfide glass. 25 C' "
                          'explicitly, meeting the same evidentiary bar as '
                          "Ta2O5's 'Amorphous thin film' COMMENTS. "
                          "Independently corroborated: 'Synowicki' (2004) "
                          "titles its dataset 'a-As2S3' (amorphous "
                          'notation), contrasted directly against '
                          "'c-ZrO2'/'c-MgO' in the SAME paper.",
    ),
    'HgS': dict(
        doi=None,
        title="Bond, W. L. et al. 1967 (RI.info page COMMENTS: 'alpha-HgS')",
        authors='Bond, W.L. et al.',
        journal=None,
        year=1967,
        verification_note="RI.info's own page name states the measured "
                          "phase directly: 'Bond et al. 1967: alpha-HgS' "
                          '(cinnabar). Cross-checked against MP (not just '
                          "trusted from the page name alone) -- MP's "
                          'lowest-energy_above_hull entry is metacinnabar '
                          '(F-43m #216, a DIFFERENT phase), so this needed '
                          'the same EXPECTED_SPACEGROUP override treatment '
                          'as CeF3/BN despite the RI.info metadata already '
                          'stating the correct phase name.',
    ),
    'Ta2O5': dict(
        doi='10.1063/1.4819325',
        title='Infrared optical properties of amorphous and nanocrystalline '
              'Ta2O5 thin films',
        authors='Bright, T.J.; Watjen, J.I.; Zhang, Z.M.; Muratore, C.; '
                'Voevodin, A.A.; Koukis, D.I.; Tanner, D.B.; Arenas, D.J.',
        journal='Journal of Applied Physics',
        year=2013,
        verification_note="RI.info's COMMENTS field for this dataset states "
                          '"Amorphous thin film" explicitly -- not a '
                          'crystalline phase name.',
    ),
    'TeO2': dict(
        doi='10.1103/PhysRevB.4.3736',
        title='Optical properties of single-crystal paratellurite (TeO2)',
        authors='Uchida, N.',
        journal='Physical Review B',
        year=1971,
        verification_note='Paper title explicitly names the measured phase: '
                          'paratellurite.',
    ),
    'VO2': dict(
        doi='10.1016/j.solmat.2019.110260',
        title='Thermochromic VO2-based smart radiator devices with ultralow '
              'refractive index cavities for increased performance',
        authors='Beaini, R.; Baloukas, B.; Loquai, S.; Klemberg-Sapieha, '
                'J.E.; Martinu, L.',
        journal='Solar Energy Materials and Solar Cells',
        year=2020,
        verification_note="70nm film measured at 25 C, below VO2's ~68 C "
                          'metal-insulator transition -- confirms '
                          'monoclinic M1 (insulating) phase.',
    ),
}
