<%inherit file="weaver.wps_restapi:templates/responses/base.mako"/>
<%namespace name="util" file="weaver.wps_restapi:templates/responses/util.mako"/>

<h2 id="title" class="page-title">
    <a href="#title">${title}</a>
</h2>

<div class="format-link">
(<a href="${weaver.wps_restapi_url}?f=json">JSON</a>)
</div>

%if description:
    <span class="field-description">${description}</span>
%else:
    <span class="field-description undefined">No description available.</span>
%endif

<h3 id="configuration">
    <a href="#configuration">Configuration Parameters</a>
</h3>

<div class="frontpage">

    <div class="content-section">
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

</div>

<h3 id="links">
    <a href="#links">Links</a>
</h3>

<div class="content-section">
    ${util.render_links(links)}
</div>
