<%inherit file="weaver.wps_restapi:templates/responses/base.mako"/>
<%namespace name="util" file="weaver.wps_restapi:templates/responses/util.mako"/>

<%block name="breadcrumbs">
<li><a href="${weaver.wps_restapi_url}?f=html">Home</a></li>
</%block>

<h2 id="title" class="page-title">
    <a href="#title">${title}</a>
</h2>

<div class="format-link">
(<a href="${weaver.wps_restapi_url}?f=json">JSON</a>)
</div>

<div class="content-section nav-menu">
%if description:
    <span class="field-description">${description}</span>
%else:
    <span class="field-description undefined">No description available.</span>
%endif
</div>

<div class="content-section nav-menu">
    <ul>
        <li>
            <div class="nav-link">
                Go to <a href="${util.get_processes_link(query='f=html')}">Processes Listing</a>
            </div>
        </li>
        <li>
            <div class="nav-link">
                Go to <a href="${util.get_jobs_link(query='f=html')}">Jobs Listing</a>
            </div>
        </li>
        <li>
            <div class="nav-link">
                Go to <a href="${weaver.wps_restapi_url}/conformance">Conformance Listing</a>
            </div>
        </li>
        <li>
            <div class="nav-link">
                Go to <a href="#configuration">Configuration</a>
            </div>
        </li>
        <li>
            <div class="nav-link">
                Go to <a href="#links">Links</a>
            </div>
        </li>
    </ul>
</div>

<div class="frontpage">

    <div class="content-section">
        <h3 id="configuration">
            <a href="#configuration">Configuration Parameters</a>
        </h3>

        <div class="tooltip">
            ${configuration}
            <div class="tooltip-text">
                See the
                <a href="https://pavics-weaver.readthedocs.io/en/latest/configuration.html#weaver-configuration">
                    Weaver Configuration
                </a>
                documentation for more details.
            </div>
        </div>

        <ul>
        %for param in parameters:
            <li>
                <div class="field">
                    <div class="field-key">Name:</div>
                    <div class="code">${param.name}</div>
                </div>
                <div class="field">
                    <div class="field-key">Enabled:</div>
                    ${util.render_bool(param.enabled)}
                </div>
                %if "api" in param:
                <div class="field">
                    <div class="field-key">OpenAPI:</div>
                    <div class="code">
                        <a href="${param.api}">${param.api}</a>
                    </div>
                </div>
                %endif
                %if "doc" in param:
                <div class="field">
                    <div class="field-key">DOC:</div>
                    <div class="code">
                        <a href="${param.doc}">${param.doc}</a>
                    </div>
                </div>
                %endif
                %if "url" in param:
                <div class="field">
                    <div class="field-key">URL:</div>
                    <div class="code">
                        <a href="${param.url}">${param.url}</a>
                    </div>
                </div>
                %endif
            </li>
        %endfor
        </ul>
    </div>

    <div class="content-section">
        <h3 id="links">
            <a href="#links">Links</a>
        </h3>
        ${util.render_links(links)}
    </div>

</div>
