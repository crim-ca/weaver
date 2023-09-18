# NOTE:
#   Inspired from (but not an exact equivalent):
#   https://finch.crim.ca/wps?service=WPS&request=DescribeProcess&version=1.0.0&identifier=ensemble_grid_point_wetdays
#   Outputs are modified to only collect stdout, since we don't have the expected outputs produced by the real process.
#   The 'baseCommand' is also added to produce this stdout output.
#   All remaining arguments are identical.
cwlVersion: v1.0
class: CommandLineTool
requirements:
  InlineJavascriptRequirement: {}
# NOTE: replaced by 'baseCommand'
#hints:
#  WPS1Requirement:
#    provider: https://finch.crim.ca/wps
#    process: ensemble_grid_point_wetdays
baseCommand: echo
inputs:
- id: lat
  type:
  - string
  - type: array
    items: string
- id: lon
  type:
  - string
  - type: array
    items: string
- id: start_date
  type:
  - 'null'
  - string
- id: end_date
  type:
  - 'null'
  - string
- id: ensemble_percentiles
  type:
  - 'null'
  - string
  default: 10,50,90
- id: average
  type:
  - 'null'
  - boolean
  default: false
- id: dataset
  type:
  - 'null'
  - type: enum
    symbols:
    - humidex-daily
    - candcs-u5
    - candcs-u6
    - bccaqv2
  default: candcs-u5
# WARNING:
#   Following definition combining 'enum' and its corresponding nested definition in 'array' caused a
#   schema-salad name resolution error. This CWL is used particularly to validate this *valid* type resolution.
#   see https://github.com/common-workflow-language/cwltool/issues/1908
- id: scenario
  type:
  - 'null'
  - type: enum
    symbols:
    - ssp126
    - rcp85
    - rcp45
    - rcp26
    - ssp585
    - ssp245
  - type: array
    items:
      type: enum
      symbols:
      - ssp126
      - rcp85
      - rcp45
      - rcp26
      - ssp585
      - ssp245
- id: models
  type:
  - 'null'
  - type: enum
    symbols:
    - KACE-1-0-G
    - CCSM4
    - MIROC5
    - EC-Earth3-Veg
    - TaiESM1
    - GFDL-ESM4
    - GFDL-CM3
    - CanESM5
    - HadGEM3-GC31-LL
    - INM-CM4-8
    - IPSL-CM5A-MR
    - EC-Earth3
    - GFDL-ESM2G
    - humidex_models
    - GFDL-ESM2M
    - MIROC-ESM
    - CSIRO-Mk3-6-0
    - MPI-ESM-LR
    - NorESM1-M
    - CNRM-CM5
    - all
    - GISS-E2-1-G
    - 24models
    - MPI-ESM1-2-HR
    - CNRM-ESM2-1
    - CNRM-CM6-1
    - CanESM2
    - FGOALS-g3
    - NorESM1-ME
    - IPSL-CM6A-LR
    - CMCC-ESM2
    - pcic12
    - EC-Earth3-Veg-LR
    - ACCESS-ESM1-5
    - MRI-CGCM3
    - MIROC-ESM-CHEM
    - NorESM2-MM
    - bcc-csm1-1-m
    - BNU-ESM
    - UKESM1-0-LL
    - CESM1-CAM5
    - MIROC-ES2L
    - MRI-ESM2-0
    - HadGEM2-ES
    - MIROC6
    - MPI-ESM-MR
    - INM-CM5-0
    - bcc-csm1-1
    - BCC-CSM2-MR
    - ACCESS-CM2
    - NorESM2-LM
    - IPSL-CM5A-LR
    - FGOALS-g2
    - HadGEM2-AO
    - 26models
    - MPI-ESM1-2-LR
    - KIOST-ESM
  - type: array
    items:
      type: enum
      symbols:
      - KACE-1-0-G
      - CCSM4
      - MIROC5
      - EC-Earth3-Veg
      - TaiESM1
      - GFDL-ESM4
      - GFDL-CM3
      - CanESM5
      - HadGEM3-GC31-LL
      - INM-CM4-8
      - IPSL-CM5A-MR
      - EC-Earth3
      - GFDL-ESM2G
      - humidex_models
      - GFDL-ESM2M
      - MIROC-ESM
      - CSIRO-Mk3-6-0
      - MPI-ESM-LR
      - NorESM1-M
      - CNRM-CM5
      - all
      - GISS-E2-1-G
      - 24models
      - MPI-ESM1-2-HR
      - CNRM-ESM2-1
      - CNRM-CM6-1
      - CanESM2
      - FGOALS-g3
      - NorESM1-ME
      - IPSL-CM6A-LR
      - CMCC-ESM2
      - pcic12
      - EC-Earth3-Veg-LR
      - ACCESS-ESM1-5
      - MRI-CGCM3
      - MIROC-ESM-CHEM
      - NorESM2-MM
      - bcc-csm1-1-m
      - BNU-ESM
      - UKESM1-0-LL
      - CESM1-CAM5
      - MIROC-ES2L
      - MRI-ESM2-0
      - HadGEM2-ES
      - MIROC6
      - MPI-ESM-MR
      - INM-CM5-0
      - bcc-csm1-1
      - BCC-CSM2-MR
      - ACCESS-CM2
      - NorESM2-LM
      - IPSL-CM5A-LR
      - FGOALS-g2
      - HadGEM2-AO
      - 26models
      - MPI-ESM1-2-LR
      - KIOST-ESM
  default: all
