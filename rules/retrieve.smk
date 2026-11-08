# SPDX-FileCopyrightText: Contributors to PyPSA-Earth
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from shutil import copyfile


rule download_custom_powerplants:
    input:
        url=HTTP.remote(
            "sandbox.zenodo.org/records/578361/files/custom_powerplants%20%285%29.csv",
            keep_local=True,
        ),
    output:
        "data/custom_powerplants.csv",
    log:
        "logs/download_custom_powerplants.log",
    run:
        copyfile(str(input["url"]), output[0])


# Nigeria study: use the existing local line data without checking Zenodo.
# Other studies, or a missing local file, retain the original download rule.
if not (config.get("nigeria_study", {}).get("enabled", False)
        and __import__("pathlib").Path("data/line_types.csv").is_file()):
    rule download_line_types:
        input:
            url=HTTP.remote(
                "sandbox.zenodo.org/records/473405/files/pypsa_line_types%20%281%29.csv",
                keep_local=True,
            ),
        output:
            "data/line_types.csv",
        log:
            "logs/download_line_types.log",
        run:
            copyfile(str(input["url"]), output[0])
