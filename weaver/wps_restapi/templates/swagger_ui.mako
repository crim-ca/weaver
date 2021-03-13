<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>${api_title}</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@3.25.1/swagger-ui.css">
    <script src="https://unpkg.com/swagger-ui-dist@3.25.1/swagger-ui-standalone-preset.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@3.25.1/swagger-ui-bundle.js"></script>
    ${api_scripts | n}  <!-- additional scripts to load -->
    <script>
        addEventListener("DOMContentLoaded", function() {
            window.ui = SwaggerUIBundle({
                ${api_loader | n}   // url or spec with corresponding reference
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
                operationsSorter: "alpha"
            });
        });
    </script>
</head>
<body>
<div id="swagger-ui"></div>
</body>
</html>