- id: thresh
  type:
  - 'null'
  - string
  default: 1.0 mm/day
- id: freq
  type:
  - 'null'
  - type: enum
    symbols:
    - YS
    - QS-DEC
    - AS-JUL
    - MS
  default: YS
- id: op
  type:
  - 'null'
  - type: enum
    symbols:
    - '>='
    - '>'
    - gt
    - ge
  default: '>='
- id: month
  type:
  - 'null'
  - int
  - type: array
    items: int
  inputBinding:
    valueFrom: "\n            ${\n                const values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];\n                if (Array.isArray(self)) {\n                    \n        if (self.every(item => values.includes(item))) {\n            return self;\n        }\n        else {\n            throw \"invalid value(s) in [\" + self + \"] are not all allowed values from [\" + values + \"]\";\n        }\n    \n                }\n                else {\n                    \n        if (values.includes(self)) {\n            return self;\n        }\n        else {\n            throw \"invalid value \" + self + \" is not an allowed value from [\" + values + \"]\";\n        }\n    \n                }\n            }\n        "
- id: season
  type:
  - 'null'
  - type: enum
    symbols:
    - SON
    - MAM
    - JJA
    - DJF
- id: check_missing
  type:
  - 'null'
  - type: enum
    symbols:
    - pct
    - at_least_n
    - wmo
    - skip
    - from_context
    - any
  default: any
- id: missing_options
  type:
  - 'null'
  - File
  format: iana:application/json
- id: cf_compliance
  type:
  - 'null'
  - type: enum
    symbols:
    - raise
    - log
    - warn
  default: warn
- id: data_validation
  type:
  - 'null'
  - type: enum
    symbols:
    - raise
    - log
    - warn
  default: raise
- id: output_name
  type:
  - 'null'
  - string
- id: output_format
  type:
  - 'null'
  - type: enum
    symbols:
    - csv
    - netcdf
  default: netcdf
- id: csv_precision
  type:
  - 'null'
  - int
# NOTE:
#   Following structure is permitted in standard CWL, but not supported in Weaver.
#   Must use the equivalent 'long form' in the meantime.
#outputs:
#- id: output
#  type: stdout
outputs:
  - id: output
    type: File
    outputBinding:
      glob: "*/stdout.log"  # auto-added by Weaver with corresponding 'stdout: stdout.log' definition
$namespaces:
  iana: https://www.iana.org/assignments/media-types/
  edam: http://edamontology.org/
