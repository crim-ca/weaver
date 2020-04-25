<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>${api_title}</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@3.25.1/swagger-ui.css">
    <script src="https://unpkg.com/swagger-ui-dist@3.25.1/swagger-ui-standalone-preset.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@3.25.1/swagger-ui-bundle.js"></script>
    <script>
        addEventListener('DOMContentLoaded', function() {
            window.ui = SwaggerUIBundle({
                url: "${api_swagger_json_path}",
                dom_id: '#swagger-ui',
                deepLinking: true,
                docExpansion: 'none',
                validatorUrl: false,
                presets: [
                    SwaggerUIBundle.presets.apis,
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                tagsSorter: 'alpha',
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
