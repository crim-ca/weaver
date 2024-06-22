<!DOCTYPE html>
<html lang="${lang or 'en'}">
<%include file="weaver.wps_restapi:templates/responses/head.mako"/>
<body>
    <div class="header">
        <%include file="weaver.wps_restapi:templates/responses/header.mako"/>
    </div>
    <div class="breadcrumbs-container">
        <div class="breadcrumbs">
            <ul>
                <%block name="breadcrumbs"/>
            </ul>
        </div>
    </div>
    <div class="content">
        ${self.body()}
    </div>
    <div class="footer">
        <%include file="weaver.wps_restapi:templates/responses/footer.mako"/>
    </div>
</body>
</html>
