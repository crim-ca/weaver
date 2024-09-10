from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # This block is only evaluated by type checkers (and jupyter-repo2cwl).
    # Therefore, it is not executed when running hte notebook.
    # In other words, 'ipython2cwl' does not even need to be installed!
    from ipython2cwl.iotypes import CWLFilePathInput, CWLFilePathOutput

import csv
import json

input_file: "CWLFilePathInput" = "data.csv"
with open(input_file, mode="r", encoding="utf-8") as f:
    csv_reader = csv.reader(f)
    data = [line for line in csv_reader if line]

headers = data[0]
values = data[1:]
items = [{k: v} for val in values for k, v in zip(headers, val)]

output_file: "CWLFilePathOutput" = "output.json"
with open(output_file, mode="w", encoding="utf-8") as f:
    json.dump(items, f)
