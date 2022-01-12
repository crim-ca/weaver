{
    "processDescription": {
        "process": {
            "id": "CatalogSearch",
            "title": "Catalog Search for Thredds URLs",
            "abstract": "Get files url from Thredds Catalog and provides file list as JSON Document.",
            "keywords": [],
            "inputs": [{
				"id": "url",
				"title": "URL of the Catalog",
				"formats": [
                    {
                        "mimeType": "application/netcdf",
                        "default": true
				    },
                    {
                        "mimeType": "application/xml",
                        "default": true
				    }
                ],
				"minOccurs": "1",
				"maxOccurs": "1"
			}],
            "outputs": [
                {
                    "id": "output",
                    "title": "JSON file with Catalog URLs",
                    "formats": [
                        {
                            "mimeType": "application/json",
                            "default": true
                        }
                    ]
                }
            ]
        },
        "processVersion": "1.0.0",
        "jobControlOptions": [
            "async-execute"
        ],
        "outputTransmission": [
            "reference"
        ]
    },
    "executionUnit": [
        {
            "href": "tests/functional/application-packages/CatalogSearch/package.cwl"
        }
    ],
    "deploymentProfileName": "http://www.opengis.net/profiles/eoc/wpsApplication"
}
