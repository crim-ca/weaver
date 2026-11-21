<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>${api_title}</title>
    <style>
        .parameter__enum,
        .parameter__default {
            display: inline;
            flex-wrap: wrap;
            white-space: normal !important;
            word-break: break-all !important;
            word-wrap: break-word !important;
            overflow-wrap: anywhere !important;
        }
        .parameter__enum > p,
        .parameter__default > p {
            font-family: 'Courier New', Courier, monospace;
            font-size: 75%;
            width: 90%;
        }
        .swagger-ui .response-col_links {
            display: none;
        }
        #api-tag-shortcuts {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
            gap: 0.25rem 1rem;
            list-style: none;
            margin: 1rem 0;
            padding: 0 1rem;
        }
    </style>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5.32.8/swagger-ui.css">
    <script src="https://unpkg.com/swagger-ui-dist@5.32.8/swagger-ui-standalone-preset.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@5.32.8/swagger-ui-bundle.js"></script>
    <script>
        addEventListener("DOMContentLoaded", function() {
            window.ui = SwaggerUIBundle({
                url: "${openapi_json_path}",
                dom_id: "#swagger-ui",
                deepLinking: true,
                defaultModelsExpandDepth: 1,
                defaultModelExpandDepth: 1,
                docExpansion: "list",
                validatorUrl: false,
                presets: [
                    SwaggerUIBundle.presets.apis,
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                apisSorter : "alpha",
                operationsSorter: "alpha",
            });
        });
    </script>
</head>
<body>
<nav aria-label="API endpoint groups">
    <ul id="api-tag-shortcuts">
        <li><a href="#operations-tag-API">API</a></li>
        <li><a href="#operations-tag-Billing_%5C%26_Quoting">Billing &amp; Quoting</a></li>
        <li><a href="#operations-tag-Deploy">Deploy</a></li>
        <li><a href="#operations-tag-DescribeProcess">DescribeProcess</a></li>
        <li><a href="#operations-tag-Dismiss">Dismiss</a></li>
        <li><a href="#operations-tag-Exceptions">Exceptions</a></li>
        <li><a href="#operations-tag-Execute">Execute</a></li>
        <li><a href="#operations-tag-GetCapabilities">GetCapabilities</a></li>
        <li><a href="#operations-tag-Jobs">Jobs</a></li>
        <li><a href="#operations-tag-Logs">Logs</a></li>
        <li><a href="#operations-tag-Processes">Processes</a></li>
        <li><a href="#operations-tag-Provenance">Provenance</a></li>
        <li><a href="#operations-tag-Providers">Providers</a></li>
        <li><a href="#operations-tag-Results">Results</a></li>
        <li><a href="#operations-tag-Statistics">Statistics</a></li>
        <li><a href="#operations-tag-Status">Status</a></li>
        <li><a href="#operations-tag-Vault">Vault</a></li>
        <li><a href="#operations-tag-Visibility">Visibility</a></li>
        <li><a href="#operations-tag-WPS">WPS</a></li>
        <li><a href="#operations-tag-Deprecated_Endpoints">Deprecated Endpoints</a></li>
    </ul>
</nav>
<div id="swagger-ui"></div>
</body>
</html>
