import json
from contextlib import ExitStack
from tests.functional.test_builtin import BuiltinAppTest


def main():
    with ExitStack() as es:
        t = BuiltinAppTest()
        body = t.setup_echo_process_execution_body(es)
        _, _, path = body["inputs"]["featureCollectionInput"]["href"].partition("file://")
        fh = open(path)
        es.push(fh)
        body["inputs"]["featureCollectionInput"] = {
            "mediaType": "application/geo+json",
            "value": json.load(fh),
        }
        print(json.dumps(body, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
