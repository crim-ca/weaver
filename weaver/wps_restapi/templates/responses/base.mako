<!DOCTYPE html>
<html lang="${lang or 'en'}">
<%inherit file="weaver.wps_restapi:templates/responses/header.mako"/>
<%inherit file="weaver.wps_restapi:templates/responses/footer.mako"/>
<%include file="weaver.wps_restapi:templates/responses/head.mako"/>
<body>
    <div class="header">
        <%block name="header"/>
    </div>
    <div class="content">
        ${self.body()}
    </div>
    <div class="footer">
        <%block name="footer"/>
    </div>
</body>
</html>
