---
name: cwl-use-expressions
description: |
  Use CWL expressions and JavaScript for dynamic behavior including parameter transformation,
  conditional logic, and computed values. Learn to leverage InlineJavascriptRequirement for powerful
  CWL packages. Use when you need dynamic, computed, or conditional behavior in CWL processes.
license: Apache-2.0
compatibility: Requires CWL v1.0+ with InlineJavascriptRequirement support.
metadata:
---

# Use CWL Expressions and JavaScript

Master CWL expressions and JavaScript for dynamic, powerful CWL packages.

## When to Use

- Computing values from inputs
- Conditional execution or arguments
- Transforming file names or paths
- Dynamic output naming
- Complex parameter manipulation
- Conditional validation

## Expression Syntax

### Parameter References

```yaml
$(inputs.parameter_name)       # Reference input
$(self)                        # Current value
$(runtime.outdir)              # Runtime output directory
$(runtime.tmpdir)              # Runtime temp directory
$(runtime.cores)               # Available CPU cores
$(runtime.ram)                 # Available RAM (MB)
```

### Simple Expressions

```yaml
inputs:
  value:
    type: int
    inputBinding:
      valueFrom: $(self * 2)  # Double the value
```

## Enabling JavaScript

### InlineJavascriptRequirement

```yaml
requirements:
  InlineJavascriptRequirement: {}

# Now you can use JavaScript expressions
```

## JavaScript Expressions

### Basic Syntax

```yaml
# Single-line
valueFrom: $(inputs.x + inputs.y)
```

```yaml
# Multi-line
valueFrom: |
  ${
    return inputs.x + inputs.y;
  }
```

### String Manipulation

```yaml
inputs:
  filename:
    type: string

outputs:
  output:
    type: File
    outputBinding:
      glob: |
        ${
          return inputs.filename.replace('.txt', '_processed.txt');
        }
```

### File Operations

```yaml
inputs:
  input_file:
    type: File

arguments:
  # Use just the filename
  - valueFrom: $(inputs.input_file.basename)
  
  # Use filename without extension
  - valueFrom: $(inputs.input_file.nameroot)
  
  # Get file extension
  - valueFrom: $(inputs.input_file.nameext)
  
  # Get directory
  - valueFrom: $(inputs.input_file.dirname)
  
  # Get file size
  - valueFrom: $(inputs.input_file.size)
```

## Common Patterns

### Conditional Arguments

```yaml
requirements:
  InlineJavascriptRequirement: {}

inputs:
  verbose:
    type: boolean
    default: false
  
  debug:
    type: boolean?

arguments:
  # Add --verbose if true
  - valueFrom: |
      ${
        return inputs.verbose ? "--verbose" : null;
      }
  
  # Add --debug if present and true
  - valueFrom: |
      ${
        return inputs.debug ? "--debug" : null;
      }
```

### Computed Output Names

```yaml
inputs:
  input_file:
    type: File
  prefix:
    type: string
    default: "processed"

outputs:
  output_file:
    type: File
    outputBinding:
      glob: |
        ${
          var base = inputs.input_file.nameroot;
          var ext = inputs.input_file.nameext;
          return inputs.prefix + "_" + base + ext;
        }
```

### Array Processing

```yaml
inputs:
  files:
    type: File[]

arguments:
  # Join array elements
  - valueFrom: |
      ${
        return inputs.files.map(function(f) {
          return f.path;
        }).join(',');
      }
```

### Conditional Defaults

```yaml
inputs:
  threshold:
    type: float?
  
  auto_threshold:
    type: boolean
    default: false

arguments:
  - prefix: --threshold
    valueFrom: |
      ${
        if (inputs.threshold !== null) {
          return inputs.threshold;
        } else if (inputs.auto_threshold) {
          return 0.5;  // Auto value
        } else {
          return null;  // No threshold
        }
      }
```

## Advanced Techniques

### Complex Validation

```yaml
requirements:
  InlineJavascriptRequirement: {}

inputs:
  value:
    type: int

arguments:
  - valueFrom: |
      ${
        if (inputs.value < 0 || inputs.value > 100) {
          throw "Value must be between 0 and 100";
        }
        return inputs.value;
      }
```

### Dynamic Command Building

```yaml
baseCommand: [python, -c]

inputs:
  operation:
    type: string
  value_a:
    type: float
  value_b:
    type: float

arguments:
  - valueFrom: |
      ${
        var ops = {
          "add": inputs.value_a + inputs.value_b,
          "subtract": inputs.value_a - inputs.value_b,
          "multiply": inputs.value_a * inputs.value_b,
          "divide": inputs.value_a / inputs.value_b
        };
        return "print(" + ops[inputs.operation] + ")";
      }
```

### Format Conversion

```yaml
inputs:
  date_string:
    type: string  # "2026-02-19"

arguments:
  - valueFrom: |
      ${
        // Convert date format
        var parts = inputs.date_string.split('-');
        return parts[2] + '/' + parts[1] + '/' + parts[0];
        // Returns: "19/02/2026"
      }
```

### Resource Calculation

```yaml
requirements:
  ResourceRequirement:
    ramMin: |
      ${
        // Calculate RAM based on input file size
        var fileSize = inputs.input_file.size / (1024 * 1024);  // MB
        return Math.max(2048, fileSize * 4);  // 4x file size, min 2GB
      }
```

