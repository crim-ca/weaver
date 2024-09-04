cwlVersion: v1.2
class: Workflow
inputs:
  message1:
    type: string
  message2:
    type: string
outputs:
  output:
    type: File
    outputSource: concat/output
requirements:
  - class: MultipleInputFeatureRequirement
  - class: InlineJavascriptRequirement
  - class: StepInputExpressionRequirement
  - class: SubworkflowFeatureRequirement
steps:
  msg1:
    # evaluate 'SubworkflowFeatureRequirement'
    run: WorkflowChainStrings.cwl
    in:
      message: message1
    out: [output]
  concat:
    run: Echo.cwl
    in:
      message:
        # evaluate 'MultipleInputFeatureRequirement'
        source:
          - msg1/output
          - message2
        # evaluate 'linkMerge' (schema definition)
        # below value is the default that would be used if omitted
        linkMerge: merge_nested
        valueFrom: "${ return self.map(txt => txt.trim()).join(); }"
    out: [output]
