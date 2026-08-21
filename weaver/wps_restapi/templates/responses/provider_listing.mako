<%inherit file="weaver.wps_restapi:templates/responses/base.mako"/>
<%namespace name="util" file="weaver.wps_restapi:templates/responses/util.mako"/>

<%block name="breadcrumbs">
<li><a href="${weaver.wps_restapi_url}?f=html">Home</a></li>
<li><a href="${util.get_providers_link(query='f=html')}">Providers</a></li>
</%block>

<h2 id="providers" class="page-title">
    <a href="#providers">Providers</a>
</h2>

<div class="format-link">
(<a href="${util.get_providers_link(query='f=json')}">JSON</a>)
</div>

<div class="provider-listing">

    <div class="content-section nav-menu">
        <ul>
            <li>
                <div class="nav-link">
                    Return to <a href="${weaver.wps_restapi_url}?f=html">API Frontpage</a>
                </div>
            </li>
            <li>
                <div class="nav-link">
                    Go to <a href="${util.get_processes_link(query='f=html&providers=true')}">All Provider Processes</a>
                </div>
            </li>
        </ul>
    </div>

    <div class="content-section">

    <div>
    Total providers: ${len(providers)}
    </div>

    <dl>
        %for provider in providers:
        <dt class="provider-list-item">
            ${util.render_provider(provider)}
        </dt>
        %endfor
    </dl>

    </div>

</div>

