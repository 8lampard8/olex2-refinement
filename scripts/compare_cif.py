"""Compare two CIF summaries and their paired FCF Miller-index populations."""
import argparse
import sys
from collections import Counter
from pathlib import Path

import gemmi


FIELDS = [
    ("Space group", "_space_group_name_H-M_alt"),
    ("Formula", "_chemical_formula_sum"),
    ("R1 observed", "_refine_ls_R_factor_gt"),
    ("Observed threshold", "_reflns_threshold_expression"),
    ("R1 all", "_refine_ls_R_factor_all"),
    ("wR2 all", "_refine_ls_wR_factor_ref"),
    ("Goodness of fit", "_refine_ls_goodness_of_fit_ref"),
    ("Reflections", "_refine_ls_number_reflns"),
    ("Parameters", "_refine_ls_number_parameters"),
    ("Restraints", "_refine_ls_number_restraints"),
    ("Constraints", "_refine_ls_number_constraints"),
    ("Max shift/s.u. (as reported)", "_refine_ls_shift/su_max"),
    ("Residual min (e/A^3)", "_refine_diff_density_min"),
    ("Residual max (e/A^3)", "_refine_diff_density_max"),
    ("Weighting details", "_refine_ls_weighting_details"),
]


def read_block(path, tag):
    blocks = [block for block in gemmi.cif.read_file(str(path)) if len(block.find_values(tag))]
    if len(blocks) != 1:
        raise ValueError(f"Expected one block with {tag} in {path}, found {len(blocks)}.")
    return blocks[0]


def display(block, tag):
    value = block.find_value(tag)
    return " ".join(gemmi.cif.as_string(value).split()) if value and value not in {".", "?"} else "unknown"


def indices(path):
    block = read_block(path, "_refln_index_h")
    table = block.find(["_refln_index_h", "_refln_index_k", "_refln_index_l"])
    if not table:
        raise ValueError(f"Incomplete Miller-index loop in {path}.")
    return Counter(tuple(map(int, row)) for row in table)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    a, b = [read_block(p, "_refine_ls_number_reflns") for p in (args.before, args.after)]
    for label, tag in FIELDS:
        print(f"{label}: {display(a, tag)} -> {display(b, tag)}")
    left, right = [indices(p.with_suffix(".fcf")) for p in (args.before, args.after)]
    removed, added = left - right, right - left
    print(f"FCF rows: {sum(left.values())} -> {sum(right.values())}")
    print(f"Exact indices (multiplicity included): lost {sum(removed.values())}, gained {sum(added.values())}")
    if removed or added:
        print("Check the setting, symmetry equivalents and Friedel handling before interpreting changes.")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        sys.exit(str(exc))
