<!doctype html>
<html lang="en">
<head>
    <title>Weaver</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
        body {
            margin: 0;
            padding: 0;
        }
    </style>
    </head>
    <body>
        <!-- redoc options -->
        <redoc lazy-rendering hide-hostname> </redoc>
        <!--
        <script src="https://cdn.jsdelivr.net/npm/redoc/bundles/redoc.standalone.js"> </script>
        <script src="https://cdn.jsdelivr.net/npm/redoc@2.0.0-alpha.45/bundles/redoc.standalone.js"> </script>
        -->
        <script type="application/javascript"
                src="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"> </script>
        <script type="application/json" id="spec">
            ${openapi_spec | n}
        </script>
        <script>
            let spec = JSON.parse(document.getElementById("spec").innerHTML);
            Redoc.init(spec);
        </script>
    </body>
</html>
