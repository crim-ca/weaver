<%block name="header">
<div class="inline">
    <img
        src="${request.static_url('weaver.wps_restapi:templates/static/crim.png')}"
        alt="logo" type="image/png" class="logo"
    >
    <h1 id="home" class="header-title">
        <a href="#home">Weaver REST API – OGC API – Processes</a>
    </h1>
</div>
<div class="version-box">
    <div class="version-title">Version: </div>
    <div class="label label-info version-tag code">${weaver.__meta__.__version__}</div>
</div>
</%block>
