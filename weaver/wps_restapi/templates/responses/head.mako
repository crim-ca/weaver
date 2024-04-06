<%block name="head">
<head>
    <title>Weaver REST API - OGC API - Processes</title>
    <meta charset="UTF-8">
    <meta name="title" content="Weaver REST API - OGC API - Processes">
    <meta name="author" content="Francis Charette-Migneault">
    <meta
        name="description"
        content="Workflow Execution Management Service (EMS); Application, Deployment and Execution Service (ADES);
                 OGC API - Processes; WPS; CWL Application Package"
    />
    <meta name="version" content="${weaver.__meta__.__version__}">
    <meta name="source" content="https://github.com/crim-ca/weaver">
    <link rel="stylesheet" type="text/css" href="//fonts.googleapis.com/css?family=Open+Sans" />
    <link href="${request.static_url('weaver.wps_restapi:templates/static/style.css')}"
          rel="stylesheet" type="text/css" media="all" />
    <link href="${request.static_url('weaver.wps_restapi:templates/static/favicon.ico')}"
          rel="icon" type="image/x-icon" />
    <script type="text/javascript" src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.1/jquery.min.js"></script>
</head>
</%block>
