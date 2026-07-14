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
                tagsSorter: "alpha",
                apisSorter : "alpha",
                operationsSorter: "alpha",
            });
        });
    </script>
</head>
<body>
<div id="swagger-ui"></div>
</body>
</html>