### Array Filtering

```yaml
inputs:
  files:
    type: File[]
  min_size:
    type: int
    default: 0

arguments:
  - valueFrom: |
      ${
        // Filter files by size
        return inputs.files
          .filter(function(f) {
            return f.size > inputs.min_size;
          })
          .map(function(f) {
            return f.path;
          })
          .join(' ');
      }
```

## InitialWorkDirRequirement with Expressions

### Dynamic File Generation

```yaml
requirements:
  InlineJavascriptRequirement: {}
  InitialWorkDirRequirement:
    listing:
      - entryname: config.json
        entry: |
          ${
            return JSON.stringify({
              "input": inputs.input_file.path,
              "threshold": inputs.threshold,
              "output": runtime.outdir + "/result.txt"
            }, null, 2);
          }
```

### Conditional File Staging

```yaml
requirements:
  InitialWorkDirRequirement:
    listing: |
      ${
        var files = [inputs.required_file];
        if (inputs.optional_file !== null) {
          files.push(inputs.optional_file);
        }
        return files;
      }
```

## Runtime Information

### Available Runtime Properties

```yaml
arguments:
  # Output directory
  - valueFrom: $(runtime.outdir)
  
  # Temp directory
  - valueFrom: $(runtime.tmpdir)
  
  # CPU cores available
  - valueFrom: $(runtime.cores)
  
  # RAM available (MB)
  - valueFrom: $(runtime.ram)
```

### Using Runtime in Paths

```yaml
outputs:
  output:
    type: File
    outputBinding:
      glob: |
        ${
          return runtime.outdir + "/output.txt";
        }
```

## Debugging Expressions

### Add Logging

```yaml
arguments:
  - valueFrom: |
      ${
        console.log("Input value:", inputs.value);
        console.log("Computed result:", inputs.value * 2);
        return inputs.value * 2;
      }
```

### Test Locally

```bash
# Run with cwltool to see expression output
cwltool --debug tool.cwl inputs.json
```

## Best Practices

### 1. Keep Expressions Simple

```yaml
# ❌ Too complex
valueFrom: |
  ${
    var result;
    if (inputs.a) {
      if (inputs.b) {
        result = inputs.a + inputs.b;
      } else {
        result = inputs.a;
      }
    } else {
      result = 0;
    }
    return result;
  }
```

```yaml
# ✅ Better - simplify logic
valueFrom: $(inputs.a + (inputs.b || 0))
```

### 2. Use Null Checks

```yaml
valueFrom: |
  ${
    return inputs.optional !== null ? inputs.optional : "default";
  }
```

### 3. Document Complex Expressions

```yaml
inputs:
  files:
    type: File[]

arguments:
  # Filter files > 1MB and join paths with commas
  - valueFrom: |
      ${
        return inputs.files
          .filter(function(f) { return f.size > 1048576; })
          .map(function(f) { return f.path; })
          .join(',');
      }
```

### 4. Avoid Side Effects

```yaml
# ❌ Don't modify inputs
valueFrom: |
  ${
    inputs.value = inputs.value * 2;  // Bad!
    return inputs.value;
  }
```

```yaml
# ✅ Return new value
valueFrom: $(inputs.value * 2)
```

### 5. Handle Errors Gracefully

```yaml
valueFrom: |
  ${
    try {
      return someComplexOperation(inputs.value);
    } catch (e) {
      console.error("Error:", e.message);
      throw e;
    }
  }
```

## Common Gotchas

### Null vs Undefined

```yaml
# CWL uses null for missing optional inputs
valueFrom: |
  ${
    // ✅ Check for null
    if (inputs.optional === null) {
      return "default";
    }
    return inputs.optional;
  }
```

### File Path vs Object

The `inputs.file` is an object with properties. The `file` portion is the input ID.

```yaml
# ✅Use .path for the file path
valueFrom: $(inputs.file.path)
```

```yaml
# ❌ Returns object
valueFrom: $(inputs.file)
```

### String Concatenation

```yaml
# ✅ Use + for concatenation
valueFrom: $(inputs.prefix + "_" + inputs.suffix)
```

```yaml
# ❌ Don't rely on automatic coercion
valueFrom: $(inputs.prefix inputs.suffix)
```

## Related Skills

- [cwl-create-commandlinetool](../cwl-create-commandlinetool/) - Build CWL tools
- [cwl-understand-workflow](../cwl-understand-workflow/) - Use in workflows
- [cwl-debug-package](../cwl-debug-package/) - Debug expressions
- [cwl-validate-package](../cwl-validate-package/) - Validate expressions

## Documentation

- [CWL Expressions](https://www.commonwl.org/v1.2/CommandLineTool.html#Expressions)
- [InlineJavascriptRequirement](https://www.commonwl.org/v1.2/CommandLineTool.html#InlineJavascriptRequirement)
- [JavaScript in CWL](https://www.commonwl.org/user_guide/17-expressions/)
- [Runtime Context](https://www.commonwl.org/v1.2/CommandLineTool.html#Runtime_environment)

## Examples Repository

Check the CWL examples repository for more expression patterns:
[https://github.com/common-workflow-language/workflows](https://github.com/common-workflow-language/workflows)
