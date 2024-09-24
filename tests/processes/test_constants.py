import pytest

from weaver.processes.constants import (
    CWL_NAMESPACE_CWL_SPEC_DEFINITION,
    CWL_NAMESPACE_CWLTOOL_DEFINITION,
    CWL_NAMESPACE_SCHEMA_DEFINITION,
    CWL_NAMESPACE_WEAVER_DEFINITION,
    CWL_NAMESPACES,
    CWL_NAMESPACES_REVERSED,
    CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS
)


def test_cuda_default_parameters_immutable():
    with pytest.raises(TypeError):
        CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS["value"] = 1
    assert "value" not in CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS

    key = list(CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS)[0]
    before = CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS[key]
    with pytest.raises(TypeError):
        CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS[key] = "test"
    assert CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS[key] == before


@pytest.mark.parametrize("parameters_copy", [
    dict(CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS),
    CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS.copy(),
])
def test_cuda_default_parameters_copy_mutable(parameters_copy):
    assert parameters_copy is not CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS
    key = list(parameters_copy)[0]
    try:
        parameters_copy["value"] = "test"
        parameters_copy.pop(key)
    except TypeError:
        pytest.fail("Only original mapping should be immutable, copy should be permitted updates.")
    assert "value" not in CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS
    assert parameters_copy["value"] == "test"
    assert key in CWL_REQUIREMENT_CUDA_DEFAULT_PARAMETERS
    assert key not in parameters_copy


@pytest.mark.parametrize(
    "namespace",
    [
        CWL_NAMESPACES,
        CWL_NAMESPACES_REVERSED,
        CWL_NAMESPACE_CWLTOOL_DEFINITION,
        CWL_NAMESPACE_SCHEMA_DEFINITION,
        CWL_NAMESPACE_CWL_SPEC_DEFINITION,
        CWL_NAMESPACE_WEAVER_DEFINITION,
    ]
)
def test_cwl_namespaces_immutable(namespace):
    with pytest.raises((AttributeError, TypeError)):  # type: ignore
        namespace.update({"random": "ignore"})
    assert "random" not in namespace
