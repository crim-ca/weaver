import pytest

from weaver.owsexceptions import OWSException


@pytest.mark.parametrize(
    ["test", "expect"],
    [
        ("\nLeading new-line",
         "Leading new-line."),
        ("\nnew-lines\n\neverywhere\n",
         "New-lines. Everywhere."),
        ("Loads of new-lines\nat the end\n\n\n\n\n",
         "Loads of new-lines. At the end."),
        ("many new-lines\n\n\nin the middle",
         "Many new-lines. In the middle."),
        ("Already has dot at the end.\n",
         "Already has dot at the end."),
        ("\nDot only\n\n\nat the end.",
         "Dot only. At the end."),
        ("Loads of dots remains...\n",
         "Loads of dots remains..."),
        ("Contains some u''strings' not escaped",
         "Contains some 'strings' not escaped."),
        ("Does not remove double quotes \"\" or '' that represent an empty string: {\"test\": \"\", \"other\": ''}.",
         "Does not remove double quotes '' or '' that represent an empty string: {'test': '', 'other': ''}."),
        ("With \"double quotes\" not escaped.",
         "With 'double quotes' not escaped."),
        ("With \'single quotes\' not escaped.",
         "With 'single quotes' not escaped."),
        ("With many spacing \\\\slashes not escaped.",
         "With many spacing slashes not escaped."),
        ("With combo of wrong \\\"\'u''escapes'\'\" not cleaned.",
         "With combo of wrong 'escapes' not cleaned."),
        ("Commas within list [u'w', \'\'x', u''y', ''z''] fixed.",
         "Commas within list ['w', 'x', 'y', 'z'] fixed."),
        ("Many \"\"double\"\"\" or '''''single'' commas 'cleaned'.",
         "Many 'double' or 'single' commas 'cleaned'."),
        ("Long line that, for some reason,\n was split on next line after comma.",
         "Long line that, for some reason, was split on next line after comma."),
        ("Another long line,\n with many commas and newlines, \nbut placed differently,\njust for the heck of it.",
         "Another long line, with many commas and newlines, but placed differently, just for the heck of it."),
        ("Literal new-lines are\\nresolved to space", "Literal new-lines are resolved to space."),
    ]
)
def test_owsexceptions_json_formatter(test, expect):
    test_code = 418
    test_status = f"{test_code} I'm a teapot"
    json_body = OWSException.json_formatter(status=test_status, body=test, title="SomeCode", environ={})
    assert json_body["code"] == "SomeCode"
    assert json_body["error"]["code"] == test_code
    assert json_body["error"]["status"] == test_status
    result = json_body["description"]
    assert json_body["description"] == expect, (
        "Result does not match expected value"
        f"\n  Result: '{result}'"
        f"\n  Expect: '{expect}'"
    )
