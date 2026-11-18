cwlVersion: v1.2
class: Workflow
inputs:
  zarr_in: Directory
outputs:
  zarr_out:
    type: Directory
    outputSource: second/zarr_out
steps:
  first:
    run: ZarrCopy.cwl
    in:
      zarr_in: zarr_in
    out: [zarr_out]
  second:
    run: ZarrCopy.cwl
    in:
      zarr_in: first/zarr_out
    out: [zarr_out]
